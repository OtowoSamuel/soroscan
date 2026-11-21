"""
DRF Serializers for SoroScan API.
"""
import re

from rest_framework import serializers

from django.utils.text import slugify

from .cache_utils import get_event_count
from .models import (
    APIKey,
    ContractDeployment,
    ContractEvent,
    ContractInvocation,
    ContractMetadata,
    ContractSnapshot,
    ContractSource,
    ContractVerification,
    Organization,
    OrganizationBudget,
    OrganizationCostSnapshot,
    OrganizationMembership,
    StateChange,
    Team,
    TeamMembership,
    TrackedContract,
    WebhookSubscription,
)
from .services.event_dedup import ALLOWED_DEDUP_FIELDS

_CONTRACT_ID_RE = re.compile(r"^C[A-Z2-7]{55}$")
_STELLAR_ADDRESS_RE = re.compile(r"^[GC][A-Z2-7]{55}$")
_SHA256_HEX_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_VALID_NETWORKS = {choice[0] for choice in TrackedContract.Network.choices}

try:  # pragma: no cover - import path depends on installed extras
    from stellar_sdk import StrKey as _StellarStrKey
except Exception:  # pragma: no cover
    _StellarStrKey = None


def _is_valid_contract_address(value):
    if _StellarStrKey is not None:
        try:
            return bool(_StellarStrKey.is_valid_contract(value))
        except Exception:
            return False
    return bool(_CONTRACT_ID_RE.fullmatch(value))


def _is_valid_stellar_address(value):
    if _StellarStrKey is not None:
        for validator in (
            _StellarStrKey.is_valid_ed25519_public_key,
            _StellarStrKey.is_valid_contract,
        ):
            try:
                if validator(value):
                    return True
            except Exception:
                continue
        return False
    return bool(_STELLAR_ADDRESS_RE.fullmatch(value))


_FILTER_CONDITION_LOGICAL_OPS = {"and", "or"}
_FILTER_CONDITION_COMPARISON_OPS = {
    "eq",
    "neq",
    "gt",
    "gte",
    "lt",
    "lte",
    "contains",
    "startswith",
    "in",
    "regex",
}


def _validate_filter_condition_node(condition, path="filter_condition"):
    """Recursively validate a webhook filter_condition JSON AST node.

    Mirrors the operators handled by ``evaluate_condition`` in tasks.py so a
    typo'd or unsupported operator is rejected at write time instead of
    silently evaluating to "no match" at dispatch time.
    """
    if not isinstance(condition, dict):
        raise serializers.ValidationError({path: "Each condition must be an object."})

    op = (condition.get("op") or "").lower()

    if op == "not":
        sub = condition.get("condition")
        if not isinstance(sub, dict):
            raise serializers.ValidationError(
                {path: "'not' requires a nested 'condition' object."}
            )
        _validate_filter_condition_node(sub, f"{path}.condition")
        return

    if op in _FILTER_CONDITION_LOGICAL_OPS:
        subs = condition.get("conditions")
        if not isinstance(subs, list) or not subs:
            raise serializers.ValidationError(
                {path: f"'{op}' requires a non-empty 'conditions' list."}
            )
        for idx, sub in enumerate(subs):
            _validate_filter_condition_node(sub, f"{path}.conditions[{idx}]")
        return

    if op not in _FILTER_CONDITION_COMPARISON_OPS:
        raise serializers.ValidationError(
            {path: f"Unknown operator '{condition.get('op')}'."}
        )

    if not condition.get("field"):
        raise serializers.ValidationError(
            {path: f"'{op}' requires a non-empty 'field'."}
        )

    if "value" not in condition:
        raise serializers.ValidationError({path: f"'{op}' requires a 'value'."})


class OrganizationSerializer(serializers.ModelSerializer):
    """Organization serializer with owner-managed tenancy settings."""

    class Meta:
        model = Organization
        fields = ["id", "name", "slug", "settings", "quota", "cors_origins", "created_at", "updated_at"]
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


