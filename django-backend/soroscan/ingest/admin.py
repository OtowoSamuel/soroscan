"""
Django Admin configuration for SoroScan models.
"""
from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm
from django.db.models import Count
from django.http import HttpResponse
from django.urls import path
from django.utils.html import format_html

from .models import (
    AlertExecution,
    AlertRule,
    APIKey,
    ContractEvent,
    ContractQuota,
    IndexerState,
    TrackedContract,
    WebhookDeliveryLog,
    WebhookSubscription,
    EventSchema,
)
from .tasks import backfill_contract_events


class BackfillActionForm(ActionForm):
    from_ledger = forms.IntegerField(min_value=1, required=False, label="From ledger")
    to_ledger = forms.IntegerField(min_value=1, required=False, label="To ledger")


@admin.register(TrackedContract)
class TrackedContractAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "contract_id_short",
        "owner",
        "is_active",
        "last_indexed_ledger",
        "event_count",
        "created_at",
    ]
    list_filter = ["is_active", "created_at"]
    search_fields = ["name", "contract_id"]
    readonly_fields = ["created_at", "updated_at"]
    ordering = ["-created_at"]
    action_form = BackfillActionForm
    actions = ["backfill_events"]

    @admin.display(description="Contract ID")
    def contract_id_short(self, obj):
        return f"{obj.contract_id[:8]}...{obj.contract_id[-4:]}"

    def get_queryset(self, request):
        """Optimize queries with Count annotation to avoid N+1 queries."""
        queryset = super().get_queryset(request)
        return queryset.annotate(
            _event_count=Count("events", distinct=True)
        ).select_related("owner")

    @admin.display(description="Events")
    def event_count(self, obj):
        """Use annotated count to avoid N+1 queries."""
        return getattr(obj, "_event_count", 0)

    @admin.action(description="Backfill events")
    def backfill_events(self, request, queryset):
        from_ledger = request.POST.get("from_ledger")
        to_ledger = request.POST.get("to_ledger")

        if not from_ledger or not to_ledger:
            self.message_user(
                request,
                "Backfill requires both 'From ledger' and 'To ledger' values.",
                level=messages.ERROR,
            )
            return

        try:
            from_ledger_int = int(from_ledger)
            to_ledger_int = int(to_ledger)
        except ValueError:
            self.message_user(
                request,
                "Ledger range must be integers.",
                level=messages.ERROR,
            )
            return

        if from_ledger_int <= 0 or to_ledger_int <= 0 or from_ledger_int > to_ledger_int:
            self.message_user(
                request,
                "Ledger range must satisfy: 1 <= from_ledger <= to_ledger.",
                level=messages.ERROR,
            )
            return

        task_ids = []
        for contract in queryset:
            task = backfill_contract_events.delay(contract.contract_id, from_ledger_int, to_ledger_int)
            task_ids.append(f"{contract.name}: {task.id}")

        if task_ids:
            task_ids_text = ", ".join(task_ids)
            self.message_user(
                request,
                f"Backfill started for {len(task_ids)} contract(s). Task IDs: {task_ids_text}",
                level=messages.SUCCESS,
            )


@admin.register(EventSchema)
class EventSchemaAdmin(admin.ModelAdmin):
    list_display = ["contract", "event_type", "version", "created_at"]
    list_filter = ["contract", "event_type"]
    search_fields = ["event_type", "contract__name"]


