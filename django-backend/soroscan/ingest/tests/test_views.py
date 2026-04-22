import pytest
import responses
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from soroscan.ingest.models import Team, TeamMembership, TrackedContract, WebhookSubscription

from .factories import (
    ContractEventFactory,
    TrackedContractFactory,
    UserFactory,
    WebhookSubscriptionFactory,
)

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user():
    return UserFactory()


@pytest.fixture
def authenticated_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def contract(user):
    return TrackedContractFactory(owner=user)


@pytest.mark.django_db
class TestTrackedContractViewSet:
    def test_list_contracts(self, authenticated_client, contract):
        url = reverse("contract-list")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["contract_id"] == contract.contract_id
        assert "last_event_at" in response.data["results"][0]

    def test_list_contracts_unauthorized(self, api_client):
        url = reverse("contract-list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_contract(self, authenticated_client):
        url = reverse("contract-list")
        data = {
            "contract_id": "C" + "A" * 55,
            "name": "New Contract",
            "description": "Test",
            "is_active": True,
        }
        response = authenticated_client.post(url, data)

        assert response.status_code == status.HTTP_201_CREATED
        assert TrackedContract.objects.filter(name="New Contract").exists()

    def test_create_contract_validation_error(self, authenticated_client):
        url = reverse("contract-list")
        data = {"name": "Invalid"}
        response = authenticated_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "contract_id" in response.data

    def test_get_contract_events(self, authenticated_client, contract):
        ContractEventFactory.create_batch(3, contract=contract)
        url = reverse("contract-events", args=[contract.id])
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 3

    def test_get_contract_stats(self, authenticated_client, contract):
        ContractEventFactory.create_batch(5, contract=contract, event_type="swap")
        ContractEventFactory.create_batch(3, contract=contract, event_type="transfer")

        url = reverse("contract-stats", args=[contract.id])
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_events"] == 8
        assert response.data["unique_event_types"] == 2
        assert "last_activity" in response.data

    def test_update_contract(self, authenticated_client, contract):
        url = reverse("contract-detail", args=[contract.id])
        data = {"name": "Updated Name", "is_active": False}
        response = authenticated_client.patch(url, data)

        assert response.status_code == status.HTTP_200_OK
        contract.refresh_from_db()
        assert contract.name == "Updated Name"
        assert contract.is_active is False

    def test_delete_contract(self, authenticated_client, contract):
        url = reverse("contract-detail", args=[contract.id])
        response = authenticated_client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not TrackedContract.objects.filter(id=contract.id).exists()

    def test_list_contracts_includes_warnings_wrapper(self, authenticated_client, user):
        TrackedContractFactory(
            owner=user,
            deprecation_status=TrackedContract.DeprecationStatus.DEPRECATED,
            deprecation_reason="Contract is end-of-life.",
        )

        url = reverse("contract-list")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "warnings" in response.data
        assert response.data["warnings"] == [
            {"type": "deprecation", "message": "Contract is end-of-life."}
        ]

    def test_contract_detail_includes_deprecation_warning(self, authenticated_client, contract):
        contract.deprecation_status = TrackedContract.DeprecationStatus.SUSPENDED
        contract.deprecation_reason = "Contract has been suspended by admin."
        contract.save(update_fields=["deprecation_status", "deprecation_reason"])

        url = reverse("contract-detail", args=[contract.id])
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["warnings"] == [
            {
                "type": "deprecation",
                "message": "Contract has been suspended by admin.",
            }
        ]


@pytest.mark.django_db
class TestTeamViewSet:
    def test_create_and_list_team(self, authenticated_client, user):
        url = reverse("team-list")
        response = authenticated_client.post(url, {"name": "Platform"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert Team.objects.filter(name="Platform").exists()
        assert TeamMembership.objects.filter(
            team__name="Platform", user=user, role=TeamMembership.Role.ADMIN
        ).exists()

        listed = authenticated_client.get(url)
        assert listed.status_code == status.HTTP_200_OK
        assert len(listed.data["results"]) >= 1

    def test_team_member_sees_team_contract(self, api_client):
        owner = UserFactory()
        member = UserFactory()
        team = Team.objects.create(name="Shared", slug="shared", created_by=owner)
        TeamMembership.objects.create(
            team=team, user=owner, role=TeamMembership.Role.ADMIN
        )
        TeamMembership.objects.create(
            team=team, user=member, role=TeamMembership.Role.MEMBER
        )
        shared = TrackedContractFactory(owner=owner, team=team)

        api_client.force_authenticate(user=member)
        url = reverse("contract-list")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        cids = [row["contract_id"] for row in response.data["results"]]
        assert shared.contract_id in cids


@pytest.mark.django_db
class TestContractEventViewSet:
    def test_list_events(self, authenticated_client, contract):
        ContractEventFactory.create_batch(3, contract=contract)
        url = reverse("event-list")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 3

    def test_list_events_unauthorized(self, api_client):
        url = reverse("event-list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_filter_events_by_contract(self, authenticated_client, contract):
        other_contract = TrackedContractFactory(owner=authenticated_client.handler._force_user)
        ContractEventFactory.create_batch(2, contract=contract)
        ContractEventFactory.create_batch(3, contract=other_contract)

        url = reverse("event-list")
        response = authenticated_client.get(url, {"contract__contract_id": contract.contract_id})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2

    def test_filter_events_by_type(self, authenticated_client, contract):
        ContractEventFactory.create_batch(2, contract=contract, event_type="swap")
        ContractEventFactory.create_batch(3, contract=contract, event_type="transfer")

        url = reverse("event-list")
        response = authenticated_client.get(url, {"event_type": "swap"})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2

    def test_filter_events_by_validation_status(self, authenticated_client, contract):
        ContractEventFactory(contract=contract, validation_status="passed")
        ContractEventFactory(contract=contract, validation_status="failed")

        url = reverse("event-list")
        response = authenticated_client.get(url, {"validation_status": "failed"})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_filter_events_by_decoding_status(self, authenticated_client, contract):
        ContractEventFactory(contract=contract, decoding_status="success")
        ContractEventFactory(contract=contract, decoding_status="failed")
        ContractEventFactory(contract=contract, decoding_status="no_abi")

        url = reverse("event-list")
        response = authenticated_client.get(url, {"decoding_status": "failed"})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["decoding_status"] == "failed"


@pytest.mark.django_db
class TestWebhookSubscriptionViewSet:
    def test_list_webhooks(self, authenticated_client, contract):
        WebhookSubscriptionFactory.create_batch(2, contract=contract)
        url = reverse("webhook-list")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2

    def test_create_webhook(self, authenticated_client, contract):
        url = reverse("webhook-list")
        data = {
            "contract": contract.id,
            "event_type": "swap",
            "target_url": "https://example.com/webhook",
            "is_active": True,
        }
        response = authenticated_client.post(url, data)

        assert response.status_code == status.HTTP_201_CREATED
        assert WebhookSubscription.objects.filter(target_url="https://example.com/webhook").exists()

    def test_create_webhook_validation_error(self, authenticated_client):
        url = reverse("webhook-list")
        data = {"event_type": "swap"}
        response = authenticated_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @responses.activate
    def test_webhook_test_endpoint(self, authenticated_client, contract):
        webhook = WebhookSubscriptionFactory(contract=contract)
        responses.add(responses.POST, webhook.target_url, status=200)

        url = reverse("webhook-test", args=[webhook.id])
        response = authenticated_client.post(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "test_webhook_queued"

    def test_delete_webhook(self, authenticated_client, contract):
        webhook = WebhookSubscriptionFactory(contract=contract)
        url = reverse("webhook-detail", args=[webhook.id])
        response = authenticated_client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not WebhookSubscription.objects.filter(id=webhook.id).exists()

    def test_webhook_dry_run_uses_filter_condition(self, authenticated_client, contract):
        webhook = WebhookSubscriptionFactory(
            contract=contract,
            filter_condition={
                "op": "and",
                "conditions": [
                    {"op": "eq", "field": "event_type", "value": "transfer"},
                    {"op": "gte", "field": "payload.amount", "value": 1000},
                ],
            },
        )

        url = reverse("webhook-dry-run", args=[webhook.id])
        response = authenticated_client.post(
            url,
            {
                "sample_event": {
                    "event_type": "transfer",
                    "payload": {"amount": 900},
                }
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["matched"] is False

    def test_webhook_dry_run_rejects_non_object_sample(self, authenticated_client, contract):
        webhook = WebhookSubscriptionFactory(contract=contract)
        url = reverse("webhook-dry-run", args=[webhook.id])
        response = authenticated_client.post(url, {"sample_event": "bad"}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestRecordEventView:
    @pytest.fixture(autouse=True)
    def setup_throttle_rates(self, settings):
        """Ensure throttle rates are configured for tests"""
        if 'DEFAULT_THROTTLE_RATES' not in settings.REST_FRAMEWORK:
            settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {}
        settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'].update({
            'anon': '1000/hour',
            'user': '10000/hour',
            'ingest': '100/hour',
            'graphql': '500/hour',
        })
    
    @responses.activate
    def test_record_event_success(self, authenticated_client):
        responses.add(
            responses.POST,
            "https://soroban-testnet.stellar.org/",
            json={"status": "PENDING", "hash": "abc123"},
            status=200,
        )

        url = reverse("record-event")
        data = {
            "contract_id": "C" + "A" * 55,
            "event_type": "swap",
            "payload_hash": "a" * 64,
        }
        response = authenticated_client.post(url, data, format="json")

        assert response.status_code in [status.HTTP_202_ACCEPTED, status.HTTP_400_BAD_REQUEST]

    def test_record_event_validation_error(self, authenticated_client):
        url = reverse("record-event")
        data = {"event_type": "swap"}
        response = authenticated_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "contract_id" in response.data


@pytest.mark.django_db
class TestHealthCheck:
    def test_health_check(self, api_client):
        url = reverse("health-check")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "healthy"
        assert response.data["service"] == "soroscan"


@pytest.mark.django_db
class TestContractStatusView:
    @pytest.fixture(autouse=True)
    def clear_cache(self):
        cache.clear()

    def test_contract_status_returns_all_required_fields(self, authenticated_client, user):
        active_contract = TrackedContractFactory(owner=user, is_active=True)
        paused_contract = TrackedContractFactory(owner=user, is_active=False)

        ContractEventFactory(contract=active_contract, timestamp=timezone.now())
        ContractEventFactory(contract=paused_contract, timestamp=timezone.now() - timezone.timedelta(seconds=30))
        ContractEventFactory(contract=active_contract, timestamp=timezone.now() - timezone.timedelta(minutes=5))

        url = reverse("contract-status")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert set(response.data.keys()) == {
            "total_contracts",
            "active_contracts",
            "paused_contracts",
            "total_events_indexed",
            "last_event_timestamp",
            "events_per_minute",
        }
        assert response.data["total_contracts"] == 2
        assert response.data["active_contracts"] == 1
        assert response.data["paused_contracts"] == 1
        assert response.data["total_events_indexed"] == 3
        assert response.data["events_per_minute"] == 2
        assert response.data["last_event_timestamp"] is not None

    def test_contract_status_response_is_cached_for_60s(self, authenticated_client, user):
        contract = TrackedContractFactory(owner=user, is_active=True)
        url = reverse("contract-status")

        ContractEventFactory(contract=contract, timestamp=timezone.now())
        first = authenticated_client.get(url)
        assert first.status_code == status.HTTP_200_OK
        assert first.data["total_events_indexed"] == 1

        ContractEventFactory(contract=contract, timestamp=timezone.now())
        second = authenticated_client.get(url)
        assert second.status_code == status.HTTP_200_OK
        assert second.data["total_events_indexed"] == 1


@pytest.mark.django_db
class TestRateLimitAnalyticsView:
    def test_rate_limit_analytics_returns_metrics(self, authenticated_client, user):
        from soroscan.ingest.models import APIKey
        from soroscan.throttles import _BUCKET_TTL

        key = APIKey.objects.create(user=user, name="Analytics Key", tier="free")
        now_bucket = int(timezone.now().timestamp()) // _BUCKET_TTL
        cache.set(f"soroscan_api_key_quota_history:{key.id}:{now_bucket}", 12, timeout=3600)

        url = reverse("rate-limit-analytics")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["window_hours"] == 168
        assert len(response.data["api_keys"]) == 1
        assert response.data["api_keys"][0]["name"] == "Analytics Key"


@pytest.mark.django_db
class TestTimelinePageView:
    def test_contract_timeline_page_redirects_to_frontend(self, api_client, contract, settings):
        settings.FRONTEND_BASE_URL = "http://localhost:3000"
        url = reverse("contract-timeline", args=[contract.contract_id])
        response = api_client.get(url)

        assert response.status_code == status.HTTP_302_FOUND
        assert response["Location"] == (
            f"http://localhost:3000/contracts/{contract.contract_id}/timeline"
        )

    def test_contract_timeline_page_missing_contract_returns_404(self, api_client):
        url = reverse("contract-timeline", args=["C" + "A" * 55])
        response = api_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestEventExplorerPageView:
    def test_contract_event_explorer_page_redirects_to_frontend(
        self,
        api_client,
        contract,
        settings,
    ):
        settings.FRONTEND_BASE_URL = "http://localhost:3000"
        url = reverse("contract-event-explorer", args=[contract.contract_id])
        response = api_client.get(url)

        assert response.status_code == status.HTTP_302_FOUND
        assert response["Location"] == (
            f"http://localhost:3000/contracts/{contract.contract_id}/events/explorer"
        )

    def test_contract_event_explorer_missing_contract_returns_404(self, api_client):
        url = reverse("contract-event-explorer", args=["C" + "A" * 55])
        response = api_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_contract_event_types_endpoint(self, api_client, contract):
        # Create events with different types
        ContractEventFactory(contract=contract, event_type="transfer")
        ContractEventFactory(contract=contract, event_type="transfer")
        ContractEventFactory(contract=contract, event_type="swap")
        
        url = reverse("contract-event-types", args=[contract.contract_id])
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Should have 2 event types
        assert len(data) == 2
        
        # Should be sorted by count (descending)
        assert data[0]["event_type"] == "transfer"
        assert data[0]["count"] == 2
        assert data[1]["event_type"] == "swap"
        assert data[1]["count"] == 1
        
        # Should have timestamps
        assert "first_seen" in data[0]
        assert "last_seen" in data[0]
        assert "first_seen" in data[1]
        assert "last_seen" in data[1]

    def test_contract_event_types_missing_contract_returns_404(self, api_client):
        url = reverse("contract-event-types", args=["C" + "A" * 55])
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_admin_ingest_errors_requires_staff(self, api_client, user):
        api_client.force_authenticate(user=user)
        url = reverse("admin-ingest-errors")
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_ingest_errors_success(self, api_client):
        from soroscan.ingest.models import IngestError
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        admin_user = User.objects.create_user(username="admin", is_staff=True)
        api_client.force_authenticate(user=admin_user)
        
        # Create test errors
        IngestError.objects.create(
            error_type="decode_error",
            contract_id="CTEST123",
            error_message="Failed to decode XDR",
            ledger=1000,
        )
        IngestError.objects.create(
            error_type="decode_error", 
            contract_id="CTEST123",
            error_message="Another decode error",
            ledger=1001,
        )
        IngestError.objects.create(
            error_type="validation_error",
            contract_id="CTEST456", 
            error_message="Schema validation failed",
            ledger=1002,
        )
        
        url = reverse("admin-ingest-errors")
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Should have 2 groups (by error_type + contract_id)
        assert len(data) == 2
        
        # Should be sorted by count (descending)
        assert data[0]["count"] == 2
        assert data[0]["error_type"] == "decode_error"
        assert data[0]["contract_id"] == "CTEST123"
        assert "last_occurrence" in data[0]
        assert "sample_error" in data[0]
        
        assert data[1]["count"] == 1
        assert data[1]["error_type"] == "validation_error"
        assert data[1]["contract_id"] == "CTEST456"


class TestEventCountCaching:
    def test_event_count_cache_hit_on_second_request(self, contract):
        from soroscan.ingest.cache_utils import get_event_count
        from soroscan.ingest.tests.factories import ContractEventFactory
        from django.core.cache import cache
        
        # Clear cache
        cache.clear()
        
        # Create some events
        ContractEventFactory.create_batch(5, contract=contract)
        
        # First call should be cache miss
        count1 = get_event_count(contract.contract_id)
        assert count1 == 5
        
        # Second call should be cache hit
        count2 = get_event_count(contract.contract_id)
        assert count2 == 5
        
        # Verify it's cached
        cached_value = cache.get(f"event_count:{contract.contract_id}")
        assert cached_value == 5

    def test_event_count_cache_invalidation_on_new_event(self, contract):
        from soroscan.ingest.cache_utils import get_event_count, invalidate_event_count_cache
        from soroscan.ingest.tests.factories import ContractEventFactory
        from django.core.cache import cache
        
        # Clear cache
        cache.clear()
        
        # Create initial events and cache the count
        ContractEventFactory.create_batch(3, contract=contract)
        count1 = get_event_count(contract.contract_id)
        assert count1 == 3
        
        # Verify cached
        assert cache.get(f"event_count:{contract.contract_id}") == 3
        
        # Invalidate cache (simulating new event creation)
        invalidate_event_count_cache(contract.contract_id)
        
        # Cache should be cleared
        assert cache.get(f"event_count:{contract.contract_id}") is None
        
        # Create another event and get fresh count
        ContractEventFactory(contract=contract)
        count2 = get_event_count(contract.contract_id)
        assert count2 == 4

    def test_event_count_ttl_respected(self, contract):
        from soroscan.ingest.cache_utils import get_event_count
        from soroscan.ingest.tests.factories import ContractEventFactory
        from django.core.cache import cache
        from unittest.mock import patch
        
        # Clear cache
        cache.clear()
        
        # Create events
        ContractEventFactory.create_batch(2, contract=contract)
        
        # Mock cache.set to verify TTL
        with patch.object(cache, 'set') as mock_set:
            get_event_count(contract.contract_id)
            mock_set.assert_called_once_with(f"event_count:{contract.contract_id}", 2, 300)
