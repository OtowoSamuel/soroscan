"""
Celery tasks for SoroScan background processing.
"""
import cProfile
import hashlib
import hmac
import io
import json
import logging
import pstats
import time
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any

import jsonschema
import requests
from celery import shared_task
from celery.signals import task_postrun, task_prerun
from django.conf import settings
from django.db.models import F
from django.utils import timezone

from .models import ContractEvent, TrackedContract, WebhookSubscription, IndexerState, EventSchema
from .stellar_client import SorobanClient

logger = logging.getLogger(__name__)
BATCH_LEDGER_SIZE = 200
_SLOW_TASK_THRESHOLD_S = 5.0  # log profiling stats when task exceeds this

# ---------------------------------------------------------------------------
# Celery task profiling via signals — instruments all tasks automatically
# ---------------------------------------------------------------------------
_task_profilers: dict[str, tuple] = {}


@task_prerun.connect
def _start_task_profiling(task_id: str, task, **kwargs) -> None:
    profiler = cProfile.Profile()
    profiler.enable()
    _task_profilers[task_id] = (profiler, time.monotonic())


@task_postrun.connect
def _stop_task_profiling(task_id: str, task, **kwargs) -> None:
    entry = _task_profilers.pop(task_id, None)
    if entry is None:
        return
    profiler, start = entry
    profiler.disable()
    elapsed = time.monotonic() - start
    if elapsed > _SLOW_TASK_THRESHOLD_S:
        stream = io.StringIO()
        pstats.Stats(profiler, stream=stream).sort_stats(pstats.SortKey.CUMULATIVE).print_stats(20)
        logger.warning(
            "Slow task %s took %.2fs\n%s",
            task.name,
            elapsed,
            stream.getvalue(),
            extra={"task_name": task.name, "total_time_s": round(elapsed, 3)},
        )

# ---------------------------------------------------------------------------
# Prometheus metrics (imported lazily to avoid import-time side-effects
# during migrations/management commands that don't need metrics).
# ---------------------------------------------------------------------------

def _get_metrics():
    """Return the metrics module, importing it on first call."""
    from soroscan.ingest import metrics  # noqa: PLC0415
    return metrics


def _network_label() -> str:
    """Return a short label for the current Stellar network."""
    passphrase: str = getattr(settings, "STELLAR_NETWORK_PASSPHRASE", "")
    if "Public" in passphrase:
        return "mainnet"
    if "Test" in passphrase:
        return "testnet"
    return "unknown"


def _short_contract_id(contract_id: str) -> str:
    """
    Truncate contract_id to its first 8 chars to keep Prometheus label
    cardinality bounded (full 56-char IDs would create one series per contract).
    """
    return contract_id[:8] if contract_id else "unknown"


