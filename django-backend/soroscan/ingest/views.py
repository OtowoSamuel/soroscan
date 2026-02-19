"""
API Views for SoroScan event ingestion.
"""
import logging

from django.db.models import Count, Max
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import ContractEvent, TrackedContract, WebhookSubscription
from .serializers import (
    ContractEventSerializer,
    RecordEventRequestSerializer,
    TrackedContractSerializer,
    WebhookSubscriptionSerializer,
)
from .stellar_client import SorobanClient
from .tasks import dispatch_webhook

logger = logging.getLogger(__name__)


class TrackedContractViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing tracked contracts.

    Endpoints:
    - GET /contracts/ - List all tracked contracts
    - POST /contracts/ - Register a new contract
    - GET /contracts/{id}/ - Get contract details
    - PUT /contracts/{id}/ - Update contract
    - DELETE /contracts/{id}/ - Delete contract
    - GET /contracts/{id}/events/ - Get events for contract
    - GET /contracts/{id}/stats/ - Get contract statistics
    """

    queryset = TrackedContract.objects.all()
    serializer_class = TrackedContractSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["is_active"]
    search_fields = ["name", "contract_id"]
    ordering_fields = ["created_at", "name"]
    ordering = ["-created_at"]

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def get_queryset(self):
        return TrackedContract.objects.filter(owner=self.request.user)

    @action(detail=True, methods=["get"])
    def events(self, request, pk=None):
        """Get all events for a specific contract."""
        contract = self.get_object()
        events = contract.events.all()[:100]
        serializer = ContractEventSerializer(events, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        """Get statistics for a contract."""
        contract = self.get_object()
        stats = contract.events.aggregate(
            total_events=Count("id"),
            unique_event_types=Count("event_type", distinct=True),
            latest_ledger=Max("ledger"),
            last_activity=Max("timestamp"),
        )
        stats["contract_id"] = contract.contract_id
        stats["name"] = contract.name
        return Response(stats)


class ContractEventViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for querying indexed events.

    Endpoints:
    - GET /events/ - List all events (paginated)
    - GET /events/{id}/ - Get event details
    """

    queryset = ContractEvent.objects.all()
    serializer_class = ContractEventSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["contract__contract_id", "event_type", "ledger", "validation_status"]
    ordering_fields = ["timestamp", "ledger"]
    ordering = ["-timestamp"]

    def get_queryset(self):
        return ContractEvent.objects.filter(contract__owner=self.request.user)


class WebhookSubscriptionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing webhook subscriptions.

    Endpoints:
    - GET /webhooks/ - List all webhooks
    - POST /webhooks/ - Create a new webhook
    - GET /webhooks/{id}/ - Get webhook details
    - PUT /webhooks/{id}/ - Update webhook
    - DELETE /webhooks/{id}/ - Delete webhook
    - POST /webhooks/{id}/test/ - Send a test webhook
    """

    queryset = WebhookSubscription.objects.all()
    serializer_class = WebhookSubscriptionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return WebhookSubscription.objects.filter(contract__owner=self.request.user)

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """Send a test webhook."""
        webhook = self.get_object()
        test_event = {
            "event_type": "test",
            "payload": {"message": "This is a test webhook"},
            "contract_id": webhook.contract.contract_id,
            "timestamp": "2026-01-19T00:00:00Z",
        }
        dispatch_webhook.delay(test_event, webhook.id)
        return Response({"status": "test_webhook_queued"})


@api_view(["POST"])
@permission_classes([AllowAny])  # TODO: Add API key authentication
def record_event_view(request):
    """
    Record a new event by submitting a transaction to the SoroScan contract.

    Request body:
    {
        "contract_id": "CABC...",
        "event_type": "swap",
        "payload_hash": "abc123..."  // 64-char hex string
    }
    """
    serializer = RecordEventRequestSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data

    try:
        client = SorobanClient()
        result = client.record_event(
            target_contract_id=data["contract_id"],
            event_type=data["event_type"],
            payload_hash_hex=data["payload_hash"],
        )

        if result.success:
            return Response(
                {
                    "status": "submitted",
                    "tx_hash": result.tx_hash,
                    "transaction_status": result.status,
                },
                status=status.HTTP_202_ACCEPTED,
            )
        else:
            return Response(
                {
                    "status": "failed",
                    "error": result.error,
                    "transaction_status": result.status,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    except Exception as e:
        logger.exception("Failed to record event")
        return Response(
            {"status": "error", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    """Health check endpoint."""
    return Response({"status": "healthy", "service": "soroscan"})
