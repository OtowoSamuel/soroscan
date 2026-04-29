import json
import pytest
from django.test import RequestFactory, override_settings
from django.http import HttpResponse

from soroscan.middleware import MaintenanceModeMiddleware


@pytest.fixture
def get_response():
    return lambda req: HttpResponse("OK", status=200)


@pytest.fixture
def rf():
    return RequestFactory()


@override_settings(MAINTENANCE_MODE=True)
def test_returns_503_for_api_routes(rf, get_response):
    request = rf.get("/api/events/")
    response = MaintenanceModeMiddleware(get_response)(request)
    assert response.status_code == 503


@override_settings(MAINTENANCE_MODE=True)
def test_response_is_json_with_error_message(rf, get_response):
    request = rf.get("/api/events/")
    response = MaintenanceModeMiddleware(get_response)(request)
    data = json.loads(response.content)
    assert "error" in data


@override_settings(MAINTENANCE_MODE=True)
def test_admin_routes_remain_accessible(rf, get_response):
    request = rf.get("/admin/")
    response = MaintenanceModeMiddleware(get_response)(request)
    assert response.status_code == 200


@override_settings(MAINTENANCE_MODE=True)
def test_admin_sub_routes_remain_accessible(rf, get_response):
    request = rf.get("/admin/ingest/webhooksubscription/")
    response = MaintenanceModeMiddleware(get_response)(request)
    assert response.status_code == 200


@override_settings(MAINTENANCE_MODE=False)
def test_disabled_maintenance_mode_passes_through(rf, get_response):
    request = rf.get("/api/events/")
    response = MaintenanceModeMiddleware(get_response)(request)
    assert response.status_code == 200


def test_maintenance_mode_off_by_default(rf, get_response):
    """MAINTENANCE_MODE defaults to False when not set."""
    request = rf.get("/api/events/")
    with override_settings(MAINTENANCE_MODE=False):
        response = MaintenanceModeMiddleware(get_response)(request)
    assert response.status_code == 200
