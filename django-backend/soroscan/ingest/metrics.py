"""
Prometheus metrics for SoroScan.

Registers application-level metrics using prometheus_client.
Guards against duplicate registration so tests can import this module
multiple times without raising ``ValueError: Duplicated timeseries``.
"""
from prometheus_client import REGISTRY, Counter, Gauge, Histogram

__all__ = [
    # original
    "events_ingested_total",
    "task_duration_seconds",
    "active_contracts_gauge",
    # detailed pipeline metrics
    "ingest_errors_total",
    "events_skipped_total",
    "events_validated_total",
    "backfill_ledgers_processed_total",
    "backfill_batch_duration_seconds",
    "webhook_deliveries_total",
    "webhook_delivery_duration_seconds",
    "webhook_ack_total",
    "webhook_sla_total",
    "webhook_escalations_total",
    "webhook_deduplicated_total",
    "webhook_dead_letter_depth",
    "alert_rules_evaluated_total",
    "alert_deduplicated_total",
    "remediation_rules_evaluated_total",
    "archive_events_total",
    "ledgers_scanned_total",
    "events_rate_limited_total",
    "events_filtered_total",
    "events_validation_failures_total",
    "webhook_payload_bytes",
    "cache_hits_total",
    "cache_misses_total",
    "event_streaming_total",
    "ledger_gaps_total",
    "missing_events_total",
    "event_ingestion_rate_gauge",
    "event_payload_compression_ratio",
    "circuit_breaker_state_gauge",
    "circuit_breaker_trips_total",
    "circuit_breaker_calls_total",
]


def _get_or_create(metric_cls, name, documentation, labelnames=(), **metric_kwargs):
    """
    Return an existing collector from REGISTRY if one with *name* is already
    registered, otherwise create and register a new one.

    prometheus_client stores Counters under several derived keys:
    e.g. passing name="foo_total" registers keys "foo", "foo_total",
    "foo_created".  We strip conventional suffixes to find the base name,
    then check whether that base (or any derived key) is already registered.
    """
    # Strip conventional suffixes to get the base name prometheus_client uses.
    base_name = name
    for suffix in ("_total", "_created", "_count", "_sum", "_bucket"):
        if base_name.endswith(suffix):
            base_name = base_name[: -len(suffix)]
            break

    # If any registered key starts with our base name, the metric exists.
    for registered_name, collector in list(REGISTRY._names_to_collectors.items()):
        if registered_name == base_name or registered_name.startswith(base_name + "_"):
            return collector

    # Not found — safe to create (which auto-registers).
    if labelnames:
        return metric_cls(name, documentation, labelnames, **metric_kwargs)
    return metric_cls(name, documentation, **metric_kwargs)


# ---------------------------------------------------------------------------
# Original three metrics
# ---------------------------------------------------------------------------

events_ingested_total = _get_or_create(
    Counter,
    "soroscan_events_ingested_total",
    "Total number of contract events ingested",
    ["contract_id", "network", "event_type"],
)

task_duration_seconds = _get_or_create(
    Histogram,
    "soroscan_task_duration_seconds",
    "Duration of Celery tasks in seconds",
    ["task_name"],
)

active_contracts_gauge = _get_or_create(
    Gauge,
    "soroscan_tracked_contracts_active",
    "Number of currently active tracked contracts",
)

# ---------------------------------------------------------------------------
# Detailed pipeline metrics
# ---------------------------------------------------------------------------

ingest_errors_total = _get_or_create(
    Counter,
    "soroscan_ingest_errors_total",
    "Total number of unhandled exceptions inside ingest tasks",
    ["task_name", "error_type"],
)

events_skipped_total = _get_or_create(
    Counter,
    "soroscan_events_skipped_total",
    "Total number of events skipped during ingest (e.g. untracked contract)",
    ["contract_id", "network", "reason"],
)

events_validated_total = _get_or_create(
    Counter,
    "soroscan_events_validated_total",
    "Events that passed or failed schema validation during ingest",
    ["status", "network"],
)

backfill_ledgers_processed_total = _get_or_create(
    Counter,
    "soroscan_backfill_ledgers_processed_total",
    "Total number of ledgers processed across all backfill batches",
    ["contract_id"],
)

backfill_batch_duration_seconds = _get_or_create(
    Histogram,
    "soroscan_backfill_batch_duration_seconds",
    "Duration of a single ledger-range batch inside backfill_contract_events",
    ["contract_id"],
)

webhook_deliveries_total = _get_or_create(
    Counter,
    "soroscan_webhook_deliveries_total",
    "Total webhook delivery attempts by final status",
    ["status"],
)

