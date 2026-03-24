"""
Tests for Celery tasks — webhook dispatch, retry logic, HMAC signing, suspension.
"""
import hashlib
import hmac
from datetime import timedelta

import pytest
import requests
import requests.exceptions
import responses
from celery.exceptions import Retry
from django.utils import timezone

from soroscan.ingest.models import AdminAction, RemediationIncident, RemediationRule, WebhookDeliveryLog, WebhookSubscription
from soroscan.ingest.tasks import (
    cleanup_webhook_delivery_logs,
    dispatch_webhook,
    evaluate_remediation_rules,
    process_new_event,
    validate_event_payload,
)

from .factories import (
    ContractEventFactory,
    EventSchemaFactory,
    TrackedContractFactory,
    UserFactory,
    WebhookDeliveryLogFactory,
    WebhookSubscriptionFactory,
)


@pytest.fixture
def user():
    return UserFactory()


@pytest.fixture
def contract(user):
    return TrackedContractFactory(owner=user)


@pytest.fixture
def event(contract):
    return ContractEventFactory(contract=contract, ledger=5000, event_index=0)


@pytest.fixture
def webhook(contract):
    return WebhookSubscriptionFactory(
        contract=contract,
        target_url="https://example.com/webhook",
        secret="test-secret-abc123",
        is_active=True,
        status=WebhookSubscription.STATUS_ACTIVE,
        failure_count=0,
    )


# ---------------------------------------------------------------------------
# validate_event_payload
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestValidateEventPayload:
    def test_validation_success(self, contract):
        schema = EventSchemaFactory(
            contract=contract,
            event_type="swap",
            json_schema={
                "type": "object",
                "properties": {"amount": {"type": "number"}},
                "required": ["amount"],
            },
        )
        payload = {"amount": 100}

        passed, version = validate_event_payload(contract, "swap", payload, ledger=1000)

        assert passed is True
        assert version == schema.version

    def test_validation_failure(self, contract):
        EventSchemaFactory(
            contract=contract,
            event_type="swap",
            json_schema={
                "type": "object",
                "properties": {"amount": {"type": "number"}},
                "required": ["amount"],
            },
        )
        payload = {"wrong_field": "value"}

        passed, version = validate_event_payload(contract, "swap", payload, ledger=1000)

        assert passed is False
        assert version is not None

    def test_no_schema_passes(self, contract):
        payload = {"any": "data"}

        passed, version = validate_event_payload(contract, "unknown_event", payload)

        assert passed is True
        assert version is None

    def test_invalid_payload_type(self, contract):
        passed, version = validate_event_payload(contract, "test", None)

        assert passed is True
        assert version is None


# ---------------------------------------------------------------------------
# dispatch_webhook — success path
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestDispatchWebhookSuccess:
    @responses.activate
    def test_successful_delivery_returns_true(self, webhook, event):
        responses.add(responses.POST, webhook.target_url, status=200)

        result = dispatch_webhook.apply(args=[webhook.id, event.id])

        assert result.successful()
        assert result.result is True

    @responses.activate
    def test_success_resets_failure_count(self, webhook, event):
        webhook.failure_count = 3
        webhook.save()
        responses.add(responses.POST, webhook.target_url, status=200)

        dispatch_webhook.apply(args=[webhook.id, event.id])

        webhook.refresh_from_db()
        assert webhook.failure_count == 0
        assert webhook.last_triggered is not None

    @responses.activate
    def test_delivery_log_created_on_success(self, webhook, event):
        responses.add(responses.POST, webhook.target_url, status=200)

        dispatch_webhook.apply(args=[webhook.id, event.id])

        log = WebhookDeliveryLog.objects.get(subscription=webhook, event=event)
        assert log.success is True
        assert log.status_code == 200
        assert log.attempt_number == 1
        assert log.error == ""

    @responses.activate
    def test_2xx_with_malformed_body_treated_as_success(self, webhook, event):
        """Any 2xx response counts as success regardless of body."""
        responses.add(
            responses.POST, webhook.target_url,
            status=201,
            body="not-json-at-all",
        )

        result = dispatch_webhook.apply(args=[webhook.id, event.id])

        assert result.result is True
        log = WebhookDeliveryLog.objects.get(subscription=webhook, event=event)
        assert log.success is True


