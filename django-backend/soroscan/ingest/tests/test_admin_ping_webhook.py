import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
from unittest.mock import patch, MagicMock

import requests as http_requests

from soroscan.ingest.admin import WebhookSubscriptionAdmin
from soroscan.ingest.models import WebhookSubscription
from soroscan.ingest.tests.factories import WebhookSubscriptionFactory


@pytest.mark.django_db
class TestPingWebhookAdminView:
    def setup_method(self):
        self.site = AdminSite()
        self.admin = WebhookSubscriptionAdmin(WebhookSubscription, self.site)
        self.rf = RequestFactory()

    def _make_request(self, method="post"):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User(username=f"admin_{id(self)}", is_staff=True, is_superuser=True, is_active=True)
        user.set_password("x")
        user.save()
        req = getattr(self.rf, method)("/")
        req.user = user
        req._messages = MagicMock()
        return req

    @patch("soroscan.ingest.admin.http_requests.post")
    def test_ping_success_shows_success_message(self, mock_post):
        """Successful ping shows a SUCCESS admin message and redirects."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        sub = WebhookSubscriptionFactory()
        request = self._make_request()

        with patch.object(self.admin, "message_user") as mock_msg:
            response = self.admin.ping_webhook(request, sub.pk)

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[0][0] == sub.target_url
        mock_msg.assert_called_once()
        _, msg_text, level = mock_msg.call_args[0]
        assert "successfully" in msg_text.lower()
        from django.contrib import messages
        assert level == messages.SUCCESS
        assert response.status_code == 302

    @patch("soroscan.ingest.admin.http_requests.post")
    def test_ping_failure_shows_error_message(self, mock_post):
        """Network error shows an ERROR admin message and redirects."""
        mock_post.side_effect = http_requests.ConnectionError("refused")

        sub = WebhookSubscriptionFactory()
        request = self._make_request()

        with patch.object(self.admin, "message_user") as mock_msg:
            response = self.admin.ping_webhook(request, sub.pk)

        mock_msg.assert_called_once()
        _, msg_text, level = mock_msg.call_args[0]
        assert "failed" in msg_text.lower()
        from django.contrib import messages
        assert level == messages.ERROR
        assert response.status_code == 302

    @patch("soroscan.ingest.admin.http_requests.post")
    def test_ping_http_error_shows_error_message(self, mock_post):
        """Non-2xx response (raise_for_status) shows an ERROR admin message."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = http_requests.HTTPError("500")
        mock_post.return_value = mock_response

        sub = WebhookSubscriptionFactory()
        request = self._make_request()

        with patch.object(self.admin, "message_user") as mock_msg:
            self.admin.ping_webhook(request, sub.pk)

        _, msg_text, level = mock_msg.call_args[0]
        assert "failed" in msg_text.lower()
        from django.contrib import messages
        assert level == messages.ERROR

    @patch("soroscan.ingest.admin.http_requests.post")
    def test_ping_sends_correct_payload_and_signature(self, mock_post):
        """Ping sends HMAC-signed JSON payload with correct headers."""
        import hashlib
        import hmac
        import json

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        sub = WebhookSubscriptionFactory(secret="testsecret")
        request = self._make_request()

        with patch.object(self.admin, "message_user"):
            self.admin.ping_webhook(request, sub.pk)

        call_args = mock_post.call_args
        sent_bytes = call_args[1]["data"]
        sent_headers = call_args[1]["headers"]

        payload = json.loads(sent_bytes)
        assert payload["event_type"] == "ping"
        assert payload["contract_id"] == sub.contract.contract_id

        expected_sig = "sha256=" + hmac.new(
            b"testsecret", msg=sent_bytes, digestmod=hashlib.sha256
        ).hexdigest()
        assert sent_headers["X-SoroScan-Signature"] == expected_sig

    @patch("soroscan.ingest.admin.http_requests.post")
    def test_ping_redirects_to_change_page(self, mock_post):
        """After ping, admin is redirected back to the subscription change page."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        sub = WebhookSubscriptionFactory()
        request = self._make_request()

        with patch.object(self.admin, "message_user"):
            response = self.admin.ping_webhook(request, sub.pk)

        assert response.status_code == 302
        assert f"/ingest/webhooksubscription/{sub.pk}/change/" in response["Location"]

    def test_ping_url_registered(self):
        """The ping URL is registered in the admin URL patterns."""
        urls = self.admin.get_urls()
        names = [u.name for u in urls if hasattr(u, "name")]
        assert "webhooksubscription_ping" in names
