"""
DRF Serializers for SoroScan API.
"""
import re

from rest_framework import serializers

from django.utils.text import slugify

from .cache_utils import get_event_count
from .models import (
    APIKey,
    ContractEvent,
    ContractInvocation,
    ContractSource,
    ContractVerification,
    Organization,
    OrganizationBudget,
    OrganizationCostSnapshot,
    OrganizationMembership,
    Team,
    TeamMembership,
    TrackedContract,
    WebhookSubscription,
)

_CONTRACT_ID_RE = re.compile(r"^C[A-Z2-7]{55}$")
_VALID_NETWORKS = {choice[0] for choice in TrackedContract.Network.choices}


class OrganizationSerializer(serializers.ModelSerializer):
    """Organization serializer with owner-managed tenancy settings."""

    class Meta:
        model = Organization
        fields = ["id", "name", "slug", "settings", "quota", "created_at", "updated_at"]
        read_only_fields = ["id", "slug", "created_at", "updated_at"]

    def create(self, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            raise serializers.ValidationError("Authentication required.")
        org = Organization.objects.create(owner=user, **validated_data)
        OrganizationMembership.objects.get_or_create(
            organization=org,
            user=user,
            defaults={"role": OrganizationMembership.Role.OWNER, "invited_by": user},
        )
        return org


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


class OrganizationBudgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationBudget
        fields = [
            "monthly_budget_usd",
            "warning_threshold_percent",
            "critical_threshold_percent",
            "is_active",
            "updated_at",
        ]


class OrganizationCostSnapshotSerializer(serializers.ModelSerializer):
    organization_id = serializers.IntegerField(source="organization.id", read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)

    class Meta:
        model = OrganizationCostSnapshot
        fields = [
            "organization_id",
            "organization_name",
            "month",
            "rpc_calls",
            "storage_bytes",
            "compute_units",
            "rpc_cost_usd",
            "storage_cost_usd",
            "compute_cost_usd",
            "actual_cost_usd",
            "projected_monthly_cost_usd",
            "breakdown",
            "updated_at",
        ]


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

    # Declare these as plain CharField to bypass model-level RegexValidator/UniqueValidator
    # and choices validation so our validate_* methods control error messages entirely.
    contract_id = serializers.CharField(validators=[])
    network = serializers.CharField(required=False, default=TrackedContract.Network.MAINNET)

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
            "network",
            "abi_schema",
            "json_schema",
            "is_active",
            "deprecation_status",
            "deprecation_reason",
            "max_events_per_minute",
            "event_filter_type",
            "event_filter_list",
            "metadata",
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

    def validate_contract_id(self, value: str) -> str:
        value = value.strip()

        if not _CONTRACT_ID_RE.match(value):
            raise serializers.ValidationError(
                "Invalid contract address. A Soroban contract address must start "
                "with 'C', be exactly 56 characters long, and use only uppercase "
                "Base32 characters (A-Z and 2-7)."
            )

        # On create, reject duplicates with a clear message.
        if self.instance is None:
            if TrackedContract.objects.filter(contract_id=value).exists():
                raise serializers.ValidationError(
                    f"Contract '{value}' is already registered. "
                    "Each contract address can only be tracked once."
                )

        return value

    def validate_network(self, value: str) -> str:
        if value not in _VALID_NETWORKS:
            valid = ", ".join(sorted(_VALID_NETWORKS))
            raise serializers.ValidationError(
                f"'{value}' is not a valid network. Choose one of: {valid}."
            )
        return value

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
    transaction_id = serializers.CharField(source="tx_hash", read_only=True)

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
            "transaction_id",
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
            "transaction_id",
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
            "signature_algorithm",
            "ack_header_name",
            "ack_header_value",
            "delivery_sla_seconds",
            "escalation_policy",
            "filter_condition",
            "created_at",
            "last_triggered",
            "failure_count",
        ]
        read_only_fields = ["id", "contract_id", "created_at", "last_triggered", "failure_count"]
        extra_kwargs = {
            "secret": {"write_only": True},
        }

    def validate_filter_condition(self, value):
        if value in (None, {}):
            return value
        if not isinstance(value, dict):
            raise serializers.ValidationError("filter_condition must be an object.")


    def validate(self, attrs):
            contract = attrs.get("contract")
            if not contract and self.instance:
                contract = self.instance.contract
                
            target_url = attrs.get("target_url")
            if not target_url and self.instance:
                target_url = self.instance.target_url

            # Check for duplicates (Issue #474)
            if contract and target_url:
                qs = WebhookSubscription.objects.filter(contract=contract, target_url=target_url)
                if self.instance:
                    qs = qs.exclude(pk=self.instance.pk)
                if qs.exists():
                    raise serializers.ValidationError({
                        "target_url": "A webhook subscription for this URL and contract already exists."
                    })

            if contract:
                estimated_size = contract.metadata.get("estimated_payload_size", 0)
                if estimated_size > 1048576:  # 1MB
                    raise serializers.ValidationError({"contract": "Estimated payload exceeds 1MB limit."})
                    
                if contract.metadata.get("is_massive", False):
                    raise serializers.ValidationError({"contract": "Contract events are known to be massive."})
                    
            return attrs

    def validate_escalation_policy(self, value):
        if value in (None, []):
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError("escalation_policy must be a list.")

        for idx, item in enumerate(value):
            if not isinstance(item, dict):
                raise serializers.ValidationError(
                    f"escalation_policy[{idx}] must be an object."
                )
            channel = str(item.get("channel", "")).strip().lower()
            if channel not in {"slack", "sms", "pagerduty"}:
                raise serializers.ValidationError(
                    f"escalation_policy[{idx}].channel must be slack, sms, or pagerduty."
                )
            if not str(item.get("target", "")).strip():
                raise serializers.ValidationError(
                    f"escalation_policy[{idx}].target is required."
                )
            try:
                threshold = int(item.get("after_failures", 1))
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError(
                    f"escalation_policy[{idx}].after_failures must be an integer."
                ) from exc
            if threshold < 1:
                raise serializers.ValidationError(
                    f"escalation_policy[{idx}].after_failures must be >= 1."
                )
        return value


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
    transaction_id = serializers.CharField(source="tx_hash", read_only=True)
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
            "transaction_id",
            "validation_status",
            "signature_status",
            "relevance_score",
        ]
        read_only_fields = fields

    def get_relevance_score(self, obj) -> float:
        # Placeholder — set to 1.0 until full-text ranking is implemented.
        return 1.0


class ContractSourceSerializer(serializers.ModelSerializer):
    """
    Serializer for ContractSource model.
    """

    class Meta:
        model = ContractSource
        fields = [
            "id",
            "contract",
            "source_file",
            "abi_json",
            "uploaded_by",
            "uploaded_at",
        ]
        read_only_fields = ["id", "uploaded_by", "uploaded_at"]


class ContractVerificationSerializer(serializers.ModelSerializer):
    """
    Serializer for ContractVerification model.
    """

    class Meta:
        model = ContractVerification
        fields = [
            "id",
            "contract",
            "source",
            "status",
            "bytecode_hash",
            "compiler_version",
            "verified_at",
            "error_message",
        ]
        read_only_fields = ["id", "verified_at"]
