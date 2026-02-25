"""
Tests for the new features:
  - Tiered rate limiting (APIKey, ContractQuota, APIKeyThrottle)
  - Event-driven alerts (AlertRule, AlertExecution, evaluate_condition, send_alert)
  - Full-text search (/events/search/, GraphQL search_events)
  - Performance monitoring (SlowQueryMiddleware, Celery signal profiling)
"""
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase, override_settings
from rest_framework.test import APIClient, APIRequestFactory

from soroscan.ingest.models import (
    APIKey,
    AlertExecution,
    AlertRule,
    ContractEvent,
    ContractQuota,
    TrackedContract,
)
from soroscan.ingest.tasks import evaluate_condition

User = get_user_model()


# ---------------------------------------------------------------------------
# evaluate_condition  (pure-logic, no DB needed)
# ---------------------------------------------------------------------------

class EvaluateConditionTests(TestCase):
    """Tests for the evaluate_condition JSON condition AST engine."""

    def test_eq(self):
        c = {"op": "eq", "field": "event_type", "value": "transfer"}
        self.assertTrue(evaluate_condition(c, {"event_type": "transfer"}))
        self.assertFalse(evaluate_condition(c, {"event_type": "swap"}))

    def test_neq(self):
        c = {"op": "neq", "field": "event_type", "value": "transfer"}
        self.assertTrue(evaluate_condition(c, {"event_type": "swap"}))
        self.assertFalse(evaluate_condition(c, {"event_type": "transfer"}))

    def test_gt_lt(self):
        self.assertTrue(evaluate_condition(
            {"op": "gt", "field": "ledger", "value": "5"},
            {"ledger": 10},
        ))
        self.assertFalse(evaluate_condition(
            {"op": "lt", "field": "ledger", "value": "5"},
            {"ledger": 10},
        ))

    def test_gte_lte(self):
        self.assertTrue(evaluate_condition(
            {"op": "gte", "field": "ledger", "value": "10"},
            {"ledger": 10},
        ))
        self.assertTrue(evaluate_condition(
            {"op": "lte", "field": "ledger", "value": "10"},
            {"ledger": 10},
        ))

    def test_contains(self):
        c = {"op": "contains", "field": "payload.to", "value": "abc"}
        self.assertTrue(evaluate_condition(c, {"payload": {"to": "xabcdef"}}))
        self.assertFalse(evaluate_condition(c, {"payload": {"to": "xyz"}}))

    def test_startswith(self):
        c = {"op": "startswith", "field": "payload.to", "value": "G"}
        self.assertTrue(evaluate_condition(c, {"payload": {"to": "GBQ1234"}}))
        self.assertFalse(evaluate_condition(c, {"payload": {"to": "xyzG"}}))

    def test_in_operator(self):
        c = {"op": "in", "field": "event_type", "value": ["swap", "transfer"]}
        self.assertTrue(evaluate_condition(c, {"event_type": "swap"}))
        self.assertFalse(evaluate_condition(c, {"event_type": "mint"}))

    def test_and(self):
        c = {
            "op": "and",
            "conditions": [
                {"op": "eq", "field": "event_type", "value": "transfer"},
                {"op": "gt", "field": "ledger", "value": "5"},
            ],
        }
        self.assertTrue(evaluate_condition(c, {"event_type": "transfer", "ledger": 10}))
        self.assertFalse(evaluate_condition(c, {"event_type": "transfer", "ledger": 3}))

    def test_or(self):
        c = {
            "op": "or",
            "conditions": [
                {"op": "eq", "field": "event_type", "value": "swap"},
                {"op": "eq", "field": "event_type", "value": "transfer"},
            ],
        }
        self.assertTrue(evaluate_condition(c, {"event_type": "swap"}))
        self.assertTrue(evaluate_condition(c, {"event_type": "transfer"}))
        self.assertFalse(evaluate_condition(c, {"event_type": "mint"}))

    def test_not(self):
        c = {"op": "not", "condition": {"op": "eq", "field": "event_type", "value": "swap"}}
        self.assertTrue(evaluate_condition(c, {"event_type": "transfer"}))
        self.assertFalse(evaluate_condition(c, {"event_type": "swap"}))

    def test_unknown_op(self):
        c = {"op": "unknown_op", "field": "event_type", "value": "x"}
        self.assertFalse(evaluate_condition(c, {"event_type": "x"}))

    def test_numeric_comparison_non_numeric(self):
        c = {"op": "gt", "field": "event_type", "value": "5"}
        # "transfer" is not numeric → False
        self.assertFalse(evaluate_condition(c, {"event_type": "transfer"}))

    def test_nested_dotted_path(self):
        c = {"op": "eq", "field": "payload.nested.deep", "value": "42"}
        self.assertTrue(evaluate_condition(c, {"payload": {"nested": {"deep": "42"}}}))
        self.assertFalse(evaluate_condition(c, {"payload": {"nested": {"deep": "99"}}}))

    def test_missing_field_eq(self):
        c = {"op": "eq", "field": "missing_field", "value": "None"}
        self.assertTrue(evaluate_condition(c, {}))

    def test_contains_none_field(self):
        c = {"op": "contains", "field": "missing", "value": "abc"}
        self.assertFalse(evaluate_condition(c, {}))

    def test_startswith_none_field(self):
        c = {"op": "startswith", "field": "missing", "value": "G"}
        self.assertFalse(evaluate_condition(c, {}))