@admin.register(ContractEvent)
class ContractEventAdmin(admin.ModelAdmin):
    """
    Read-only admin interface for contract events.
    
    All ContractEvent records are indexed data and must never be manually edited.
    Re-index operations dispatch async Celery tasks only.
    """
    list_display = [
        "contract_id_short",
        "event_type",
        "ledger",
        "validation_status_colored",
        "timestamp",
        "tx_hash_short",
    ]
    list_filter = [
        "event_type",
        "validation_status",
        "timestamp",
    ]
    search_fields = [
        "contract__contract_id",
        "contract__name",
        "event_type",
        "tx_hash",
    ]
    readonly_fields = [
        "contract",
        "contract_id",
        "event_type",
        "ledger",
        "event_index",
        "timestamp",
        "tx_hash",
        "payload",
        "payload_hash",
        "raw_xdr",
        "schema_version",
        "validation_status",
        "timestamp",
    ]
    ordering = ["timestamp"]
    date_hierarchy = "timestamp"
    actions = ["trigger_reindex"]

    def get_queryset(self, request):
        """Optimize queries with select_related to prevent N+1 issues."""
        queryset = super().get_queryset(request)
        return queryset.select_related("contract")

    def has_add_permission(self, request):
        """Disable creating new events via admin - events are indexed only."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of indexed events."""
        return False

    def has_change_permission(self, request, obj=None):
        """Disable editing of events - read-only interface."""
        return False

    @admin.display(description="Contract ID")
    def contract_id_short(self, obj):
        """Display shortened contract ID."""
        return f"{obj.contract.contract_id[:8]}...{obj.contract.contract_id[-4:]}"

    @admin.display(description="Validation Status")
    def validation_status_colored(self, obj):
        """Display validation status with color coding."""
        if obj.validation_status == "passed":
            color = "#28a745"  # green
            label = "✓ Passed"
        else:
            color = "#dc3545"  # red
            label = "✗ Failed"
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            label,
        )

    @admin.display(description="TX Hash")
    def tx_hash_short(self, obj):
        """Display shortened transaction hash."""
        return f"{obj.tx_hash[:8]}...{obj.tx_hash[-4:]}"

    @admin.action(description="Trigger re-index for contract")
    def trigger_reindex(self, request, queryset):
        """
        Dispatch async Celery task to re-index selected contracts.
        Groups selected events by contract and queues re-indexing tasks.
        """
        contract_ids = set(event.contract.contract_id for event in queryset)

        if not contract_ids:
            self.message_user(request, "No events selected.", level=messages.WARNING)
            return

        task_ids = []
        for contract_id in contract_ids:
            try:
                contract = TrackedContract.objects.get(contract_id=contract_id)
                from_ledger = (
                    contract.last_indexed_ledger + 1 if contract.last_indexed_ledger else 1
                )
                to_ledger = (contract.last_indexed_ledger or 0) + 1000
                task = backfill_contract_events.delay(contract_id, from_ledger, to_ledger)
                task_ids.append(f"{contract.name}: {task.id}")
            except TrackedContract.DoesNotExist:
                self.message_user(
                    request, f"Contract {contract_id} not found.", level=messages.ERROR
                )
                continue

        if task_ids:
            self.message_user(
                request,
                f"Re-index started for {len(task_ids)} contract(s). Task IDs: {', '.join(task_ids)}",
                level=messages.SUCCESS,
            )

    # ------------------------------------------------------------------
    # Slow query report — accessible at /admin/ingest/contractevent/slow-query-report/
    # ------------------------------------------------------------------

    def get_urls(self):
        extra = [
            path(
                "slow-query-report/",
                self.admin_site.admin_view(self._slow_query_view),
                name="ingest_slowqueryreport",
            ),
        ]
        return extra + super().get_urls()

    def _slow_query_view(self, request):
        """Top-20 slow queries sourced from Django Silk (when enabled)."""
        try:
            from silk.models import SQLQuery  # type: ignore[import]

            top_queries = (
                SQLQuery.objects.values("query")
                .annotate(freq=Count("id"))
                .order_by("-freq")[:20]
            )
            rows_html = "".join(
                f"<tr><td>{i + 1}</td><td>{q['freq']}</td>"
                f"<td><pre style='white-space:pre-wrap;max-width:70ch'>{q['query'][:500]}</pre></td></tr>"
                for i, q in enumerate(top_queries)
            )
            silk_status = "Silk is active — showing top queries by frequency."
        except ImportError:
            rows_html = (
                "<tr><td colspan='3'>Django Silk is not installed or not enabled. "
                "Set <code>ENABLE_SILK=true</code> to activate profiling.</td></tr>"
            )
            silk_status = "Silk is NOT active."

        html = (
            "<html><head><title>Slow Query Report</title>"
            "<link rel='stylesheet' type='text/css' href='/static/admin/css/base.css'></head>"
            "<body id='django-admin'><div id='content-main'>"
            f"<h1>Top-20 Slow Queries</h1><p><strong>{silk_status}</strong></p>"
            "<p>You can also check <code>logs/slow_queries.log</code> for queries "
            "exceeding the configured threshold.</p>"
            "<table><thead><tr><th>#</th><th>Count</th><th>Query</th></tr></thead>"
            f"<tbody>{rows_html}</tbody></table>"
            "</div></body></html>"
        )
        return HttpResponse(html)


