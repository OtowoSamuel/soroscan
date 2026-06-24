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
    compliance_export_view,
    contract_event_explorer_view,
    contract_event_types_view,
    event_type_statistics_view,
    contract_identity_view,
    organization_cost_breakdown_view,
    WebhookSubscriptionViewSet,
    contract_timeline_view,
    deletion_requests_view,
    deployment_timeline_view,
    health_check,
    networks_view,
    record_event_view,
    restore_archived_events,
    transaction_events_view,
    vulnerability_impact_view,
    webhook_signing_public_key_view,
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

    path(
        "events/type-statistics/",
        event_type_statistics_view,
        name="event-type-statistics",
    ),
    path(
        "contracts/<str:contract_id>/deployments/",
        deployment_timeline_view,
        name="contract-deployments",
    ),
    path("transactions/<str:tx_id>/", transaction_events_view, name="transaction-events"),
    path(
        "contracts/<str:contract_id>/vulnerability-impact/",
        vulnerability_impact_view,
        name="contract-vulnerability-impact",
    ),
    path(
        "webhooks/signing-public-key/",
        webhook_signing_public_key_view,
        name="webhook-signing-public-key",
    ),
    path("", include(router.urls)),
    path("record/", record_event_view, name="record-event"),
    path("health/", health_check, name="health-check"),
    path("events/type-statistics/", event_type_statistics_view, name="event-type-statistics"),
    path("events/restore-archive/", restore_archived_events, name="restore-archive"),
    path("audit-trail/", audit_trail_view, name="audit-trail"),
    path("admin/ingest-errors/", admin_ingest_errors_view, name="admin-ingest-errors"),
    path(
        "admin/organization-costs/",
        organization_cost_breakdown_view,
        name="admin-organization-costs",
    ),
    path("deletion-requests/", deletion_requests_view, name="deletion-requests"),
    path("compliance-export/", compliance_export_view, name="compliance-export"),
    path("networks/", networks_view, name="networks"),
    path("contract/identity/", contract_identity_view, name="contract-identity"),
]
