"""
URL patterns for SoroScan ingest API.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    APIKeyViewSet,
    ContractEventViewSet,
    ContractInvocationViewSet,
    TeamViewSet,
    TrackedContractViewSet,
    admin_ingest_errors_view,
    audit_trail_view,
    contract_event_explorer_view,
    contract_event_types_view,
    WebhookSubscriptionViewSet,
    contract_timeline_view,
    health_check,
    record_event_view,
    restore_archived_events,
)

router = DefaultRouter()
router.register(r"contracts", TrackedContractViewSet, basename="contract")
router.register(r"events", ContractEventViewSet, basename="event")
router.register(r"invocations", ContractInvocationViewSet, basename="invocation")
router.register(r"webhooks", WebhookSubscriptionViewSet, basename="webhook")
router.register(r"api-keys", APIKeyViewSet, basename="apikey")
router.register(r"teams", TeamViewSet, basename="team")

urlpatterns = [
    path("contracts/<str:contract_id>/timeline/", contract_timeline_view, name="contract-timeline"),
    path(
        "contracts/<str:contract_id>/events/explorer/",
        contract_event_explorer_view,
        name="contract-event-explorer",
    ),
    path(
        "contracts/<str:contract_id>/event-types/",
        contract_event_types_view,
        name="contract-event-types",
    ),
    path("", include(router.urls)),
    path("record/", record_event_view, name="record-event"),
    path("health/", health_check, name="health-check"),
    path("events/restore-archive/", restore_archived_events, name="restore-archive"),
    path("audit-trail/", audit_trail_view, name="audit-trail"),
    path("admin/ingest-errors/", admin_ingest_errors_view, name="admin-ingest-errors"),
]