webhook_delivery_duration_seconds = _get_or_create(
    Histogram,
    "soroscan_webhook_delivery_duration_seconds",
    "End-to-end latency of a single webhook delivery attempt in seconds",
)

webhook_ack_total = _get_or_create(
    Counter,
    "soroscan_webhook_ack_total",
    "Webhook acknowledgement outcomes by validation result",
    ["status"],
)

webhook_sla_total = _get_or_create(
    Counter,
    "soroscan_webhook_sla_total",
    "Webhook delivery SLA outcomes for acknowledged deliveries",
    ["outcome"],
)

webhook_escalations_total = _get_or_create(
    Counter,
    "soroscan_webhook_escalations_total",
    "Number of escalation notifications sent for webhook failures",
    ["channel", "status"],
)

webhook_deduplicated_total = _get_or_create(
    Counter,
    "soroscan_webhook_deduplicated_total",
    "Number of webhook deliveries skipped due to deduplication",
)

alert_rules_evaluated_total = _get_or_create(
    Counter,
    "soroscan_alert_rules_evaluated_total",
    "Number of alert-rule evaluations, labelled by outcome",
    ["outcome"],
)

alert_deduplicated_total = _get_or_create(
    Counter,
    "soroscan_alert_deduplicated_total",
    "Number of alert sends skipped due to deduplication",
    ["scope"],
)

remediation_rules_evaluated_total = _get_or_create(
    Counter,
    "soroscan_remediation_rules_evaluated_total",
    "Number of remediation-rule cycle outcomes",
    ["outcome"],
)

archive_events_total = _get_or_create(
    Counter,
    "soroscan_archive_events_total",
    "Events processed by the archive_old_events task",
    ["outcome"],
)

ledgers_scanned_total = _get_or_create(
    Counter,
    "soroscan_ledgers_scanned_total",
    "Total ledger sequences visited during sync polling",
    ["network"],
)



events_rate_limited_total = _get_or_create(
    Counter,
    "soroscan_events_rate_limited_total",
    "Total number of events skipped due to rate limiting",
    ["contract_id", "network"],
)

events_filtered_total = _get_or_create(
    Counter,
    "soroscan_events_filtered_total",
    "Total number of events dropped by whitelist/blacklist filter",
    ["contract_id", "network", "filter_type", "event_type"],
)

events_validation_failures_total = _get_or_create(
    Counter,
    "soroscan_events_validation_failures_total",
    "Total number of ingest events dropped due to contract-level JSON schema validation failures",
    ["contract_id", "network"],
)

webhook_payload_bytes = _get_or_create(
    Histogram,
    "soroscan_webhook_payload_bytes",
    "Size of webhook payload in bytes",
    ["contract_id"],
)

webhook_dead_letter_depth = _get_or_create(
    Gauge,
    "soroscan_webhook_dead_letter_depth",
    "Current number of unresolved webhook dead-letter entries",
)

cache_hits_total = _get_or_create(
    Counter,
    "soroscan_cache_hits_total",
    "Total number of cache hits",
    ["cache_type"],
)

cache_misses_total = _get_or_create(
    Counter,
    "soroscan_cache_misses_total",
    "Total number of cache misses",
    ["cache_type"],
)

event_streaming_total = _get_or_create(
    Counter,
    "soroscan_event_streaming_total",
    "Total number of event streaming attempts by status and backend",
    ["status", "backend"],
)

ledger_gaps_total = _get_or_create(
    Counter,
    "soroscan_ledger_gaps_total",
    "Total number of detected ledger-gap ranges",
    ["contract_id"],
)

missing_events_total = _get_or_create(
    Counter,
    "soroscan_missing_events_total",
    "Total number of missing ledgers/events detected by reconciliation",
    ["contract_id"],
)

event_ingestion_rate_gauge = _get_or_create(
    Gauge,
    "soroscan_event_ingestion_rate",
    "Current event ingestion rate in events per second",
)

event_payload_compression_ratio = _get_or_create(
    Histogram,
    "soroscan_event_payload_compression_ratio",
    "Observed compressed-to-raw size ratio for stored event payloads",
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.25, 1.5),
circuit_breaker_state_gauge = _get_or_create(
    Gauge,
    "soroscan_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=half_open, 2=open)",
    ["name"],
)

circuit_breaker_trips_total = _get_or_create(
    Counter,
    "soroscan_circuit_breaker_trips_total",
    "Number of times a circuit breaker opened",
    ["name"],
)

circuit_breaker_calls_total = _get_or_create(
    Counter,
    "soroscan_circuit_breaker_calls_total",
    "Circuit breaker protected call outcomes",
    ["name", "outcome"],
)
