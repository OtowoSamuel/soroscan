"""
Django Admin configuration for SoroScan models.
"""
from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm, ACTION_CHECKBOX_NAME
from django.db.models import Count
from django.http import HttpResponse, StreamingHttpResponse
from django.urls import path, reverse
from django.utils.html import format_html
import csv
import json
from datetime import datetime
import requests as http_requests

from .models import (
    AlertExecution,
    AlertRule,
    AdminAction,
    APIKey,
    ArchivalAuditLog,
    ArchivedEventBatch,
    AuditLog,
    ContractABI,
    ContractABIVersion,
    ContractDependency,
    ContractDeployment,
    ContractEvent,
    DependencyImpactAssessment,
    ContractMetadata,
    CallGraph,
    ContractSigningKey,
    ContractQuota,
    ContractSource,
    ContractVerification,
    DataDeletionRequest,
    DataRetentionPolicy,
    EventSchema,
    IndexerState,
    IngestError,
    Organization,
    OrganizationBudget,
    OrganizationCostSnapshot,
    OrganizationMembership,
    PIIField,
    RemediationIncident,
    RemediationRule,
    Team,
    TeamMembership,
    TrackedContract,
    WebhookDeadLetter,
    WebhookDeliveryLog,
    WebhookSubscription,
)
from .tasks import backfill_contract_events, dispatch_webhook


class BackfillActionForm(ActionForm):
    from_ledger = forms.IntegerField(min_value=1, required=False, label="From ledger")
    to_ledger = forms.IntegerField(min_value=1, required=False, label="To ledger")


class AdminAuditMixin:
    """Write immutable admin action entries with user attribution and IP."""

    def _client_ip(self, request) -> str:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            first = forwarded.split(",", maxsplit=1)[0].strip()
            if first:
                return first
        return request.META.get("REMOTE_ADDR") or "0.0.0.0"

    def _normalize_changes(self, message):
        if isinstance(message, (dict, list)):
            return {"message": message}
        if not message:
            return {}
        if isinstance(message, str):
            try:
                return {"message": json.loads(message)}
            except json.JSONDecodeError:
                return {"message": message}
        return {"message": str(message)}

    def _audit(self, request, obj, action: str, message) -> None:
        try:
            AdminAction.objects.create(
                user=request.user if getattr(request.user, "is_authenticated", False) else None,
                action=action,
                object_type=obj._meta.model_name[:32],
                object_id=str(getattr(obj, "pk", "")),
                ip_address=self._client_ip(request),
                changes=self._normalize_changes(message),
            )
        except Exception:
            # Audit failures should not block admin operations.
            return

    def log_addition(self, request, obj, message):
        super().log_addition(request, obj, message)
        self._audit(request, obj, "add", message)

    def log_change(self, request, obj, message):
        super().log_change(request, obj, message)
        self._audit(request, obj, "change", message)

    def log_deletions(self, request, queryset):
        snapshot = list(queryset)
        super().log_deletions(request, queryset)
        for obj in snapshot:
            self._audit(request, obj, "delete", "Deleted via Django admin")




