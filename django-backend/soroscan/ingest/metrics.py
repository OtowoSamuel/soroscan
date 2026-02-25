"""
Prometheus metrics for SoroScan.

Registers application-level metrics using prometheus_client.
Guards against duplicate registration so tests can import this module
multiple times without raising ``ValueError: Duplicated timeseries``.
"""
from prometheus_client import REGISTRY, Counter, Gauge, Histogram

__all__ = [
    "events_ingested_total",
    "task_duration_seconds",
    "active_contracts_gauge",
]


def _get_or_create(metric_cls, name, documentation, labelnames=()):
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
        return metric_cls(name, documentation, labelnames)
    return metric_cls(name, documentation)


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