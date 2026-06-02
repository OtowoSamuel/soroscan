import time
import pytest
from django.conf import settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from soroscan.health import format_uptime

@pytest.fixture
def api_client():
    return APIClient()

@pytest.mark.django_db
class TestHealthView:
    def test_health_returns_ok_with_uptime(self, api_client):
        url = reverse("health")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "ok"
        assert "uptime_seconds" in response.data
        assert "uptime" in response.data
        assert isinstance(response.data["uptime_seconds"], int)
        assert response.data["uptime_seconds"] >= 0
        assert isinstance(response.data["uptime"], str)
        assert response["X-SoroScan-Version"] == settings.SOFTWARE_VERSION

    def test_health_uptime_is_human_readable(self):
        assert format_uptime(0) == "0D:00:00:00"
        assert format_uptime(59) == "0D:00:00:59"
        assert format_uptime(60) == "0D:00:01:00"
        assert format_uptime(3600) == "0D:01:00:00"
        assert format_uptime(90061) == "1D:01:01:01"

    def test_health_uptime_counter_increases_across_requests(self, api_client):
        url = reverse("health")

        first_response = api_client.get(url)
        time.sleep(1.1)
        second_response = api_client.get(url)

        assert first_response.status_code == status.HTTP_200_OK
        assert second_response.status_code == status.HTTP_200_OK
        assert second_response.data["uptime_seconds"] >= first_response.data["uptime_seconds"]


@pytest.mark.django_db
class TestReadinessView:
    def test_ready_when_db_and_cache_connected(self, api_client):
        url = reverse("readiness")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "healthy"
        assert "components" in response.data
        assert response["X-SoroScan-Version"] == settings.SOFTWARE_VERSION

    def test_not_ready_when_db_fails(self, api_client, monkeypatch):
        from django.db import connection
        monkeypatch.setattr(connection, "cursor", lambda: (_ for _ in ()).throw(Exception("DB fail")))

        url = reverse("readiness")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert response.data["status"] == "degraded"
        assert "database" in response.data["components"]
        assert response["X-SoroScan-Version"] == settings.SOFTWARE_VERSION

    def test_not_ready_when_cache_fails(self, api_client, monkeypatch):
        from django.core.cache import cache
        monkeypatch.setattr(cache, "get", lambda *args, **kwargs: (_ for _ in ()).throw(Exception("Redis fail")))

        url = reverse("readiness")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert response.data["status"] == "degraded"
        assert "redis" in response.data["components"]
        assert response["X-SoroScan-Version"] == settings.SOFTWARE_VERSION


@pytest.mark.django_db
class TestWorkerHealthView:
    def test_worker_health_returns_200_when_worker_responds(self, api_client, monkeypatch):
        class DummyInspect:
            def ping(self):
                return {"worker1@hostname": {"ok": "pong"}}

        monkeypatch.setattr(
            "soroscan.health.app.control.inspect",
            lambda timeout=None: DummyInspect(),
        )

        url = reverse("worker-health")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "healthy"
        assert response.data["workers"] == {"worker1@hostname": {"ok": "pong"}}
        assert response["X-SoroScan-Version"] == settings.SOFTWARE_VERSION

    def test_worker_health_returns_503_when_workers_unresponsive(self, api_client, monkeypatch):
        class DummyInspect:
            def ping(self):
                return {}

        monkeypatch.setattr(
            "soroscan.health.app.control.inspect",
            lambda timeout=None: DummyInspect(),
        )

        url = reverse("worker-health")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert response.data["status"] == "unhealthy"
        assert "no worker responded" in response.data["error"]
        assert response["X-SoroScan-Version"] == settings.SOFTWARE_VERSION