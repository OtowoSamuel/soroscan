"""
Database models for SoroScan event indexing.
"""
import hashlib
import secrets

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.db import models
from django.utils.text import slugify

User = get_user_model()


class Organization(models.Model):
    """Top-level tenant boundary for contracts, teams, and members."""

    name = models.CharField(max_length=128)
    slug = models.SlugField(max_length=160, unique=True, db_index=True)
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="owned_organizations",
    )
    settings = models.JSONField(default=dict, blank=True)
    quota = models.PositiveIntegerField(default=0, help_text="Optional monthly event quota")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "organization"
            slug = base
            n = 0
            while Organization.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                n += 1
                slug = f"{base}-{n}"
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class OrganizationMembership(models.Model):
    """Links a user to an organization with RBAC roles."""

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="organization_memberships",
    )
    role = models.CharField(
        max_length=16,
        choices=Role.choices,
        default=Role.MEMBER,
    )
    invited_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_organization_invites",
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("organization", "user")]
        ordering = ["-joined_at"]

    def __str__(self):
        return f"{self.user} @ {self.organization} ({self.role})"


class OrganizationBudget(models.Model):
    """Monthly cost budget configuration per organization."""

    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name="budget",
    )
    monthly_budget_usd = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Monthly budget ceiling in USD.",
    )
    warning_threshold_percent = models.PositiveIntegerField(
        default=80,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Percent threshold for warning alerts.",
    )
    critical_threshold_percent = models.PositiveIntegerField(
        default=100,
        validators=[MinValueValidator(1), MaxValueValidator(200)],
        help_text="Percent threshold for critical alerts.",
    )
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["organization__name"]

    def __str__(self):
        return f"Budget({self.organization.name}: ${self.monthly_budget_usd})"


