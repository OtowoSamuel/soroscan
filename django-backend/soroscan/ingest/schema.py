"""GraphQL schema for SoroScan API using Strawberry."""

from __future__ import annotations

import base64
from datetime import datetime
from enum import Enum
from typing import AsyncGenerator, Optional

import strawberry
import strawberry_django
from channels.layers import get_channel_layer
from strawberry import auto
from strawberry.types import Info

from .models import ContractEvent, TrackedContract
from .services.timeline import build_timeline


def _get_authenticated_user(info: Info):
    """Safely extract authenticated user from context."""
    if info.context is None:
        return None
    if not hasattr(info.context, "request"):
        return None
    request = info.context.request
    if request is None:
        return None
    if not hasattr(request, "user"):
        return None
    user = request.user
    if user and hasattr(user, "is_authenticated") and user.is_authenticated:
        return user
    return None


# ---------------------------------------------------------------------------
# GraphQL types
# ---------------------------------------------------------------------------

@strawberry_django.type(TrackedContract)
class ContractType:
    id: auto
    contract_id: auto
    name: auto
    description: auto
    is_active: auto
    created_at: auto

    @strawberry.field
    def event_count(self) -> int:
        return self.events.count()


@strawberry_django.type(ContractEvent)
class EventType:
    id: auto
    event_type: auto
    payload: strawberry.scalars.JSON
    payload_hash: auto
    ledger: auto
    event_index: auto
    timestamp: auto
    tx_hash: auto
    schema_version: auto
    validation_status: auto

    @strawberry.field
    def contract_id(self) -> str:
        return self.contract.contract_id

    @strawberry.field
    def contract_name(self) -> str:
        return self.contract.name


@strawberry.type
class EventSearchResult:
    """A single event returned by the search resolver with a relevance score."""

    id: int
    contract_id: str
    event_type: str
    payload: strawberry.scalars.JSON
    ledger: int
    timestamp: datetime
    tx_hash: str
    relevance_score: float = 1.0


@strawberry.input
class EventFieldFilter:
    """Single field-level comparison filter."""

    eq: Optional[str] = None
    neq: Optional[str] = None
    gte: Optional[str] = None
    lte: Optional[str] = None
    gt: Optional[str] = None
    lt: Optional[str] = None
    contains: Optional[str] = None
    startswith: Optional[str] = None
    in_list: Optional[list[str]] = strawberry.field(
        name="in", default=None, description="Value must be one of these"
    )


@strawberry.input
class EventSearchQuery:
    """
    Input type for the ``searchEvents`` resolver.

    ``filters`` maps a dot-notation payload field path to a comparison object,
    e.g. ``{\"decodedPayload.to\": {eq: \"GXXX...\"}}``.
    """

    contract_id: Optional[str] = None
    payload_contains: Optional[str] = None
    event_type: Optional[str] = None
    filters: Optional[strawberry.scalars.JSON] = None
    first: int = 20
    after: Optional[str] = None


@strawberry.type
class PageInfo:
    has_next_page: bool
    end_cursor: Optional[str]


@strawberry.type
class EventEdge:
    node: EventType
    cursor: str


@strawberry.type
class EventConnection:
    edges: list[EventEdge]
    page_info: PageInfo
    total_count: int


@strawberry.type
class ContractStats:
    contract_id: str
    name: str
    total_events: int
    unique_event_types: int
    last_activity: Optional[datetime]


@strawberry.type
class EventTypeCount:
    event_type: str
    count: int


@strawberry.enum
class TimelineBucketSize(Enum):
    FIVE_MINUTES = "FIVE_MINUTES"
    THIRTY_MINUTES = "THIRTY_MINUTES"
    ONE_HOUR = "ONE_HOUR"
    ONE_DAY = "ONE_DAY"


BUCKET_SECONDS_BY_SIZE = {
    TimelineBucketSize.FIVE_MINUTES: 300,
    TimelineBucketSize.THIRTY_MINUTES: 1800,
    TimelineBucketSize.ONE_HOUR: 3600,
    TimelineBucketSize.ONE_DAY: 86_400,
}


@strawberry.type
class EventTimelineGroup:
    start: datetime
    end: datetime
    event_count: int
    event_type_counts: list[EventTypeCount]
    events: list[EventType]


@strawberry.type
class EventTimelineResult:
    contract_id: str
    bucket_size: TimelineBucketSize
    since: datetime
    until: datetime
    total_events: int
    groups: list[EventTimelineGroup]


