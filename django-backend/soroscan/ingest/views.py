"""
API Views for SoroScan event ingestion.
"""
import hashlib
import hmac
import json
import logging
import time
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Max, Min, Q, Avg
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

from .cache_utils import cache_result, get_or_set_json, query_cache_ttl, stable_cache_key
from .models import (
    APIKey,
    AdminAction,
    ArchivedEventBatch,
    ContractEvent,
    ContractInvocation,
    ContractSource,
    ContractVerification,
    OrganizationCostSnapshot,
    OrganizationBudget,
    IngestError,
    IndexerState,
    Team,
    TeamMembership,
    TrackedContract,
    WebhookDeliveryLog,
    WebhookSubscription,
)
from .cache_utils import get_cached_contract
from .serializers import (
    APIKeySerializer,
    ContractEventSerializer,
    ContractInvocationSerializer,
    ContractSourceSerializer,
    ContractVerificationSerializer,
    EventSearchSerializer,
    OrganizationBudgetSerializer,
    OrganizationCostSnapshotSerializer,
    RecordEventRequestSerializer,
    TeamMemberAddSerializer,
    TeamSerializer,
    TrackedContractSerializer,
    WebhookSubscriptionSerializer,
)
from .stellar_client import SorobanClient

logger = logging.getLogger(__name__)


class AdminActionSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = AdminAction
        fields = [
            "id",
            "username",
            "action",
            "object_type",
            "object_id",
            "timestamp",
            "ip_address",
            "changes",
        ]


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
    search_fields = ["name", "alias", "contract_id"]
    ordering_fields = ["created_at", "name", "alias"]
    ordering = ["-created_at"]
    action_throttle_scopes = {
        "stats": "contract_stats",
    }

    @staticmethod
    def _collect_warnings(items: list[dict]) -> list[dict[str, str]]:
        warnings: list[dict[str, str]] = []
        for item in items:
            for warning in item.get("warnings", []):
                if warning not in warnings:
                    warnings.append(warning)
        return warnings

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        if isinstance(response.data, dict) and "results" in response.data:
            response.data["warnings"] = self._collect_warnings(response.data["results"])
        return response

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        if isinstance(response.data, dict):
            response.data.setdefault("warnings", [])
        return response

    def create(self, request, *args, **kwargs):
        dry_run = request.query_params.get("dry_run", "").lower() == "true"
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if dry_run:
            return Response({"detail": "Valid"}, status=status.HTTP_200_OK)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def perform_update(self, serializer):
        instance = serializer.save()
        from .tasks import alert_downstream_contract_change

        alert_downstream_contract_change.delay(instance.contract_id, "modified")

    def get_queryset(self):
        qs = TrackedContract.objects.all()
        user = self.request.user
        if self.request.method in ["GET", "HEAD", "OPTIONS"]:
            if user.is_authenticated:
                return qs.filter(Q(owner=user) | Q(team__memberships__user=user)).distinct()
            return qs
        return qs.filter(owner=self.request.user)

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
        cache_key = stable_cache_key(
            "rest_contract_stats",
            {"contract_pk": contract.pk, "cid": contract.contract_id},
        )

        def _build():
            agg = contract.events.aggregate(
                total_events=Count("id"),
                unique_event_types=Count("event_type", distinct=True),
                latest_ledger=Max("ledger"),
            )
            agg["contract_id"] = contract.contract_id
            agg["name"] = contract.name
            agg["last_activity"] = contract.last_event_at
            return agg

        stats = get_or_set_json(cache_key, query_cache_ttl(), _build)
        return Response(stats)

    @action(detail=True, methods=["get"])
    def completeness(self, request, pk=None):
        contract = self.get_object()
        state = IndexerState.objects.filter(key=f"completeness:{contract.id}").first()
        if state:
            try:
                return Response(json.loads(state.value))
            except json.JSONDecodeError:
                pass

        from .tasks import _calculate_completeness

        return Response(_calculate_completeness(contract))

    @action(detail=False, methods=["get"])
    def completeness_dashboard(self, request):
        from .tasks import _calculate_completeness

        rows = []
        for contract in self.get_queryset():
            state = IndexerState.objects.filter(key=f"completeness:{contract.id}").first()
            if state:
                try:
                    rows.append(json.loads(state.value))
                    continue
                except json.JSONDecodeError:
                    pass
            rows.append(_calculate_completeness(contract))

        rows.sort(key=lambda item: item.get("completeness_percentage", 100.0))
        return Response({"contracts": rows})

    @action(detail=True, methods=["post"])
    def upload_source(self, request, pk=None):
        """
        Upload contract source code for verification.
        Accepts a file (Rust code or tarball) and optional ABI JSON.
        """
        contract = self.get_object()

        # Check permissions - only contract owner or team members
        if contract.owner != request.user and not contract.team.members.filter(user=request.user).exists():
            return Response({"error": "Permission denied"}, status=403)

        serializer = ContractSourceSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(contract=contract, uploaded_by=request.user)
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)

    @action(detail=True, methods=["post"])
    def verify_source(self, request, pk=None):
        """
        Verify contract source against deployed bytecode.
        """
        contract = self.get_object()

        # Get latest source
        try:
            source = contract.sources.latest('uploaded_at')
        except ContractSource.DoesNotExist:
            return Response({"error": "No source uploaded"}, status=400)

        # Placeholder verification logic
        # In real implementation, this would:
        # 1. Extract/compile source code to get bytecode
        # 2. Query Stellar network for deployed bytecode
        # 3. Compare hashes

        # For now, mark as verified
        verification, created = ContractVerification.objects.get_or_create(
            contract=contract,
            defaults={
                'source': source,
                'status': 'verified',
                'bytecode_hash': 'placeholder_hash',
                'compiler_version': 'unknown',
                'verified_at': timezone.now(),
            }
        )

        if not created:
            verification.status = 'verified'
            verification.source = source
            verification.bytecode_hash = 'placeholder_hash'
            verification.compiler_version = 'unknown'
            verification.verified_at = timezone.now()
            verification.save()

        serializer = ContractVerificationSerializer(verification)
        return Response(serializer.data)


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
    filterset_fields = [
        "contract__contract_id",
        "event_type",
        "ledger",
        "tx_hash",
        "validation_status",
        "decoding_status",
        "signature_status",
    ]
    ordering_fields = ["timestamp", "ledger"]
    ordering = ["-timestamp"]
    action_throttle_scopes = {
        "search": "events_search",
    }

    def get_queryset(self):
        qs = ContractEvent.objects.select_related("contract").all()
        
        # Support comma-separated 'type' filter (Issue #476)
        event_types = self.request.query_params.get("type")
        if event_types:
            types_list = [t.strip() for t in event_types.split(",") if t.strip()]
            if types_list:
                qs = qs.filter(event_type__in=types_list)
                
        return qs

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
        cache_key = stable_cache_key(
            "rest_event_search",
            dict(request.GET.items()),
        )

        def _build():
            total = qs.count()
            offset = (page - 1) * page_size
            items = list(qs[offset : offset + page_size])
            ser = EventSearchSerializer(items, many=True)
            return {
                "count": total,
                "page": page,
                "page_size": page_size,
                "results": ser.data,
            }

        payload = get_or_set_json(cache_key, query_cache_ttl(), _build)
        return Response(payload)


class ContractInvocationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for querying contract invocations.

    Endpoints:
    - GET /api/contracts/{contract_id}/invocations/ - List invocations
    - GET /api/invocations/{id}/ - Get invocation details
    """

    serializer_class = ContractInvocationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["caller", "function_name"]
    ordering_fields = ["created_at", "ledger_sequence"]
    ordering = ["-created_at"]

    def get_queryset(self):
        """Filter by contract and user ownership."""
        contract_id = self.kwargs.get("contract_id")
        qs = ContractInvocation.objects.select_related("contract").filter(
            contract__owner=self.request.user
        )
        if contract_id:
            qs = qs.filter(contract__contract_id=contract_id)
        return qs

    def get_serializer_context(self):
        """Add include_events flag from query params."""
        context = super().get_serializer_context()
        context["include_events"] = self.request.query_params.get("include_events") == "true"
        return context

    def list(self, request, *args, **kwargs):
        """
        List invocations with optional filters.

        Query params:
        - caller: Filter by caller address
        - function_name: Filter by function name
        - since: ISO timestamp for start of range
        - until: ISO timestamp for end of range
        - include_events: Include nested events (default: false)
        """
        queryset = self.filter_queryset(self.get_queryset())

        # Timestamp range filtering
        since = request.query_params.get("since")
        until = request.query_params.get("until")
        if since:
            queryset = queryset.filter(created_at__gte=since)
        if until:
            queryset = queryset.filter(created_at__lte=until)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)



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
        algorithm = (webhook.signature_algorithm or WebhookSubscription.SIGNATURE_SHA256).lower()
        if algorithm == WebhookSubscription.SIGNATURE_SHA1:
            digestmod = hashlib.sha1
            prefix = "sha1"
        else:
            digestmod = hashlib.sha256
            prefix = "sha256"
        sig_hex = hmac.new(
            webhook.secret.encode("utf-8"),
            msg=payload_bytes,
            digestmod=digestmod,
        ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "X-SoroScan-Signature": f"{prefix}={sig_hex}",
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

    @extend_schema(
        request=None,
        responses={
            200: inline_serializer(
                name="PingWebhookResponse",
                fields={
                    "status": serializers.CharField(),
                    "webhook_id": serializers.IntegerField(),
                },
            )
        },
    )
    @action(detail=True, methods=["post"])
    def ping(self, request, pk=None):
        """
        Dispatch a background task that sends a test ping payload to the webhook
        endpoint.  The task logs whether the target responded with HTTP 200.
        """
        from .tasks import ping_webhook

        webhook = self.get_object()
        ping_webhook.delay(webhook.id)
        return Response({"status": "ping_queued", "webhook_id": webhook.id})

    @extend_schema(
        request=inline_serializer(
            name="WebhookConditionDryRunRequest",
            fields={
                "sample_event": serializers.JSONField(),
            },
        ),
        responses={
            200: inline_serializer(
                name="WebhookConditionDryRunResponse",
                fields={
                    "matched": serializers.BooleanField(),
                },
            )
        },
    )
    @action(detail=True, methods=["post"], url_path="dry-run")
    def dry_run(self, request, pk=None):
        webhook = self.get_object()
        sample_event = request.data.get("sample_event")
        if not isinstance(sample_event, dict):
            return Response(
                {"detail": "sample_event must be an object."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not webhook.filter_condition:
            return Response({"matched": True})

        from .tasks import evaluate_condition

        matched = evaluate_condition(webhook.filter_condition, sample_event)
        return Response({"matched": bool(matched)})


class TeamViewSet(viewsets.ModelViewSet):
    """
    Teams: multi-tenant organization of contracts and members.

    - GET /teams/ — teams the current user belongs to
    - POST /teams/ — create a team (creator becomes admin)
    - POST /teams/{id}/members/ — add a user (admin only)
    """

    serializer_class = TeamSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [OrderingFilter]
    ordering_fields = ["name", "created_at"]
    ordering = ["name"]

    def get_queryset(self):
        return Team.objects.filter(memberships__user=self.request.user).distinct()

    @extend_schema(
        request=TeamMemberAddSerializer,
        responses={
            201: inline_serializer(
                name="TeamMemberAdded",
                fields={"status": serializers.CharField()},
            )
        },
    )
    @action(detail=True, methods=["post"], url_path="members")
    def members(self, request, pk=None):
        team = self.get_object()
        admin = TeamMembership.objects.filter(
            team=team,
            user=request.user,
            role=TeamMembership.Role.ADMIN,
        ).exists()
        if not admin:
            return Response(
                {"detail": "Only team admins can add members."},
                status=status.HTTP_403_FORBIDDEN,
            )
        ser = TeamMemberAddSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            new_user = User.objects.get(pk=ser.validated_data["user_id"])
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        _, created = TeamMembership.objects.get_or_create(
            team=team,
            user=new_user,
            defaults={"role": ser.validated_data["role"]},
        )
        if not created:
            return Response({"status": "already_member"}, status=status.HTTP_200_OK)
        return Response({"status": "created"}, status=status.HTTP_201_CREATED)


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


@extend_schema(
    responses=inline_serializer(
        name="NetworkListResponse",
        fields={
            "networks": serializers.ListField(
                child=inline_serializer(
                    name="NetworkEntry",
                    fields={
                        "id": serializers.CharField(),
                        "name": serializers.CharField(),
                        "rpc_url": serializers.CharField(),
                        "network_passphrase": serializers.CharField(),
                    },
                )
            )
        },
    )
)
@api_view(["GET"])
@permission_classes([AllowAny])
def networks_view(request):
    """Return the list of Soroban networks supported by this indexer."""
    networks = getattr(settings, "SOROBAN_NETWORKS", [])
    return Response({"networks": networks})


@extend_schema(
    responses=inline_serializer(
        name="ContractStatusResponse",
        fields={
            "total_contracts": serializers.IntegerField(),
            "active_contracts": serializers.IntegerField(),
            "paused_contracts": serializers.IntegerField(),
            "total_events_indexed": serializers.IntegerField(),
            "last_event_timestamp": serializers.DateTimeField(allow_null=True),
            "events_per_minute": serializers.IntegerField(),
        },
    )
)
@api_view(["GET"])
@cache_result(ttl=60)
def contract_status(request):
    """Return aggregate contract and event indexing snapshot statistics."""
    contract_agg = TrackedContract.objects.aggregate(
        total_contracts=Count("id"),
        active_contracts=Count("id", filter=Q(is_active=True)),
        paused_contracts=Count("id", filter=Q(is_active=False)),
    )

    one_minute_ago = timezone.now() - timedelta(seconds=60)
    event_agg = ContractEvent.objects.aggregate(
        total_events_indexed=Count("id"),
        last_event_timestamp=Max("timestamp"),
        events_per_minute=Count("id", filter=Q(timestamp__gte=one_minute_ago)),
    )

    return Response(
        {
            "total_contracts": contract_agg["total_contracts"] or 0,
            "active_contracts": contract_agg["active_contracts"] or 0,
            "paused_contracts": contract_agg["paused_contracts"] or 0,
            "total_events_indexed": event_agg["total_events_indexed"] or 0,
            "last_event_timestamp": event_agg["last_event_timestamp"],
            "events_per_minute": event_agg["events_per_minute"] or 0,
        }
    )


@extend_schema(
    responses=inline_serializer(
        name="VulnerabilityImpactResponse",
        fields={
            "contract_id": serializers.CharField(),
            "affected_contracts": serializers.JSONField(),
            "impacted_count": serializers.IntegerField(),
            "risk_score": serializers.FloatField(),
            "impact_level": serializers.CharField(),
            "has_cycles": serializers.BooleanField(),
        },
    )
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def vulnerability_impact_view(request, contract_id: str):
    from .tasks import assess_vulnerability_impact

    result = assess_vulnerability_impact(contract_id)
    return Response(result)


@extend_schema(
    parameters=[
        inline_serializer(
            name="OrganizationCostBreakdownParams",
            fields={
                "organization_id": serializers.IntegerField(required=False),
                "month": serializers.CharField(required=False),
            },
        )
    ],
    responses=inline_serializer(
        name="OrganizationCostBreakdownResponse",
        fields={
            "results": serializers.JSONField(),
        },
    ),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def organization_cost_breakdown_view(request):
    """Admin endpoint exposing per-organization cost snapshots and budget state."""
    if not request.user.is_staff:
        return Response({"error": "Admin access required"}, status=status.HTTP_403_FORBIDDEN)

    snapshots = OrganizationCostSnapshot.objects.select_related("organization").all()
    org_id = request.query_params.get("organization_id")
    month = request.query_params.get("month")

    if org_id:
        snapshots = snapshots.filter(organization_id=org_id)
    if month:
        try:
            year, month_num = month.split("-", 1)
            snapshots = snapshots.filter(month__year=int(year), month__month=int(month_num))
        except (TypeError, ValueError):
            return Response(
                {"error": "month must be in YYYY-MM format"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    budgets = {
        budget.organization_id: OrganizationBudgetSerializer(budget).data
        for budget in OrganizationBudget.objects.select_related("organization").all()
    }

    payload = []
    for snapshot in snapshots.order_by("-month", "organization__name"):
        item = OrganizationCostSnapshotSerializer(snapshot).data
        item["budget"] = budgets.get(snapshot.organization_id)
        payload.append(item)

    return Response({"results": payload})


def contract_timeline_view(request, contract_id: str):
    """Redirect timeline requests to the frontend contract timeline page."""
    contract = get_cached_contract(contract_id)
    if not contract:
        from django.http import Http404
        raise Http404
    frontend_base = _frontend_base_url()
    return redirect(f"{frontend_base}/contracts/{contract.contract_id}/timeline")


@api_view(["GET"])
@permission_classes([AllowAny])
def transaction_events_view(request, tx_id: str):
    """Return all events participating in the same atomic transaction."""
    events = list(
        ContractEvent.objects.select_related("contract")
        .filter(tx_hash=tx_id)
        .order_by("ledger", "event_index", "id")
    )
    serializer = ContractEventSerializer(events, many=True)
    return Response(
        {
            "transaction_id": tx_id,
            "event_count": len(events),
            "events": serializer.data,
        }
    )


def contract_event_explorer_view(request, contract_id: str):
    """Redirect explorer requests to the frontend event explorer page."""
    contract = get_cached_contract(contract_id)
    if not contract:
        from django.http import Http404
        raise Http404
    frontend_base = _frontend_base_url()
    return redirect(f"{frontend_base}/contracts/{contract.contract_id}/events/explorer")


@api_view(["GET"])
@permission_classes([AllowAny])
def contract_event_types_view(request, contract_id: str):
    """Get event types and their counts for a specific contract."""
    contract = get_cached_contract(contract_id)
    if not contract:
        from django.http import Http404
        raise Http404
    
    cache_key = stable_cache_key("contract_event_types", {"contract_id": contract_id})
    
    def _build():
        return list(
            ContractEvent.objects.filter(contract=contract)
            .values("event_type")
            .annotate(
                count=Count("id"),
                first_seen=Min("timestamp"),
                last_seen=Max("timestamp")
            )
            .order_by("-count")
        )
    
    result = get_or_set_json(cache_key, 60, _build)
    return Response(result)


@extend_schema(
    parameters=[
        inline_serializer(
            name="EventTypeStatisticsParams",
            fields={
                "contract_id": serializers.CharField(required=False),
            },
        )
    ],
    responses=inline_serializer(
        name="EventTypeStatisticsResponse",
        fields={
            "contract_id": serializers.CharField(allow_null=True),
            "total_events": serializers.IntegerField(),
            "event_types": serializers.JSONField(),
        },
    ),
)
@api_view(["GET"])
@permission_classes([AllowAny])
def event_type_statistics_view(request):
    """Return event type distribution globally or for a specific contract."""
    contract_id = request.query_params.get("contract_id")

    contract = None
    if contract_id:
        contract = get_cached_contract(contract_id)
        if not contract:
            from django.http import Http404
            raise Http404

    cache_key = stable_cache_key(
        "event_type_statistics",
        {"contract_id": contract_id or "all"},
    )

    def _build():
        events = ContractEvent.objects.select_related("contract").all()

        if contract:
            events = events.filter(contract=contract)

        total_events = events.count()

        event_types = list(
            events.values("contract__contract_id", "event_type")
            .annotate(
                count=Count("id"),
                first_seen=Min("timestamp"),
                last_seen=Max("timestamp"),
            )
            .order_by("contract__contract_id", "-count", "event_type")
        )

        return {
            "contract_id": contract_id if contract_id else None,
            "total_events": total_events,
            "event_types": [
                {
                    "contract_id": item["contract__contract_id"],
                    "event_type": item["event_type"],
                    "count": item["count"],
                    "first_seen": item["first_seen"],
                    "last_seen": item["last_seen"],
                }
                for item in event_types
            ],
        }

    payload = get_or_set_json(cache_key, query_cache_ttl(), _build)
    return Response(payload)


@extend_schema(
    parameters=[
        inline_serializer(
            name="RestoreArchiveParams",
            fields={"batch_id": serializers.IntegerField()},
        )
    ],
    responses={
        200: inline_serializer(
            name="RestoreArchiveResponse",
            fields={
                "status": serializers.CharField(),
                "restored_count": serializers.IntegerField(),
                "batch_id": serializers.IntegerField(),
            },
        ),
        404: inline_serializer(
            name="RestoreNotFound",
            fields={"detail": serializers.CharField()},
        ),
        429: inline_serializer(
            name="RestoreRateLimited",
            fields={"detail": serializers.CharField()},
        ),
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([UserRateThrottle])
def restore_archived_events(request):
    """
    Retrieve an archived event batch from S3 and re-import events into PostgreSQL.

    Query params:
    - batch_id: ID of the ArchivedEventBatch to restore
    """
    batch_id = request.query_params.get("batch_id") or request.data.get("batch_id")
    if not batch_id:
        return Response({"detail": "batch_id is required."}, status=status.HTTP_400_BAD_REQUEST)

    batch = get_object_or_404(ArchivedEventBatch, id=batch_id)

    if batch.status == ArchivedEventBatch.STATUS_RESTORED:
        return Response(
            {"detail": "Batch already restored.", "batch_id": batch.id},
            status=status.HTTP_200_OK,
        )

    try:
        import boto3  # noqa: PLC0415
        import gzip  # noqa: PLC0415

        s3 = boto3.client(
            "s3",
            region_name=getattr(settings, "AWS_S3_REGION_NAME", None),
            endpoint_url=getattr(settings, "AWS_S3_ENDPOINT_URL", None),
            aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None),
            aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
        )
        policy = batch.policy
        obj = s3.get_object(Bucket=policy.s3_bucket, Key=batch.s3_key)
        compressed = obj["Body"].read()
        raw_json = gzip.decompress(compressed)
        rows = json.loads(raw_json)

    except Exception as exc:
        logger.exception("Failed to download archive batch %s from S3", batch_id)
        return Response(
            {"detail": f"S3 retrieval failed: {str(exc)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    restored_count = 0
    for row in rows:
        try:
            contract = get_cached_contract(row["contract__contract_id"])
            if not contract:
                raise TrackedContract.DoesNotExist(f"Contract {row['contract__contract_id']} not found")
            ContractEvent.objects.get_or_create(
                contract=contract,
                ledger=row["ledger"],
                event_index=row["event_index"],
                defaults={
                    "event_type": row["event_type"],
                    "payload": row["payload"],
                    "payload_hash": row.get("payload_hash", ""),
                    "timestamp": row["timestamp"],
                    "tx_hash": row.get("tx_hash", ""),
                },
            )
            restored_count += 1
        except Exception:
            logger.warning("Skipped row during restore: %s", row.get("id"), exc_info=True)

    batch.status = ArchivedEventBatch.STATUS_RESTORED
    batch.save(update_fields=["status"])

    from .models import ArchivalAuditLog  # noqa: PLC0415
    ArchivalAuditLog.objects.create(
        action=ArchivalAuditLog.ACTION_RESTORE,
        batch=batch,
        policy=batch.policy,
        event_count=restored_count,
        detail=f"Restored by user {request.user.id}",
        performed_by=request.user,
    )

    return Response(
        {"status": "restored", "restored_count": restored_count, "batch_id": batch.id},
        status=status.HTTP_200_OK,
    )


@extend_schema(
    parameters=[
        inline_serializer(
            name="AuditTrailParams",
            fields={
                "action": serializers.CharField(required=False),
                "object_type": serializers.CharField(required=False),
                "object_id": serializers.CharField(required=False),
                "user": serializers.CharField(required=False),
                "since": serializers.DateTimeField(required=False),
                "until": serializers.DateTimeField(required=False),
                "limit": serializers.IntegerField(required=False),
            },
        )
    ],
    responses=AdminActionSerializer(many=True),
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def audit_trail_view(request):
    """Query immutable admin audit trail entries."""
    qs = AdminAction.objects.select_related("user").all().order_by("-timestamp")

    action = request.query_params.get("action")
    object_type = request.query_params.get("object_type")
    object_id = request.query_params.get("object_id")
    username = request.query_params.get("user")
    since = request.query_params.get("since")
    until = request.query_params.get("until")

    if action:
        qs = qs.filter(action=action)
    if object_type:
        qs = qs.filter(object_type=object_type)
    if object_id:
        qs = qs.filter(object_id=object_id)
    if username:
        qs = qs.filter(user__username=username)
    if since:
        qs = qs.filter(timestamp__gte=since)
    if until:
        qs = qs.filter(timestamp__lte=until)

    try:
        limit = max(1, min(int(request.query_params.get("limit", 100)), 1000))
    except (TypeError, ValueError):
        limit = 100

    serializer = AdminActionSerializer(qs[:limit], many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_ingest_errors_view(request):
    """Get recent ingest errors (admin only)."""
    if not request.user.is_staff:
        return Response({"error": "Admin access required"}, status=status.HTTP_403_FORBIDDEN)
    
    # Last 24 hours
    since = timezone.now() - timezone.timedelta(hours=24)
    
    # Group by error_type + contract_id and aggregate
    errors = (
        IngestError.objects.filter(created_at__gte=since)
        .values("error_type", "contract_id")
        .annotate(
            count=Count("id"),
            last_occurrence=Max("created_at"),
            sample_error=Max("sample_error")  # Get one sample error message
        )
        .order_by("-count")
    )
    
    return Response(list(errors))


@extend_schema(
    responses=inline_serializer(
        name="RateLimitAnalyticsResponse",
        fields={
            "window_hours": serializers.IntegerField(),
            "generated_at": serializers.DateTimeField(),
            "api_keys": serializers.JSONField(),
        },
    )
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def rate_limit_analytics_view(request):
    """Return 7-day API key usage analytics from Redis-backed counters."""
    from django.core.cache import cache
    from soroscan.throttles import _BUCKET_TTL

    now_bucket = int(time.time()) // _BUCKET_TTL
    window_hours = 24 * 7
    keys = APIKey.objects.filter(user=request.user, is_active=True).order_by("name")
    results = []

    for key in keys:
        hourly_hits = []
        overages = 0
        for offset in range(window_hours - 1, -1, -1):
            bucket = now_bucket - offset
            history_key = f"soroscan_api_key_quota_history:{key.id}:{bucket}"
            hits = int(cache.get(history_key, 0) or 0)
            if hits > key.quota_per_hour:
                overages += 1
            hourly_hits.append(hits)

        total_hits = sum(hourly_hits)
        avg_hits = (total_hits / window_hours) if window_hours else 0.0
        quota = key.quota_per_hour
        quota_used_percent = (avg_hits / quota * 100.0) if quota > 0 else 0.0
        projected_next_24h_hits = int(round(avg_hits * 24))
        projected_overage = projected_next_24h_hits > quota

        results.append(
            {
                "api_key_id": key.id,
                "name": key.name,
                "tier": key.tier,
                "quota_per_hour": quota,
                "hourly_hits": hourly_hits,
                "avg_hits_per_hour": round(avg_hits, 2),
                "quota_used_percent": round(quota_used_percent, 2),
                "overage_events": overages,
                "projected_next_24h_hits": projected_next_24h_hits,
                "projected_overage": projected_overage,
            }
        )

    return Response(
        {
            "window_hours": window_hours,
            "generated_at": timezone.now(),
            "api_keys": results,
        }
    )


# ---------------------------------------------------------------------------
# Issue #280: GDPR — deletion requests & compliance export
# ---------------------------------------------------------------------------

class DataDeletionRequestSerializer(serializers.ModelSerializer):
    requested_by = serializers.CharField(source="requested_by.username", read_only=True)
    contract_ids = serializers.SerializerMethodField()

    class Meta:
        from .models import DataDeletionRequest
        model = DataDeletionRequest
        fields = [
            "id", "requested_by", "subject_identifier", "contract_ids",
            "status", "events_deleted", "error_message", "requested_at", "completed_at",
        ]
        read_only_fields = ["status", "events_deleted", "error_message", "requested_at", "completed_at"]

    def get_contract_ids(self, obj):
        return list(obj.contracts.values_list("contract_id", flat=True))


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def deletion_requests_view(request):
    """
    GET  /api/deletion-requests/   — list all requests (staff) or own requests
    POST /api/deletion-requests/   — submit a new GDPR deletion request
    """
    from .models import DataDeletionRequest, TrackedContract

    if request.method == "GET":
        qs = (
            DataDeletionRequest.objects.all()
            if request.user.is_staff
            else DataDeletionRequest.objects.filter(requested_by=request.user)
        )
        serializer = DataDeletionRequestSerializer(qs, many=True)
        return Response(serializer.data)

    # POST — create a new deletion request
    subject = request.data.get("subject_identifier", "").strip()
    if not subject:
        return Response({"error": "subject_identifier is required"}, status=status.HTTP_400_BAD_REQUEST)

    contract_ids = request.data.get("contract_ids", [])
    req = DataDeletionRequest.objects.create(
        requested_by=request.user,
        subject_identifier=subject,
    )
    if contract_ids:
        contracts = TrackedContract.objects.filter(contract_id__in=contract_ids)
        req.contracts.set(contracts)

    return Response(DataDeletionRequestSerializer(req).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def compliance_export_view(request):
    """
    GET /api/compliance-export/?from={iso}&to={iso}
    Returns a CSV audit trail of AuditLog entries for compliance auditors.
    Staff only.
    """
    import csv
    from django.http import StreamingHttpResponse
    from .models import AuditLog

    if not request.user.is_staff:
        return Response({"error": "Staff only"}, status=status.HTTP_403_FORBIDDEN)

    qs = AuditLog.objects.select_related("user").order_by("timestamp")
    from_ts = request.query_params.get("from")
    to_ts = request.query_params.get("to")
    if from_ts:
        qs = qs.filter(timestamp__gte=from_ts)
    if to_ts:
        qs = qs.filter(timestamp__lte=to_ts)

    def rows():
        yield ["id", "timestamp", "user", "action", "model_name", "object_id", "ip_address", "changes"]
        for entry in qs.iterator():
            yield [
                entry.id,
                entry.timestamp.isoformat(),
                entry.user.username if entry.user else "",
                entry.action,
                entry.model_name,
                entry.object_id,
                entry.ip_address or "",
                json.dumps(entry.changes),
            ]

    class EchoBuffer:
        def write(self, value):
            return value

    writer = csv.writer(EchoBuffer())
    response = StreamingHttpResponse(
        (writer.writerow(row) for row in rows()),
        content_type="text/csv",
    )
    response["Content-Disposition"] = 'attachment; filename="compliance_audit.csv"'
    return response


# ---------------------------------------------------------------------------
# Issue #592: Batch webhook delivery status
# ---------------------------------------------------------------------------

@extend_schema(
    request=inline_serializer(
        name="WebhookBatchStatusRequest",
        fields={
            "delivery_ids": serializers.ListField(
                child=serializers.IntegerField(),
                help_text="WebhookDeliveryLog primary keys to look up",
            ),
        },
    ),
    responses={
        200: inline_serializer(
            name="WebhookBatchStatusResponse",
            fields={
                "deliveries": serializers.ListField(
                    child=inline_serializer(
                        name="WebhookDeliveryStatusEntry",
                        fields={
                            "id": serializers.IntegerField(),
                            "subscription_id": serializers.IntegerField(allow_null=True),
                            "success": serializers.BooleanField(allow_null=True),
                            "http_status_code": serializers.IntegerField(allow_null=True),
                            "status": serializers.CharField(),
                            "attempt_number": serializers.IntegerField(allow_null=True),
                            "timestamp": serializers.DateTimeField(allow_null=True),
                        },
                    )
                ),
            },
        ),
        400: inline_serializer(
            name="WebhookBatchStatusBadRequest",
            fields={"detail": serializers.CharField()},
        ),
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def webhook_batch_delivery_status_view(request):
    """
    POST /api/webhooks/deliveries/batch-status/

    Look up delivery status for multiple WebhookDeliveryLog records in one query.
    """
    delivery_ids = request.data.get("delivery_ids")
    if not isinstance(delivery_ids, list) or not delivery_ids:
        return Response(
            {"detail": "delivery_ids must be a non-empty list of integers."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        parsed_ids = [int(delivery_id) for delivery_id in delivery_ids]
    except (TypeError, ValueError):
        return Response(
            {"detail": "delivery_ids must contain only integers."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if len(parsed_ids) > 200:
        return Response(
            {"detail": "delivery_ids may contain at most 200 ids."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    logs = (
        WebhookDeliveryLog.objects.filter(pk__in=parsed_ids)
        .only(
            "id",
            "subscription_id",
            "success",
            "status_code",
            "attempt_number",
            "timestamp",
        )
        .order_by("id")
    )
    by_id = {log.id: log for log in logs}

    deliveries = []
    for delivery_id in parsed_ids:
        log = by_id.get(delivery_id)
        if log is None:
            deliveries.append(
                {
                    "id": delivery_id,
                    "subscription_id": None,
                    "success": None,
                    "http_status_code": None,
                    "status": "not_found",
                    "attempt_number": None,
                    "timestamp": None,
                }
            )
            continue

        deliveries.append(
            {
                "id": log.id,
                "subscription_id": log.subscription_id,
                "success": log.success,
                "http_status_code": log.status_code,
                "status": "success" if log.success else "failed",
                "attempt_number": log.attempt_number,
                "timestamp": log.timestamp,
            }
        )

    return Response({"deliveries": deliveries})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def webhook_delivery_metrics_view(request):
    """
    GET /api/webhooks/deliveries/metrics/

    Returns webhook delivery health metrics.

    Query params:
    - subscription_id: optional integer to restrict to a specific subscription
    - minutes: optional integer for a relative time range (last N minutes)
    - recent: optional integer number of recent deliveries to include (default 10)
    """
    now = timezone.now()

    # Time range: prefer `minutes` when provided, otherwise default to 24 hours
    minutes = request.query_params.get("minutes")
    try:
        minutes = int(minutes) if minutes is not None else None
    except (TypeError, ValueError):
        return Response({"detail": "minutes must be an integer."}, status=status.HTTP_400_BAD_REQUEST)

    if minutes is not None and minutes <= 0:
        return Response({"detail": "minutes must be > 0."}, status=status.HTTP_400_BAD_REQUEST)

    if minutes is None:
        start = now - timedelta(hours=24)
    else:
        start = now - timedelta(minutes=minutes)

    qs = WebhookDeliveryLog.objects.filter(timestamp__gte=start, timestamp__lte=now)

    subscription_id = request.query_params.get("subscription_id")
    if subscription_id is not None:
        try:
            subpk = int(subscription_id)
        except (TypeError, ValueError):
            return Response({"detail": "subscription_id must be an integer."}, status=status.HTTP_400_BAD_REQUEST)
        qs = qs.filter(subscription_id=subpk)

    # Aggregates
    total = qs.count()
    success_count = qs.filter(success=True).count()
    success_rate = (success_count / total) * 100.0 if total > 0 else None
    avg_latency = qs.aggregate(avg_latency_ms=Avg("latency_ms"))["avg_latency_ms"]

    # Recent deliveries
    try:
        recent_n = int(request.query_params.get("recent", 10))
    except (TypeError, ValueError):
        recent_n = 10

    recent_qs = qs.order_by("-timestamp")[: recent_n]
    recent_deliveries = list(
        recent_qs.values(
            "id",
            "subscription_id",
            "status_code",
            "success",
            "error",
            "attempt_number",
            "timestamp",
        )
    )

    # Failure breakdown by status_code (including null network errors)
    failed = qs.filter(success=False)
    breakdown_qs = (
        failed.values("status_code")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    failure_breakdown = []
    for row in breakdown_qs:
        code = row["status_code"]
        key = "network_error" if code is None else str(code)
        failure_breakdown.append({"code": key, "count": row["count"]})

    resp = {
        "total_deliveries": total,
        "success_count": success_count,
        "success_rate_percent": success_rate,
        "avg_latency_ms": avg_latency,
        "recent_deliveries": recent_deliveries,
        "failure_breakdown": failure_breakdown,
        "time_range": {"start": start, "end": now},
    }

    return Response(resp)


# ---------------------------------------------------------------------------
# Issue #284: Contract deployment timeline
# ---------------------------------------------------------------------------

class ContractDeploymentSerializer(serializers.ModelSerializer):
    class Meta:
        from .models import ContractDeployment
        model = ContractDeployment
        fields = [
            "id", "bytecode_hash", "ledger_deployed", "deployer_address",
            "is_upgrade", "tx_hash", "notes", "detected_at",
        ]


class ContractABIVersionSerializer(serializers.ModelSerializer):
    class Meta:
        from .models import ContractABIVersion
        model = ContractABIVersion
        fields = [
            "id", "version_number", "valid_from_ledger", "valid_to_ledger",
            "has_breaking_changes", "breaking_change_details", "created_at",
        ]


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def deployment_timeline_view(request, contract_id):
    """
    GET /api/contracts/<contract_id>/deployments/
    Returns the full deployment history and ABI versions for a contract.
    Includes compatibility warnings for breaking ABI changes.
    """
    from .models import ContractDeployment, ContractABIVersion

    contract = get_cached_contract(contract_id)
    if not contract:
        from django.http import Http404
        raise Http404
    deployments = ContractDeployment.objects.filter(contract=contract).order_by("ledger_deployed")
    abi_versions = ContractABIVersion.objects.filter(contract=contract).order_by("version_number")

    warnings = []
    for av in abi_versions:
        if av.has_breaking_changes:
            warnings.append({
                "abi_version": av.version_number,
                "ledger": av.valid_from_ledger,
                "detail": av.breaking_change_details or "Breaking ABI change detected",
            })

    return Response({
        "contract_id": contract_id,
        "deployments": ContractDeploymentSerializer(deployments, many=True).data,
        "abi_versions": ContractABIVersionSerializer(abi_versions, many=True).data,
        "compatibility_warnings": warnings,
    })


# ---------------------------------------------------------------------------
# Issue: Contract Identity Endpoint
# ---------------------------------------------------------------------------

@extend_schema(
    responses=inline_serializer(
        name="ContractIdentityResponse",
        fields={
            "contract_id": serializers.CharField(),
            "network_passphrase": serializers.CharField(),
            "rpc_url": serializers.CharField(),
        },
    )
)
@api_view(["GET"])
@permission_classes([AllowAny])
def contract_identity_view(request):
    """
    GET /api/contract/identity/
    Returns the SoroScan contract ID and network information.
    Allows clients to verify where events are coming from.
    """
    return Response({
        "contract_id": getattr(settings, "SOROSCAN_CONTRACT_ID", ""),
        "network_passphrase": getattr(settings, "STELLAR_NETWORK_PASSPHRASE", ""),
        "rpc_url": getattr(settings, "SOROBAN_RPC_URL", ""),
    })