# ---------------------------------------------------------------------------
# APIKey / ContractQuota model tests
# ---------------------------------------------------------------------------

class APIKeyModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pass")

    def test_key_auto_generated(self):
        key = APIKey(user=self.user, name="Test", tier="free")
        key.save()
        self.assertTrue(len(key.key) >= 32)

    def test_free_tier_default_quota(self):
        key = APIKey(user=self.user, name="Test", tier="free")
        key.save()
        self.assertEqual(key.quota_per_hour, 50)

    def test_pro_tier_quota(self):
        key = APIKey(user=self.user, name="Pro", tier="pro")
        key.save()
        self.assertEqual(key.quota_per_hour, 5000)

    def test_enterprise_tier_quota(self):
        key = APIKey(user=self.user, name="Ent", tier="enterprise")
        key.save()
        self.assertEqual(key.quota_per_hour, APIKey.UNLIMITED_QUOTA)

    def test_str(self):
        key = APIKey(user=self.user, name="Test", tier="free")
        key.save()
        self.assertIn("Test", str(key))
        self.assertIn("free", str(key))


class ContractQuotaModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pass")
        self.contract = TrackedContract.objects.create(
            contract_id="C" * 56,
            name="TestContract",
            owner=self.user,
        )
        self.api_key = APIKey(user=self.user, name="Free", tier="free")
        self.api_key.save()

    def test_valid_quota(self):
        cq = ContractQuota(contract=self.contract, api_key=self.api_key, quota_per_hour=30)
        cq.clean()  # Should not raise

    def test_quota_exceeds_tier_limit_raises(self):
        cq = ContractQuota(contract=self.contract, api_key=self.api_key, quota_per_hour=9999)
        with self.assertRaises(ValidationError):
            cq.clean()

    def test_enterprise_no_limit(self):
        ent_key = APIKey(user=self.user, name="Ent", tier="enterprise")
        ent_key.save()
        cq = ContractQuota(contract=self.contract, api_key=ent_key, quota_per_hour=999999)
        cq.clean()  # Should not raise

    def test_str(self):
        cq = ContractQuota(contract=self.contract, api_key=self.api_key, quota_per_hour=30)
        cq.save()
        self.assertIn("TestContract", str(cq))


# ---------------------------------------------------------------------------
# AlertRule / AlertExecution model tests
# ---------------------------------------------------------------------------

class AlertRuleModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pass")
        self.contract = TrackedContract.objects.create(
            contract_id="A" * 56,
            name="AlertContract",
            owner=self.user,
        )

    def test_create_alertrule(self):
        rule = AlertRule.objects.create(
            contract=self.contract,
            name="Big Transfer",
            condition={"op": "gt", "field": "payload.amount", "value": "1000"},
            action_type="slack",
            action_target="https://hooks.slack.com/x",
        )
        self.assertTrue(rule.is_active)
        self.assertIn("Big Transfer", str(rule))

    def test_create_alertexecution(self):
        rule = AlertRule.objects.create(
            contract=self.contract,
            name="Rule1",
            condition={"op": "eq", "field": "event_type", "value": "swap"},
            action_type="email",
            action_target="admin@example.com",
        )
        event = ContractEvent.objects.create(
            contract=self.contract,
            event_type="swap",
            payload={"amount": 100},
            ledger=1000,
            tx_hash="abc123",
            timestamp="2024-01-01T00:00:00Z",
        )
        exe = AlertExecution.objects.create(rule=rule, event=event, status="sent", response="ok")
        self.assertEqual(exe.status, "sent")
        self.assertIn("sent", str(exe))