@strawberry.type
class Query:
    @strawberry.field
    def contracts(self, is_active: Optional[bool] = None) -> list[ContractType]:
        """Get all tracked contracts."""
        qs = TrackedContract.objects.all()
        if is_active is not None:
            qs = qs.filter(is_active=is_active)
        return qs

    @strawberry.field
    def contract(self, contract_id: str) -> Optional[ContractType]:
        """Get a specific contract by ID."""
        try:
            return TrackedContract.objects.get(contract_id=contract_id)
        except TrackedContract.DoesNotExist:
            return None

    @strawberry.field
    def events(
        self,
        contract_id: Optional[str] = None,
        event_type: Optional[str] = None,
        ledger_min: Optional[int] = None,
        ledger_max: Optional[int] = None,
        first: int = 20,
        after: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> EventConnection:
        """Query events with cursor-based pagination and filtering."""
        qs = ContractEvent.objects.select_related("contract").order_by("id")

        if contract_id:
            qs = qs.filter(contract__contract_id=contract_id)
        if event_type:
            qs = qs.filter(event_type=event_type)
        if ledger_min is not None:
            qs = qs.filter(ledger__gte=ledger_min)
        if ledger_max is not None:
            qs = qs.filter(ledger__lte=ledger_max)
        if since:
            qs = qs.filter(timestamp__gte=since)
        if until:
            qs = qs.filter(timestamp__lte=until)

        total_count = qs.count()

        if after:
            try:
                decoded = base64.b64decode(after).decode("utf-8")
                after_id = int(decoded.split(":", 1)[1])
                qs = qs.filter(id__gt=after_id)
            except (ValueError, IndexError, UnicodeDecodeError):
                pass

        first = max(0, min(first, 100))

        if first == 0:
            return EventConnection(
                edges=[],
                page_info=PageInfo(has_next_page=qs.exists(), end_cursor=None),
                total_count=total_count,
            )

        items = list(qs[: first + 1])
        has_next = len(items) > first
        items = items[:first]

        edges = []
        for item in items:
            cursor = base64.b64encode(f"cursor:{item.id}".encode()).decode("utf-8")
            edges.append(EventEdge(node=item, cursor=cursor))

        return EventConnection(
            edges=edges,
            page_info=PageInfo(
                has_next_page=has_next,
                end_cursor=edges[-1].cursor if edges else None,
            ),
            total_count=total_count,
        )

    @strawberry.field
    def event(self, id: int) -> Optional[EventType]:
        """Get a specific event by ID."""
        try:
            return ContractEvent.objects.get(id=id)
        except ContractEvent.DoesNotExist:
            return None

    @strawberry.field
    def search_events(self, query: EventSearchQuery) -> list[EventSearchResult]:
        """
        Full-text and field-level search on contract event payloads.

        Supports:
        - ``contractId`` — filter by contract address
        - ``eventType`` — filter by event type
        - ``payloadContains`` — case-insensitive substring in JSON payload text
        - ``filters`` — dict mapping dot-notation field paths to comparison objects
          Supported operators per field: eq, neq, gte, lte, gt, lt, contains,
          startswith, in
        - Cursor-based pagination via ``first`` / ``after``
        """
        from django.db.models import TextField
        from django.db.models.functions import Cast

        qs = ContractEvent.objects.select_related("contract").all()

        if query.contract_id:
            qs = qs.filter(contract__contract_id=query.contract_id)
        if query.event_type:
            qs = qs.filter(event_type=query.event_type)

        if query.payload_contains:
            qs = qs.annotate(_pt=Cast("payload", output_field=TextField())).filter(
                _pt__icontains=query.payload_contains
            )

        if query.filters and isinstance(query.filters, dict):
            for field_path, ops in query.filters.items():
                if not isinstance(ops, dict):
                    continue
                orm_base = "payload__" + field_path.replace(".", "__")
                for op, val in ops.items():
                    if val is None:
                        continue
                    if op == "eq":
                        qs = qs.filter(**{orm_base: val})
                    elif op == "neq":
                        qs = qs.exclude(**{orm_base: val})
                    elif op in ("gte", "lte", "gt", "lt"):
                        qs = qs.filter(**{f"{orm_base}__{op}": val})
                    elif op == "contains":
                        qs = qs.filter(**{f"{orm_base}__icontains": val})
                    elif op == "startswith":
                        qs = qs.filter(**{f"{orm_base}__istartswith": val})
                    elif op in ("in", "in_list"):
                        values = val if isinstance(val, list) else [val]
                        qs = qs.filter(**{f"{orm_base}__in": values})

        # Cursor pagination (max 1000 per page)
        first = max(0, min(query.first, 1000))
        if query.after:
            try:
                decoded = base64.b64decode(query.after).decode()
                after_id = int(decoded.split(":", 1)[1])
                qs = qs.filter(id__gt=after_id)
            except (ValueError, IndexError, UnicodeDecodeError):
                pass

        qs = qs.order_by("id")
        items = list(qs[:first])

        return [
            EventSearchResult(
                id=e.id,
                contract_id=e.contract.contract_id,
                event_type=e.event_type,
                payload=e.payload,
                ledger=e.ledger,
                timestamp=e.timestamp,
                tx_hash=e.tx_hash,
                relevance_score=1.0,
            )
            for e in items
        ]

    @strawberry.field
    def contract_stats(self, contract_id: str) -> Optional[ContractStats]:
        """Get aggregate statistics for a contract."""
        try:
            contract = TrackedContract.objects.get(contract_id=contract_id)
        except TrackedContract.DoesNotExist:
            return None

        from django.db.models import Count, Max

        stats = contract.events.aggregate(
            total=Count("id"),
            unique_types=Count("event_type", distinct=True),
            last=Max("timestamp"),
        )

        return ContractStats(
            contract_id=contract.contract_id,
            name=contract.name,
            total_events=stats["total"] or 0,
            unique_event_types=stats["unique_types"] or 0,
            last_activity=stats["last"],
        )

    @strawberry.field
    def event_types(self, contract_id: str) -> list[str]:
        """Get all unique event types for a contract."""
        return list(
            ContractEvent.objects.filter(contract__contract_id=contract_id)
            .values_list("event_type", flat=True)
            .distinct()
        )

    @strawberry.field
    def event_timeline(
        self,
        contract_id: str,
        bucket_size: TimelineBucketSize = TimelineBucketSize.THIRTY_MINUTES,
        event_types: Optional[list[str]] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        timezone: str = "UTC",
        limit_groups: int = 500,
        include_events: bool = True,
    ) -> EventTimelineResult:
        """Return grouped timeline data for contract event history."""
        bucket_seconds = BUCKET_SECONDS_BY_SIZE[bucket_size]
        timeline = build_timeline(
            contract_id=contract_id,
            bucket_seconds=bucket_seconds,
            event_types=event_types,
            since=since,
            until=until,
            timezone_name=timezone,
            limit_groups=limit_groups,
            include_events=include_events,
        )

        groups = [
            EventTimelineGroup(
                start=group.start,
                end=group.end,
                event_count=group.event_count,
                event_type_counts=[
                    EventTypeCount(event_type=item.event_type, count=item.count)
                    for item in group.event_type_counts
                ],
                events=group.events,
            )
            for group in timeline.groups
        ]

        return EventTimelineResult(
            contract_id=timeline.contract_id,
            bucket_size=bucket_size,
            since=timeline.since,
            until=timeline.until,
            total_events=timeline.total_events,
            groups=groups,
        )


@strawberry.type
class Mutation:
    @strawberry.mutation
    def register_contract(
        self,
        info: Info,
        contract_id: str,
        name: str,
        description: str = "",
    ) -> ContractType:
        """Register a new contract for indexing."""
        user = _get_authenticated_user(info)
        if not user:
            raise Exception("Authentication required")
        
        contract = TrackedContract.objects.create(
            contract_id=contract_id,
            name=name,
            description=description,
            owner=user,
        )
        return contract

    @strawberry.mutation
    def update_contract(
        self,
        info: Info,
        contract_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[ContractType]:
        """Update a tracked contract."""
        user = _get_authenticated_user(info)
        if not user:
            raise Exception("Authentication required")
        
        try:
            contract = TrackedContract.objects.get(contract_id=contract_id)
        except TrackedContract.DoesNotExist:
            return None

        if name is not None:
            contract.name = name
        if description is not None:
            contract.description = description
        if is_active is not None:
            contract.is_active = is_active

        contract.save()
        return contract


@strawberry.type
class Subscription:
    @strawberry.subscription
    async def contract_events(
        self, info: Info, contract_id: str
    ) -> AsyncGenerator[EventType, None]:
        """
        Subscribe to real-time events for a specific contract.
        
        Args:
            contract_id: The contract ID to subscribe to
            
        Yields:
            EventType: Real-time contract events as they occur
        """
        from channels.db import database_sync_to_async
        
        channel_layer = get_channel_layer()
        if not channel_layer:
            # If no channel layer, exit gracefully
            return
            
        channel_name = await channel_layer.new_channel()
        group_name = f"events_{contract_id}"
        
        await channel_layer.group_add(group_name, channel_name)
        
        try:
            while True:
                message = await channel_layer.receive(channel_name)
                event_data = message.get("data", {})
                
                # Create EventType from the message data
                try:
                    # Fetch the actual event from database to get proper EventType instance
                    @database_sync_to_async
                    def get_event():
                        return ContractEvent.objects.select_related("contract").get(
                            contract__contract_id=event_data.get("contract_id"),
                            ledger=event_data.get("ledger"),
                            event_index=event_data.get("event_index", 0)
                        )
                    
                    event = await get_event()
                    yield event
                except ContractEvent.DoesNotExist:
                    # If event not found, skip this message
                    continue
                except Exception:
                    # Skip any other errors and continue listening
                    continue
                    
        finally:
            await channel_layer.group_discard(group_name, channel_name)


schema = strawberry.Schema(query=Query, mutation=Mutation, subscription=Subscription)