# ---------------------------------------------------------------------------
# dispatch_webhook — HMAC signing
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestDispatchWebhookHmac:
    @responses.activate
    def test_signature_header_present(self, webhook, event):
        """Every outgoing request must include X-SoroScan-Signature."""
        responses.add(responses.POST, webhook.target_url, status=200)

        dispatch_webhook.apply(args=[webhook.id, event.id])

        assert len(responses.calls) == 1
        sent_headers = responses.calls[0].request.headers
        assert "X-SoroScan-Signature" in sent_headers

    @responses.activate
    def test_signature_format_sha256_prefix(self, webhook, event):
        """Signature must be ``sha256=<hex>``."""
        responses.add(responses.POST, webhook.target_url, status=200)

        dispatch_webhook.apply(args=[webhook.id, event.id])

        sig = responses.calls[0].request.headers["X-SoroScan-Signature"]
        assert sig.startswith("sha256=")

    @responses.activate
    def test_signature_is_valid_hmac(self, webhook, event):
        """Signature must be the HMAC-SHA256 of the sorted-JSON payload."""
        responses.add(responses.POST, webhook.target_url, status=200)

        dispatch_webhook.apply(args=[webhook.id, event.id])

        request = responses.calls[0].request
        sent_sig = request.headers["X-SoroScan-Signature"]

        # Recompute expected signature
        body = request.body
        if isinstance(body, str):
            body = body.encode("utf-8")
        expected_hex = hmac.new(
            webhook.secret.encode("utf-8"),
            msg=body,
            digestmod=hashlib.sha256,
        ).hexdigest()

        assert sent_sig == f"sha256={expected_hex}"


# ---------------------------------------------------------------------------
# dispatch_webhook — retry / failure paths
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestDispatchWebhookRetry:
    @responses.activate
    def test_network_error_triggers_retry(self, webhook, event):
        """RequestException causes a Retry to be raised."""
        responses.add(
            responses.POST, webhook.target_url,
            body=requests.exceptions.ConnectionError("Connection refused"),
        )

        with pytest.raises(Retry):
            dispatch_webhook.apply(args=[webhook.id, event.id], throw=True)

    @responses.activate
    def test_5xx_triggers_retry(self, webhook, event):
        """HTTP 500 increments failure_count and schedules a retry."""
        responses.add(responses.POST, webhook.target_url, status=500)

        with pytest.raises(Retry):
            dispatch_webhook.apply(args=[webhook.id, event.id], throw=True)

        webhook.refresh_from_db()
        assert webhook.failure_count == 1

    @responses.activate
    def test_failure_log_created_on_5xx(self, webhook, event):
        """A WebhookDeliveryLog with success=False is created on 5xx."""
        responses.add(responses.POST, webhook.target_url, status=503)

        with pytest.raises(Retry):
            dispatch_webhook.apply(args=[webhook.id, event.id], throw=True)

        log = WebhookDeliveryLog.objects.get(subscription=webhook, event=event)
        assert log.success is False
        assert log.status_code == 503

    @responses.activate
    def test_network_error_log_has_no_status_code(self, webhook, event):
        """Network errors produce a log entry with status_code=None."""
        responses.add(
            responses.POST, webhook.target_url,
            body=requests.exceptions.ConnectionError("timeout"),
        )

        with pytest.raises(Retry):
            dispatch_webhook.apply(args=[webhook.id, event.id], throw=True)

        log = WebhookDeliveryLog.objects.get(subscription=webhook, event=event)
        assert log.success is False
        assert log.status_code is None
        assert "timeout" in log.error


# ---------------------------------------------------------------------------
# dispatch_webhook — 429 handling
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestDispatchWebhook429:
    @responses.activate
    def test_429_triggers_retry(self, webhook, event):
        responses.add(responses.POST, webhook.target_url, status=429)

        with pytest.raises(Retry):
            dispatch_webhook.apply(args=[webhook.id, event.id], throw=True)

    @responses.activate
    def test_429_logged_as_failure(self, webhook, event):
        responses.add(responses.POST, webhook.target_url, status=429)

        with pytest.raises(Retry):
            dispatch_webhook.apply(args=[webhook.id, event.id], throw=True)

        log = WebhookDeliveryLog.objects.get(subscription=webhook, event=event)
        assert log.success is False
        assert log.status_code == 429
        assert "429" in log.error

    @responses.activate
    def test_429_respects_retry_after_header(self, webhook, event):
        """When Retry-After is present the retry countdown must equal its value."""
        responses.add(
            responses.POST, webhook.target_url,
            status=429,
            headers={"Retry-After": "120"},
        )

        with pytest.raises(Retry) as exc_info:
            dispatch_webhook.apply(args=[webhook.id, event.id], throw=True)

        # Celery stores the countdown in Retry.when
        assert exc_info.value.when == 120


