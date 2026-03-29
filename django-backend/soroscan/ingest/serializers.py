"""
DRF Serializers for SoroScan API.
"""
from rest_framework import serializers

from django.utils.text import slugify

from .cache_utils import get_event_count
from .models import APIKey, ContractEvent, ContractInvocation, Team, TeamMembership, TrackedContract, WebhookSubscription


class TeamSerializer(serializers.ModelSerializer):
    """Team (multi-tenant organization). Slug is auto-assigned on create."""

    class Meta:
        model = Team
        fields = ["id", "name", "slug", "created_at"]
        read_only_fields = ["id", "slug", "created_at"]

    def create(self, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        name = validated_data["name"]
        base = slugify(name) or "team"
        slug = base
        n = 0
        while Team.objects.filter(slug=slug).exists():
            n += 1
            slug = f"{base}-{n}"
        validated_data["slug"] = slug
        if user and user.is_authenticated:
            validated_data["created_by"] = user
        team = super().create(validated_data)
        if user and user.is_authenticated:
            TeamMembership.objects.create(
                team=team,
                user=user,
                role=TeamMembership.Role.ADMIN,
            )
        return team


class TeamMemberAddSerializer(serializers.Serializer):
    """Add an existing user to a team (by user id)."""

    user_id = serializers.IntegerField(min_value=1)
    role = serializers.ChoiceField(
        choices=TeamMembership.Role.choices,
        default=TeamMembership.Role.MEMBER,
    )


class TrackedContractSerializer(serializers.ModelSerializer):
    """
    Serializer for TrackedContract model.
    Used for creating, updating, and returning tracked Soroban smart contracts.
    """

    event_count = serializers.SerializerMethodField()
    warnings = serializers.SerializerMethodField()
    team = serializers.PrimaryKeyRelatedField(
        queryset=Team.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = TrackedContract
        fields = [
            "id",
            "contract_id",
            "name",
            "alias",
            "description",
            "abi_schema",
            "is_active",
            "deprecation_status",
            "deprecation_reason",
            "max_events_per_minute",
            "event_filter_type",
            "event_filter_list",
            "last_indexed_ledger",
            "team",
            "event_count",
            "last_event_at",
            "warnings",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "last_indexed_ledger", "event_count", "last_event_at", "warnings", "created_at", "updated_at"]

    def get_event_count(self, obj) -> int:
        return get_event_count(obj.contract_id)

    def get_warnings(self, obj) -> list[dict[str, str]]:
        warning = obj.deprecation_warning()
        return [warning] if warning else []

    def validate_team(self, value):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if value is not None and user and user.is_authenticated:
            if not TeamMembership.objects.filter(team=value, user=user).exists():
                raise serializers.ValidationError("You are not a member of this team.")
        return value


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
            "decoded_payload",
            "decoding_status",
            "ledger",
            "event_index",
            "timestamp",
            "tx_hash",
            "schema_version",
            "validation_status",
            "signature_status",
        ]
        read_only_fields = [
            "id",
            "contract_id",
            "contract_name",
            "event_type",
            "payload",
            "payload_hash",
            "decoded_payload",
            "decoding_status",
            "ledger",
            "timestamp",
            "tx_hash",
            "schema_version",
            "validation_status",
            "signature_status",
        ]


class ContractInvocationSerializer(serializers.ModelSerializer):
    """
    Serializer for ContractInvocation model.
    Provides read-only details of a contract function invocation.
    """

    contract_id = serializers.CharField(source="contract.contract_id", read_only=True)
    contract_name = serializers.CharField(source="contract.name", read_only=True)
    events_count = serializers.SerializerMethodField()
    events = ContractEventSerializer(many=True, read_only=True, required=False)

    class Meta:
        model = ContractInvocation
        fields = [
            "id",
            "tx_hash",
            "caller",
            "contract_id",
            "contract_name",
            "function_name",
            "parameters",
            "result",
            "ledger_sequence",
            "created_at",
            "events_count",
            "events",
        ]
        read_only_fields = fields

    def get_events_count(self, obj) -> int:
        """Return count of related events."""
        return get_event_count(obj.contract_id)


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
            "signature_status",
            "relevance_score",
        ]
        read_only_fields = fields

    def get_relevance_score(self, obj) -> float:
        # Placeholder — set to 1.0 until full-text ranking is implemented.
        return 1.0
