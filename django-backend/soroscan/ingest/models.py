"""
Database models for SoroScan event indexing.
"""
import hashlib
import secrets

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models

User = get_user_model()


class TrackedContract(models.Model):
    """
    Contracts registered for event indexing.
    """

    contract_id = models.CharField(
        max_length=56,
        unique=True,
        db_index=True,
        help_text="Stellar contract address (C...)",
    )
    name = models.CharField(max_length=100, help_text="Human-readable contract name")
    description = models.TextField(blank=True, help_text="Optional description")
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="tracked_contracts",
        help_text="User who registered this contract",
    )
    abi_schema = models.JSONField(
        null=True,
        blank=True,
        help_text="Optional ABI/schema for decoding events",
    )
    last_indexed_ledger = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Last ledger sequence that was indexed for this contract",
    )
    is_active = models.BooleanField(default=True, help_text="Whether indexing is active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["contract_id", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.contract_id[:8]}...)"


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

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Webhook -> {self.target_url} ({self.contract.name})"

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

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["subscription", "timestamp"]),
        ]

    def __str__(self):
        status_label = "OK" if self.success else f"FAIL({self.status_code})"
        return f"Delivery #{self.attempt_number} [{status_label}] sub={self.subscription_id}"


class IndexerState(models.Model):
    """
    Tracks the current indexing state (cursor position).
    """

    key = models.CharField(max_length=50, unique=True, primary_key=True)
    value = models.CharField(max_length=200)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.key}: {self.value}"


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
    action_type = models.CharField(
        max_length=16,
        choices=[
            ("slack", "Slack"),
            ("email", "Email"),
            ("webhook", "Webhook"),
        ],
    )
    action_target = models.TextField(
        help_text="Slack channel, email address, or webhook URL"
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