# ---------------------------------------------------------------------------
# dispatch_webhook — suspension after max retries
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestDispatchWebhookSuspension:
    @responses.activate
    def test_subscription_suspended_after_max_retries(self, webhook, event):
        """Subscription is marked suspended when all 5 retries are exhausted."""
        responses.add(responses.POST, webhook.target_url, status=500)

        # retries=5 == max_retries, so this is the last attempt.
        # With task_eager_propagates=True the final HTTPError propagates.
        with pytest.raises(requests.exceptions.HTTPError):
            dispatch_webhook.apply(
                args=[webhook.id, event.id],
                retries=5,
                throw=True,
            )

        webhook.refresh_from_db()
        assert webhook.status == WebhookSubscription.STATUS_SUSPENDED
        assert webhook.is_active is False

    @responses.activate
    def test_delivery_log_created_on_final_failure(self, webhook, event):
        """A delivery log must exist for the final failing attempt."""
        responses.add(responses.POST, webhook.target_url, status=500)

        with pytest.raises(requests.exceptions.HTTPError):
            dispatch_webhook.apply(args=[webhook.id, event.id], retries=5, throw=True)

        assert WebhookDeliveryLog.objects.filter(subscription=webhook, event=event).exists()

    @responses.activate
    def test_suspended_subscription_skipped(self, contract, event):
        """dispatch_webhook returns False immediately for suspended subscriptions."""
        suspended = WebhookSubscriptionFactory(
            contract=contract,
            is_active=False,
            status=WebhookSubscription.STATUS_SUSPENDED,
        )

        result = dispatch_webhook.apply(args=[suspended.id, event.id])

        assert result.result is False
        assert len(responses.calls) == 0  # no HTTP call made

    @responses.activate
    def test_non_last_retry_does_not_suspend(self, webhook, event):
        """Subscription must NOT be suspended on intermediate retry attempts."""
        responses.add(responses.POST, webhook.target_url, status=500)

        # retries=2 means this is the 3rd attempt, not the last (max_retries=5)
        with pytest.raises(Retry):
            dispatch_webhook.apply(args=[webhook.id, event.id], retries=2, throw=True)

        webhook.refresh_from_db()
        assert webhook.status == WebhookSubscription.STATUS_ACTIVE
        assert webhook.is_active is True


# ---------------------------------------------------------------------------
# dispatch_webhook — edge: subscription/event not found
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestDispatchWebhookEdgeCases:
    def test_subscription_not_found_returns_false(self, event):
        result = dispatch_webhook.apply(args=[99999, event.id])
        assert result.result is False

    def test_inactive_subscription_returns_false(self, contract, event):
        inactive = WebhookSubscriptionFactory(contract=contract, is_active=False)
        result = dispatch_webhook.apply(args=[inactive.id, event.id])
        assert result.result is False

    def test_event_not_found_returns_false(self, webhook):
        result = dispatch_webhook.apply(args=[webhook.id, 99999])
        assert result.result is False


# ---------------------------------------------------------------------------
# process_new_event
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestProcessNewEvent:
    @responses.activate
    def test_process_event_dispatches_to_matching_webhooks(self, contract):
        event = ContractEventFactory(
            contract=contract, event_type="swap", ledger=6000, event_index=0
        )
        webhook_swap = WebhookSubscriptionFactory(
            contract=contract, event_type="swap", is_active=True,
        )
        webhook_all = WebhookSubscriptionFactory(
            contract=contract, event_type="", is_active=True,
        )
        # non-matching event type — must NOT be dispatched
        WebhookSubscriptionFactory(
            contract=contract, event_type="transfer", is_active=True,
        )

        responses.add(responses.POST, webhook_swap.target_url, status=200)
        responses.add(responses.POST, webhook_all.target_url, status=200)

        event_data = {
            "contract_id": contract.contract_id,
            "event_type": "swap",
            "payload": event.payload,
            "ledger": event.ledger,
            "event_index": event.event_index,
        }
        process_new_event.apply(args=[event_data])

        assert len(responses.calls) == 2

    def test_process_event_no_contract_id(self):
        result = process_new_event.apply(args=[{"event_type": "swap"}])
        assert result.successful()

    @responses.activate
    def test_process_event_no_matching_webhooks(self, contract):
        event = ContractEventFactory(
            contract=contract, event_type="swap", ledger=7000, event_index=0
        )
        event_data = {
            "contract_id": contract.contract_id,
            "event_type": "swap",
            "payload": event.payload,
            "ledger": event.ledger,
            "event_index": event.event_index,
        }
        result = process_new_event.apply(args=[event_data])
        assert result.successful()
        assert len(responses.calls) == 0

    def test_suspended_webhooks_not_dispatched(self, contract):
        event = ContractEventFactory(
            contract=contract, event_type="swap", ledger=8000, event_index=0
        )
        WebhookSubscriptionFactory(
            contract=contract,
            event_type="swap",
            is_active=False,
            status=WebhookSubscription.STATUS_SUSPENDED,
        )

        event_data = {
            "contract_id": contract.contract_id,
            "event_type": "swap",
            "payload": event.payload,
            "ledger": event.ledger,
            "event_index": event.event_index,
        }
        result = process_new_event.apply(args=[event_data])
        assert result.successful()


