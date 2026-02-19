"""
DRF Serializers for SoroScan API.
"""
from rest_framework import serializers

from .models import ContractEvent, TrackedContract, WebhookSubscription


class TrackedContractSerializer(serializers.ModelSerializer):
    """Serializer for TrackedContract model."""

    event_count = serializers.SerializerMethodField()

    class Meta:
        model = TrackedContract
        fields = [
            "id",
            "contract_id",
            "name",
            "description",
            "abi_schema",
            "is_active",
            "event_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "event_count", "created_at", "updated_at"]

    def get_event_count(self, obj) -> int:
        return obj.events.count()


class ContractEventSerializer(serializers.ModelSerializer):
    """Serializer for ContractEvent model."""

    contract_id = serializers.CharField(source="contract.contract_id", read_only=True)
    contract_name = serializers.CharField(source="contract.name", read_only=True)

    class Meta:
        model = ContractEvent
        fields = [
            "id",
            "contract_id",
            "contract_name",
            "event_type",
            "payload",
            "payload_hash",
            "ledger",
            "timestamp",
            "tx_hash",
            "schema_version",
            "validation_status",
        ]
        read_only_fields = [
            "id",
            "contract_id",
            "contract_name",
            "event_type",
            "payload",
            "payload_hash",
            "ledger",
            "timestamp",
            "tx_hash",
            "schema_version",
            "validation_status",
        ]


class WebhookSubscriptionSerializer(serializers.ModelSerializer):
    """Serializer for WebhookSubscription model."""

    contract_id = serializers.CharField(source="contract.contract_id", read_only=True)

    class Meta:
        model = WebhookSubscription
        fields = [
            "id",
            "contract",
            "contract_id",
            "event_type",
            "target_url",
            "is_active",
            "created_at",
            "last_triggered",
            "failure_count",
        ]
        read_only_fields = ["id", "contract_id", "created_at", "last_triggered", "failure_count"]
        extra_kwargs = {
            "secret": {"write_only": True},
        }


class RecordEventRequestSerializer(serializers.Serializer):
    """Serializer for incoming event recording requests."""

    contract_id = serializers.CharField(
        max_length=56,
        help_text="Target contract address",
    )
    event_type = serializers.CharField(
        max_length=100,
        help_text="Event type name",
    )
    payload_hash = serializers.CharField(
        max_length=64,
        help_text="SHA-256 hash of payload (hex)",
    )