class OrganizationCorsSerializer(serializers.ModelSerializer):
    """
    Serializer for updating an Organization's per-org CORS allowed origins.

    Each entry must be a non-empty string beginning with ``http://`` or
    ``https://``.  Trailing slashes are stripped for consistency.
    """

    cors_origins = serializers.ListField(
        child=serializers.CharField(max_length=2048),
        allow_empty=True,
        help_text=(
            'List of allowed CORS origins, e.g. ["https://app.example.com"]. '
            "Each entry must start with http:// or https://."
        ),
    )

    class Meta:
        model = Organization
        fields = ["id", "name", "cors_origins"]
        read_only_fields = ["id", "name"]

    def validate_cors_origins(self, value):
        cleaned = []
        for raw in value:
            origin = raw.strip().rstrip("/")
            if not (origin.startswith("http://") or origin.startswith("https://")):
                raise serializers.ValidationError(
                    f"Invalid origin '{raw}': must start with http:// or https://"
                )
            if origin:
                cleaned.append(origin)
        return cleaned


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
            "is_paused",
            "paused_at",
            "pause_reason",
            "resume_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "last_indexed_ledger",
            "event_count",
            "last_event_at",
            "warnings",
            "is_paused",
            "paused_at",
            "pause_reason",
            "resume_at",
            "created_at",
            "updated_at",
        ]

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


class ContractDeploymentSerializer(serializers.ModelSerializer):
    detected_at = serializers.DateTimeField(read_only=True, allow_null=True)

    class Meta:
        model = ContractDeployment
        fields = [
            "id",
            "bytecode_hash",
            "ledger_deployed",
            "deployer_address",
            "is_upgrade",
            "tx_hash",
            "notes",
            "detected_at",
        ]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if representation["detected_at"] is None:
            discovery_date = getattr(instance.contract, "created_at", None)
            detected_at_field = self.fields["detected_at"]
            representation["detected_at"] = detected_at_field.to_representation(
                discovery_date
            )
        return representation


class ContractEventSerializer(serializers.ModelSerializer):
    """
    Serializer for ContractEvent model.
    Provides read-only details of an indexed event from the Soroban network.
    """

    contract_id = serializers.CharField(source="contract.contract_id", read_only=True)
    contract_name = serializers.CharField(source="contract.name", read_only=True)
    transaction_id = serializers.CharField(source="tx_hash", read_only=True)
    # ContractEvent.payload is a CompressedJSONField (models.BinaryField subclass
    # that stores/returns Python dicts); DRF has no default mapping for it and
    # falls back to a generic ModelField that calls BinaryField.value_to_string
    # (base64-encodes bytes), crashing on a dict. Declare it explicitly as JSON.
    payload = serializers.JSONField(read_only=True)

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
            "status",
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
            "timeout_seconds",
            "retry_backoff_strategy",
            "retry_backoff_seconds",
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
        _validate_filter_condition_node(value)
        return value

    def validate_timeout_seconds(self, value):
        if value is None:
            return value
        if not isinstance(value, int) or isinstance(value, bool):
            raise serializers.ValidationError("timeout_seconds must be an integer.")
        if value < 1 or value > 60:
            raise serializers.ValidationError("timeout_seconds must be between 1 and 60.")
        return value

    def validate_retry_backoff_strategy(self, value):
        if value in (None, ""):
            return value
        allowed = {"exponential", "linear", "fixed"}
        if value not in allowed:
            raise serializers.ValidationError(
                "retry_backoff_strategy must be one of: exponential, linear, fixed."
            )
        return value

    def validate_retry_backoff_seconds(self, value):
        if value is None:
            return value
        if not isinstance(value, int) or isinstance(value, bool):
            raise serializers.ValidationError("retry_backoff_seconds must be an integer.")
        if value < 1 or value > 3600:
            raise serializers.ValidationError(
                "retry_backoff_seconds must be between 1 and 3600."
            )
        return value

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


class WebhookDeliveryLogSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for WebhookDeliveryLog entries.

    Exposed via ``GET /api/webhooks/{id}/deliveries/`` (Issue #765).
    """

    subscription_id = serializers.IntegerField(source="subscription.id", read_only=True)
    event_id = serializers.IntegerField(source="event.id", read_only=True, allow_null=True)

    class Meta:
        from .models import WebhookDeliveryLog
        model = WebhookDeliveryLog
        fields = [
            "id",
            "subscription_id",
            "event_id",
            "attempt_number",
            "status",
            "status_code",
            "success",
            "acknowledged",
            "within_sla",
            "latency_ms",
            "duration_ms",
            "payload_bytes",
            "error",
            "response_body",
            "timestamp",
        ]
        read_only_fields = fields


class DLQDeliveryLogSerializer(WebhookDeliveryLogSerializer):
    """
    Dead-lettered WebhookDeliveryLog entry, including the contract it belongs to.

    Exposed via ``GET /api/v1/webhooks/dlq/`` (Issue #1405).
    """

    contract_id = serializers.CharField(
        source="subscription.contract.contract_id", read_only=True
    )

    class Meta(WebhookDeliveryLogSerializer.Meta):
        fields = WebhookDeliveryLogSerializer.Meta.fields + ["contract_id"]
        read_only_fields = fields


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

    def validate_contract_id(self, value):
        if not _is_valid_contract_address(value):
            raise serializers.ValidationError("Must be a valid Soroban contract address.")
        return value

    def validate_payload_hash(self, value):
        if not _SHA256_HEX_RE.fullmatch(value):
            raise serializers.ValidationError("Must be exactly 64 hexadecimal characters.")
        return value.lower()


class AddIndexerRequestSerializer(serializers.Serializer):
    """Serializer for SC-9: authorize an indexer on the SoroScan contract."""

    indexer_address = serializers.CharField(
        max_length=56,
        help_text="Stellar address of the indexer to authorize",
    )

    def validate_indexer_address(self, value):
        if not _is_valid_stellar_address(value):
            raise serializers.ValidationError("Must be a valid Stellar account or contract address.")
        return value


class StructuredEventRequestSerializer(RecordEventRequestSerializer):
    """SC-38 request payload for versioned, idempotent contract events."""

    schema_version = serializers.IntegerField(min_value=1, help_text="Payload schema version")
    correlation_id = serializers.CharField(
        max_length=64,
        min_length=64,
        help_text="64-character hexadecimal id used to deduplicate retries",
    )

    def validate_correlation_id(self, value):
        if not _SHA256_HEX_RE.fullmatch(value):
            raise serializers.ValidationError("Must be exactly 64 hexadecimal characters.")
        return value.lower()


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
        read_only_fields = ["id", "key", "is_active", "quota_per_hour", "last_used_at", "created_at"]
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
    # See ContractEventSerializer.payload for why this must be explicit.
    payload = serializers.JSONField(read_only=True)

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


class StateChangeSerializer(serializers.ModelSerializer):
    class Meta:
        model = StateChange
        fields = [
            "id",
            "field_name",
            "old_value",
            "new_value",
            "change_type",
            "created_at",
        ]


class ContractSnapshotSerializer(serializers.ModelSerializer):
    changes = StateChangeSerializer(many=True, read_only=True)

    class Meta:
        model = ContractSnapshot
        fields = [
            "id",
            "ledger_sequence",
            "state_data",
            "captured_at",
            "changes",
        ]


class EventAggregationSerializer(serializers.Serializer):
    """
    Read-only serializer for a single pre-computed aggregation bucket.
    Used by ``AnalyticsViewSet`` to return event-volume time-series data.
    """

    timestamp = serializers.DateTimeField()
    contract_id = serializers.CharField()
    contract_name = serializers.CharField()
    event_type = serializers.CharField(allow_blank=True)
    event_count = serializers.IntegerField()
    is_anomaly = serializers.BooleanField()


class EventsByContractsRequestSerializer(serializers.Serializer):
    """Request payload serializer for fetching events across multiple contracts."""

    contract_ids = serializers.ListField(
        child=serializers.CharField(),
        min_length=1,
        max_length=10,
        help_text="List of contract IDs to filter events by (max 10)",
    )
    event_type = serializers.CharField(
        required=False,
        allow_blank=True,
        default=None,
        help_text="Optional event type name to filter",
    )
    ledger_min = serializers.IntegerField(
        required=False,
        min_value=0,
        default=None,
        help_text="Minimum ledger sequence",
    )
    ledger_max = serializers.IntegerField(
        required=False,
        min_value=0,
        default=None,
        help_text="Maximum ledger sequence",
    )
    ordering = serializers.ChoiceField(
        choices=["-created_at", "created_at", "-ledger", "ledger"],
        default="-created_at",
        help_text="Sort ordering field",
    )
    page = serializers.IntegerField(default=1, min_value=1, help_text="Page number")
    page_size = serializers.IntegerField(default=20, min_value=1, max_value=100, help_text="Page size")


class WebhookReplayRequestSerializer(serializers.Serializer):
    """Request body for POST /webhooks/{id}/replay/ and contract-scoped replay."""

    contract_id = serializers.CharField(required=False, allow_blank=True)
    event_type = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    from_date = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    to_date = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    from_ledger = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    to_ledger = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    limit = serializers.IntegerField(required=False, default=100, min_value=0, max_value=10000)
    rate_limit_per_second = serializers.FloatField(
        required=False, default=5.0, min_value=0.1, max_value=100.0
    )
    dry_run = serializers.BooleanField(required=False, default=False)


class WebhookReplayJobSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.CharField()
    contract_id = serializers.CharField()
    subscription_id = serializers.IntegerField(allow_null=True)
    filters = serializers.JSONField()
    rate_limit_per_second = serializers.FloatField()
    dry_run = serializers.BooleanField()
    total_events = serializers.IntegerField()
    processed_events = serializers.IntegerField()
    succeeded = serializers.IntegerField()
    failed = serializers.IntegerField()
    skipped = serializers.IntegerField()
    error_message = serializers.CharField(allow_blank=True)
    result = serializers.JSONField()
    created_at = serializers.CharField(allow_null=True)
    started_at = serializers.CharField(allow_null=True)
    finished_at = serializers.CharField(allow_null=True)
    updated_at = serializers.CharField(allow_null=True)


class EventDeduplicationConfigSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(default=True)
    fields = serializers.ListField(
        child=serializers.CharField(max_length=128),
        allow_empty=True,
        help_text="Fields / special tokens used for the dedup fingerprint",
    )

    def validate_fields(self, value):
        cleaned = []
        for item in value:
            name = str(item).strip()
            if not name:
                raise serializers.ValidationError("Deduplication field cannot be blank.")
            if len(name) > 128:
                raise serializers.ValidationError(f"Field name too long: {name}")
            if name not in ALLOWED_DEDUP_FIELDS:
                raise serializers.ValidationError(
                    f"Unknown deduplication field '{name}'. Allowed fields: "
                    f"{', '.join(ALLOWED_DEDUP_FIELDS)}"
                )
            cleaned.append(name)
        return cleaned


class EventDeduplicationTestSerializer(serializers.Serializer):
    event_type = serializers.CharField(required=False, allow_blank=True)
    ledger = serializers.IntegerField(required=False, allow_null=True)
    event_index = serializers.IntegerField(required=False, allow_null=True)
    tx_hash = serializers.CharField(required=False, allow_blank=True)
    payload = serializers.JSONField(required=False, default=dict)


class BulkMetadataImportSerializer(serializers.Serializer):
    format = serializers.ChoiceField(choices=["csv", "json"], required=False)
    dry_run = serializers.BooleanField(required=False, default=False)
    on_error = serializers.ChoiceField(
        choices=["rollback", "skip"], required=False, default="rollback"
    )
    content = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Raw CSV/JSON body when not uploading a file",
    )

class ContractMetadataSerializer(serializers.ModelSerializer):
    contract_id = serializers.CharField(source="contract.contract_id", read_only=True)

    class Meta:
        model = ContractMetadata
        fields = [
            "contract_id",
            "name",
            "description",
            "tags",
            "documentation_url",
            "github_repo",
            "team_email",
        ]


class BulkContractMetadataRequestSerializer(serializers.Serializer):
    contract_ids = serializers.ListField(
        child=serializers.CharField(max_length=255),
        allow_empty=False,
        max_length=50,
    )