def _event_attr(event: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if hasattr(event, name):
            return getattr(event, name)
        if isinstance(event, dict) and name in event:
            return event[name]
    return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _extract_event_index(event: Any, fallback_index: int = 0) -> int:
    direct_index = _event_attr(event, "event_index", "index")
    if direct_index is not None:
        return _safe_int(direct_index, fallback_index)

    identifier = str(_event_attr(event, "id", "paging_token", default="") or "")
    if "-" in identifier:
        maybe_index = identifier.rsplit("-", maxsplit=1)[-1]
        if maybe_index.isdigit():
            return int(maybe_index)

    return fallback_index


def _upsert_contract_event(
    contract: TrackedContract,
    event: Any,
    fallback_event_index: int = 0,
) -> tuple[ContractEvent, bool]:
    ledger = _safe_int(_event_attr(event, "ledger", "ledger_sequence"), default=0)
    event_index = _extract_event_index(event, fallback_event_index)
    tx_hash = str(_event_attr(event, "tx_hash", "transaction_hash", default="") or "")
    event_type = str(_event_attr(event, "type", "event_type", default="unknown") or "unknown")
    payload = _event_attr(event, "value", "payload", default={}) or {}
    raw_xdr = str(_event_attr(event, "xdr", "raw_xdr", default="") or "")

    timestamp = _event_attr(event, "timestamp", default=timezone.now())
    if isinstance(timestamp, datetime) and timezone.is_naive(timestamp):
        timestamp = timezone.make_aware(timestamp, dt_timezone.utc)
    if not isinstance(timestamp, datetime):
        timestamp = timezone.now()

    result = ContractEvent.objects.update_or_create(
        contract=contract,
        ledger=ledger,
        event_index=event_index,
        defaults={
            "tx_hash": tx_hash,
            "event_type": event_type,
            "payload": payload,
            "timestamp": timestamp,
            "raw_xdr": raw_xdr,
        },
    )
    obj, created = result
    if created:
        m = _get_metrics()
        m.events_ingested_total.labels(
            contract_id=_short_contract_id(contract.contract_id),
            network=_network_label(),
            event_type=event_type,
        ).inc()
        # Refresh the active contracts gauge whenever a new event arrives.
        m.active_contracts_gauge.set(
            TrackedContract.objects.filter(is_active=True).count()
        )
    return result


def validate_event_payload(
    contract: TrackedContract,
    event_type: str,
    payload: dict[str, Any],
    ledger: int | None = None,
) -> tuple[bool, int | None]:
    """
    Validate event payload against the latest EventSchema for this contract+event_type.

    Returns:
        (passed, version_used): passed is True if no schema exists or validation succeeded;
        version_used is the EventSchema.version used, or None if no schema.
    """
    if payload is None or not isinstance(payload, dict):
        return (True, None)
    schema = (
        EventSchema.objects.filter(
            contract=contract,
            event_type=event_type,
        )
        .order_by("-version")
        .first()
    )
    if schema is None:
        return (True, None)
    try:
        jsonschema.validate(instance=payload, schema=schema.json_schema)
        return (True, schema.version)
    except jsonschema.ValidationError:
        logger.warning(
            "Event payload schema validation failed for contract_id=%s event_type=%s ledger=%s",
            contract.contract_id,
            event_type,
            ledger,
            extra={
                "contract_id": contract.contract_id,
                "event_type": event_type,
                "ledger": ledger,
            },
        )
        return (False, schema.version)


@shared_task(
    bind=True,
    autoretry_for=(requests.exceptions.RequestException,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=5,
)
def dispatch_webhook(self, subscription_id: int, event_id: int) -> bool:
    """
    Deliver a single ContractEvent to a WebhookSubscription endpoint.
    """
    _start = time.monotonic()
    m = _get_metrics()

    try:
        webhook = WebhookSubscription.objects.get(
            id=subscription_id,
            is_active=True,
            status=WebhookSubscription.STATUS_ACTIVE,
        )
    except WebhookSubscription.DoesNotExist:
        logger.warning(
            "Webhook subscription %s not found, inactive, or suspended — skipping",
            subscription_id,
            extra={"webhook_id": subscription_id},
        )
        return False

    try:
        event = ContractEvent.objects.select_related("contract").get(id=event_id)
    except ContractEvent.DoesNotExist:
        logger.warning(
            "ContractEvent %s not found — skipping dispatch for subscription %s",
            event_id,
            subscription_id,
            extra={"event_id": event_id, "webhook_id": subscription_id},
        )
        return False

    event_data = {
        "contract_id": event.contract.contract_id,
        "event_type": event.event_type,
        "payload": event.payload,
        "ledger": event.ledger,
        "event_index": event.event_index,
        "tx_hash": event.tx_hash,
    }
    payload_bytes = json.dumps(event_data, sort_keys=True).encode("utf-8")
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

    attempt_number = self.request.retries + 1
    attempt_logged = False

    try:
        response = requests.post(
            webhook.target_url,
            data=payload_bytes,
            headers=headers,
            timeout=10,
        )
        status_code = response.status_code

        if status_code == 429:
            error_msg = "Rate limited by subscriber (429)"
            _log_delivery_attempt(webhook, event, attempt_number, status_code, False, error_msg)
            attempt_logged = True
            _on_delivery_failure(webhook, self)

            countdown: int | None = None
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    countdown = int(retry_after)
                except (ValueError, TypeError):
                    pass

            raise self.retry(
                exc=requests.HTTPError("Rate limited (429)", response=response),
                countdown=countdown,
            )

        success = 200 <= status_code < 300
        error_msg = "" if success else f"HTTP {status_code}"

        _log_delivery_attempt(webhook, event, attempt_number, status_code, success, error_msg)
        attempt_logged = True

        if success:
            WebhookSubscription.objects.filter(pk=webhook.pk).update(
                failure_count=0,
                last_triggered=timezone.now(),
            )
            logger.info(
                "Webhook %s delivered successfully (attempt %s)",
                subscription_id,
                attempt_number,
                extra={"webhook_id": subscription_id},
            )
            m.task_duration_seconds.labels(task_name="dispatch_webhook").observe(
                time.monotonic() - _start
            )
            return True

        _on_delivery_failure(webhook, self)
        response.raise_for_status()

    except requests.RequestException as exc:
        if not attempt_logged:
            _log_delivery_attempt(webhook, event, attempt_number, None, False, str(exc))
            _on_delivery_failure(webhook, self)

        logger.warning(
            "Webhook %s dispatch failed (attempt %s/%s): %s",
            subscription_id,
            attempt_number,
            self.max_retries + 1,
            exc,
            extra={"webhook_id": subscription_id},
        )
        raise

    m.task_duration_seconds.labels(task_name="dispatch_webhook").observe(
        time.monotonic() - _start
    )
    return False


# ---------------------------------------------------------------------------
# Private helpers for dispatch_webhook
# ---------------------------------------------------------------------------

def _log_delivery_attempt(
    webhook: WebhookSubscription,
    event: ContractEvent,
    attempt_number: int,
    status_code: int | None,
    success: bool,
    error: str,
) -> None:
    """Create a ``WebhookDeliveryLog`` record for one dispatch attempt."""
    from .models import WebhookDeliveryLog

    WebhookDeliveryLog.objects.create(
        subscription=webhook,
        event=event,
        attempt_number=attempt_number,
        status_code=status_code,
        success=success,
        error=error,
    )


def _on_delivery_failure(
    webhook: WebhookSubscription,
    task_instance,
) -> None:
    """
    Atomically increment ``failure_count`` and, when all retries are exhausted,
    mark the subscription as ``suspended`` + ``is_active=False``.
    """
    WebhookSubscription.objects.filter(pk=webhook.pk).update(
        failure_count=F("failure_count") + 1,
    )

    is_last_attempt = task_instance.request.retries >= task_instance.max_retries
    if is_last_attempt:
        WebhookSubscription.objects.filter(pk=webhook.pk).update(
            status=WebhookSubscription.STATUS_SUSPENDED,
            is_active=False,
        )
        logger.error(
            "Webhook subscription %s suspended after %d consecutive failures",
            webhook.id,
            task_instance.max_retries + 1,
            extra={"webhook_id": webhook.id},
        )


@shared_task
def cleanup_webhook_delivery_logs() -> int:
    """
    Prune ``WebhookDeliveryLog`` entries older than 30 days (TTL cleanup).
    """
    from .models import WebhookDeliveryLog

    _start = time.monotonic()
    cutoff = timezone.now() - timedelta(days=30)
    deleted_count, _ = WebhookDeliveryLog.objects.filter(timestamp__lt=cutoff).delete()
    logger.info(
        "Pruned %d WebhookDeliveryLog entries older than 30 days",
        deleted_count,
        extra={},
    )
    _get_metrics().task_duration_seconds.labels(
        task_name="cleanup_webhook_delivery_logs"
    ).observe(time.monotonic() - _start)
    return deleted_count


@shared_task
def process_new_event(event_data: dict[str, Any]) -> None:
    """
    Process a newly indexed event and trigger webhooks.
    """
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    contract_id = event_data.get("contract_id")
    event_type = event_data.get("event_type")

    if not contract_id:
        logger.warning("Event missing contract_id", extra={})
        return

    channel_layer = get_channel_layer()
    if channel_layer:
        try:
            async_to_sync(channel_layer.group_send)(
                f"events_{contract_id}",
                {
                    "type": "contract_event",
                    "data": event_data,
                },
            )
        except Exception as e:
            logger.error(
                "Failed to publish event to channel layer: %s",
                e,
                extra={"contract_id": contract_id},
            )

    webhooks = WebhookSubscription.objects.filter(
        contract__contract_id=contract_id,
        is_active=True,
        status=WebhookSubscription.STATUS_ACTIVE,
    ).filter(
        event_type__in=[event_type, ""]
    )

    if not webhooks.exists():
        logger.info(
            "No active webhooks for contract %s event_type %s",
            contract_id,
            event_type,
            extra={"contract_id": contract_id},
        )
        return

    ledger = event_data.get("ledger")
    event_index = event_data.get("event_index", 0)
    event_obj = None
    if ledger is not None:
        try:
            event_obj = ContractEvent.objects.get(
                contract__contract_id=contract_id,
                ledger=ledger,
                event_index=event_index,
            )
        except ContractEvent.DoesNotExist:
            logger.warning(
                "ContractEvent not found for contract=%s ledger=%s index=%s — skipping webhook dispatch",
                contract_id,
                ledger,
                event_index,
                extra={"contract_id": contract_id},
            )
            return

    if event_obj is None:
        logger.warning(
            "No ledger/event_index in event_data — cannot dispatch webhooks",
            extra={"contract_id": contract_id},
        )
        return

    dispatched = 0
    for webhook in webhooks:
        dispatch_webhook.delay(webhook.id, event_obj.id)
        dispatched += 1

    # Evaluate alert rules asynchronously (separate queue, non-blocking)
    evaluate_alert_rules.apply_async(args=[event_obj.id], queue="default")

    logger.info(
        "Dispatched event to %s webhooks",
        dispatched,
        extra={"contract_id": contract_id},
    )


@shared_task
def sync_events_from_horizon() -> int:
    """
    Sync events from Horizon/Soroban RPC.
    """
    from stellar_sdk import SorobanServer

    _start = time.monotonic()
    m = _get_metrics()

    cursor_state, _ = IndexerState.objects.get_or_create(
        key="horizon_cursor",
        defaults={"value": "now"},
    )
    cursor = cursor_state.value
    server = SorobanServer(settings.SOROBAN_RPC_URL)
    new_events = 0

    try:
        contract_ids = list(
            TrackedContract.objects.filter(is_active=True).values_list("contract_id", flat=True)
        )

        # Always update the gauge, even when there are no active contracts.
        m.active_contracts_gauge.set(len(contract_ids))

        if not contract_ids:
            logger.info("No active contracts to index", extra={})
            return 0

        events_response = server.get_events(
            start_ledger=int(cursor) if cursor.isdigit() else None,
            filters=[
                {
                    "type": "contract",
                    "contractIds": contract_ids,
                }
            ],
            pagination={"limit": 100},
        )

        network = _network_label()
        for fallback_event_index, event in enumerate(events_response.events):
            try:
                contract = TrackedContract.objects.get(contract_id=event.contract_id)
            except TrackedContract.DoesNotExist:
                continue

            payload = event.value
            passed, version_used = validate_event_payload(
                contract, event.type, payload, ledger=event.ledger
            )
            validation_status = "passed" if passed else "failed"
            schema_version = version_used

            event_record, created = ContractEvent.objects.get_or_create(
                tx_hash=event.tx_hash,
                ledger=event.ledger,
                event_type=event.type,
                defaults={
                    "contract": contract,
                    "payload": payload,
                    "timestamp": timezone.now(),
                    "raw_xdr": event.xdr if hasattr(event, "xdr") else "",
                    "validation_status": validation_status,
                    "schema_version": schema_version,
                },
            )
            if not created:
                if (
                    event_record.validation_status != validation_status
                    or event_record.schema_version != schema_version
                ):
                    event_record.validation_status = validation_status
                    event_record.schema_version = schema_version
                    event_record.save(update_fields=["validation_status", "schema_version"])

            if created:
                new_events += 1
                m.events_ingested_total.labels(
                    contract_id=_short_contract_id(contract.contract_id),
                    network=network,
                    event_type=event_record.event_type,
                ).inc()
                process_new_event.delay(
                    {
                        "contract_id": contract.contract_id,
                        "event_type": event_record.event_type,
                        "payload": event_record.payload,
                        "ledger": event_record.ledger,
                        "event_index": event_record.event_index,
                        "tx_hash": event_record.tx_hash,
                    }
                )

            if contract.last_indexed_ledger is None or event_record.ledger > contract.last_indexed_ledger:
                contract.last_indexed_ledger = event_record.ledger
                contract.save(update_fields=["last_indexed_ledger"])

        last_ledger = None
        if events_response.events:
            last_ledger = events_response.events[-1].ledger
            cursor_state.value = str(last_ledger)
            cursor_state.save()

        logger.info(
            "Indexed %s new events",
            new_events,
            extra={"ledger_sequence": last_ledger},
        )

    except Exception:
        logger.exception("Failed to sync events from Horizon", extra={})

    finally:
        # Always record duration, even if an exception occurred.
        m.task_duration_seconds.labels(
            task_name="sync_events_from_horizon"
        ).observe(time.monotonic() - _start)

    return new_events


@shared_task(bind=True, queue="backfill", max_retries=3, default_retry_delay=60)
def backfill_contract_events(
    self,
    contract_id: str,
    from_ledger: int,
    to_ledger: int,
) -> dict[str, Any]:
    """
    Backfill events for one contract within an inclusive ledger range.
    """
    _start = time.monotonic()
    m = _get_metrics()

    start_ledger = _safe_int(from_ledger, default=0)
    end_ledger = _safe_int(to_ledger, default=0)

    if start_ledger <= 0 or end_ledger <= 0 or start_ledger > end_ledger:
        raise ValueError("Invalid ledger range provided")

    try:
        contract = TrackedContract.objects.get(contract_id=contract_id)
    except TrackedContract.DoesNotExist as exc:
        raise ValueError(f"Tracked contract not found: {contract_id}") from exc

    next_ledger = start_ledger
    if contract.last_indexed_ledger is not None:
        next_ledger = max(next_ledger, contract.last_indexed_ledger + 1)

    client = SorobanClient()
    processed_events = 0
    created_events = 0
    updated_events = 0

    try:
        for batch_start in range(next_ledger, end_ledger + 1, BATCH_LEDGER_SIZE):
            batch_end = min(batch_start + BATCH_LEDGER_SIZE - 1, end_ledger)
            batch_events = client.get_events_range(contract.contract_id, batch_start, batch_end)

            if not batch_events:
                logger.warning(
                    "No events returned for contract=%s ledgers=%s-%s",
                    contract.contract_id,
                    batch_start,
                    batch_end,
                )

            for fallback_event_index, event in enumerate(batch_events):
                _, created = _upsert_contract_event(contract, event, fallback_event_index)
                processed_events += 1
                if created:
                    created_events += 1
                else:
                    updated_events += 1

            contract.last_indexed_ledger = batch_end
            contract.save(update_fields=["last_indexed_ledger"])

        # Ensure gauge is fresh after a bulk backfill.
        m.active_contracts_gauge.set(
            TrackedContract.objects.filter(is_active=True).count()
        )
        return {
            "contract_id": contract.contract_id,
            "from_ledger": start_ledger,
            "to_ledger": end_ledger,
            "last_indexed_ledger": contract.last_indexed_ledger,
            "processed_events": processed_events,
            "created_events": created_events,
            "updated_events": updated_events,
        }

    except Exception as exc:
        logger.exception(
            "Backfill failed for contract=%s range=%s-%s",
            contract.contract_id,
            start_ledger,
            end_ledger,
        )
        raise self.retry(exc=exc)
    finally:
        # Always record duration, even if an exception occurred.
        m.task_duration_seconds.labels(
            task_name="backfill_contract_events"
        ).observe(time.monotonic() - _start)


# ---------------------------------------------------------------------------
# Issue: Event-driven alerts — condition evaluator and dispatch tasks
# ---------------------------------------------------------------------------

def _get_field(data: dict, dotted_path: str):
    """Traverse a dot-notation path through nested dicts."""
    current = data
    for part in dotted_path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def evaluate_condition(condition: dict, event_data: dict) -> bool:
    """
    Evaluate a JSON condition AST against flattened event data.

    Supported ops (case-insensitive):
      - Logical: and, or, not
      - Comparison: eq, neq, gt, gte, lt, lte, contains, startswith, in
    """
    op = (condition.get("op") or "").lower()

    if op == "not":
        sub = condition.get("condition", {})
        return not evaluate_condition(sub, event_data)

    if op in ("and", "or"):
        subs = condition.get("conditions", [])
        if op == "and":
            return all(evaluate_condition(c, event_data) for c in subs)
        return any(evaluate_condition(c, event_data) for c in subs)

    # Field comparison
    field = condition.get("field", "")
    value = condition.get("value")
    current = _get_field(event_data, field)

    if op == "eq":
        return str(current) == str(value) if current is not None else str(None) == str(value)
    if op == "neq":
        return str(current) != str(value)
    if op in ("gt", "gte", "lt", "lte"):
        try:
            lhs, rhs = float(str(current)), float(str(value))
            return {"gt": lhs > rhs, "gte": lhs >= rhs, "lt": lhs < rhs, "lte": lhs <= rhs}[op]
        except (TypeError, ValueError):
            return False
    if op == "contains":
        return str(value).lower() in str(current).lower() if current is not None else False
    if op == "startswith":
        return str(current).startswith(str(value)) if current is not None else False
    if op == "in":
        return current in value if isinstance(value, list) else str(current) == str(value)

    logger.warning("Unknown condition op '%s' — treating as False", op)
    return False


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=5,
)
def send_alert(self, rule_id: int, event_id: int) -> str:
    """
    Send a single alert for a matched AlertRule / ContractEvent pair.
    Retries with exponential backoff on failure.
    """
    from .models import AlertRule, AlertExecution

    try:
        rule = AlertRule.objects.select_related("contract").get(id=rule_id, is_active=True)
    except AlertRule.DoesNotExist:
        return "skipped:rule_gone"

    try:
        event = ContractEvent.objects.select_related("contract").get(id=event_id)
    except ContractEvent.DoesNotExist:
        return "skipped:event_gone"

    payload = {
        "rule": rule.name,
        "contract": event.contract.contract_id,
        "event_type": event.event_type,
        "payload": event.payload,
        "ledger": event.ledger,
        "timestamp": event.timestamp.isoformat(),
    }

    try:
        if rule.action_type == "slack":
            _send_slack_alert(rule.action_target, payload)
        elif rule.action_type == "email":
            _send_email_alert(rule.action_target, rule.name, payload)
        elif rule.action_type == "webhook":
            _send_webhook_alert(rule.action_target, payload)
        else:
            raise ValueError(f"Unknown action_type: {rule.action_type}")

        AlertExecution.objects.create(rule=rule, event=event, status="sent", response="ok")
        logger.info(
            "Alert '%s' sent via %s for event %s",
            rule.name,
            rule.action_type,
            event_id,
            extra={"rule_id": rule_id, "event_id": event_id},
        )
        return "sent"

    except Exception as exc:
        AlertExecution.objects.create(
            rule=rule, event=event, status="failed", response=str(exc)[:500]
        )
        logger.warning(
            "Alert '%s' failed (attempt %d): %s",
            rule.name,
            self.request.retries + 1,
            exc,
            extra={"rule_id": rule_id, "event_id": event_id},
        )
        raise


def _send_slack_alert(channel_or_url: str, payload: dict) -> None:
    from django.conf import settings

    text = (
        f"*SoroScan Alert: {payload['rule']}*\n"
        f"Contract: `{payload['contract']}`\n"
        f"Event: `{payload['event_type']}` @ ledger {payload['ledger']}\n"
        f"```{json.dumps(payload['payload'], indent=2)[:800]}```"
    )
    timeout = getattr(settings, "SLACK_ALERT_TIMEOUT_SECONDS", 10)
    resp = requests.post(
        channel_or_url,
        json={"text": text},
        timeout=timeout,
    )
    resp.raise_for_status()


def _send_email_alert(to_addr: str, rule_name: str, payload: dict) -> None:
    from django.core.mail import send_mail

    subject = f"[SoroScan] Alert: {rule_name}"
    body = (
        f"Alert rule '{rule_name}' was triggered.\n\n"
        f"Contract:   {payload['contract']}\n"
        f"Event type: {payload['event_type']}\n"
        f"Ledger:     {payload['ledger']}\n"
        f"Timestamp:  {payload['timestamp']}\n\n"
        f"Payload:\n{json.dumps(payload['payload'], indent=2)}"
    )
    send_mail(
        subject=subject,
        message=body,
        from_email=None,  # uses DEFAULT_FROM_EMAIL
        recipient_list=[to_addr],
        fail_silently=False,
    )


def _send_webhook_alert(url: str, payload: dict) -> None:
    resp = requests.post(url, json=payload, timeout=10)
    resp.raise_for_status()


@shared_task
def evaluate_alert_rules(event_id: int) -> int:
    """
    Check all active AlertRules for the contract that owns *event_id*.
    Dispatches ``send_alert`` tasks for every matching rule.
    Returns the number of rules that matched.
    """
    from .models import AlertRule

    try:
        event = ContractEvent.objects.select_related("contract").get(id=event_id)
    except ContractEvent.DoesNotExist:
        return 0

    rules = AlertRule.objects.filter(
        contract=event.contract,
        is_active=True,
    ).order_by("id")[:AlertRule.MAX_RULES_PER_CONTRACT]

    event_data = {
        "event_type": event.event_type,
        "ledger": event.ledger,
        "payload": event.payload or {},
        # Flatten payload fields under decodedPayload for AST compatibility
        "decodedPayload": event.payload or {},
    }

    matched = 0
    for rule in rules:
        try:
            if evaluate_condition(rule.condition, event_data):
                # Fire-and-forget; exponential backoff handled inside send_alert
                send_alert.apply_async(
                    args=[rule.id, event_id],
                    queue="default",
                )
                matched += 1
        except Exception:
            logger.exception(
                "Error evaluating condition for rule %s", rule.id, extra={"rule_id": rule.id}
            )

    return matched


# ---------------------------------------------------------------------------
# Issue: Performance monitoring — Silk cleanup Celery task
# ---------------------------------------------------------------------------

@shared_task
def cleanup_silk_data() -> int:
    """
    Prune Django Silk Request/Response profiling data older than 7 days.
    Schedule via Celery Beat, e.g. weekly.
    """
    try:
        from silk.models import Request as SilkRequest  # type: ignore[import]
    except ImportError:
        return 0

    cutoff = timezone.now() - timedelta(days=7)
    deleted_count, _ = SilkRequest.objects.filter(start_time__lt=cutoff).delete()
    logger.info(
        "Pruned %d Silk profiling records older than 7 days",
        deleted_count,
        extra={},
    )
    return deleted_count
