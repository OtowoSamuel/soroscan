"""
Tests for DynamicEndpointThrottle.

These tests call the throttle class directly rather than going through the
full HTTP stack, which avoids the test-isolation issues caused by
django.test.TestCase cache clearing and LocMemCache backend switching when
this test module is run as part of the full suite.
"""
import pytest
from django.core.cache import cache
from django.test import override_settings
from rest_framework.settings import api_settings
from rest_framework.test import APIRequestFactory
# from rest_framework import status
from unittest.mock import MagicMock

from django.contrib.auth.models import User
from soroscan.ingest.models import TrackedContract
from soroscan.throttles import DynamicEndpointThrottle


THROTTLE_RATES_SEARCH = {
    "anon": "1000/hour",
    "user": "10000/hour",
    "ingest": "100/hour",
    "graphql": "500/hour",
    "events_search": "1/minute",
}

THROTTLE_RATES_STATS = {
    "anon": "1000/hour",
    "user": "10000/hour",
    "ingest": "100/hour",
    "graphql": "500/hour",
    "contract_stats": "1/minute",
}


@pytest.fixture(autouse=True)
def isolated_cache():
    """Use a separate LocMemCache location so these tests never share state
    with other test modules that call cache.clear() on the default cache."""
    with override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "throttle-test-isolated",
            }
        }
    ):
        cache.clear()
        yield
        cache.clear()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="throttle_testuser", password="password")


@pytest.fixture
def test_contract(user):
    return TrackedContract.objects.create(
        contract_id="CAXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        name="Test Contract",
        owner=user,
        is_active=True
    )


def _make_view(action, throttle_scopes):
    """Return a minimal mock view compatible with DynamicEndpointThrottle."""
    view = MagicMock()
    view.action = action
    view.action_throttle_scopes = throttle_scopes
    view.scope_attr = "throttle_scope"
    view.throttle_scope = None
    return view


@pytest.mark.django_db
def test_events_search_throttle(user):
    """
    DynamicEndpointThrottle must allow the first request and block the second
    when the rate limit is 1/minute for the events_search scope.
    """
    with override_settings(
        REST_FRAMEWORK={
            "DEFAULT_THROTTLE_RATES": THROTTLE_RATES_SEARCH,
        }
    ):
        api_settings.reload()
        factory = APIRequestFactory()
        view = _make_view("search", {"search": "events_search"})

        req1 = factory.get("/api/ingest/events/search/")
        req1.user = user
        result1 = DynamicEndpointThrottle().allow_request(req1, view)
        assert result1 is True, "First request should be allowed"

        req2 = factory.get("/api/ingest/events/search/")
        req2.user = user
        throttle2 = DynamicEndpointThrottle()
        result2 = throttle2.allow_request(req2, view)
        assert result2 is False, "Second request should be throttled (limit: 1/min)"

        # wait() should return a positive number
        wait = throttle2.wait()
        assert wait is not None and wait > 0

    api_settings.reload()


@pytest.mark.django_db
def test_contract_stats_throttle(user):
    """
    DynamicEndpointThrottle must allow the first request and block the second
    when the rate limit is 1/minute for the contract_stats scope.
    """
    with override_settings(
        REST_FRAMEWORK={
            "DEFAULT_THROTTLE_RATES": THROTTLE_RATES_STATS,
        }
    ):
        api_settings.reload()
        factory = APIRequestFactory()
        view = _make_view("stats", {"stats": "contract_stats"})

        req1 = factory.get("/api/ingest/contracts/1/stats/")
        req1.user = user
        result1 = DynamicEndpointThrottle().allow_request(req1, view)
        assert result1 is True, "First request should be allowed"

        req2 = factory.get("/api/ingest/contracts/1/stats/")
        req2.user = user
        throttle2 = DynamicEndpointThrottle()
        result2 = throttle2.allow_request(req2, view)
        assert result2 is False, "Second request should be throttled (limit: 1/min)"

    api_settings.reload()


@pytest.mark.django_db
def test_throttle_no_scope_allows_all_requests(user):
    """
    When the view defines no matching scope in action_throttle_scopes and no
    throttle_scope attribute, the throttle must allow every request (pass-through).
    """
    with override_settings(
        REST_FRAMEWORK={
            "DEFAULT_THROTTLE_RATES": THROTTLE_RATES_SEARCH,
        }
    ):
        api_settings.reload()
        factory = APIRequestFactory()
        view = _make_view("list", {})  # no scope for "list"

        for _ in range(5):
            req = factory.get("/api/ingest/events/")
            req.user = user
            assert DynamicEndpointThrottle().allow_request(req, view) is True

    api_settings.reload()
