"""Tests for Ed25519 webhook signing (issue #508)."""
import pytest
import responses
from django.urls import reverse
from rest_framework.test import APIClient

from soroscan.webhook_signing import (
    build_x_signature_header,
    public_key_base64,
    verify_webhook_payload,
)
from soroscan.ingest.tasks import dispatch_webhook
from soroscan.ingest.models import WebhookSubscription
from soroscan.ingest.tests.factories import (
    ContractEventFactory,
    WebhookSubscriptionFactory,
)


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


@pytest.fixture
def event(contract):
    return ContractEventFactory(contract=contract, ledger=5000, event_index=0)


@pytest.mark.django_db
class TestWebhookEd25519Signing:
    @responses.activate
    def test_dispatch_includes_x_signature_header(self, webhook, event):
        responses.add(
            responses.POST,
            webhook.target_url,
            status=200,
            headers={"X-SoroScan-Ack": "ok"},
        )

        dispatch_webhook.apply(args=[webhook.id, event.id])

        sent_headers = responses.calls[0].request.headers
        assert "X-Signature" in sent_headers
        assert sent_headers["X-Signature"].startswith("ed25519=")

    @responses.activate
    def test_x_signature_verifies_against_platform_key(self, webhook, event):
        responses.add(
            responses.POST,
            webhook.target_url,
            status=200,
            headers={"X-SoroScan-Ack": "ok"},
        )

        dispatch_webhook.apply(args=[webhook.id, event.id])

        request = responses.calls[0].request
        body = request.body
        if isinstance(body, str):
            body = body.encode("utf-8")

        assert verify_webhook_payload(
            body,
            request.headers["X-Signature"],
            public_key_b64=public_key_base64(),
        )

    def test_build_x_signature_header_round_trip(self):
        payload = b'{"event_type":"test"}'
        header = build_x_signature_header(payload)
        assert verify_webhook_payload(payload, header)


@pytest.mark.django_db
def test_signing_public_key_endpoint():
    client = APIClient()
    url = reverse("webhook-signing-public-key")
    response = client.get(url)

    assert response.status_code == 200
    assert response.data["algorithm"] == "ed25519"
    assert response.data["public_key"] == public_key_base64()
    assert response.data["header"] == "X-Signature"
