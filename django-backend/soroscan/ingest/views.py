"""
API Views for SoroScan event ingestion.
"""
import hashlib
import hmac
import json
import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Max, Q
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
    ContractEvent,
    ContractInvocation,
    Team,
    TeamMembership,
    TrackedContract,
    WebhookSubscription,
    ArchivedEventBatch,
)
from .serializers import (
    APIKeySerializer,
    ContractEventSerializer,
    ContractInvocationSerializer,
    EventSearchSerializer,
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

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

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
                last_activity=Max("timestamp"),
            )
            agg["contract_id"] = contract.contract_id
            agg["name"] = contract.name
            return agg

        stats = get_or_set_json(cache_key, query_cache_ttl(), _build)
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
    filterset_fields = [
        "contract__contract_id",
        "event_type",
        "ledger",
        "validation_status",
        "decoding_status",
        "signature_status",
    ]
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
            contract = TrackedContract.objects.get(contract_id=row["contract__contract_id"])
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
