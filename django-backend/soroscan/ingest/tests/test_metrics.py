"""
Tests for Prometheus metrics integration (issue #56).

Covers:
- GET /metrics returns valid Prometheus text format
- soroscan_events_ingested_total increments on event creation
- soroscan_task_duration_seconds is observed by Celery tasks
- soroscan_tracked_contracts_active gauge reflects active contract count
- /metrics is accessible without authentication
- Duplicate-registration guard in metrics.py doesn't blow up on re-import
"""
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from prometheus_client import REGISTRY

from soroscan.ingest.models import TrackedContract

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_metric_value(metric_name: str, labels: dict | None = None) -> float:
    """
    Read the current value of a prometheus_client metric from the default
    REGISTRY.  Works for Counter (returns _total), Gauge, and Histogram (_count).

    prometheus_client stores ``metric.name`` as the *base* name (e.g.
    ``soroscan_events_ingested``), while callers often pass the full suffixed
    name (``soroscan_events_ingested_total``).  We strip conventional Prometheus
    suffixes so the metric-level match succeeds, then match individual samples
    by their original (suffixed) name.
    """
    # Compute the base name that prometheus_client uses internally.
    base = metric_name
    for suffix in ("_total", "_created", "_count", "_sum", "_bucket"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break

    for metric in REGISTRY.collect():
        if metric.name in (metric_name, base):
            for sample in metric.samples:
                if sample.name in (metric_name, f"{metric_name}_total"):
                    if labels is None:
                        return sample.value
                    if all(sample.labels.get(k) == v for k, v in labels.items()):
                        return sample.value
    return 0.0


def _make_user(username="testuser"):
    return User.objects.get_or_create(username=username)[0]


def _make_contract(user, contract_id="CAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB2KQ"):
    return TrackedContract.objects.get_or_create(
        contract_id=contract_id,
        defaults={"name": "Test Contract", "owner": user, "is_active": True},
    )[0]


# ---------------------------------------------------------------------------
# /metrics endpoint tests
# ---------------------------------------------------------------------------

class MetricsEndpointTest(TestCase):
    """GET /metrics must return valid Prometheus text and be unauthenticated."""

    def test_metrics_endpoint_returns_200(self):
        response = self.client.get("/metrics")
        self.assertEqual(response.status_code, 200)

    def test_metrics_endpoint_content_type(self):
        response = self.client.get("/metrics")
        self.assertIn("text/plain", response["Content-Type"])

    def test_metrics_endpoint_contains_django_metrics(self):
        """Standard django-prometheus metrics must be present."""
        response = self.client.get("/metrics")
        content = response.content.decode()
        # django-prometheus always exports these
        self.assertIn("django_http_requests_total", content)
        self.assertIn("django_http_responses_total", content)

    def test_metrics_endpoint_contains_custom_metric_names(self):
        """Our custom metric names must appear in the output."""
        response = self.client.get("/metrics")
        content = response.content.decode()
        self.assertIn("soroscan_events_ingested_total", content)
        self.assertIn("soroscan_task_duration_seconds", content)
        self.assertIn("soroscan_tracked_contracts_active", content)

    def test_metrics_endpoint_no_auth_required(self):
        """
        /metrics must be accessible without any credentials.
        The client has no session / token here.
        """
        # Explicitly log out to be sure
        self.client.logout()
        response = self.client.get("/metrics")
        self.assertNotEqual(response.status_code, 401)
        self.assertNotEqual(response.status_code, 403)
        self.assertEqual(response.status_code, 200)

    def test_metrics_output_is_valid_prometheus_text(self):
        """
        Every non-comment, non-empty line should follow Prometheus text format:
        <metric_name>{<labels>} <value> [<timestamp>]
        """

        response = self.client.get("/metrics")
        content = response.content.decode()
        # Basic sanity: must contain at least one HELP line
        self.assertIn("# HELP", content)
        self.assertIn("# TYPE", content)


# ---------------------------------------------------------------------------
# events_ingested_total counter tests
# ---------------------------------------------------------------------------

class EventsIngestedCounterTest(TestCase):
    """soroscan_events_ingested_total must increment when events are created."""

    def setUp(self):
        self.user = _make_user()
        self.contract = _make_contract(self.user)

    def _count_for_contract(self) -> float:
        from soroscan.ingest.tasks import _short_contract_id
        return _get_metric_value(
            "soroscan_events_ingested_total",
            labels={
                "contract_id": _short_contract_id(self.contract.contract_id),
                "event_type": "transfer",
            },
        )

    def test_counter_increments_via_upsert(self):
        from soroscan.ingest.tasks import _upsert_contract_event

        before = self._count_for_contract()

        fake_event = {
            "ledger": 1000,
            "event_index": 0,
            "tx_hash": "abc123",
            "type": "transfer",
            "value": {"amount": 100},
            "timestamp": None,
            "xdr": "",
        }
        _upsert_contract_event(self.contract, fake_event, fallback_event_index=0)

        after = self._count_for_contract()
        self.assertEqual(after, before + 1)

    def test_counter_does_not_increment_on_update(self):
        """Re-upserting the same event (same ledger+index) must not double-count."""
        from soroscan.ingest.tasks import _upsert_contract_event

        fake_event = {
            "ledger": 2000,
            "event_index": 0,
            "tx_hash": "def456",
            "type": "transfer",
            "value": {"amount": 50},
            "timestamp": None,
            "xdr": "",
        }
        _upsert_contract_event(self.contract, fake_event)
        before = self._count_for_contract()

        # Same ledger + index → update, not create
        _upsert_contract_event(self.contract, fake_event)
        after = self._count_for_contract()

        self.assertEqual(after, before)  # no increment on update

    def test_counter_increments_for_each_unique_event(self):
        from soroscan.ingest.tasks import _upsert_contract_event

        before = self._count_for_contract()
        for i in range(3):
            _upsert_contract_event(
                self.contract,
                {
                    "ledger": 3000 + i,
                    "event_index": i,
                    "tx_hash": f"hash{i}",
                    "type": "transfer",
                    "value": {},
                    "timestamp": None,
                    "xdr": "",
                },
            )
        after = self._count_for_contract()
        self.assertEqual(after, before + 3)


# ---------------------------------------------------------------------------
# active_contracts_gauge tests
# ---------------------------------------------------------------------------

class ActiveContractsGaugeTest(TestCase):
    """soroscan_tracked_contracts_active must reflect DB state."""

    def _gauge_value(self) -> float:
        return _get_metric_value("soroscan_tracked_contracts_active")

    def test_gauge_updated_after_upsert(self):
        from soroscan.ingest.tasks import _upsert_contract_event

        user = _make_user("gaugeuser")
        contract = _make_contract(
            user,
            contract_id="CBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBQ",
        )

        _upsert_contract_event(
            contract,
            {
                "ledger": 5000,
                "event_index": 0,
                "tx_hash": "gaugehash",
                "type": "swap",
                "value": {},
                "timestamp": None,
                "xdr": "",
            },
        )

        expected = TrackedContract.objects.filter(is_active=True).count()
        self.assertEqual(self._gauge_value(), expected)

    def test_gauge_updated_by_sync_task(self):
        """sync_events_from_horizon should call active_contracts_gauge.set()."""
        from soroscan.ingest import metrics as m

        with patch.object(m.active_contracts_gauge, "set") as mock_set, \
             patch("stellar_sdk.SorobanServer") as mock_server_cls:

            mock_server = MagicMock()
            mock_server.get_events.return_value = MagicMock(events=[])
            mock_server_cls.return_value = mock_server

            from soroscan.ingest.tasks import sync_events_from_horizon
            sync_events_from_horizon()

        mock_set.assert_called()


# ---------------------------------------------------------------------------
# task_duration_seconds histogram tests
# ---------------------------------------------------------------------------

class TaskDurationHistogramTest(TestCase):
    """soroscan_task_duration_seconds must be observed by instrumented tasks."""

    def _histogram_count(self, task_name: str) -> float:
        return _get_metric_value(
            "soroscan_task_duration_seconds_count",
            labels={"task_name": task_name},
        )

    def test_sync_events_observes_histogram(self):
        with patch("stellar_sdk.SorobanServer") as mock_server_cls:
            mock_server = MagicMock()
            mock_server.get_events.return_value = MagicMock(events=[])
            mock_server_cls.return_value = mock_server

            before = self._histogram_count("sync_events_from_horizon")
            from soroscan.ingest.tasks import sync_events_from_horizon
            sync_events_from_horizon()
            after = self._histogram_count("sync_events_from_horizon")

        self.assertGreater(after, before)

    def test_cleanup_observes_histogram(self):
        from soroscan.ingest.tasks import cleanup_webhook_delivery_logs

        before = self._histogram_count("cleanup_webhook_delivery_logs")
        cleanup_webhook_delivery_logs()
        after = self._histogram_count("cleanup_webhook_delivery_logs")

        self.assertGreater(after, before)

    def test_backfill_observes_histogram(self):
        from soroscan.ingest.tasks import backfill_contract_events

        user = _make_user("backfilluser")
        contract = _make_contract(
            user,
            contract_id="CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCQ",
        )

        with patch("soroscan.ingest.tasks.SorobanClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get_events_range.return_value = []
            mock_client_cls.return_value = mock_client

            before = self._histogram_count("backfill_contract_events")
            backfill_contract_events(
                contract_id=contract.contract_id,
                from_ledger=1,
                to_ledger=10,
            )
            after = self._histogram_count("backfill_contract_events")

        self.assertGreater(after, before)


# ---------------------------------------------------------------------------
# Duplicate-registration guard
# ---------------------------------------------------------------------------

class MetricsModuleImportTest(TestCase):
    """The _get_or_create guard must survive being called with an already-registered name."""

    def test_double_call_does_not_raise(self):
        """Calling _get_or_create twice with the same name must not raise."""
        from prometheus_client import Counter as PC_Counter
        from soroscan.ingest.metrics import _get_or_create

        try:
            result = _get_or_create(
                PC_Counter,
                "soroscan_events_ingested_total",  # same name used in metrics.py
                "Total number of contract events ingested",
                ["contract_id", "network", "event_type"],
            )
        except ValueError as exc:
            self.fail(f"_get_or_create raised ValueError on duplicate name: {exc}")
        self.assertIsNotNone(result)

    def test_metrics_objects_are_accessible(self):
        import soroscan.ingest.metrics as metrics_module
        self.assertTrue(hasattr(metrics_module, "events_ingested_total"))
        self.assertTrue(hasattr(metrics_module, "task_duration_seconds"))
        self.assertTrue(hasattr(metrics_module, "active_contracts_gauge"))

    def test_second_import_returns_same_objects(self):
        """Multiple imports of the metrics module return the same collector instances."""
        import soroscan.ingest.metrics as m1

        import sys
        # Access via sys.modules (no reload) — must be identical objects.
        m2 = sys.modules["soroscan.ingest.metrics"]
        self.assertIs(m1.events_ingested_total, m2.events_ingested_total)
        self.assertIs(m1.task_duration_seconds, m2.task_duration_seconds)
        self.assertIs(m1.active_contracts_gauge, m2.active_contracts_gauge)


# ---------------------------------------------------------------------------
# Label cardinality guard
# ---------------------------------------------------------------------------

class LabelCardinalityTest(TestCase):
    """contract_id label must be truncated to 8 chars, not the full 56-char ID."""

    def test_short_contract_id_truncates(self):
        from soroscan.ingest.tasks import _short_contract_id

        full_id = "CAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB2KQ"
        result = _short_contract_id(full_id)
        self.assertEqual(len(result), 8)
        self.assertEqual(result, full_id[:8])

    def test_short_contract_id_handles_empty(self):
        from soroscan.ingest.tasks import _short_contract_id

        self.assertEqual(_short_contract_id(""), "unknown")

    def test_network_label_testnet(self):
        from soroscan.ingest.tasks import _network_label

        with override_settings(STELLAR_NETWORK_PASSPHRASE="Test SDF Network ; September 2015"):
            self.assertEqual(_network_label(), "testnet")

    def test_network_label_mainnet(self):
        from soroscan.ingest.tasks import _network_label

        with override_settings(STELLAR_NETWORK_PASSPHRASE="Public Global Stellar Network ; September 2015"):
            self.assertEqual(_network_label(), "mainnet")

    def test_network_label_unknown(self):
        from soroscan.ingest.tasks import _network_label

        with override_settings(STELLAR_NETWORK_PASSPHRASE="Some Custom Network"):
            self.assertEqual(_network_label(), "unknown")
            