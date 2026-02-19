"""
Django Admin configuration for SoroScan models.
"""
from django.contrib import admin

from .models import ContractEvent, EventSchema, IndexerState, TrackedContract, WebhookSubscription


@admin.register(TrackedContract)
class TrackedContractAdmin(admin.ModelAdmin):
    list_display = ["name", "contract_id_short", "owner", "is_active", "event_count", "created_at"]
    list_filter = ["is_active", "created_at"]
    search_fields = ["name", "contract_id"]
    readonly_fields = ["created_at", "updated_at"]
    ordering = ["-created_at"]

    @admin.display(description="Contract ID")
    def contract_id_short(self, obj):
        return f"{obj.contract_id[:8]}...{obj.contract_id[-4:]}"

    @admin.display(description="Events")
    def event_count(self, obj):
        return obj.events.count()


@admin.register(EventSchema)
class EventSchemaAdmin(admin.ModelAdmin):
    list_display = ["contract", "event_type", "version", "created_at"]
    list_filter = ["contract", "event_type"]
    search_fields = ["event_type", "contract__name"]


@admin.register(ContractEvent)
class ContractEventAdmin(admin.ModelAdmin):
    list_display = ["event_type", "contract_name", "ledger", "validation_status", "timestamp", "tx_hash_short"]
    list_filter = ["event_type", "contract", "validation_status", "timestamp"]
    search_fields = ["event_type", "tx_hash", "contract__name"]
    readonly_fields = ["payload_hash", "timestamp"]
    ordering = ["-timestamp"]
    date_hierarchy = "timestamp"

    @admin.display(description="Contract")
    def contract_name(self, obj):
        return obj.contract.name

    @admin.display(description="TX Hash")
    def tx_hash_short(self, obj):
        return f"{obj.tx_hash[:8]}...{obj.tx_hash[-4:]}"


@admin.register(WebhookSubscription)
class WebhookSubscriptionAdmin(admin.ModelAdmin):
    list_display = ["target_url", "contract", "event_type", "is_active", "failure_count", "last_triggered"]
    list_filter = ["is_active", "contract"]
    search_fields = ["target_url", "contract__name"]
    readonly_fields = ["secret", "created_at", "last_triggered", "failure_count"]
    ordering = ["-created_at"]


@admin.register(IndexerState)
class IndexerStateAdmin(admin.ModelAdmin):
    list_display = ["key", "value", "updated_at"]
    readonly_fields = ["updated_at"]