# ---------------------------------------------------------------------------
# cleanup_webhook_delivery_logs
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCleanupWebhookDeliveryLogs:
    def test_prunes_old_entries(self, webhook, event):
        from django.utils import timezone
        from datetime import timedelta

        old_log = WebhookDeliveryLogFactory(subscription=webhook, event=event)
        # Manually backdate the timestamp via queryset update
        WebhookDeliveryLog.objects.filter(pk=old_log.pk).update(
            timestamp=timezone.now() - timedelta(days=31)
        )
        recent_log = WebhookDeliveryLogFactory(subscription=webhook, event=event)

        deleted_count = cleanup_webhook_delivery_logs.apply().result

        assert deleted_count == 1
        assert WebhookDeliveryLog.objects.filter(pk=recent_log.pk).exists()
        assert not WebhookDeliveryLog.objects.filter(pk=old_log.pk).exists()

    def test_returns_zero_when_nothing_to_prune(self):
        deleted_count = cleanup_webhook_delivery_logs.apply().result
        assert deleted_count == 0


# ---------------------------------------------------------------------------
# evaluate_remediation_rules
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestEvaluateRemediationRules:
    @responses.activate
    def test_alerts_before_action_then_executes_after_grace(self, contract):
        # No recent events => anomaly should trigger.
        responses.add(responses.POST, "https://ops.example.com/hook", status=200)

        rule = RemediationRule.objects.create(
            name="No events for 1h",
            condition={
                "type": "no_events_for_minutes",
                "contract_id": contract.contract_id,
                "minutes": 60,
            },
            actions=[{"type": "pause_contract"}],
            enabled=True,
            grace_period_minutes=10,
            alert_type=RemediationRule.ALERT_SLACK,
            alert_target="https://ops.example.com/hook",
            dry_run=False,
        )

        first = evaluate_remediation_rules.apply().result
        assert first["detected"] == 1
        assert first["alerted"] == 1
        assert first["executed"] == 0

        incident = RemediationIncident.objects.get(rule=rule, contract=contract)
        RemediationIncident.objects.filter(pk=incident.pk).update(
            action_after_at=timezone.now() - timedelta(minutes=1)
        )

        second = evaluate_remediation_rules.apply().result
        assert second["executed"] == 1

        contract.refresh_from_db()
        assert contract.is_active is False

    @responses.activate
    def test_dry_run_does_not_execute_actions(self, contract):
        responses.add(responses.POST, "https://ops.example.com/hook", status=200)

        rule = RemediationRule.objects.create(
            name="No events dry run",
            condition={
                "type": "no_events_for_minutes",
                "contract_id": contract.contract_id,
                "minutes": 60,
            },
            actions=[{"type": "pause_contract"}, {"type": "disable_webhooks"}],
            enabled=True,
            grace_period_minutes=0,
            alert_type=RemediationRule.ALERT_SLACK,
            alert_target="https://ops.example.com/hook",
            dry_run=True,
        )

        # First run creates/alerts incident.
        evaluate_remediation_rules.apply().result

        # Second run executes in dry-run mode.
        summary = evaluate_remediation_rules.apply().result
        assert summary["executed"] == 1

        contract.refresh_from_db()
        assert contract.is_active is True
        incident = RemediationIncident.objects.get(rule=rule, contract=contract)
        assert incident.status == RemediationIncident.STATUS_EXECUTED

    def test_resolves_incident_when_anomaly_clears(self, contract):
        rule = RemediationRule.objects.create(
            name="No events resolve",
            condition={
                "type": "no_events_for_minutes",
                "contract_id": contract.contract_id,
                "minutes": 60,
            },
            actions=[{"type": "pause_contract"}],
            enabled=True,
            grace_period_minutes=10,
            alert_type=RemediationRule.ALERT_WEBHOOK,
            alert_target="https://ops.example.com/hook",
            dry_run=False,
        )

        # Detect incident first.
        evaluate_remediation_rules.apply().result

        # Add a recent event so condition clears.
        ContractEventFactory(
            contract=contract,
            timestamp=timezone.now(),
            decoding_status="success",
        )

        summary = evaluate_remediation_rules.apply().result
        assert summary["resolved"] == 1

        incident = RemediationIncident.objects.get(rule=rule, contract=contract)
        assert incident.status == RemediationIncident.STATUS_RESOLVED
        assert AdminAction.objects.filter(action="remediation_resolved").exists()