@admin.register(WebhookSubscription)
class WebhookSubscriptionAdmin(admin.ModelAdmin):
    """Admin interface for webhook subscriptions with delivery status display."""
    list_display = [
        "target_url",
        "contract_name",
        "event_type_display",
        "status",
        "is_active_display",
        "failure_count",
        "last_delivery_status",
    ]
    list_filter = ["is_active", "status", "contract", "created_at"]
    search_fields = ["target_url", "contract__name", "event_type"]
    readonly_fields = ["secret", "created_at", "last_triggered", "failure_count", "status"]
    ordering = ["-created_at"]

    def get_queryset(self, request):
        """Optimize queries with select_related to prevent N+1 issues."""
        queryset = super().get_queryset(request)
        return queryset.select_related("contract")

    @admin.display(description="Contract")
    def contract_name(self, obj):
        """Display contract name."""
        return obj.contract.name

    @admin.display(description="Event Type")
    def event_type_display(self, obj):
        """Display event type filter or 'All events'."""
        return obj.event_type or "All events"

    @admin.display(description="Active", boolean=True)
    def is_active_display(self, obj):
        """Display active status as boolean."""
        return obj.is_active

    @admin.display(description="Last Delivery Status")
    def last_delivery_status(self, obj):
        """Display last delivery status with color coding."""
        if obj.last_triggered is None:
            return format_html(
                '<span style="color: #6c757d;">Never triggered</span>'
            )

        if obj.failure_count == 0:
            return format_html(
                '<span style="color: #28a745; font-weight: bold;">✓ Success</span><br/>'
                '<small>{}</small>',
                obj.last_triggered.strftime("%Y-%m-%d %H:%M:%S"),
            )
        else:
            return format_html(
                '<span style="color: #dc3545; font-weight: bold;">✗ Failed ({} retries)</span><br/>'
                '<small>{}</small>',
                obj.failure_count,
                obj.last_triggered.strftime("%Y-%m-%d %H:%M:%S"),
            )


@admin.register(IndexerState)
class IndexerStateAdmin(admin.ModelAdmin):
    list_display = ["key", "value", "updated_at"]
    readonly_fields = ["updated_at"]


@admin.register(WebhookDeliveryLog)
class WebhookDeliveryLogAdmin(admin.ModelAdmin):
    """
    Read-only audit log of every webhook delivery attempt.

    Records are pruned after 30 days by the ``cleanup_webhook_delivery_logs``
    Celery task.  Manual editing is intentionally disabled.
    """

    list_display = [
        "id",
        "subscription_url",
        "attempt_number",
        "status_code_display",
        "success_display",
        "timestamp",
    ]
    list_filter = ["success", "timestamp"]
    search_fields = ["subscription__target_url", "error"]
    readonly_fields = [
        "subscription",
        "event",
        "attempt_number",
        "status_code",
        "success",
        "error",
        "timestamp",
    ]
    ordering = ["-timestamp"]
    date_hierarchy = "timestamp"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("subscription", "event")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Target URL")
    def subscription_url(self, obj):
        return obj.subscription.target_url

    @admin.display(description="Status Code")
    def status_code_display(self, obj):
        if obj.status_code is None:
            return format_html('<span style="color: #6c757d;">—</span>')
        if 200 <= obj.status_code < 300:
            color = "#28a745"
        elif obj.status_code == 429:
            color = "#ffc107"
        else:
            color = "#dc3545"
        return format_html('<span style="color: {};">{}</span>', color, obj.status_code)

    @admin.display(description="Success", boolean=True)
    def success_display(self, obj):
        return obj.success


