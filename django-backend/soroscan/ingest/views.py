"""
API Views for SoroScan event ingestion.
"""
import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.db.models import Count, Max
from django.db.models.functions import Cast
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

import requests as http_requests

from soroscan.throttles import IngestRateThrottle

from .models import APIKey, ContractEvent, TrackedContract, WebhookSubscription
from .serializers import (
    APIKeySerializer,
    ContractEventSerializer,
    EventSearchSerializer,
    RecordEventRequestSerializer,
    TrackedContractSerializer,
    WebhookSubscriptionSerializer,
)
from .stellar_client import SorobanClient

logger = logging.getLogger(__name__)


def _frontend_base_url() -> str:
    return getattr(settings, "FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/")


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
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["is_active"]
    search_fields = ["name", "contract_id"]
    ordering_fields = ["created_at", "name"]
    ordering = ["-created_at"]

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def get_queryset(self):
        # Public read access, but filter by owner for write operations
        if self.request.method in ['GET', 'HEAD', 'OPTIONS']:
            return TrackedContract.objects.all()
        return TrackedContract.objects.filter(owner=self.request.user)

    @extend_schema(responses=ContractEventSerializer(many=True))
    @action(detail=True, methods=["get"])
    def events(self, request, pk=None):
        """Get all events for a specific contract."""
        contract = self.get_object()
        events = contract.events.select_related("contract").all()[:100]
        serializer = ContractEventSerializer(events, many=True)
        return Response(serializer.data)

    @extend_schema(
        responses=inline_serializer(
            name="ContractStats",
            fields={
                "total_events": serializers.IntegerField(),
                "unique_event_types": serializers.IntegerField(),
                "latest_ledger": serializers.IntegerField(),
                "last_activity": serializers.DateTimeField(),
                "contract_id": serializers.CharField(),
                "name": serializers.CharField(),
            },
        )
    )
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
    - GET /events/search/ - Full-text + field-level search
    """

    queryset = ContractEvent.objects.all()
    serializer_class = ContractEventSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["contract__contract_id", "event_type", "ledger", "validation_status"]
    ordering_fields = ["timestamp", "ledger"]
    ordering = ["-timestamp"]

    def get_queryset(self):
        return ContractEvent.objects.select_related("contract").all()

    @extend_schema(
        parameters=[
            inline_serializer(
                name="EventSearchParams",
                fields={
                    "q": serializers.CharField(required=False),
                    "contract_id": serializers.CharField(required=False),
                    "event_type": serializers.CharField(required=False),
                    "payload_contains": serializers.CharField(required=False),
                    "payload_field": serializers.CharField(required=False),
                    "payload_op": serializers.ChoiceField(
                        choices=["eq", "neq", "gte", "lte", "gt", "lt", "contains", "startswith", "in"],
                        required=False,
                    ),
                    "payload_value": serializers.CharField(required=False),
                    "page": serializers.IntegerField(required=False),
                    "page_size": serializers.IntegerField(required=False),
                },
            )
        ],
        responses=EventSearchSerializer(many=True),
    )
    @action(detail=False, methods=["get"])
    def search(self, request):
        """
        Full-text and field-level search on contract event payloads.

        Query params:
        - q                 — free-text substring match against JSON payload text
        - contract_id       — filter by contract
        - event_type        — filter by event type
        - payload_contains  — JSON containment sub-string (fast with GIN index)
        - payload_field     — dot-notation field path, e.g. decodedPayload.to
        - payload_op        — operator: eq|neq|gte|lte|gt|lt|contains|startswith|in
        - payload_value     — value for field comparison
        - page / page_size  — pagination (max 1000 per page)
        """
        qs = ContractEvent.objects.select_related("contract").all()

        # --- contract / event_type pre-filters --------------------------------
        contract_id = request.GET.get("contract_id")
        if contract_id:
            qs = qs.filter(contract__contract_id=contract_id)

        event_type = request.GET.get("event_type")
        if event_type:
            qs = qs.filter(event_type=event_type)

        # --- free-text substring search against JSON cast to text -------------
        q = request.GET.get("q", "").strip()
        if q:
            # Cast JSON payload to text and do a case-insensitive contains search.
            # The GIN index speeds up JSON containment (@>) queries; for plain text
            # search we rely on PostgreSQL's icontains on the cast.
            from django.db.models import TextField
            qs = qs.annotate(
                _payload_text=Cast("payload", output_field=TextField())
            ).filter(_payload_text__icontains=q)

        # --- payload_contains: JSON containment using GIN index ---------------
        payload_contains = request.GET.get("payload_contains", "").strip()
        if payload_contains:
            # Simple text containment inside the JSON; works with GIN index
            from django.db.models import TextField
            if not q:  # avoid double annotation
                qs = qs.annotate(
                    _payload_text=Cast("payload", output_field=TextField())
                )
            qs = qs.filter(_payload_text__icontains=payload_contains)

        # --- payload_field / payload_op / payload_value -----------------------
        payload_field = request.GET.get("payload_field", "").strip()
        payload_op = request.GET.get("payload_op", "eq").strip().lower()
        payload_value = request.GET.get("payload_value")

        if payload_field and payload_value is not None:
            # Build ORM lookup key from dot-notation → Django JSONField traversal
            # e.g. "decodedPayload.to" → payload__decodedPayload__to
            orm_path = "payload__" + payload_field.replace(".", "__")

            op_map = {
                "eq": "",
                "neq": None,  # handled below
                "gte": "__gte",
                "lte": "__lte",
                "gt": "__gt",
                "lt": "__lt",
                "contains": "__icontains",
                "startswith": "__istartswith",
                "in": "__in",
            }
            suffix = op_map.get(payload_op, "")
            if payload_op == "neq":
                qs = qs.exclude(**{orm_path: payload_value})
            elif payload_op == "in":
                values = [v.strip() for v in payload_value.split(",")]
                qs = qs.filter(**{f"{orm_path}__in": values})
            else:
                qs = qs.filter(**{f"{orm_path}{suffix}": payload_value})

        # --- pagination -------------------------------------------------------
        try:
            page = max(1, int(request.GET.get("page", 1)))
            page_size = min(max(1, int(request.GET.get("page_size", 50))), 1000)
        except (ValueError, TypeError):
            page = 1
            page_size = 50

        qs = qs.order_by("-timestamp")
        total = qs.count()
        offset = (page - 1) * page_size
        items = list(qs[offset: offset + page_size])

        serializer = EventSearchSerializer(items, many=True)
        return Response(
            {
                "count": total,
                "page": page,
                "page_size": page_size,
                "results": serializer.data,
            }
        )


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

    def get_queryset(self):
        # Public read access, but filter by owner for write operations
        if self.request.method in ['GET', 'HEAD', 'OPTIONS']:
            return WebhookSubscription.objects.all()
        return WebhookSubscription.objects.filter(contract__owner=self.request.user)

    @extend_schema(
        request=None,
        responses={
            200: inline_serializer(
                name="TestWebhookResponse",
                fields={"status": serializers.CharField()},
            )
        },
    )
    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """
        Send a test delivery directly to the webhook endpoint.

        The request is sent synchronously with a proper HMAC-SHA256 signature
        so the subscriber can verify authenticity.  A 200 response from this
        endpoint does NOT mean the delivery succeeded — check the response body
        for the actual outcome.
        """
        webhook = self.get_object()
        test_payload = {
            "event_type": "test",
            "payload": {"message": "This is a test webhook"},
            "contract_id": webhook.contract.contract_id,
            "timestamp": timezone.now().isoformat(),
        }
        payload_bytes = json.dumps(test_payload, sort_keys=True).encode("utf-8")
        sig_hex = hmac.new(
            webhook.secret.encode("utf-8"),
            msg=payload_bytes,
            digestmod=hashlib.sha256,
        ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "X-SoroScan-Signature": f"sha256={sig_hex}",
            "X-SoroScan-Timestamp": timezone.now().isoformat(),
        }

        try:
            http_requests.post(
                webhook.target_url,
                data=payload_bytes,
                headers=headers,
                timeout=10,
            )
        except http_requests.RequestException as exc:
            logger.warning(
                "Test webhook delivery to %s failed: %s",
                webhook.target_url,
                exc,
                extra={"webhook_id": webhook.id},
            )

        return Response({"status": "test_webhook_queued"})


class APIKeyViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing API keys with tiered rate limiting.

    Endpoints:
    - GET /api-keys/ - List your API keys
    - POST /api-keys/ - Create a new API key
    - GET /api-keys/{id}/ - Get key details (key value shown only on creation)
    - DELETE /api-keys/{id}/ - Revoke an API key
    """

    serializer_class = APIKeySerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        return APIKey.objects.filter(user=self.request.user).order_by("-created_at")

    def perform_create(self, serializer):
        key_instance = serializer.save(user=self.request.user)
        # Expose plain-text key *only* in the creation response
        self.request._created_key_plain = key_instance.key

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        plain_key = getattr(request, "_created_key_plain", None)
        if plain_key:
            response.data["key"] = plain_key
        return response

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    request=RecordEventRequestSerializer,
    responses={
        202: inline_serializer(
            name="RecordEventAccepted",
            fields={
                "status": serializers.CharField(),
                "tx_hash": serializers.CharField(),
                "transaction_status": serializers.CharField(),
            },
        ),
        400: inline_serializer(
            name="RecordEventFailed",
            fields={
                "status": serializers.CharField(),
                "error": serializers.CharField(),
                "transaction_status": serializers.CharField(),
            },
        ),
        401: inline_serializer(
            name="Unauthorized",
            fields={
                "detail": serializers.CharField(),
            },
        ),
        500: inline_serializer(
            name="RecordEventError",
            fields={
                "status": serializers.CharField(),
                "error": serializers.CharField(),
            },
        ),
        429: inline_serializer(
            name="RateLimitExceeded",
            fields={
                "detail": serializers.CharField(),
            },
        ),
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([IngestRateThrottle, AnonRateThrottle, UserRateThrottle])
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
        logger.exception(
            "Failed to record event",
            extra={"contract_id": data.get("contract_id")},
        )
        return Response(
            {"status": "error", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@extend_schema(
    responses=inline_serializer(
        name="HealthCheckResponse",
        fields={
            "status": serializers.CharField(),
            "service": serializers.CharField(),
        },
    )
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    """Health check endpoint."""
    return Response({"status": "healthy", "service": "soroscan"})


def contract_timeline_view(request, contract_id: str):
    """Redirect timeline requests to the frontend contract timeline page."""
    contract = get_object_or_404(TrackedContract, contract_id=contract_id)
    frontend_base = _frontend_base_url()
    return redirect(f"{frontend_base}/contracts/{contract.contract_id}/timeline")


def contract_event_explorer_view(request, contract_id: str):
    """Redirect explorer requests to the frontend event explorer page."""
    contract = get_object_or_404(TrackedContract, contract_id=contract_id)
    frontend_base = _frontend_base_url()
    return redirect(f"{frontend_base}/contracts/{contract.contract_id}/events/explorer")