@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ["name", "organization", "slug", "created_by", "created_at"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(TeamMembership)
class TeamMembershipAdmin(admin.ModelAdmin):
    list_display = ["team", "user", "role", "joined_at"]
    list_filter = ["role"]
    search_fields = ["team__name", "user__username"]


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "owner", "quota", "created_at"]
    search_fields = ["name", "slug", "owner__username"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ["organization", "user", "role", "invited_by", "joined_at"]
    list_filter = ["role"]
    search_fields = ["organization__name", "user__username"]


@admin.register(OrganizationBudget)
class OrganizationBudgetAdmin(admin.ModelAdmin):
    list_display = [
        "organization",
        "monthly_budget_usd",
        "warning_threshold_percent",
        "critical_threshold_percent",
        "is_active",
        "updated_at",
    ]
    list_filter = ["is_active"]
    search_fields = ["organization__name", "organization__slug"]


@admin.register(OrganizationCostSnapshot)
class OrganizationCostSnapshotAdmin(admin.ModelAdmin):
    list_display = [
        "organization",
        "month",
        "rpc_calls",
        "storage_bytes",
        "compute_units",
        "actual_cost_usd",
        "projected_monthly_cost_usd",
    ]
    list_filter = ["month"]
    search_fields = ["organization__name", "organization__slug"]
    readonly_fields = ["created_at", "updated_at"]



@admin.register(TrackedContract)
class TrackedContractAdmin(AdminAuditMixin, admin.ModelAdmin):
    list_display = [
        "name",
        "alias",
        "contract_id_short",
        "network",
        "owner",
        "team",
        "is_active",
        "deprecation_status",
        "event_filter_type",
        "max_events_per_minute",
        "last_indexed_ledger",
        "event_count",
        "created_at",
    ]
    list_filter = ["is_active", "network", "deprecation_status", "event_filter_type", "created_at"]
    search_fields = ["name", "alias", "contract_id"]
    readonly_fields = ["created_at", "updated_at"]
    ordering = ["-created_at", "name"]
    action_form = BackfillActionForm
    actions = ["backfill_events", "clear_cache"]
    fieldsets = (
        (None, {
            "fields": (
                "contract_id", "name", "alias", "description",
                "owner", "team", "network", "is_active",
            ),
        }),
        ("Event Filtering", {
            "fields": ("event_filter_type", "event_filter_list"),
            "description": (
                "Control which event types are persisted at ingest time. "
                "Whitelist: only listed types are stored. "
                "Blacklist: listed types are dropped."
            ),
        }),
        ("Advanced", {
            "fields": (
                "deprecation_status", "deprecation_reason",
                "max_events_per_minute", "abi_schema", "json_schema", "metadata",
                "last_indexed_ledger",
            ),
            "classes": ("collapse",),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Contract ID")
    def contract_id_short(self, obj):
        return f"{obj.contract_id[:8]}...{obj.contract_id[-4:]}"

    def get_queryset(self, request):
        """Optimize queries with Count annotation to avoid N+1 queries."""
        queryset = super().get_queryset(request)
        return queryset.annotate(
            _event_count=Count("events", distinct=True)
        ).select_related("owner", "team")

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

    @admin.action(description="Clear Redis cache for selected contracts")
    def clear_cache(self, request, queryset):
        from .cache_utils import invalidate_contract_query_cache, invalidate_event_count_cache

        cleared = 0
        for contract in queryset:
            invalidate_contract_query_cache(contract.contract_id)
            invalidate_event_count_cache(contract.contract_id)
            cleared += 1

        self.message_user(
            request,
            f"Cache cleared for {cleared} contract(s).",
            level=messages.SUCCESS,
        )


@admin.register(EventSchema)
class EventSchemaAdmin(AdminAuditMixin, admin.ModelAdmin):
    list_display = ["contract", "event_type", "version", "created_at"]
    list_filter = ["contract", "event_type"]
    search_fields = ["event_type", "contract__name"]


@admin.register(ContractABI)
class ContractABIAdmin(AdminAuditMixin, admin.ModelAdmin):
    """Admin interface for per-contract ABI definitions (issue #58)."""

    list_display = ["contract", "uploaded_at", "updated_at"]
    list_filter = ["uploaded_at"]
    search_fields = ["contract__name", "contract__contract_id"]
    readonly_fields = ["uploaded_at", "updated_at"]

    def save_model(self, request, obj, form, change):
        """Validate ABI JSON structure before saving."""
        from .decoder import validate_abi_json
        import jsonschema as _jsonschema

        try:
            validate_abi_json(obj.abi_json)
        except _jsonschema.ValidationError as exc:
            self.message_user(
                request,
                f"Invalid ABI JSON: {exc.message}",
                level=messages.ERROR,
            )
            return
        super().save_model(request, obj, form, change)


@admin.register(ContractEvent)
class ContractEventAdmin(AdminAuditMixin, admin.ModelAdmin):
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
        "decoding_status",
        "timestamp",
        "tx_hash_short",
    ]
    list_filter = [
        "event_type",
        "validation_status",
        "decoding_status",
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
        "decoded_payload",
        "decoding_status",
        "schema_version",
        "validation_status",
        "timestamp",
    ]
    ordering = ["timestamp"]
    date_hierarchy = "timestamp"
    actions = ["trigger_reindex", "export_events_csv"]

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

    @admin.action(description="Export selected events to CSV")
    def export_events_csv(self, request, queryset):
        """
        Export selected ContractEvent records to CSV using a streaming response.
        Streams the file to handle large selections efficiently.
        """
        class Echo:
            """An object that implements just the write method of the file-like interface."""
            def write(self, value):
                return value

        def stream_csv():
            pseudo_buffer = Echo()
            writer = csv.writer(pseudo_buffer)
            # Yield header
            yield writer.writerow(["ID", "Contract Address", "Event Type", "Timestamp"])
            
            # Fetch events efficiently
            events = queryset.select_related("contract").iterator(chunk_size=2000)
            for event in events:
                yield writer.writerow([
                    event.id,
                    event.contract.contract_id,
                    event.event_type,
                    event.timestamp.isoformat() if event.timestamp else "",
                ])

        filename = f"contract_events_{datetime.now().strftime('%Y%m%d')}.csv"
        response = StreamingHttpResponse(stream_csv(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

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
class WebhookSubscriptionAdmin(AdminAuditMixin, admin.ModelAdmin):
    """Admin interface for webhook subscriptions with delivery status display."""
    change_form_template = "admin/ingest/webhooksubscription/change_form.html"
    list_display = [
        "target_url",
        "contract_name",
        "event_type_display",
        "status",
        "is_active_display",
        "timeout_seconds",
        "failure_count",
        "last_delivery_status",
    ]
    list_filter = ["is_active", "status", "contract", "created_at", "retry_backoff_strategy"]
    search_fields = ["target_url", "contract__name", "event_type"]
    readonly_fields = ["secret", "created_at", "last_triggered", "failure_count", "status"]
    fieldsets = (
        (None, {
            "fields": ("contract", "target_url", "event_type", "is_active"),
        }),
        ("Configuration", {
            "fields": (
                "timeout_seconds",
                "signature_algorithm",
                "ack_header_name",
                "ack_header_value",
                "delivery_sla_seconds",
                "escalation_policy",
                "filter_condition",
            ),
        }),
        ("Retry Configuration", {
            "fields": ("retry_backoff_strategy", "retry_backoff_seconds"),
            "description": "Configure how the webhook retries failed deliveries. "
                          "Exponential: base * 2^attempt | Linear: base * attempt | Fixed: base",
        }),
        ("Status", {
            "fields": ("status", "failure_count", "last_triggered"),
            "classes": ("collapse",),
        }),
        ("Secret", {
            "fields": ("secret",),
            "classes": ("collapse",),
        }),
    )
    ordering = ["-created_at"]

    class Media:
        js = ("ingest/admin_event_type_autocomplete.js",)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "event-types/",
                self.admin_site.admin_view(self.event_types_api),
                name="webhooksubscription_event_types",
            ),
            path(
                "<int:pk>/ping/",
                self.admin_site.admin_view(self.ping_webhook),
                name="webhooksubscription_ping",
            ),
        ]
        return custom_urls + urls

    def ping_webhook(self, request, pk):
        import hashlib
        import hmac
        from django.shortcuts import redirect
        from django.utils import timezone

        webhook = WebhookSubscription.objects.get(pk=pk)
        test_payload = {
            "event_type": "ping",
            "payload": {"message": "This is a test ping from SoroScan admin"},
            "contract_id": webhook.contract.contract_id,
            "timestamp": timezone.now().isoformat(),
        }
        payload_bytes = json.dumps(test_payload, sort_keys=True).encode("utf-8")
        algorithm = (webhook.signature_algorithm or WebhookSubscription.SIGNATURE_SHA256).lower()
        digestmod = hashlib.sha1 if algorithm == WebhookSubscription.SIGNATURE_SHA1 else hashlib.sha256
        prefix = "sha1" if algorithm == WebhookSubscription.SIGNATURE_SHA1 else "sha256"
        sig_hex = hmac.new(
            webhook.secret.encode("utf-8"),
            msg=payload_bytes,
            digestmod=digestmod,
        ).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "X-SoroScan-Signature": f"{prefix}={sig_hex}",
            "X-SoroScan-Timestamp": timezone.now().isoformat(),
        }
        try:
            response = http_requests.post(
                webhook.target_url,
                data=payload_bytes,
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()
            self.message_user(
                request,
                f"Test ping sent successfully to {webhook.target_url} (HTTP {response.status_code}).",
                messages.SUCCESS,
            )
        except http_requests.RequestException as exc:
            self.message_user(
                request,
                f"Test ping to {webhook.target_url} failed: {exc}",
                messages.ERROR,
            )
        return redirect(
            reverse("admin:ingest_webhooksubscription_change", args=[pk])
        )

    def event_types_api(self, request):
        from django.http import JsonResponse
        from soroscan.ingest.models import TrackedContract
        contract_id = request.GET.get("contract_id")
        if not contract_id:
            return JsonResponse({"results": []})
        try:
            contract = TrackedContract.objects.get(pk=contract_id)
        except TrackedContract.DoesNotExist:
            return JsonResponse({"results": []})
        
        types = set()
        if hasattr(contract, "event_schemas"):
            types.update(contract.event_schemas.values_list("event_type", flat=True))
        if hasattr(contract, "abi") and contract.abi.abi_json:
            for ev in contract.abi.abi_json:
                if isinstance(ev, dict) and ev.get("name"):
                    types.add(ev["name"])
        types.update(contract.events.values_list("event_type", flat=True).distinct())
        
        results = [{"id": t, "text": t} for t in sorted(types)]
        return JsonResponse({"results": results})

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
class IndexerStateAdmin(AdminAuditMixin, admin.ModelAdmin):
    list_display = ["key", "value", "updated_at"]
    readonly_fields = ["updated_at"]


@admin.register(WebhookDeliveryLog)
class WebhookDeliveryLogAdmin(AdminAuditMixin, admin.ModelAdmin):
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
        "acknowledged",
        "within_sla",
        "latency_ms",
        "success_display",
        "timestamp",
    ]
    list_filter = ["success", "acknowledged", "within_sla", "timestamp"]
    search_fields = ["subscription__target_url", "error"]
    readonly_fields = [
        "subscription",
        "event",
        "attempt_number",
        "status_code",
        "success",
        "acknowledged",
        "latency_ms",
        "within_sla",
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

    @admin.action(description="Retry selected webhook deliveries")
    def retry_webhook_delivery(self, request, queryset):
        """
        Manually retry selected webhook deliveries by requeueing the Celery task.
        Shows a confirmation page before proceeding.
        """
        from django.template.response import TemplateResponse

        if request.POST.get("post"):
            # Process the retry
            count = 0
            for obj in queryset:
                dispatch_webhook.delay(obj.subscription_id, obj.event_id)
                count += 1

            self.message_user(
                request,
                f"Successfully requeued {count} webhook delivery/deliveries.",
                messages.SUCCESS,
            )
            return None

        context = {
            **self.admin_site.each_context(request),
            "title": "Are you sure?",
            "queryset": queryset,
            "opts": self.model._meta,
            "action_checkbox_name": ACTION_CHECKBOX_NAME,
            "media": self.media,
        }

        return TemplateResponse(
            request,
            "admin/ingest/webhookdeliverylog/webhook_retry_confirmation.html",
            context,
        )

    actions = ["retry_webhook_delivery"]


@admin.register(WebhookDeadLetter)
class WebhookDeadLetterAdmin(AdminAuditMixin, admin.ModelAdmin):
    """Manual review queue for webhook deliveries that exhausted retries."""

    list_display = [
        "id",
        "subscription",
        "status_code",
        "retries_exhausted",
        "resolved",
        "created_at",
    ]
    list_filter = ["resolved", "created_at", "status_code"]
    search_fields = ["subscription__target_url", "error"]
    readonly_fields = [
        "subscription",
        "event",
        "payload",
        "status_code",
        "error",
        "retries_exhausted",
        "created_at",
    ]
    ordering = ["-created_at"]


# ---------------------------------------------------------------------------
# Issue: Tiered rate limiting — APIKey and ContractQuota admin
# ---------------------------------------------------------------------------

@admin.register(APIKey)
class APIKeyAdmin(AdminAuditMixin, admin.ModelAdmin):
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


@admin.register(ContractDependency)
class ContractDependencyAdmin(AdminAuditMixin, admin.ModelAdmin):
    list_display = ["caller", "callee", "call_count", "risk_score", "last_call"]
    list_filter = ["last_call"]
    search_fields = ["caller__contract_id", "callee__contract_id"]


@admin.register(CallGraph)
class CallGraphAdmin(AdminAuditMixin, admin.ModelAdmin):
    list_display = ["contract", "has_cycles", "computed_at"]
    list_filter = ["has_cycles", "computed_at"]
    readonly_fields = ["computed_at"]


@admin.register(DependencyImpactAssessment)
class DependencyImpactAssessmentAdmin(AdminAuditMixin, admin.ModelAdmin):
    list_display = [
        "root_contract",
        "impacted_count",
        "risk_score",
        "impact_level",
        "has_cycles",
        "computed_at",
    ]
    list_filter = ["impact_level", "has_cycles", "computed_at"]
    search_fields = ["root_contract__contract_id", "root_contract__name"]


@admin.register(ContractQuota)
class ContractQuotaAdmin(AdminAuditMixin, admin.ModelAdmin):
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
class AlertRuleAdmin(AdminAuditMixin, admin.ModelAdmin):
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
        target = obj.action_target or ""
        if not target:
            return "—"
        return target[:40] + "…" if len(target) > 40 else target

    @admin.display(description="Executions")
    def execution_count(self, obj):
        return getattr(obj, "_execution_count", 0)


@admin.register(AlertExecution)
class AlertExecutionAdmin(AdminAuditMixin, admin.ModelAdmin):
    list_display = ["rule", "event_short", "channel", "status_colored", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["rule__name"]
    readonly_fields = ["rule", "event", "channel", "status", "response", "created_at"]
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


@admin.register(RemediationRule)
class RemediationRuleAdmin(AdminAuditMixin, admin.ModelAdmin):
    list_display = [
        "name",
        "enabled",
        "grace_period_minutes",
        "alert_type",
        "dry_run",
        "created_at",
    ]
    list_filter = ["enabled", "alert_type", "dry_run", "created_at"]
    search_fields = ["name", "alert_target"]
    readonly_fields = ["created_at", "updated_at"]
    ordering = ["-created_at"]


@admin.register(RemediationIncident)
class RemediationIncidentAdmin(AdminAuditMixin, admin.ModelAdmin):
    list_display = [
        "id",
        "rule",
        "contract",
        "status",
        "first_detected_at",
        "alerted_at",
        "executed_at",
        "resolved_at",
    ]
    list_filter = ["status", "first_detected_at"]
    search_fields = ["rule__name", "contract__contract_id", "contract__name"]
    readonly_fields = [
        "rule",
        "contract",
        "status",
        "anomaly_snapshot",
        "first_detected_at",
        "alerted_at",
        "action_after_at",
        "executed_at",
        "resolved_at",
        "last_seen_at",
    ]
    ordering = ["-first_detected_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# Data Retention Policies and Archival
# ---------------------------------------------------------------------------

class ArchivedEventBatchInline(admin.TabularInline):
    model = ArchivedEventBatch
    extra = 0
    readonly_fields = ["s3_key", "event_count", "size_bytes", "min_timestamp", "max_timestamp", "status", "archived_at"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(DataRetentionPolicy)
class DataRetentionPolicyAdmin(AdminAuditMixin, admin.ModelAdmin):
    list_display = ["scope", "retention_days", "archive_enabled", "s3_bucket", "batch_count", "created_at"]
    list_filter = ["archive_enabled"]
    search_fields = ["contract__name", "contract__contract_id", "s3_bucket"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [ArchivedEventBatchInline]

    @admin.display(description="Scope")
    def scope(self, obj):
        return obj.contract.name if obj.contract else "Global"

    @admin.display(description="Batches")
    def batch_count(self, obj):
        return obj.batches.count()


@admin.register(ArchivedEventBatch)
class ArchivedEventBatchAdmin(AdminAuditMixin, admin.ModelAdmin):
    list_display = ["id", "policy_scope", "event_count", "size_bytes", "status", "archived_at"]
    list_filter = ["status", "archived_at"]
    search_fields = ["s3_key", "policy__contract__name"]
    readonly_fields = ["s3_key", "event_count", "size_bytes", "min_timestamp", "max_timestamp", "status", "archived_at"]
    ordering = ["-archived_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Policy Scope")
    def policy_scope(self, obj):
        return obj.policy.contract.name if obj.policy.contract else "Global"


@admin.register(ArchivalAuditLog)
class ArchivalAuditLogAdmin(AdminAuditMixin, admin.ModelAdmin):
    list_display = ["id", "action_colored", "event_count", "performed_by", "created_at"]
    list_filter = ["action", "created_at"]
    search_fields = ["detail", "performed_by__username"]
    readonly_fields = ["action", "batch", "policy", "event_count", "detail", "performed_by", "created_at"]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Action")
    def action_colored(self, obj):
        color = "#17a2b8" if obj.action == "archive" else "#28a745"
        return format_html('<span style="color:{};font-weight:bold">{}</span>', color, obj.action.upper())


@admin.register(ContractSigningKey)
class ContractSigningKeyAdmin(AdminAuditMixin, admin.ModelAdmin):
    list_display = ["contract", "algorithm", "is_active", "created_at", "updated_at"]
    list_filter = ["algorithm", "is_active", "created_at"]
    search_fields = ["contract__contract_id", "contract__name"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(AdminAction)
class AdminActionAdmin(admin.ModelAdmin):
    list_display = ["timestamp", "action", "object_type", "object_id", "user", "ip_address"]
    list_filter = ["action", "object_type", "timestamp"]
    search_fields = ["object_id", "user__username", "ip_address"]
    readonly_fields = [
        "user",
        "action",
        "object_type",
        "object_id",
        "timestamp",
        "ip_address",
        "changes",
    ]
    ordering = ["-timestamp"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(IngestError)
class IngestErrorAdmin(admin.ModelAdmin):
    list_display = ["created_at", "error_type", "contract_id", "sample_error", "ledger"]
    list_filter = ["error_type", "created_at"]
    search_fields = ["contract_id", "error_message", "tx_hash"]
    readonly_fields = ["created_at", "sample_error"]
    ordering = ["-created_at"]
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False



# ---------------------------------------------------------------------------
# Contract Metadata Registry
# ---------------------------------------------------------------------------

class TagListFilter(admin.SimpleListFilter):
    title = "tags"
    parameter_name = "tags"

    def lookups(self, request, model_admin):
        return [
            ("has_tags", "Has Tags"),
            ("no_tags", "No Tags"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "has_tags":
            return queryset.exclude(tags=[])
        if self.value() == "no_tags":
            return queryset.filter(tags=[])
        return queryset


@admin.register(ContractMetadata)
class ContractMetadataAdmin(AdminAuditMixin, admin.ModelAdmin):
    list_display = ["contract", "name", "tags", "documentation_url", "github_repo", "team_email"]
    search_fields = ["name", "description", "tags"]
    list_filter = [TagListFilter]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(ContractSource)
class ContractSourceAdmin(AdminAuditMixin, admin.ModelAdmin):
    list_display = ["contract", "uploaded_by", "uploaded_at", "file_size"]
    list_filter = ["uploaded_at"]
    search_fields = ["contract__name", "contract__contract_id", "uploaded_by__username"]
    readonly_fields = ["uploaded_at"]

    def file_size(self, obj):
        if obj.source_file:
            return f"{obj.source_file.size} bytes"
        return "—"
    file_size.short_description = "File Size"


@admin.register(ContractVerification)
class ContractVerificationAdmin(AdminAuditMixin, admin.ModelAdmin):
    list_display = ["contract", "status", "verified_at", "compiler_version"]
    list_filter = ["status", "verified_at"]
    search_fields = ["contract__name", "contract__contract_id"]
    readonly_fields = ["verified_at"]


# ---------------------------------------------------------------------------
# Issue #280: GDPR Data Governance
# ---------------------------------------------------------------------------

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["timestamp", "action", "model_name", "object_id", "user", "ip_address"]
    list_filter = ["action", "model_name", "timestamp"]
    search_fields = ["object_id", "user__username", "model_name"]
    readonly_fields = ["timestamp", "action", "model_name", "object_id", "user", "ip_address", "changes"]
    ordering = ["-timestamp"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PIIField)
class PIIFieldAdmin(admin.ModelAdmin):
    list_display = ["contract", "event_type", "field_path", "description", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["contract__contract_id", "contract__name", "field_path"]
    readonly_fields = ["created_at"]


@admin.register(DataDeletionRequest)
class DataDeletionRequestAdmin(admin.ModelAdmin):
    list_display = ["subject_identifier", "status", "requested_by", "events_deleted", "requested_at", "completed_at"]
    list_filter = ["status", "requested_at"]
    search_fields = ["subject_identifier", "requested_by__username"]
    readonly_fields = ["requested_at", "completed_at", "events_deleted", "error_message"]
    filter_horizontal = ["contracts"]


# ---------------------------------------------------------------------------
# Issue #284: Contract Deployment Tracking
# ---------------------------------------------------------------------------

@admin.register(ContractDeployment)
class ContractDeploymentAdmin(admin.ModelAdmin):
    list_display = ["contract", "bytecode_hash_short", "ledger_deployed", "deployer_address", "is_upgrade", "detected_at"]
    list_filter = ["is_upgrade", "detected_at"]
    search_fields = ["contract__contract_id", "contract__name", "bytecode_hash", "deployer_address"]
    readonly_fields = ["detected_at"]

    def bytecode_hash_short(self, obj):
        return obj.bytecode_hash[:16] + "..."
    bytecode_hash_short.short_description = "Bytecode Hash"


@admin.register(ContractABIVersion)
class ContractABIVersionAdmin(admin.ModelAdmin):
    list_display = ["contract", "version_number", "valid_from_ledger", "valid_to_ledger", "has_breaking_changes", "created_at"]
    list_filter = ["has_breaking_changes", "created_at"]
    search_fields = ["contract__contract_id", "contract__name"]
    readonly_fields = ["created_at"]