# ---------------------------------------------------------------------------
# Issue: Tiered rate limiting — APIKey and ContractQuota admin
# ---------------------------------------------------------------------------

@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "user",
        "tier",
        "quota_per_hour",
        "is_active",
        "requests_this_hour",
        "last_used_at",
        "created_at",
    ]
    list_filter = ["tier", "is_active", "created_at"]
    search_fields = ["name", "user__username", "user__email"]
    readonly_fields = ["key", "created_at", "last_used_at"]
    ordering = ["-created_at"]

    @admin.display(description="Usage (this hour)")
    def requests_this_hour(self, obj):
        """Read usage counter from Redis."""
        import time

        from django.core.cache import cache
        from soroscan.throttles import _BUCKET_TTL

        bucket_hour = int(time.time()) // _BUCKET_TTL
        cache_key = f"soroscan_api_key_quota:{obj.id}:{bucket_hour}"
        count = cache.get(cache_key, 0)
        if obj.quota_per_hour >= APIKey.UNLIMITED_QUOTA:
            return f"{count} / ∞"
        return f"{count} / {obj.quota_per_hour}"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")

    def save_model(self, request, obj, form, change):
        # Auto-set quota based on tier when saving via admin
        if not change or "tier" in form.changed_data:
            quota = APIKey.TIER_QUOTAS.get(obj.tier, 50)
            obj.quota_per_hour = quota if quota is not None else APIKey.UNLIMITED_QUOTA
        super().save_model(request, obj, form, change)


@admin.register(ContractQuota)
class ContractQuotaAdmin(admin.ModelAdmin):
    list_display = ["api_key", "contract", "quota_per_hour", "created_at"]
    list_filter = ["api_key__tier"]
    search_fields = ["api_key__name", "contract__name", "contract__contract_id"]
    readonly_fields = ["created_at"]
    ordering = ["-created_at"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("api_key", "contract")


# ---------------------------------------------------------------------------
# Issue: Event-driven alerts — AlertRule and AlertExecution admin
# ---------------------------------------------------------------------------

@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "contract",
        "action_type",
        "action_target_short",
        "is_active",
        "execution_count",
        "created_at",
    ]
    list_filter = ["action_type", "is_active", "created_at"]
    search_fields = ["name", "contract__name", "action_target"]
    readonly_fields = ["created_at"]
    ordering = ["-created_at"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("contract")
            .annotate(_execution_count=Count("executions", distinct=True))
        )

    @admin.display(description="Target")
    def action_target_short(self, obj):
        target = obj.action_target
        return target[:40] + "…" if len(target) > 40 else target

    @admin.display(description="Executions")
    def execution_count(self, obj):
        return getattr(obj, "_execution_count", 0)


@admin.register(AlertExecution)
class AlertExecutionAdmin(admin.ModelAdmin):
    list_display = ["rule", "event_short", "status_colored", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["rule__name"]
    readonly_fields = ["rule", "event", "status", "response", "created_at"]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("rule", "event")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="Event")
    def event_short(self, obj):
        return f"{obj.event.event_type}@{obj.event.ledger}"

    @admin.display(description="Status")
    def status_colored(self, obj):
        color = "#28a745" if obj.status == "sent" else "#dc3545"
        return format_html('<span style="color:{};font-weight:bold">{}</span>', color, obj.status)