# ---------------------------------------------------------------------------
# APIKeyThrottle tests
# ---------------------------------------------------------------------------

class APIKeyThrottleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="throttleuser", password="pass")
        self.api_key = APIKey(user=self.user, name="Throttle", tier="free")
        self.api_key.save()
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_allow_without_api_key(self):
        from soroscan.throttles import APIKeyThrottle

        throttle = APIKeyThrottle()
        factory = APIRequestFactory()
        request = factory.get("/api/ingest/events/")
        request.user = self.user
        self.assertTrue(throttle.allow_request(request, MagicMock()))

    def test_reject_invalid_key(self):
        from soroscan.throttles import APIKeyThrottle

        throttle = APIKeyThrottle()
        factory = APIRequestFactory()
        request = factory.get("/api/ingest/events/", HTTP_AUTHORIZATION="ApiKey BADKEY")
        request.user = self.user
        self.assertFalse(throttle.allow_request(request, MagicMock()))

    def test_allow_valid_key(self):
        from soroscan.throttles import APIKeyThrottle

        throttle = APIKeyThrottle()
        factory = APIRequestFactory()
        request = factory.get(
            "/api/ingest/events/",
            HTTP_AUTHORIZATION=f"ApiKey {self.api_key.key}",
        )
        request.user = self.user
        view = MagicMock()
        view.kwargs = {}
        self.assertTrue(throttle.allow_request(request, view))

    def test_headers_set_on_valid_key(self):
        from soroscan.throttles import APIKeyThrottle

        throttle = APIKeyThrottle()
        factory = APIRequestFactory()
        request = factory.get(
            "/api/ingest/events/",
            HTTP_AUTHORIZATION=f"ApiKey {self.api_key.key}",
        )
        request.user = self.user
        view = MagicMock()
        view.kwargs = {}
        throttle.allow_request(request, view)
        headers = getattr(request, "_api_key_throttle_headers", {})
        self.assertIn("X-RateLimit-Limit", headers)
        self.assertIn("X-RateLimit-Remaining", headers)
        self.assertIn("X-RateLimit-Reset", headers)

    def test_key_from_query_param(self):
        from soroscan.throttles import APIKeyThrottle

        throttle = APIKeyThrottle()
        factory = APIRequestFactory()
        request = factory.get(f"/api/ingest/events/?api_key={self.api_key.key}")
        request.user = self.user
        view = MagicMock()
        view.kwargs = {}
        self.assertTrue(throttle.allow_request(request, view))

    def test_wait(self):
        from soroscan.throttles import APIKeyThrottle

        throttle = APIKeyThrottle()
        wait_seconds = throttle.wait()
        self.assertGreaterEqual(wait_seconds, 0.0)
        self.assertLessEqual(wait_seconds, 3600)


# ---------------------------------------------------------------------------
# SlowQueryMiddleware tests
# ---------------------------------------------------------------------------

class SlowQueryMiddlewareTests(TestCase):
    def test_middleware_initialises(self):
        from soroscan.middleware import SlowQueryMiddleware

        mw = SlowQueryMiddleware(lambda r: MagicMock())
        self.assertEqual(mw.threshold_ms, 100)

    @override_settings(LOGGING_SLOW_QUERIES_THRESHOLD_MS=500)
    def test_custom_threshold(self):
        from soroscan.middleware import SlowQueryMiddleware

        mw = SlowQueryMiddleware(lambda r: MagicMock())
        self.assertEqual(mw.threshold_ms, 500)

    def test_forwards_rate_limit_headers(self):
        from soroscan.middleware import SlowQueryMiddleware

        inner_response = {}

        def get_response(req):
            return inner_response

        mw = SlowQueryMiddleware(get_response)
        request = RequestFactory().get("/")
        request._api_key_throttle_headers = {
            "X-RateLimit-Limit": "50",
            "X-RateLimit-Remaining": "49",
            "X-RateLimit-Reset": "3600",
        }
        response = mw(request)
        self.assertEqual(response.get("X-RateLimit-Limit"), "50")


# ---------------------------------------------------------------------------
# APIKeyViewSet tests
# ---------------------------------------------------------------------------

class APIKeyViewSetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="apikeyuser", password="pass")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_create_api_key(self):
        resp = self.client.post(
            "/api/ingest/api-keys/",
            data={"name": "MyKey", "tier": "free"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertIn("key", resp.data)
        self.assertTrue(len(resp.data["key"]) >= 32)

    def test_list_api_keys(self):
        APIKey(user=self.user, name="K1", tier="free").save()
        resp = self.client.get("/api/ingest/api-keys/")
        self.assertEqual(resp.status_code, 200)
        # Response may be paginated (list or dict with 'results')
        if isinstance(resp.data, list):
            self.assertGreaterEqual(len(resp.data), 1)
        else:
            self.assertGreaterEqual(len(resp.data.get("results", resp.data)), 1)

    def test_delete_revokes_key(self):
        k = APIKey(user=self.user, name="K1", tier="free")
        k.save()
        resp = self.client.delete(f"/api/ingest/api-keys/{k.id}/")
        self.assertEqual(resp.status_code, 204)
        k.refresh_from_db()
        self.assertFalse(k.is_active)


# ---------------------------------------------------------------------------
# Full-text search tests
# ---------------------------------------------------------------------------

class EventSearchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="searcher", password="pass")
        self.contract = TrackedContract.objects.create(
            contract_id="S" * 56,
            name="SearchContract",
            owner=self.user,
        )
        ContractEvent.objects.create(
            contract=self.contract,
            event_type="transfer",
            payload={"from": "alice", "to": "bob", "amount": 100},
            ledger=1000,
            tx_hash="tx1",
            timestamp="2024-01-01T00:00:00Z",
        )
        ContractEvent.objects.create(
            contract=self.contract,
            event_type="swap",
            payload={"from": "charlie", "to": "dave", "amount": 50},
            ledger=1001,
            tx_hash="tx2",
            timestamp="2024-01-02T00:00:00Z",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_search_no_params(self):
        resp = self.client.get("/api/ingest/events/search/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 2)

    def test_search_by_event_type(self):
        resp = self.client.get("/api/ingest/events/search/?event_type=transfer")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 1)

    def test_search_by_contract_id(self):
        resp = self.client.get(f"/api/ingest/events/search/?contract_id={'S' * 56}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 2)

    def test_search_by_q(self):
        resp = self.client.get("/api/ingest/events/search/?q=alice")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.data["count"], 1)

    def test_search_pagination(self):
        resp = self.client.get("/api/ingest/events/search/?page=1&page_size=1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["results"]), 1)
        self.assertEqual(resp.data["count"], 2)

    def test_search_payload_contains(self):
        resp = self.client.get("/api/ingest/events/search/?payload_contains=bob")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.data["count"], 1)

    def test_search_invalid_page(self):
        resp = self.client.get("/api/ingest/events/search/?page=notanumber")
        self.assertEqual(resp.status_code, 200)
        # Falls back to page=1
        self.assertEqual(resp.data["page"], 1)


# ---------------------------------------------------------------------------
# send_alert / evaluate_alert_rules tests
# ---------------------------------------------------------------------------

class SendAlertTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alertuser", password="pass")
        self.contract = TrackedContract.objects.create(
            contract_id="B" * 56,
            name="AlertC",
            owner=self.user,
        )
        self.event = ContractEvent.objects.create(
            contract=self.contract,
            event_type="transfer",
            payload={"amount": 500},
            ledger=100,
            tx_hash="hash1",
            timestamp="2024-06-01T00:00:00Z",
        )
        self.rule = AlertRule.objects.create(
            contract=self.contract,
            name="BigTx",
            condition={"op": "gt", "field": "payload.amount", "value": "100"},
            action_type="webhook",
            action_target="https://example.com/hook",
        )

    @patch("soroscan.ingest.tasks._send_webhook_alert")
    def test_send_alert_webhook(self, mock_webhook):
        from soroscan.ingest.tasks import send_alert

        result = send_alert(self.rule.id, self.event.id)
        self.assertEqual(result, "sent")
        mock_webhook.assert_called_once()
        self.assertEqual(AlertExecution.objects.count(), 1)
        self.assertEqual(AlertExecution.objects.first().status, "sent")

    @patch("soroscan.ingest.tasks._send_slack_alert")
    def test_send_alert_slack(self, mock_slack):
        from soroscan.ingest.tasks import send_alert

        self.rule.action_type = "slack"
        self.rule.save()
        result = send_alert(self.rule.id, self.event.id)
        self.assertEqual(result, "sent")
        mock_slack.assert_called_once()

    @patch("soroscan.ingest.tasks._send_email_alert")
    def test_send_alert_email(self, mock_email):
        from soroscan.ingest.tasks import send_alert

        self.rule.action_type = "email"
        self.rule.action_target = "admin@example.com"
        self.rule.save()
        result = send_alert(self.rule.id, self.event.id)
        self.assertEqual(result, "sent")
        mock_email.assert_called_once()

    def test_send_alert_rule_not_found(self):
        from soroscan.ingest.tasks import send_alert

        result = send_alert(9999, self.event.id)
        self.assertEqual(result, "skipped:rule_gone")

    def test_send_alert_event_not_found(self):
        from soroscan.ingest.tasks import send_alert

        result = send_alert(self.rule.id, 9999)
        self.assertEqual(result, "skipped:event_gone")


class EvaluateAlertRulesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="evaluser", password="pass")
        self.contract = TrackedContract.objects.create(
            contract_id="E" * 56,
            name="EvalContract",
            owner=self.user,
        )
        self.event = ContractEvent.objects.create(
            contract=self.contract,
            event_type="transfer",
            payload={"amount": 500},
            ledger=100,
            tx_hash="h1",
            timestamp="2024-06-01T00:00:00Z",
        )
        # Rule that should match
        AlertRule.objects.create(
            contract=self.contract,
            name="MatchRule",
            condition={"op": "eq", "field": "event_type", "value": "transfer"},
            action_type="webhook",
            action_target="https://example.com/hook",
        )
        # Inactive rule (should not match)
        AlertRule.objects.create(
            contract=self.contract,
            name="Inactive",
            condition={"op": "eq", "field": "event_type", "value": "transfer"},
            action_type="webhook",
            action_target="https://example.com/hook2",
            is_active=False,
        )

    @patch("soroscan.ingest.tasks.send_alert")
    def test_evaluate_dispatches_matching(self, mock_send):
        mock_send.apply_async = MagicMock()
        from soroscan.ingest.tasks import evaluate_alert_rules

        matched = evaluate_alert_rules(self.event.id)
        self.assertEqual(matched, 1)
        mock_send.apply_async.assert_called_once()

    def test_evaluate_missing_event(self):
        from soroscan.ingest.tasks import evaluate_alert_rules

        matched = evaluate_alert_rules(999999)
        self.assertEqual(matched, 0)


# ---------------------------------------------------------------------------
# Celery signal profiling setup tests
# ---------------------------------------------------------------------------

class CeleryProfilingSignalTests(TestCase):
    def test_profiler_dict_exists(self):
        from soroscan.ingest.tasks import _task_profilers

        self.assertIsInstance(_task_profilers, dict)

    @patch("soroscan.ingest.tasks.cProfile")
    def test_start_profiling_creates_entry(self, mock_cprofile):
        from soroscan.ingest.tasks import _start_task_profiling, _task_profilers

        mock_profiler = MagicMock()
        mock_cprofile.Profile.return_value = mock_profiler
        _start_task_profiling(task_id="test-123", task=MagicMock())
        self.assertIn("test-123", _task_profilers)
        mock_profiler.enable.assert_called_once()
        _task_profilers.pop("test-123", None)  # cleanup

    @patch("soroscan.ingest.tasks.cProfile")
    def test_stop_profiling_removes_entry(self, mock_cprofile):
        from soroscan.ingest.tasks import (
            _start_task_profiling,
            _stop_task_profiling,
            _task_profilers,
        )

        mock_profiler = MagicMock()
        mock_cprofile.Profile.return_value = mock_profiler
        _start_task_profiling(task_id="test-456", task=MagicMock())
        _stop_task_profiling(task_id="test-456", task=MagicMock(name="test_task"))
        self.assertNotIn("test-456", _task_profilers)
        mock_profiler.disable.assert_called_once()

    def test_stop_profiling_noop_for_unknown(self):
        from soroscan.ingest.tasks import _stop_task_profiling

        # Should not raise
        _stop_task_profiling(task_id="nonexistent", task=MagicMock(name="x"))


# ---------------------------------------------------------------------------
# cleanup_silk_data tests
# ---------------------------------------------------------------------------

class CleanupSilkDataTests(TestCase):
    def test_cleanup_when_silk_not_in_installed_apps(self):
        """Silk is installed as a package but not in INSTALLED_APPS for tests."""
        from soroscan.ingest.tasks import cleanup_silk_data

        # Patch the import target so it raises ImportError
        with patch.dict("sys.modules", {"silk": None, "silk.models": None}):
            result = cleanup_silk_data()
        self.assertEqual(result, 0)