class OrganizationCostSnapshot(models.Model):
    """Monthly cost and usage snapshot for one organization."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="cost_snapshots",
    )
    month = models.DateField(
        help_text="Month bucket represented by first day of the month (UTC).",
    )
    rpc_calls = models.PositiveBigIntegerField(default=0)
    storage_bytes = models.PositiveBigIntegerField(default=0)
    compute_units = models.PositiveBigIntegerField(default=0)
    rpc_cost_usd = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    storage_cost_usd = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    compute_cost_usd = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    actual_cost_usd = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    projected_monthly_cost_usd = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0,
    )
    breakdown = models.JSONField(
        default=dict,
        blank=True,
        help_text="Cost breakdown by contract, event type, and storage consumption.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-month", "organization__name"]
        unique_together = [("organization", "month")]
        indexes = [
            models.Index(fields=["organization", "month"]),
        ]

    def __str__(self):
        return (
            f"CostSnapshot({self.organization.name}, {self.month}, "
            f"projected=${self.projected_monthly_cost_usd})"
        )


class Team(models.Model):
    """
    Multi-tenant organization: groups users and shared tracked contracts.
    """

    name = models.CharField(max_length=128)
    slug = models.SlugField(max_length=160, unique=True, db_index=True)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="teams",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_teams",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "team"
            slug = base
            n = 0
            while Team.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                n += 1
                slug = f"{base}-{n}"
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class TeamMembership(models.Model):
    """Links a user to a team with a role."""

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"

    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="team_memberships",
    )
    role = models.CharField(
        max_length=16,
        choices=Role.choices,
        default=Role.MEMBER,
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("team", "user")]
        ordering = ["-joined_at"]

    def __str__(self):
        return f"{self.user} @ {self.team} ({self.role})"


class TrackedContract(models.Model):
    """
    Contracts registered for event indexing.
    """

    class DeprecationStatus(models.TextChoices):
        ACTIVE = "active", "Active"
        DEPRECATED = "deprecated", "Deprecated"
        SUSPENDED = "suspended", "Suspended"

    class Network(models.TextChoices):
        MAINNET = "mainnet", "Mainnet"
        TESTNET = "testnet", "Testnet"
        FUTURENET = "futurenet", "Futurenet"

    contract_id = models.CharField(
        max_length=56,
        unique=True,
        db_index=True,
        validators=[
            RegexValidator(
                regex=r"^C[A-Z2-7]{55}$",
                message="Contract address must start with 'C' and be exactly 56 characters using valid Base32 characters (A-Z, 2-7).",
            )
        ],
        help_text="Stellar contract address (C...)",
    )
    name = models.CharField(max_length=100, db_index=True, help_text="Human-readable contract name")
    alias = models.CharField(
        max_length=256,
        blank=True,
        default="",
        help_text="Optional friendly name/alias for easier identification (e.g. 'Token Transfer Contract')",
    )
    description = models.TextField(blank=True, help_text="Optional description")
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="tracked_contracts",
        help_text="User who registered this contract",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="tracked_contracts",
        null=True,
        blank=True,
        help_text="Organization scope for tenant isolation",
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tracked_contracts",
        help_text="Optional team scope for multi-tenant access",
    )
    abi_schema = models.JSONField(
        null=True,
        blank=True,
        help_text="Optional ABI/schema for decoding events",
    )
    json_schema = models.JSONField(
        null=True,
        blank=True,
        help_text="Optional JSON Schema used to validate ingested event payloads.",
    )
    last_indexed_ledger = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Last ledger sequence that was indexed for this contract",
    )
    is_active = models.BooleanField(default=True, help_text="Whether indexing is active")
    last_event_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Timestamp of the last indexed event for this contract",
    )
    deprecation_status = models.CharField(
        max_length=16,
        choices=DeprecationStatus.choices,
        default=DeprecationStatus.ACTIVE,
        db_index=True,
        help_text="Manual lifecycle/deprecation state for warning users",
    )
    deprecation_reason = models.TextField(
        blank=True,
        help_text="Optional reason shown to users when contract is deprecated/suspended",
    )
    max_events_per_minute = models.IntegerField(
        null=True,
        blank=True,
        help_text="Max events per minute for ingest-time rate limiting (None = unlimited)",
    )
    network = models.CharField(
        max_length=16,
        choices=Network.choices,
        default=Network.MAINNET,
        db_index=True,
        help_text="Stellar network this contract is deployed on (mainnet, testnet, futurenet)",
    )

    # ---------------------------------------------------------------------------
    # Event filtering (whitelist / blacklist)
    # ---------------------------------------------------------------------------
    FILTER_NONE = "none"
    FILTER_WHITELIST = "whitelist"
    FILTER_BLACKLIST = "blacklist"
    FILTER_TYPE_CHOICES = [
        (FILTER_NONE, "No Filter"),
        (FILTER_WHITELIST, "Whitelist"),
        (FILTER_BLACKLIST, "Blacklist"),
    ]

    event_filter_type = models.CharField(
        max_length=16,
        choices=FILTER_TYPE_CHOICES,
        default=FILTER_NONE,
        help_text=(
            "Ingest filter mode: none = store all events; "
            "whitelist = only store listed event types; "
            "blacklist = drop listed event types."
        ),
    )
    event_filter_list = models.JSONField(
        default=list,
        blank=True,
        help_text="List of event type names used by the whitelist/blacklist filter.",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Custom attributes for storing contract metadata (team, owner, cost center, etc.)",
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["contract_id", "is_active"]),
            models.Index(fields=["alias"]),
            models.Index(fields=["network", "is_active"]),
        ]

    def __str__(self):
        display = self.alias or self.name
        return f"{display} ({self.contract_id[:8]}...)"

    def display_name(self) -> str:
        """Return alias if set, otherwise contract_id."""
        return self.alias if self.alias else self.contract_id

    def deprecation_warning(self) -> dict[str, str] | None:
        if self.deprecation_status == self.DeprecationStatus.ACTIVE:
            return None
        status_label = self.get_deprecation_status_display().lower()
        if self.deprecation_reason:
            message = self.deprecation_reason
        else:
            message = f"This contract is {status_label}."
        return {"type": "deprecation", "message": message}

    def should_ingest_event(self, event_type: str) -> bool:
        """Return True if *event_type* should be persisted given the filter config."""
        if self.event_filter_type == self.FILTER_NONE:
            return True
        if self.event_filter_type == self.FILTER_WHITELIST:
            return event_type in (self.event_filter_list or [])
        if self.event_filter_type == self.FILTER_BLACKLIST:
            return event_type not in (self.event_filter_list or [])
        return True


class ContractInvocation(models.Model):
    """
    Record of a contract function invocation that generated events.
    """

    tx_hash = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Transaction hash",
    )
    caller = models.CharField(
        max_length=56,
        db_index=True,
        help_text="Source account address (G...)",
    )
    contract = models.ForeignKey(
        TrackedContract,
        on_delete=models.CASCADE,
        related_name="invocations",
        help_text="Target contract invoked",
    )
    function_name = models.CharField(
        max_length=128,
        db_index=True,
        help_text="Contract function name",
    )
    parameters = models.JSONField(
        help_text="Function parameters in XDR-encoded form",
    )
    result = models.JSONField(
        null=True,
        blank=True,
        help_text="Function result in XDR-encoded form",
    )
    ledger_sequence = models.PositiveBigIntegerField(
        db_index=True,
        help_text="Ledger sequence number",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Timestamp when record was created",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["contract", "created_at"]),
            models.Index(fields=["caller"]),
            models.Index(fields=["tx_hash"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tx_hash", "contract"],
                name="unique_tx_hash_contract",
            )
        ]

    def __str__(self):
        return f"{self.function_name}@{self.ledger_sequence} ({self.contract.name})"


class EventSchema(models.Model):
    """
    Versioned JSON schema for contract event types (issue #17).
    """

    contract = models.ForeignKey(
        TrackedContract,
        on_delete=models.CASCADE,
        related_name="event_schemas",
        help_text="Contract this schema applies to",
    )
    version = models.PositiveIntegerField(help_text="Schema version number")
    event_type = models.CharField(
        max_length=128,
        help_text="Event type/name this schema describes",
    )
    json_schema = models.JSONField(help_text="JSON Schema for validating event payloads")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["contract", "version", "event_type"],
                name="ingest_eventschema_contract_version_event_type_uniq",
            )
        ]

    def __str__(self):
        return f"{self.event_type} v{self.version} ({self.contract.name})"


class ContractABI(models.Model):
    """
    ABI definition for decoding raw Soroban event payloads (issue #58).

    Stores a JSON array of event definitions that map positional XDR
    fields to human-readable names and types.
    """

    contract = models.OneToOneField(
        TrackedContract,
        on_delete=models.CASCADE,
        related_name="abi",
        help_text="Contract this ABI applies to",
    )
    abi_json = models.JSONField(
        help_text='JSON array of event definitions: [{"name": "...", "fields": [{"name": "...", "type": "..."}]}]',
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Contract ABI"
        verbose_name_plural = "Contract ABIs"

    def __str__(self):
        return f"ABI for {self.contract}"


class ContractSigningKey(models.Model):
    """
    Public verification key registered per contract for event signature checks.
    """

    class Algorithm(models.TextChoices):
        ED25519 = "ed25519", "Ed25519"
        ECDSA = "ecdsa", "ECDSA"

    contract = models.OneToOneField(
        TrackedContract,
        on_delete=models.CASCADE,
        related_name="signing_key",
    )
    algorithm = models.CharField(
        max_length=16,
        choices=Algorithm.choices,
        default=Algorithm.ED25519,
    )
    public_key = models.TextField(
        help_text="Public key for signature verification (hex/base64/raw PEM)",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Contract Signing Key"
        verbose_name_plural = "Contract Signing Keys"

    def __str__(self):
        return f"SigningKey({self.contract.contract_id[:8]}..., {self.algorithm})"


class ContractEvent(models.Model):
    """
    Individual events emitted by tracked contracts.
    """

    contract = models.ForeignKey(
        TrackedContract,
        on_delete=models.CASCADE,
        related_name="events",
        help_text="The contract that emitted this event",
    )
    event_type = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Event type/name (e.g., 'swap', 'transfer')",
    )
    schema_version = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="EventSchema version used for validation (if any)",
    )
    validation_status = models.CharField(
        max_length=32,
        choices=[
            ("passed", "Passed"),
            ("failed", "Failed"),
        ],
        default="passed",
        db_index=True,
        help_text="Result of schema validation",
    )
    payload = models.JSONField(help_text="Decoded event payload")
    payload_hash = models.CharField(
        max_length=64,
        db_index=True,
        help_text="SHA-256 hash of the payload",
    )
    ledger = models.PositiveBigIntegerField(
        db_index=True,
        help_text="Ledger sequence number",
    )
    event_index = models.PositiveIntegerField(
        default=0,
        help_text="0-based event index within the ledger",
    )
    timestamp = models.DateTimeField(db_index=True, help_text="Event timestamp")
    tx_hash = models.CharField(max_length=64, help_text="Transaction hash")
    raw_xdr = models.TextField(blank=True, help_text="Raw XDR for debugging")
    invocation = models.ForeignKey(
        "ContractInvocation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
        help_text="Invocation that generated this event",
    )
    decoded_payload = models.JSONField(
        null=True,
        blank=True,
        help_text="ABI-decoded event payload (human-readable fields)",
    )
    decoding_status = models.CharField(
        max_length=16,
        choices=[
            ("success", "Success"),
            ("failed", "Failed"),
            ("no_abi", "No ABI"),
        ],
        default="no_abi",
        db_index=True,
        help_text="Result of ABI-based XDR decoding",
    )
    signature_status = models.CharField(
        max_length=16,
        choices=[
            ("valid", "Valid"),
            ("invalid", "Invalid"),
            ("missing", "Missing"),
        ],
        default="missing",
        db_index=True,
        help_text="Result of event signature verification",
    )

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["contract", "event_type", "timestamp"]),
            models.Index(fields=["contract", "timestamp"]),
            models.Index(fields=["ledger"]),
            models.Index(fields=["tx_hash"]),
            models.Index(fields=["contract", "ledger", "event_index"]),
            models.Index(fields=["invocation"]),
            models.Index(fields=["signature_status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["contract", "ledger", "event_index"],
                name="unique_contract_ledger_event_index",
            ),
        ]

    def __str__(self):
        return f"{self.event_type}@{self.ledger} ({self.contract.name})"

    def save(self, *args, **kwargs):
        # Auto-compute payload hash if not set
        if not self.payload_hash and self.payload:
            payload_bytes = str(self.payload).encode("utf-8")
            self.payload_hash = hashlib.sha256(payload_bytes).hexdigest()
        super().save(*args, **kwargs)


class WebhookSubscription(models.Model):
    """
    Webhook subscriptions for push notifications on specific events.
    """

    STATUS_ACTIVE = "active"
    STATUS_SUSPENDED = "suspended"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_SUSPENDED, "Suspended"),
    ]

    BACKOFF_EXPONENTIAL = "exponential"
    BACKOFF_LINEAR = "linear"
    BACKOFF_FIXED = "fixed"
    BACKOFF_STRATEGY_CHOICES = [
        (BACKOFF_EXPONENTIAL, "Exponential (base * 2^attempt)"),
        (BACKOFF_LINEAR, "Linear (base * attempt)"),
        (BACKOFF_FIXED, "Fixed (base seconds)"),
    ]

    SIGNATURE_SHA256 = "sha256"
    SIGNATURE_SHA1 = "sha1"
    SIGNATURE_ALGORITHM_CHOICES = [
        (SIGNATURE_SHA256, "SHA-256"),
        (SIGNATURE_SHA1, "SHA-1 (legacy)"),
    ]

    contract = models.ForeignKey(
        TrackedContract,
        on_delete=models.CASCADE,
        related_name="webhooks",
        help_text="Contract to monitor",
    )
    event_type = models.CharField(
        max_length=100,
        blank=True,
        help_text="Event type filter (blank = all events)",
    )
    target_url = models.URLField(help_text="URL to POST event data to")
    secret = models.CharField(
        max_length=64,
        help_text="HMAC secret — stored as a hex token, never logged or exposed via API",
    )
    is_active = models.BooleanField(default=True)
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
        help_text="Lifecycle state: active dispatches events; suspended has exhausted all retries",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_triggered = models.DateTimeField(null=True, blank=True)
    failure_count = models.PositiveIntegerField(default=0)
    timeout_seconds = models.IntegerField(
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(60)],
        help_text="Timeout for webhook dispatch in seconds (1-60, default: 10)",
    )
    retry_backoff_strategy = models.CharField(
        max_length=16,
        choices=BACKOFF_STRATEGY_CHOICES,
        default=BACKOFF_EXPONENTIAL,
        help_text="Strategy for calculating retry delays",
    )
    retry_backoff_seconds = models.PositiveIntegerField(
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(3600)],
        help_text="Base seconds for backoff calculation (e.g. 2s, 4s, 8s...) (1-3600, default: 2)",
    )
    signature_algorithm = models.CharField(
        max_length=16,
        choices=SIGNATURE_ALGORITHM_CHOICES,
        default=SIGNATURE_SHA256,
        help_text="HMAC algorithm used for X-SoroScan-Signature header.",
    )
    ack_header_name = models.CharField(
        max_length=64,
        default="X-SoroScan-Ack",
        help_text="HTTP response header that must be present to acknowledge receipt.",
    )
    ack_header_value = models.CharField(
        max_length=128,
        default="ok",
        help_text="Expected acknowledgement header value.",
    )
    delivery_sla_seconds = models.PositiveIntegerField(
        default=30,
        validators=[MinValueValidator(1), MaxValueValidator(3600)],
        help_text="SLA target in seconds for successful delivery acknowledgements.",
    )
    escalation_policy = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Ordered escalation policy list, e.g. "
            '[{"channel": "slack", "target": "...", "after_failures": 2}]. '
            "Defaults to Slack -> SMS -> PagerDuty when empty."
        ),
    )
    filter_condition = models.JSONField(
        blank=True,
        null=True,
        help_text="Optional JSON condition DSL used to route events to this webhook.",
    )

    class Meta:
        ordering = ["-created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["target_url", "contract"],
                name="unique_url_contract_subscription",
            )
        ]

    def __str__(self):
        return f"Webhook -> {self.target_url} ({self.contract.name})"

    def get_known_event_types(self):
        types = set()
        if hasattr(self.contract, "event_schemas"):
            types.update(self.contract.event_schemas.values_list("event_type", flat=True))
        if hasattr(self.contract, "abi") and self.contract.abi.abi_json:
            for ev in self.contract.abi.abi_json:
                if isinstance(ev, dict) and ev.get("name"):
                    types.add(ev["name"])
        types.update(self.contract.events.values_list("event_type", flat=True).distinct())
        return types

    def clean(self):
        super().clean()
        if self.event_type and self.contract_id:
            known = self.get_known_event_types()
            if known and self.event_type not in known:
                from django.core.exceptions import ValidationError
                raise ValidationError({"event_type": f"Invalid event type. Available types: {', '.join(sorted(known))}"})

    def save(self, *args, **kwargs):
        # Auto-generate secret if not set
        if not self.secret:
            self.secret = secrets.token_hex(32)
        super().save(*args, **kwargs)


class WebhookDeliveryLog(models.Model):
    """
    Immutable audit log for every webhook dispatch attempt.

    Records are subject to a 30-day TTL: the ``cleanup_webhook_delivery_logs``
    Celery task (scheduled via Celery Beat) prunes entries older than 30 days.
    """

    subscription = models.ForeignKey(
        WebhookSubscription,
        on_delete=models.CASCADE,
        related_name="delivery_logs",
        help_text="Subscription this attempt belongs to",
    )
    event = models.ForeignKey(
        "ContractEvent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="delivery_logs",
        help_text="ContractEvent that triggered this delivery",
    )
    attempt_number = models.PositiveIntegerField(
        default=1,
        help_text="1-based attempt counter (1 = first try, 2 = first retry, …)",
    )
    status_code = models.IntegerField(
        null=True,
        blank=True,
        help_text="HTTP status code returned by the subscriber, or null for network errors",
    )
    success = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True when subscriber returned a 2xx response",
    )
    error = models.TextField(
        blank=True,
        help_text="Error detail when success=False",
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="UTC timestamp of this attempt",
    )
    payload_bytes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Size of the webhook payload in bytes",
    )
    acknowledged = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True when the subscriber returned the expected acknowledgement header.",
    )
    latency_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Observed delivery latency in milliseconds.",
    )
    within_sla = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True when acknowledged delivery met the configured SLA target.",
    )

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["subscription", "timestamp"]),
        ]

    def __str__(self):
        status_label = "OK" if self.success else f"FAIL({self.status_code})"
        return f"Delivery #{self.attempt_number} [{status_label}] sub={self.subscription_id}"


class WebhookDeadLetter(models.Model):
    """
    Dead-letter queue entries for webhook deliveries that exhausted retries.

    Operators can review and manually replay or resolve these records.
    """

    subscription = models.ForeignKey(
        WebhookSubscription,
        on_delete=models.CASCADE,
        related_name="dead_letters",
        help_text="Subscription whose delivery failed terminally",
    )
    event = models.ForeignKey(
        "ContractEvent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="webhook_dead_letters",
        help_text="Event payload associated with the failed delivery",
    )
    payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Serialized webhook payload for manual replay/review",
    )
    status_code = models.IntegerField(
        null=True,
        blank=True,
        help_text="Last observed subscriber HTTP status code",
    )
    error = models.TextField(blank=True)
    retries_exhausted = models.PositiveIntegerField(
        default=0,
        help_text="How many attempts were exhausted before dead-lettering",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved = models.BooleanField(default=False, db_index=True)
    resolution_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["subscription", "created_at"]),
            models.Index(fields=["resolved", "created_at"]),
        ]

    def __str__(self):
        return f"WebhookDeadLetter(sub={self.subscription_id}, resolved={self.resolved})"


class EventDeduplicationLog(models.Model):
    """
    Audit log for event deduplication attempts.

    Records are subject to a 90-day TTL: the ``cleanup_old_dedup_logs``
    Celery task (scheduled via Celery Beat) prunes entries older than 90 days.
    """

    contract = models.ForeignKey(
        TrackedContract,
        on_delete=models.CASCADE,
        related_name="dedup_logs",
        help_text="Contract the event belongs to",
    )
    ledger = models.PositiveBigIntegerField(
        db_index=True,
        help_text="Ledger sequence number",
    )
    event_index = models.PositiveIntegerField(
        help_text="0-based event index within the ledger",
    )
    tx_hash = models.CharField(
        max_length=64,
        help_text="Transaction hash",
    )
    event_type = models.CharField(
        max_length=100,
        help_text="Event type that was checked",
    )
    duplicate_detected = models.BooleanField(
        default=False,
        help_text="True if a duplicate was detected",
    )
    reason = models.CharField(
        max_length=255,
        blank=True,
        help_text="Reason for the deduplication decision",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="UTC timestamp of this deduplication check",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["contract", "created_at"]),
            models.Index(fields=["contract", "ledger", "event_index"]),
        ]

    def __str__(self):
        status = "DUP" if self.duplicate_detected else "NEW"
        return f"[{status}] {self.event_type}@{self.ledger} ({self.contract.name})"


class IndexerState(models.Model):
    """
    Tracks the current indexing state (cursor position).
    """

    key = models.CharField(max_length=50, unique=True, primary_key=True)
    value = models.CharField(max_length=200)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.key}: {self.value}"


class EventDeduplicationConfig(models.Model):
    """
    Per-contract configuration that defines which event fields should be
    considered when computing the deduplication fingerprint.

    The `fields` JSONField is a list of strings naming top-level keys from
    the event payload (or special tokens like 'event_type', 'tx_hash',
    'ledger', 'event_index') that will be used to build the dedup material.
    """

    contract = models.OneToOneField(
        TrackedContract,
        on_delete=models.CASCADE,
        related_name="dedup_config",
        help_text="Contract this dedup config applies to",
    )
    enabled = models.BooleanField(default=True, help_text="Enable deduplication for this contract")
    # list of field names to include when computing dedup fingerprint
    fields = models.JSONField(default=list, blank=True, help_text="List of event fields (or special tokens) to include in dedup key")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Event Deduplication Config"
        verbose_name_plural = "Event Deduplication Configs"

    def __str__(self):
        return f"Dedup config for {self.contract.name} (enabled={self.enabled})"


# ---------------------------------------------------------------------------
# Issue #X: Tiered rate limiting with per-API-key and per-contract quotas
# ---------------------------------------------------------------------------

class APIKey(models.Model):
    """
    API key model with tiered rate limiting.
    Keys are at least 32 characters and randomly generated.
    """

    class Tier(models.TextChoices):
        FREE = "free", "Free"
        PRO = "pro", "Pro"
        ENTERPRISE = "enterprise", "Enterprise"

    TIER_QUOTAS: dict = {
        "free": 50,
        "pro": 5000,
        "enterprise": None,  # unlimited — stored as large int
    }
    UNLIMITED_QUOTA = 10_000_000

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="api_keys",
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="api_keys",
    )
    name = models.CharField(max_length=128)
    key = models.CharField(max_length=64, unique=True, db_index=True)
    tier = models.CharField(
        max_length=16,
        choices=Tier.choices,
        default=Tier.FREE,
    )
    quota_per_hour = models.IntegerField(
        help_text="Max requests per hour. Auto-set from tier on creation.",
    )
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.key:
            # At least 32 chars, URL-safe random token
            self.key = secrets.token_urlsafe(48)[:64]
        if not self.quota_per_hour:
            quota = self.TIER_QUOTAS.get(self.tier, 50)
            self.quota_per_hour = quota if quota is not None else self.UNLIMITED_QUOTA
        if self.team and not TeamMembership.objects.filter(team=self.team, user=self.user).exists():
            raise ValidationError("API key user must be a member of the assigned team.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} [{self.tier}] ({self.user})"


class ContractQuota(models.Model):
    """
    Per-contract rate limit override for a specific APIKey.
    Cannot exceed the key's tier limit.
    """

    contract = models.ForeignKey(
        TrackedContract,
        on_delete=models.CASCADE,
        related_name="contract_quotas",
    )
    api_key = models.ForeignKey(
        APIKey,
        on_delete=models.CASCADE,
        related_name="contract_quotas",
    )
    quota_per_hour = models.IntegerField(
        help_text="Custom requests-per-hour for this contract. Cannot exceed the key tier limit.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("contract", "api_key")
        ordering = ["-created_at"]

    def clean(self):
        from django.core.exceptions import ValidationError

        if (
            self.api_key.tier != APIKey.Tier.ENTERPRISE
            and self.quota_per_hour > self.api_key.quota_per_hour
        ):
            raise ValidationError(
                "Contract quota_per_hour cannot exceed the API key's tier limit "
                f"({self.api_key.quota_per_hour}/hr)."
            )

    def __str__(self):
        return f"{self.api_key.name} / {self.contract.name}: {self.quota_per_hour}/hr"


# ---------------------------------------------------------------------------
# Issue #X: Event-driven alerts with rule engine and notifications
# ---------------------------------------------------------------------------

class AlertRule(models.Model):
    """
    Alert rule attached to a contract with a JSON condition AST.
    Supports AND / OR / NOT logic with field comparisons.
    """

    MAX_RULES_PER_CONTRACT = 100

    contract = models.ForeignKey(
        TrackedContract,
        on_delete=models.CASCADE,
        related_name="alert_rules",
    )
    name = models.CharField(max_length=256)
    condition = models.JSONField(
        help_text="Condition AST: {'op': 'and', 'conditions': [...]}"
    )
    channels = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            'Optional list of destinations: [{"type": "slack|email|webhook", "target": "..."}]. '
            "When non-empty, the rule fires to every channel in real time (same Celery task)."
        ),
    )
    action_type = models.CharField(
        max_length=16,
        choices=[
            ("slack", "Slack"),
            ("email", "Email"),
            ("webhook", "Webhook"),
        ],
    )
    action_target = models.TextField(
        blank=True,
        help_text="Legacy single destination when channels is empty",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.contract.name})"


class AlertExecution(models.Model):
    """
    Immutable record of each rule trigger attempt (sent / failed).
    """

    rule = models.ForeignKey(
        AlertRule,
        on_delete=models.CASCADE,
        related_name="executions",
    )
    event = models.ForeignKey(
        ContractEvent,
        on_delete=models.CASCADE,
        related_name="alert_executions",
    )
    channel = models.CharField(
        max_length=32,
        blank=True,
        help_text="slack, email, webhook, or empty for legacy single-channel rows",
    )
    status = models.CharField(
        max_length=16,
        choices=[("sent", "Sent"), ("failed", "Failed")],
    )
    response = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["rule", "created_at"]),
        ]

    def __str__(self):
        return f"Alert {self.rule.name}: {self.status} @ {self.created_at}"


class RemediationRule(models.Model):
    """
    Automated incident response rule.

    ``condition`` describes anomaly detection criteria.
    ``actions`` is a list of action objects, e.g.:
      [{"type": "pause_contract"}, {"type": "disable_webhooks"}]
    """

    CONDITION_NO_EVENTS = "no_events_for_minutes"
    CONDITION_DECODE_ERROR_SPIKE = "decode_error_spike"
    CONDITION_CHOICES = [
        (CONDITION_NO_EVENTS, "No events for N minutes"),
        (CONDITION_DECODE_ERROR_SPIKE, "Decode error spike"),
    ]

    ALERT_SLACK = "slack"
    ALERT_EMAIL = "email"
    ALERT_WEBHOOK = "webhook"
    ALERT_TYPE_CHOICES = [
        (ALERT_SLACK, "Slack"),
        (ALERT_EMAIL, "Email"),
        (ALERT_WEBHOOK, "Webhook"),
    ]

    name = models.CharField(max_length=256)
    condition = models.JSONField(
        help_text="Condition JSON, e.g. {'type': 'no_events_for_minutes', 'contract_id': 'C...', 'minutes': 60}",
    )
    actions = models.JSONField(
        default=list,
        help_text="List of action objects: pause_contract, send_alert, disable_webhooks",
    )
    enabled = models.BooleanField(default=True)
    grace_period_minutes = models.PositiveIntegerField(default=10)
    alert_type = models.CharField(
        max_length=16,
        choices=ALERT_TYPE_CHOICES,
        default=ALERT_SLACK,
    )
    alert_target = models.TextField(
        blank=True,
        help_text="Ops destination (Slack webhook URL, email, or webhook URL)",
    )
    dry_run = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"RemediationRule({self.name})"


class RemediationIncident(models.Model):
    """
    Tracks lifecycle of a detected anomaly for one remediation rule.
    """

    STATUS_ALERTED = "alerted"
    STATUS_EXECUTED = "executed"
    STATUS_RESOLVED = "resolved"
    STATUS_CHOICES = [
        (STATUS_ALERTED, "Alerted"),
        (STATUS_EXECUTED, "Executed"),
        (STATUS_RESOLVED, "Resolved"),
    ]

    rule = models.ForeignKey(
        RemediationRule,
        on_delete=models.CASCADE,
        related_name="incidents",
    )
    contract = models.ForeignKey(
        TrackedContract,
        on_delete=models.CASCADE,
        related_name="remediation_incidents",
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_ALERTED)
    anomaly_snapshot = models.JSONField(default=dict)
    first_detected_at = models.DateTimeField(auto_now_add=True)
    alerted_at = models.DateTimeField(null=True, blank=True)
    action_after_at = models.DateTimeField(null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-first_detected_at"]
        indexes = [
            models.Index(fields=["rule", "contract", "status"]),
            models.Index(fields=["action_after_at"]),
        ]

    def __str__(self):
        return f"Incident(rule={self.rule_id}, contract={self.contract_id}, status={self.status})"


# ---------------------------------------------------------------------------
# Data Retention Policies and Automated Archival
# ---------------------------------------------------------------------------

class DataRetentionPolicy(models.Model):
    """
    Configurable retention rule — per-contract or global (contract=None).
    Events older than retention_days are archived to S3 and deleted from PG.
    """

    contract = models.OneToOneField(
        TrackedContract,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="retention_policy",
        help_text="Leave blank for a global default policy",
    )
    retention_days = models.PositiveIntegerField(
        default=365,
        help_text="Events older than this many days will be archived",
    )
    archive_enabled = models.BooleanField(
        default=True,
        help_text="When False, events are pruned without archiving to S3",
    )
    s3_bucket = models.CharField(
        max_length=255,
        help_text="S3 bucket name for archived event batches",
    )
    s3_prefix = models.CharField(
        max_length=255,
        blank=True,
        default="soroscan/archives/",
        help_text="Key prefix inside the S3 bucket",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Data Retention Policy"
        verbose_name_plural = "Data Retention Policies"

    def __str__(self):
        scope = self.contract.name if self.contract else "Global"
        return f"RetentionPolicy({scope}, {self.retention_days}d)"


# ---------------------------------------------------------------------------
# Issue #X: Contract interaction dependency graph and call tracing
# ---------------------------------------------------------------------------

class ContractDependency(models.Model):
    """
    Tracks contract-to-contract calls identified from event data or traces.
    Used to build the interaction DAG.
    """

    caller = models.ForeignKey(
        TrackedContract,
        on_delete=models.CASCADE,
        related_name="calls",
        help_text="The contract that initiated the call",
    )
    callee = models.ForeignKey(
        TrackedContract,
        on_delete=models.CASCADE,
        related_name="called_by",
        help_text="The contract that was called",
    )
    call_count = models.IntegerField(
        default=0,
        help_text="Total number of times this dependency has been observed",
    )
    risk_score = models.FloatField(
        default=0.0,
        help_text="Edge-level risk score derived from call frequency and graph topology.",
    )
    first_call = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp of the first observed call",
    )
    last_call = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp of the most recent observed call",
    )

    class Meta:
        unique_together = ("caller", "callee")
        verbose_name_plural = "Contract Dependencies"

    def __str__(self):
        return f"{self.caller.name} -> {self.callee.name} ({self.call_count})"


class DependencyImpactAssessment(models.Model):
    """
    Latest vulnerability impact assessment for a root contract.

    Stores blast radius, downstream contracts, and a quantified risk score.
    """

    IMPACT_LOW = "low"
    IMPACT_MEDIUM = "medium"
    IMPACT_HIGH = "high"
    IMPACT_CRITICAL = "critical"
    IMPACT_CHOICES = [
        (IMPACT_LOW, "Low"),
        (IMPACT_MEDIUM, "Medium"),
        (IMPACT_HIGH, "High"),
        (IMPACT_CRITICAL, "Critical"),
    ]

    root_contract = models.OneToOneField(
        TrackedContract,
        on_delete=models.CASCADE,
        related_name="dependency_impact",
    )
    affected_contracts = models.JSONField(
        default=list,
        blank=True,
        help_text="Ordered list of downstream impacted contract IDs.",
    )
    impacted_count = models.PositiveIntegerField(default=0)
    has_cycles = models.BooleanField(default=False)
    risk_score = models.FloatField(default=0.0)
    impact_level = models.CharField(
        max_length=16,
        choices=IMPACT_CHOICES,
        default=IMPACT_LOW,
    )
    assessment_details = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-computed_at"]

    def __str__(self):
        return (
            f"DependencyImpact({self.root_contract.contract_id[:8]}..., "
            f"score={self.risk_score:.1f})"
        )


class CallGraph(models.Model):
    """
    Cached representation of the global or contract-specific call graph.
    Re-computed periodically to detect cycles and identify critical paths.
    """

    contract = models.OneToOneField(
        TrackedContract,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="call_graph",
        help_text="The root contract for this graph (null for global graph)",
    )
    graph_data = models.JSONField(
        help_text="Serialized DAG: nodes, edges, and metadata",
    )
    has_cycles = models.BooleanField(
        default=False,
        help_text="True if circular dependencies were detected during computation",
    )
    cycle_details = models.JSONField(
        null=True,
        blank=True,
        help_text="List of contract IDs involved in cycles",
    )
    computed_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        root = self.contract.name if self.contract else "Global"
        return f"CallGraph({root}) @ {self.computed_at}"


class ArchivedEventBatch(models.Model):
    """
    Metadata record for a single S3 archive object (gzip-compressed JSON).
    The actual event data lives in S3; this record is the manifest.
    """

    STATUS_ARCHIVED = "archived"
    STATUS_RESTORED = "restored"
    STATUS_CHOICES = [
        (STATUS_ARCHIVED, "Archived"),
        (STATUS_RESTORED, "Restored"),
    ]

    policy = models.ForeignKey(
        DataRetentionPolicy,
        on_delete=models.CASCADE,
        related_name="batches",
    )
    s3_key = models.CharField(
        max_length=512,
        unique=True,
        help_text="Full S3 object key for this batch",
    )
    event_count = models.IntegerField(
        help_text="Number of events in this batch",
    )
    size_bytes = models.BigIntegerField(
        default=0,
        help_text="Compressed size of the S3 object in bytes",
    )
    min_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Earliest event timestamp in this batch",
    )
    max_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Latest event timestamp in this batch",
    )
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_ARCHIVED,
        db_index=True,
    )
    archived_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-archived_at"]
        indexes = [
            models.Index(fields=["policy", "archived_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"Batch({self.s3_key}, {self.event_count} events)"


class ArchivalAuditLog(models.Model):
    """
    Immutable audit trail for every archival and restore operation.
    Records are never deleted automatically.
    """

    ACTION_ARCHIVE = "archive"
    ACTION_RESTORE = "restore"
    ACTION_CHOICES = [
        (ACTION_ARCHIVE, "Archive"),
        (ACTION_RESTORE, "Restore"),
    ]

    action = models.CharField(max_length=16, choices=ACTION_CHOICES, db_index=True)
    batch = models.ForeignKey(
        ArchivedEventBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    policy = models.ForeignKey(
        DataRetentionPolicy,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    event_count = models.IntegerField(default=0)
    detail = models.TextField(blank=True, help_text="Extra context or error message")
    performed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="User who triggered a restore (null for automated archival)",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"AuditLog({self.action}, {self.event_count} events, {self.created_at})"


class AdminAction(models.Model):
    """
    Immutable audit trail for admin actions.

    Records are append-only and retained for at least 7 years.
    """

    RETENTION_YEARS = 7

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
    )
    action = models.CharField(max_length=128)
    object_type = models.CharField(max_length=32)
    object_id = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField(default="0.0.0.0")
    changes = models.JSONField(default=dict)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["action", "timestamp"]),
            models.Index(fields=["object_type", "object_id"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("AdminAction is immutable and cannot be updated.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("AdminAction is immutable and cannot be deleted.")

    def __str__(self):
        return f"{self.action} {self.object_type}:{self.object_id}"


# ---------------------------------------------------------------------------
# Issue #137: Notification center
# ---------------------------------------------------------------------------

class Notification(models.Model):
    """
    In-app notification for a user. Covers contract events, webhook failures,
    rate-limit warnings, and system maintenance messages.
    """

    class NotificationType(models.TextChoices):
        CONTRACT_PAUSED = "contract_paused", "Contract Paused"
        WEBHOOK_FAILURE = "webhook_failure", "Webhook Failure"
        RATE_LIMIT = "rate_limit", "Rate Limit Warning"
        SYSTEM = "system", "System"
        ALERT = "alert", "Alert"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    notification_type = models.CharField(
        max_length=32,
        choices=NotificationType.choices,
        db_index=True,
    )
    title = models.CharField(max_length=256)
    message = models.TextField()
    link = models.CharField(max_length=512, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_read", "created_at"]),
        ]

    def __str__(self):
        return f"[{self.notification_type}] {self.title} → {self.user}"


class IngestError(models.Model):
    """
    Tracks ingestion errors for admin visibility.
    """
    
    class ErrorType(models.TextChoices):
        DECODE_ERROR = "decode_error", "Decode Error"
        VALIDATION_ERROR = "validation_error", "Validation Error"
        RPC_ERROR = "rpc_error", "RPC Error"
    
    error_type = models.CharField(
        max_length=32,
        choices=ErrorType.choices,
        db_index=True,
    )
    contract_id = models.CharField(
        max_length=56,
        db_index=True,
        help_text="Contract that caused the error",
    )
    error_message = models.TextField(help_text="Full error message")
    sample_error = models.CharField(
        max_length=500,
        help_text="Truncated error message for display",
    )
    ledger = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        help_text="Ledger where error occurred",
    )
    tx_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text="Transaction hash if available",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["error_type", "contract_id", "created_at"]),
            models.Index(fields=["created_at"]),
        ]
    
    def save(self, *args, **kwargs):
        if not self.sample_error:
            self.sample_error = self.error_message[:500]
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.error_type}: {self.contract_id} at {self.created_at}"


# ---------------------------------------------------------------------------
# Contract Metadata Registry
# ---------------------------------------------------------------------------

class ContractMetadata(models.Model):
    """
    Optional rich metadata for a TrackedContract.

    Stores human-readable name, description, categorization tags,
    documentation links, GitHub repo URL, and team contact email.
    Metadata is optional — a contract functions normally without it.
    """

    contract = models.OneToOneField(
        TrackedContract,
        on_delete=models.CASCADE,
        related_name="contractmetadata",
    )
    name = models.CharField(max_length=256)
    description = models.TextField(blank=True)
    tags = models.JSONField(default=list, blank=True)
    documentation_url = models.URLField(blank=True)
    github_repo = models.URLField(blank=True)
    team_email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Contract Metadata"
        verbose_name_plural = "Contract Metadata"

    def clean(self):
        from django.core.exceptions import ValidationError
        errors = {}
        
        # Validate name is not empty or just whitespace
        if not self.name or not self.name.strip():
            errors["name"] = "Name cannot be empty or just whitespace."
        
        # Validate tags is a list of strings
        if not isinstance(self.tags, list):
            errors["tags"] = "Tags must be a list of strings."
        else:
            for i, tag in enumerate(self.tags):
                if not isinstance(tag, str):
                    errors["tags"] = f"All tags must be strings. Tag at index {i} is not a string."
                    break
                if len(tag) > 100:
                    errors["tags"] = f"Tag at index {i} is too long (max 100 characters)."
                    break
                if not tag.strip():
                    errors["tags"] = f"Tag at index {i} cannot be empty or just whitespace."
                    break
        
        # Validate description length (optional, but reasonable limit)
        if len(self.description) > 10000:
            errors["description"] = "Description is too long (max 10000 characters)."
        
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"Metadata({self.contract.contract_id[:8]}...)"


class ContractSource(models.Model):
    """
    Uploaded contract source code for verification.
    """

    contract = models.ForeignKey(
        TrackedContract,
        on_delete=models.CASCADE,
        related_name="sources",
        help_text="Contract this source belongs to",
    )
    source_file = models.FileField(
        upload_to="contract_sources/",
        help_text="Uploaded source file (Rust code or tarball)",
    )
    abi_json = models.JSONField(
        null=True,
        blank=True,
        help_text="ABI JSON extracted from source or uploaded separately",
    )
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="uploaded_sources",
        help_text="User who uploaded this source",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["contract", "uploaded_at"]),
        ]

    def __str__(self):
        return f"Source for {self.contract.contract_id[:8]}... ({self.uploaded_at})"


class ContractVerification(models.Model):
    """
    Verification result for contract source against deployed bytecode.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        FAILED = "failed", "Failed"

    contract = models.OneToOneField(
        TrackedContract,
        on_delete=models.CASCADE,
        related_name="verification",
        help_text="Contract being verified",
    )
    source = models.ForeignKey(
        ContractSource,
        on_delete=models.CASCADE,
        related_name="verifications",
        help_text="Source used for verification",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        help_text="Verification status",
    )
    bytecode_hash = models.CharField(
        max_length=64,
        help_text="SHA256 hash of the deployed bytecode",
    )
    compiler_version = models.CharField(
        max_length=100,
        blank=True,
        help_text="Compiler version used to produce the bytecode",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, help_text="Error message if verification failed")

    class Meta:
        ordering = ["-verified_at"]

    def __str__(self):
        return f"Verification for {self.contract.contract_id[:8]}... ({self.status})"


# ---------------------------------------------------------------------------
# Issue #280: GDPR Data Governance Framework
# ---------------------------------------------------------------------------

class AuditLog(models.Model):
    """
    Immutable audit trail for every data mutation (create/update/delete).
    Append-only: save() blocks updates, delete() is blocked entirely.
    """

    ACTION_CREATE = "create"
    ACTION_UPDATE = "update"
    ACTION_DELETE = "delete"
    ACTION_CHOICES = [
        (ACTION_CREATE, "Create"),
        (ACTION_UPDATE, "Update"),
        (ACTION_DELETE, "Delete"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="User who performed the action (null for system actions)",
    )
    action = models.CharField(max_length=16, choices=ACTION_CHOICES, db_index=True)
    model_name = models.CharField(max_length=64, db_index=True, help_text="Django model class name")
    object_id = models.CharField(max_length=255, db_index=True)
    changes = models.JSONField(default=dict, help_text="Before/after values for mutations")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["model_name", "object_id", "timestamp"]),
            models.Index(fields=["user", "timestamp"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("AuditLog is immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("AuditLog is immutable and cannot be deleted.")

    def __str__(self):
        return f"[{self.action}] {self.model_name}:{self.object_id} by {self.user_id} @ {self.timestamp}"


class PIIField(models.Model):
    """
    Registry of fields in event payloads that contain PII.
    Used to identify data subject to GDPR deletion requests.
    """

    contract = models.ForeignKey(
        TrackedContract,
        on_delete=models.CASCADE,
        related_name="pii_fields",
        help_text="Contract whose events contain this PII field",
    )
    event_type = models.CharField(
        max_length=128,
        blank=True,
        help_text="Event type containing this field (blank = all event types)",
    )
    field_path = models.CharField(
        max_length=256,
        help_text="Dot-notation path to the PII field in the payload (e.g. 'user.email')",
    )
    description = models.CharField(max_length=256, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("contract", "event_type", "field_path")]
        ordering = ["contract", "field_path"]

    def __str__(self):
        return f"PII: {self.contract.contract_id[:8]}.../{self.event_type or '*'}/{self.field_path}"


class DataDeletionRequest(models.Model):
    """
    GDPR 'right to be forgotten' request.
    Tracks the lifecycle from submission through completion.
    """

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    requested_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deletion_requests",
        help_text="User who submitted the request",
    )
    subject_identifier = models.CharField(
        max_length=256,
        db_index=True,
        help_text="Identifier of the data subject (e.g. wallet address, user ID)",
    )
    contracts = models.ManyToManyField(
        TrackedContract,
        blank=True,
        related_name="deletion_requests",
        help_text="Contracts whose events should be scrubbed (empty = all contracts)",
    )
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    events_deleted = models.PositiveIntegerField(
        default=0,
        help_text="Number of event records deleted or scrubbed",
    )
    error_message = models.TextField(blank=True)
    requested_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["status", "requested_at"]),
        ]

    def __str__(self):
        return f"DeletionRequest({self.subject_identifier}, {self.status})"


# ---------------------------------------------------------------------------
# Issue #284: Contract Deployment & Upgrade Tracking
# ---------------------------------------------------------------------------

class ContractDeployment(models.Model):
    """
    Records each deployment or upgrade of a contract on-chain.
    A new row is created whenever a different bytecode_hash is observed
    for the same contract_id.
    """

    contract = models.ForeignKey(
        TrackedContract,
        on_delete=models.CASCADE,
        related_name="deployments",
        help_text="The tracked contract this deployment belongs to",
    )
    bytecode_hash = models.CharField(
        max_length=64,
        db_index=True,
        help_text="SHA256 hash of the deployed WASM bytecode",
    )
    ledger_deployed = models.PositiveBigIntegerField(
        db_index=True,
        help_text="Ledger sequence at which this deployment was observed",
    )
    deployer_address = models.CharField(
        max_length=56,
        blank=True,
        db_index=True,
        help_text="Stellar account that deployed/upgraded the contract",
    )
    is_upgrade = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True when this deployment replaced a previous bytecode hash",
    )
    tx_hash = models.CharField(max_length=64, blank=True, help_text="Deployment transaction hash")
    notes = models.TextField(blank=True)
    detected_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-ledger_deployed"]
        indexes = [
            models.Index(fields=["contract", "ledger_deployed"]),
            models.Index(fields=["bytecode_hash"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["contract", "bytecode_hash", "ledger_deployed"],
                name="unique_contract_bytecode_ledger",
            )
        ]

    def __str__(self):
        kind = "upgrade" if self.is_upgrade else "deploy"
        return f"{kind}@{self.ledger_deployed} ({self.contract.contract_id[:8]}...)"


class ContractABIVersion(models.Model):
    """
    Versioned ABI snapshot tied to a specific deployment.
    Stores the ledger range over which this ABI is valid so that
    historical events can be decoded with the correct ABI.
    """

    contract = models.ForeignKey(
        TrackedContract,
        on_delete=models.CASCADE,
        related_name="abi_versions",
        help_text="Contract this ABI version belongs to",
    )
    deployment = models.OneToOneField(
        ContractDeployment,
        on_delete=models.CASCADE,
        related_name="abi_version",
        null=True,
        blank=True,
        help_text="Deployment that introduced this ABI (null for manually uploaded ABIs)",
    )
    version_number = models.PositiveIntegerField(
        help_text="Monotonically increasing version counter per contract",
    )
    abi_json = models.JSONField(help_text="ABI definition for this version")
    valid_from_ledger = models.PositiveBigIntegerField(
        db_index=True,
        help_text="First ledger where this ABI applies",
    )
    valid_to_ledger = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Last ledger where this ABI applies (null = still current)",
    )
    has_breaking_changes = models.BooleanField(
        default=False,
        help_text="True if this ABI is incompatible with the previous version",
    )
    breaking_change_details = models.TextField(
        blank=True,
        help_text="Description of breaking changes detected",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version_number"]
        unique_together = [("contract", "version_number")]
        indexes = [
            models.Index(fields=["contract", "valid_from_ledger"]),
        ]

    def __str__(self):
        return f"ABI v{self.version_number} for {self.contract.contract_id[:8]}... (ledger {self.valid_from_ledger}–{self.valid_to_ledger or '∞'})"


class BlacklistedContract(models.Model):
    """
    Contracts whose events must not be indexed.

    Any contract_id present in this table is silently skipped by the
    ingestion loop, regardless of whether it also exists in
    TrackedContract.  A log entry is written each time a skip occurs
    so operators can audit the decision.
    """

    contract_id = models.CharField(
        max_length=56,
        unique=True,
        db_index=True,
        validators=[
            RegexValidator(
                regex=r"^C[A-Z2-7]{55}$",
                message="Contract address must start with 'C' and be exactly 56 characters using valid Base32 characters (A-Z, 2-7).",
            )
        ],
        help_text="Stellar contract address to block from indexing (C...)",
    )
    reason = models.TextField(
        blank=True,
        help_text="Human-readable explanation of why this contract is blacklisted",
    )
    added_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blacklisted_contracts",
        help_text="User who added this entry",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Blacklisted Contract"
        verbose_name_plural = "Blacklisted Contracts"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Blacklisted({self.contract_id[:8]}...)"
