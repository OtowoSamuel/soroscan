"""
DRF Serializers for SoroScan API.
"""
from rest_framework import serializers

from .models import APIKey, ContractEvent, TrackedContract, WebhookSubscription


class TrackedContractSerializer(serializers.ModelSerializer):
    """
    Serializer for TrackedContract model.
    Used for creating, updating, and returning tracked Soroban smart contracts.
    """

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
            "last_indexed_ledger",
            "event_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "last_indexed_ledger", "event_count", "created_at", "updated_at"]

    def get_event_count(self, obj) -> int:
        return obj.events.count()


class ContractEventSerializer(serializers.ModelSerializer):
    """
    Serializer for ContractEvent model.
    Provides read-only details of an indexed event from the Soroban network.
    """

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
            "event_index",
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
    """
    Serializer for WebhookSubscription model.
    Configures endpoints to receive event payloads when matches occur.
    """

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
    """
    Serializer for incoming event recording requests.
    Used to submit a transaction to the SoroScan contract for indexing.
    """

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


class APIKeySerializer(serializers.ModelSerializer):
    """
    Serializer for APIKey model.
    The ``key`` field is write-once: visible only in the creation response.
    """

    class Meta:
        model = APIKey
        fields = [
            "id",
            "name",
            "key",
            "tier",
            "quota_per_hour",
            "is_active",
            "last_used_at",
            "created_at",
        ]
        read_only_fields = ["id", "key", "quota_per_hour", "last_used_at", "created_at"]
        extra_kwargs = {
            "key": {"read_only": True},
        }


class EventSearchSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for event search results.
    Includes a ``relevance_score`` placeholder for future ranking support.
    """

    contract_id = serializers.CharField(source="contract.contract_id", read_only=True)
    contract_name = serializers.CharField(source="contract.name", read_only=True)
    relevance_score = serializers.SerializerMethodField()

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
            "event_index",
            "timestamp",
            "tx_hash",
            "validation_status",
            "relevance_score",
        ]
        read_only_fields = fields

    def get_relevance_score(self, obj) -> float:
        # Placeholder — set to 1.0 until full-text ranking is implemented.
        return 1.0
