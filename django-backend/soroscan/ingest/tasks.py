"""
Celery tasks for SoroScan background processing.
"""
import cProfile
import base64
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
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from celery.signals import task_postrun, task_prerun
from django.conf import settings
from django.db.models import F
from django.utils import timezone

from .models import ContractABI, ContractEvent, ContractSigningKey, TrackedContract, WebhookSubscription, IndexerState, EventSchema, RemediationRule, RemediationIncident, AdminAction
from .rate_limit import check_ingest_rate
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


def _decode_key_or_sig(value: Any) -> bytes | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value

    raw = str(value).strip()
    if not raw:
        return None
    if raw.startswith("0x"):
        raw = raw[2:]

    if len(raw) % 2 == 0 and all(c in "0123456789abcdefABCDEF" for c in raw):
        try:
            return bytes.fromhex(raw)
        except ValueError:
            pass

    try:
        return base64.b64decode(raw, validate=True)
    except Exception:
        return raw.encode("utf-8")


def _extract_signature(event: Any, payload: dict[str, Any]) -> Any:
    return (
        _event_attr(event, "signature", "event_signature")
        or payload.get("signature")
        or payload.get("event_signature")
        or payload.get("sig")
    )


def _message_for_signature(event: Any, payload: dict[str, Any]) -> bytes:
    payload_hash = _event_attr(event, "payload_hash") or payload.get("payload_hash")
    payload_hash_bytes = _decode_key_or_sig(payload_hash)
    if payload_hash_bytes:
        return payload_hash_bytes

    # Build canonical payload bytes excluding signature metadata fields.
    signing_payload = {
        k: v
        for k, v in payload.items()
        if k not in {"signature", "event_signature", "sig"}
    }
    return json.dumps(signing_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _load_signing_public_key(key: ContractSigningKey):
    value = (key.public_key or "").strip()
    if not value:
        return None

    if "-----BEGIN" in value:
        return serialization.load_pem_public_key(value.encode("utf-8"))

    key_bytes = _decode_key_or_sig(value)
    if not key_bytes:
        return None

    if key.algorithm == ContractSigningKey.Algorithm.ED25519:
        return ed25519.Ed25519PublicKey.from_public_bytes(key_bytes)

    # ECDSA flexibility: accept uncompressed points for common curves.
    for curve in (ec.SECP256R1(), ec.SECP256K1()):
        try:
            return ec.EllipticCurvePublicKey.from_encoded_point(curve, key_bytes)
        except ValueError:
            continue
    return None


def resolve_signature_status(
    contract: TrackedContract,
    event: Any,
    payload: dict[str, Any],
) -> str:
    """
    Return one of: valid, invalid, missing.

    Verification never raises and never blocks ingest.
    """
    signing_key = (
        ContractSigningKey.objects.filter(contract=contract, is_active=True)
        .only("algorithm", "public_key")
        .first()
    )
    if signing_key is None:
        return "missing"

    signature_value = _extract_signature(event, payload)
    signature = _decode_key_or_sig(signature_value)
    if not signature:
        return "missing"

    message = _message_for_signature(event, payload)

    try:
        public_key = _load_signing_public_key(signing_key)
        if public_key is None:
            logger.warning(
                "Signing key not usable for contract=%s",
                contract.contract_id,
                extra={"contract_id": contract.contract_id},
            )
            return "invalid"

        if signing_key.algorithm == ContractSigningKey.Algorithm.ED25519:
            public_key.verify(signature, message)
        else:
            public_key.verify(signature, message, ec.ECDSA(hashes.SHA256()))

        return "valid"
    except InvalidSignature:
        logger.warning(
            "Invalid event signature for contract=%s",
            contract.contract_id,
            extra={"contract_id": contract.contract_id},
        )
        return "invalid"
    except Exception:
        logger.warning(
            "Event signature verification error for contract=%s",
            contract.contract_id,
            extra={"contract_id": contract.contract_id},
            exc_info=True,
        )
        return "invalid"


def _upsert_contract_event(
    contract: TrackedContract,
    event: Any,
    fallback_event_index: int = 0,
    client: SorobanClient | None = None,
    batch_cache: dict | None = None,
) -> tuple[ContractEvent, bool]:
    # Check rate limit before processing
    if not check_ingest_rate(contract):
        m = _get_metrics()
        m.events_rate_limited_total.labels(
            contract_id=_short_contract_id(contract.contract_id),
            network=_network_label(),
        ).inc()
        logger.warning(
            "Rate limit exceeded for contract %s — skipping event",
            contract.contract_id,
            extra={"contract_id": contract.contract_id},
        )
        # Return a dummy tuple to indicate the event was skipped
        return (None, False)
    
    ledger = _safe_int(_event_attr(event, "ledger", "ledger_sequence"), default=0)
    event_index = _extract_event_index(event, fallback_event_index)
    tx_hash = str(_event_attr(event, "tx_hash", "transaction_hash", default="") or "")
    event_type = str(_event_attr(event, "type", "event_type", default="unknown") or "unknown")

    # Check whitelist/blacklist filter before persisting
    if not contract.should_ingest_event(event_type):
        m = _get_metrics()
        m.events_filtered_total.labels(
            contract_id=_short_contract_id(contract.contract_id),
            network=_network_label(),
            filter_type=contract.event_filter_type,
            event_type=event_type,
        ).inc()
        logger.debug(
            "Event type '%s' filtered (%s) for contract %s — skipping",
            event_type,
            contract.event_filter_type,
            contract.contract_id,
            extra={"contract_id": contract.contract_id, "event_type": event_type},
        )
        return (None, False)

    payload = _event_attr(event, "value", "payload", default={}) or {}
    raw_xdr = str(_event_attr(event, "xdr", "raw_xdr", default="") or "")
    signature_status = resolve_signature_status(contract, event, payload)

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
            "signature_status": signature_status,
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

        # --- ABI-based XDR decoding (issue #58) ---
        _try_decode_event(obj, contract, event_type, raw_xdr)

    return result


def _try_decode_event(
    obj: ContractEvent,
    contract: TrackedContract,
    event_type: str,
    raw_xdr: str,
) -> None:
    """Attempt ABI decoding for a newly created event.

    Never raises — failures are recorded via ``decoding_status``.
    """
    from .decoder import decode_event_payload

    try:
        abi = ContractABI.objects.get(contract=contract)
    except ContractABI.DoesNotExist:
        # No ABI registered — leave default decoding_status="no_abi"
        return

    if not raw_xdr:
        obj.decoding_status = "no_abi"
        obj.save(update_fields=["decoding_status"])
        return

    try:
        decoded = decode_event_payload(raw_xdr, abi.abi_json, event_type)
        if decoded is not None:
            obj.decoded_payload = decoded
            obj.decoding_status = "success"
        else:
            obj.decoding_status = "failed"
        obj.save(update_fields=["decoded_payload", "decoding_status"])
    except Exception:
        logger.warning(
            "ABI decoding failed for event %s (contract=%s, type=%s)",
            obj.pk,
            contract.contract_id,
            event_type,
            exc_info=True,
        )
        obj.decoding_status = "failed"
        obj.save(update_fields=["decoding_status"])


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
    name="ingest.tasks.dispatch_webhook",
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
            timeout=webhook.timeout_seconds,
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

    except requests.exceptions.Timeout:
        # Log timeout as 504 Gateway Timeout
        if not attempt_logged:
            _log_delivery_attempt(webhook, event, attempt_number, 504, False, "Timeout exceeded")
            attempt_logged = True
            _on_delivery_failure(webhook, self)

        logger.warning(
            "Webhook %s dispatch timed out (attempt %s/%s) after %d seconds",
            subscription_id,
            attempt_number,
            self.max_retries + 1,
            webhook.timeout_seconds,
            extra={"webhook_id": subscription_id},
        )
        raise

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
        # Push in-app notification to the contract owner
        try:
            from .services.notifications import create_and_push
            owner = webhook.contract.owner
            create_and_push(
                user=owner,
                notification_type="webhook_failure",
                title="Webhook Suspended",
                message=(
                    f"Webhook to {webhook.target_url} for contract "
                    f"'{webhook.contract.name}' has been suspended after "
                    f"{task_instance.max_retries + 1} consecutive failures."
                ),
                link=f"/webhooks/{webhook.id}",
            )
        except Exception:
            logger.exception("Failed to create webhook_failure notification for webhook %s", webhook.id)


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
def cleanup_old_dedup_logs(dry_run: bool = False) -> int:
    """
    Prune ``EventDeduplicationLog`` entries older than the configured retention period (TTL cleanup).
    
    Args:
        dry_run: If True, calculate count but don't delete records.
    
    Returns:
        Number of records that were (or would be) deleted.
    """
    from django.conf import settings
    from .models import EventDeduplicationLog

    _start = time.monotonic()
    retention_days = getattr(settings, "DEDUP_LOG_RETENTION_DAYS", 90)
    cutoff = timezone.now() - timedelta(days=retention_days)
    
    # Get the count of records that would be deleted
    records_to_delete = EventDeduplicationLog.objects.filter(created_at__lt=cutoff)
    deleted_count = records_to_delete.count()
    
    if not dry_run:
        # Actually delete the records
        deleted_count, _ = records_to_delete.delete()
    
    logger.info(
        "Pruned %d EventDeduplicationLog entries older than %d days (dry_run=%s)",
        deleted_count,
        retention_days,
        dry_run,
        extra={"deletion_count": deleted_count, "retention_days": retention_days, "dry_run": dry_run},
    )
    _get_metrics().task_duration_seconds.labels(
        task_name="cleanup_old_dedup_logs"
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


@shared_task(name="ingest.tasks.ingest_latest_events")
def ingest_latest_events() -> int:
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

            # Check rate limit before processing
            if not check_ingest_rate(contract):
                m.events_rate_limited_total.labels(
                    contract_id=_short_contract_id(contract.contract_id),
                    network=network,
                ).inc()
                logger.warning(
                    "Rate limit exceeded for contract %s — skipping event",
                    contract.contract_id,
                    extra={"contract_id": contract.contract_id},
                )
                continue

            # Check whitelist/blacklist filter before persisting
            if not contract.should_ingest_event(event.type):
                m.events_filtered_total.labels(
                    contract_id=_short_contract_id(contract.contract_id),
                    network=network,
                    filter_type=contract.event_filter_type,
                    event_type=event.type,
                ).inc()
                logger.debug(
                    "Event type '%s' filtered (%s) for contract %s — skipping",
                    event.type,
                    contract.event_filter_type,
                    contract.contract_id,
                    extra={"contract_id": contract.contract_id, "event_type": event.type},
                )
                continue

            payload = event.value
            passed, version_used = validate_event_payload(
                contract, event.type, payload, ledger=event.ledger
            )
            validation_status = "passed" if passed else "failed"
            schema_version = version_used
            signature_status = resolve_signature_status(
                contract,
                event,
                payload,
            )

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
                    "signature_status": signature_status,
                },
            )
            
            # Update validation status if needed
            if not created:
                if (
                    event_record.validation_status != validation_status
                    or event_record.schema_version != schema_version
                    or event_record.signature_status != signature_status
                ):
                    event_record.validation_status = validation_status
                    event_record.schema_version = schema_version
                    event_record.signature_status = signature_status
                    event_record.save(update_fields=["validation_status", "schema_version", "signature_status"])

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
            task_name="ingest_latest_events"
        ).observe(time.monotonic() - _start)

    return new_events


@shared_task(name="ingest.tasks.aggregate_event_statistics")
def aggregate_event_statistics() -> dict[str, Any]:
    """
    Perform analytics aggregation on ingested events (Low Priority).
    """
    _start = time.monotonic()
    m = _get_metrics()
    
    # Placeholder for actual aggregation logic
    total_events = ContractEvent.objects.count()
    active_contracts = TrackedContract.objects.filter(is_active=True).count()
    
    logger.info(
        "Aggregated statistics: %d events across %d contracts",
        total_events,
        active_contracts,
        extra={"total_events": total_events, "active_contracts": active_contracts},
    )
    
    m.task_duration_seconds.labels(
        task_name="aggregate_event_statistics"
    ).observe(time.monotonic() - _start)
    
    return {
        "total_events": total_events,
        "active_contracts": active_contracts,
        "timestamp": timezone.now().isoformat(),
    }


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
            
            # Create batch_cache for this batch to avoid redundant RPC calls
            batch_cache = {}

            if not batch_events:
                logger.warning(
                    "No events returned for contract=%s ledgers=%s-%s",
                    contract.contract_id,
                    batch_start,
                    batch_end,
                )

            for fallback_event_index, event in enumerate(batch_events):
                result = _upsert_contract_event(
                    contract, event, fallback_event_index, client=client, batch_cache=batch_cache
                )
                # Handle rate-limited events (returns None, False)
                if result[0] is None:
                    continue
                _, created = result
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


@shared_task(bind=True, queue="backfill")
def reprocess_events(
    self,
    contract_id: str,
    dry_run: bool = False,
    batch_size: int = 500,
    checkpoint_id: int = 0,
    rollback_on_error: bool = True,
) -> dict[str, Any]:
    """Reprocess historical events for a contract in batches."""
    from .reprocessing import reprocess_contract_events  # noqa: PLC0415

    result = reprocess_contract_events(
        contract_id,
        dry_run=dry_run,
        batch_size=batch_size,
        checkpoint_id=checkpoint_id,
        rollback_on_error=rollback_on_error,
    )
    return {
        "contract_id": result.contract_id,
        "total_events": result.total_events,
        "processed_events": result.processed_events,
        "updated_events": result.updated_events,
        "failed_events": result.failed_events,
        "last_checkpoint_id": result.last_checkpoint_id,
        "progress_percent": result.progress_percent,
        "dry_run": result.dry_run,
        "rolled_back": result.rolled_back,
    }


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


def _alert_channel_targets(rule) -> list[tuple[str, str]]:
    """
    Build (action_type, target) pairs: multi-channel JSON or legacy single field.
    """
    raw = getattr(rule, "channels", None) or []
    if isinstance(raw, list) and len(raw) > 0:
        out: list[tuple[str, str]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            ch_type = (item.get("type") or "").strip().lower()
            target = (item.get("target") or "").strip()
            if ch_type in ("slack", "email", "webhook") and target:
                out.append((ch_type, target))
        if out:
            return out
    if rule.action_target:
        return [(rule.action_type, rule.action_target)]
    return []


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=5,
)
def send_alert(self, rule_id: int, event_id: int) -> str:
    """
    Send alert(s) for a matched AlertRule / ContractEvent pair.
    When ``channels`` is set, delivers to email, Slack, and webhook in one task
    (real-time via the existing Celery path). Retries with exponential backoff
    if any channel fails.
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

    targets = _alert_channel_targets(rule)
    if not targets:
        logger.warning(
            "Alert rule %s has no channels or action_target",
            rule_id,
            extra={"rule_id": rule_id, "event_id": event_id},
        )
        return "skipped:no_targets"

    successes = 0
    failures: list[Exception] = []

    for action_type, target in targets:
        try:
            if action_type == "slack":
                _send_slack_alert(target, payload)
            elif action_type == "email":
                _send_email_alert(target, rule.name, payload)
            elif action_type == "webhook":
                _send_webhook_alert(target, payload)
            else:
                raise ValueError(f"Unknown action_type: {action_type}")
            AlertExecution.objects.create(
                rule=rule, event=event, status="sent", response="ok", channel=action_type
            )
            successes += 1
        except Exception as exc:
            failures.append(exc)
            AlertExecution.objects.create(
                rule=rule,
                event=event,
                status="failed",
                response=str(exc)[:500],
                channel=action_type,
            )

    if successes:
        logger.info(
            "Alert '%s': %d/%d channel(s) ok for event %s",
            rule.name,
            successes,
            len(targets),
            event_id,
            extra={"rule_id": rule_id, "event_id": event_id},
        )

    if failures and successes == 0:
        err = failures[0]
        logger.warning(
            "Alert '%s' all channels failed (attempt %d): %s",
            rule.name,
            self.request.retries + 1,
            err,
            extra={"rule_id": rule_id, "event_id": event_id},
        )
        raise err

    if failures:
        logger.warning(
            "Alert '%s' partial failure: %s",
            rule.name,
            failures[0],
            extra={"rule_id": rule_id, "event_id": event_id},
        )

    return "sent" if successes else "failed"


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
# Automated incident response (remediation)
# ---------------------------------------------------------------------------

def _send_ops_alert(alert_type: str, target: str, message: str, payload: dict[str, Any]) -> None:
    if not target:
        logger.warning("Remediation alert target is empty; skipping alert")
        return

    if alert_type == RemediationRule.ALERT_SLACK:
        timeout = getattr(settings, "SLACK_ALERT_TIMEOUT_SECONDS", 10)
        resp = requests.post(target, json={"text": f"{message}\n```{json.dumps(payload, indent=2)[:1500]}```"}, timeout=timeout)
        resp.raise_for_status()
        return

    if alert_type == RemediationRule.ALERT_EMAIL:
        from django.core.mail import send_mail

        send_mail(
            subject="[SoroScan] Automated remediation alert",
            message=f"{message}\n\n{json.dumps(payload, indent=2)}",
            from_email=None,
            recipient_list=[target],
            fail_silently=False,
        )
        return

    if alert_type == RemediationRule.ALERT_WEBHOOK:
        resp = requests.post(target, json={"message": message, "payload": payload}, timeout=10)
        resp.raise_for_status()
        return

    logger.warning("Unknown remediation alert type: %s", alert_type)


def _resolve_contract_for_rule(rule: RemediationRule) -> TrackedContract | None:
    contract_id = (rule.condition or {}).get("contract_id")
    if not contract_id:
        return None
    return TrackedContract.objects.filter(contract_id=contract_id).first()


def _detect_anomaly(rule: RemediationRule, contract: TrackedContract) -> tuple[bool, dict[str, Any]]:
    condition = rule.condition or {}
    condition_type = condition.get("type")
    now = timezone.now()

    if condition_type == RemediationRule.CONDITION_NO_EVENTS:
        minutes = int(condition.get("minutes", 60))
        cutoff = now - timedelta(minutes=minutes)
        has_recent = ContractEvent.objects.filter(contract=contract, timestamp__gte=cutoff).exists()
        return (not has_recent, {"type": condition_type, "minutes": minutes, "cutoff": cutoff.isoformat()})

    if condition_type == RemediationRule.CONDITION_DECODE_ERROR_SPIKE:
        window_minutes = int(condition.get("window_minutes", 60))
        threshold_percent = float(condition.get("threshold_percent", 50))
        min_events = int(condition.get("min_events", 10))
        cutoff = now - timedelta(minutes=window_minutes)
        qs = ContractEvent.objects.filter(contract=contract, timestamp__gte=cutoff)
        total = qs.count()
        failed = qs.filter(decoding_status="failed").count()
        ratio = (failed / total * 100.0) if total > 0 else 0.0
        triggered = total >= min_events and ratio >= threshold_percent
        return (
            triggered,
            {
                "type": condition_type,
                "window_minutes": window_minutes,
                "threshold_percent": threshold_percent,
                "min_events": min_events,
                "total": total,
                "failed": failed,
                "ratio": ratio,
            },
        )

    logger.warning("Unknown remediation condition type for rule=%s", rule.id)
    return (False, {"type": condition_type, "error": "unknown_condition_type"})


def _execute_remediation_actions(
    incident: RemediationIncident,
    *,
    effective_dry_run: bool,
) -> list[dict[str, Any]]:
    executed: list[dict[str, Any]] = []

    for action in incident.rule.actions or []:
        action_type = (action or {}).get("type")
        entry: dict[str, Any] = {"type": action_type, "dry_run": effective_dry_run, "status": "skipped"}

        if action_type == "pause_contract":
            if not effective_dry_run:
                incident.contract.is_active = False
                incident.contract.save(update_fields=["is_active"])
            entry["status"] = "executed"

        elif action_type == "disable_webhooks":
            if not effective_dry_run:
                disabled = WebhookSubscription.objects.filter(contract=incident.contract, is_active=True).update(
                    is_active=False,
                    status=WebhookSubscription.STATUS_SUSPENDED,
                )
                entry["disabled_count"] = disabled
            entry["status"] = "executed"

        elif action_type == "send_alert":
            target = action.get("target") or incident.rule.alert_target
            alert_type = action.get("alert_type") or incident.rule.alert_type
            message = action.get("message") or (
                f"Remediation action requested for rule '{incident.rule.name}' "
                f"on contract {incident.contract.contract_id}"
            )
            if not effective_dry_run:
                _send_ops_alert(
                    alert_type,
                    target,
                    message,
                    {
                        "rule_id": incident.rule_id,
                        "incident_id": incident.id,
                        "contract_id": incident.contract.contract_id,
                        "snapshot": incident.anomaly_snapshot,
                    },
                )
            entry["status"] = "executed"

        else:
            entry["error"] = "unknown_action"

        executed.append(entry)

    return executed


@shared_task
def evaluate_remediation_rules(dry_run: bool = False) -> dict[str, Any]:
    """
    Evaluate remediation rules and execute actions after grace period.

    Flow:
      1. Detect anomaly from rule.condition
      2. Alert ops immediately (always before actions)
      3. Wait grace_period_minutes
      4. Execute actions (or simulate in dry-run)
    """
    now = timezone.now()
    summary = {
        "evaluated": 0,
        "detected": 0,
        "alerted": 0,
        "executed": 0,
        "resolved": 0,
        "dry_run": dry_run,
    }

    rules = RemediationRule.objects.filter(enabled=True).order_by("id")

    for rule in rules:
        summary["evaluated"] += 1
        contract = _resolve_contract_for_rule(rule)
        if contract is None:
            continue

        triggered, snapshot = _detect_anomaly(rule, contract)

        open_incident = (
            RemediationIncident.objects.filter(
                rule=rule,
                contract=contract,
                status__in=[RemediationIncident.STATUS_ALERTED, RemediationIncident.STATUS_EXECUTED],
                resolved_at__isnull=True,
            )
            .order_by("-first_detected_at")
            .first()
        )

        if not triggered:
            if open_incident and open_incident.status != RemediationIncident.STATUS_RESOLVED:
                open_incident.status = RemediationIncident.STATUS_RESOLVED
                open_incident.resolved_at = now
                open_incident.save(update_fields=["status", "resolved_at", "last_seen_at"])
                AdminAction.objects.create(
                    user=None,
                    action="remediation_resolved",
                    object_type="tracked_contract",
                    object_id=str(contract.pk),
                    ip_address="0.0.0.0",
                    changes={"rule_id": rule.id, "incident_id": open_incident.id},
                )
                summary["resolved"] += 1
            continue

        summary["detected"] += 1

        if open_incident is None:
            open_incident = RemediationIncident.objects.create(
                rule=rule,
                contract=contract,
                status=RemediationIncident.STATUS_ALERTED,
                anomaly_snapshot=snapshot,
                alerted_at=now,
                action_after_at=now + timedelta(minutes=rule.grace_period_minutes),
            )
            summary["alerted"] += 1

            message = (
                f"Remediation alert: anomaly detected for rule '{rule.name}' on contract "
                f"{contract.contract_id}. Actions scheduled after {rule.grace_period_minutes} minute(s)."
            )
            try:
                _send_ops_alert(rule.alert_type, rule.alert_target, message, snapshot)
            except Exception:
                logger.warning("Failed to send remediation pre-alert for rule=%s", rule.id, exc_info=True)

            AdminAction.objects.create(
                user=None,
                action="remediation_alerted",
                object_type="tracked_contract",
                object_id=str(contract.pk),
                ip_address="0.0.0.0",
                changes={
                    "rule_id": rule.id,
                    "incident_id": open_incident.id,
                    "grace_period_minutes": rule.grace_period_minutes,
                    "snapshot": snapshot,
                },
            )
            continue

        if open_incident.status == RemediationIncident.STATUS_EXECUTED:
            open_incident.last_seen_at = now
            open_incident.save(update_fields=["last_seen_at"])
            continue

        if open_incident.action_after_at and now < open_incident.action_after_at:
            continue

        effective_dry_run = dry_run or rule.dry_run
        executed = _execute_remediation_actions(open_incident, effective_dry_run=effective_dry_run)

        open_incident.status = RemediationIncident.STATUS_EXECUTED
        open_incident.executed_at = now
        open_incident.anomaly_snapshot = snapshot
        open_incident.save(update_fields=["status", "executed_at", "anomaly_snapshot", "last_seen_at"])

        AdminAction.objects.create(
            user=None,
            action="remediation_executed",
            object_type="tracked_contract",
            object_id=str(contract.pk),
            ip_address="0.0.0.0",
            changes={
                "rule_id": rule.id,
                "incident_id": open_incident.id,
                "dry_run": effective_dry_run,
                "actions": executed,
            },
        )
        summary["executed"] += 1

    return summary


# ---------------------------------------------------------------------------
# Issue: Performance monitoring — Silk cleanup Celery task
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Data Retention — archive_old_events periodic task
# ---------------------------------------------------------------------------

_MAX_BATCH_BYTES = 100 * 1024 * 1024  # 100 MB compressed limit per S3 object


def _upload_to_s3(bucket: str, key: str, data: bytes) -> int:
    """Upload *data* to S3 and return the byte size uploaded."""
    import boto3  # noqa: PLC0415

    s3 = boto3.client(
        "s3",
        region_name=getattr(settings, "AWS_S3_REGION_NAME", None),
        endpoint_url=getattr(settings, "AWS_S3_ENDPOINT_URL", None),
        aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None),
        aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
    )
    s3.put_object(Bucket=bucket, Key=key, Body=data, ContentEncoding="gzip", ContentType="application/json")
    return len(data)


def _export_batch_to_s3(
    events_qs,
    policy,
    batch_index: int,
) -> Any:
    """
    Serialize up to 10 000 events from *events_qs* into a gzip-compressed
    JSON batch, upload to S3, and return an ArchivedEventBatch record.

    Returns None if the queryset is empty.
    """
    import gzip  # noqa: PLC0415
    from .models import ArchivedEventBatch, ArchivalAuditLog  # noqa: PLC0415

    rows = list(
        events_qs.values(
            "id", "contract__contract_id", "event_type", "payload",
            "payload_hash", "ledger", "event_index", "timestamp", "tx_hash",
        )
    )
    if not rows:
        return None

    # Serialize timestamps to ISO strings for JSON compatibility
    for row in rows:
        ts = row.get("timestamp")
        if ts is not None:
            row["timestamp"] = ts.isoformat()

    raw_json = json.dumps(rows, default=str).encode("utf-8")
    compressed = gzip.compress(raw_json)

    if len(compressed) > _MAX_BATCH_BYTES:
        logger.warning(
            "Archive batch %d for policy %d exceeds 100 MB (%d bytes) — splitting not yet supported",
            batch_index,
            policy.id,
            len(compressed),
        )

    contract_slug = (
        policy.contract.contract_id[:12] if policy.contract else "global"
    )
    key = (
        f"{policy.s3_prefix.rstrip('/')}/{contract_slug}/"
        f"batch_{policy.id}_{batch_index}_{int(timezone.now().timestamp())}.json.gz"
    )

    size_bytes = _upload_to_s3(policy.s3_bucket, key, compressed)

    timestamps = [r["timestamp"] for r in rows if r.get("timestamp")]
    timestamps_sorted = sorted(timestamps)

    from django.utils.dateparse import parse_datetime  # noqa: PLC0415

    batch = ArchivedEventBatch.objects.create(
        policy=policy,
        s3_key=key,
        event_count=len(rows),
        size_bytes=size_bytes,
        min_timestamp=parse_datetime(timestamps_sorted[0]) if timestamps_sorted else None,
        max_timestamp=parse_datetime(timestamps_sorted[-1]) if timestamps_sorted else None,
    )

    ArchivalAuditLog.objects.create(
        action=ArchivalAuditLog.ACTION_ARCHIVE,
        batch=batch,
        policy=policy,
        event_count=len(rows),
        detail=f"Uploaded to s3://{policy.s3_bucket}/{key}",
    )

    return batch


@shared_task
def archive_old_events() -> dict:
    """
    Periodic task: for each active DataRetentionPolicy, archive events older
    than retention_days to S3 (gzip-compressed JSON) then delete them from PG.

    Runs daily via Celery Beat.
    """
    from .models import DataRetentionPolicy, ArchivalAuditLog  # noqa: PLC0415

    _start = time.monotonic()
    total_archived = 0
    total_deleted = 0
    errors = []

    policies = DataRetentionPolicy.objects.filter(archive_enabled=True).select_related("contract")

    for policy in policies:
        try:
            cutoff = timezone.now() - timedelta(days=policy.retention_days)
            base_qs = ContractEvent.objects.filter(timestamp__lt=cutoff)
            if policy.contract:
                base_qs = base_qs.filter(contract=policy.contract)

            batch_index = 0
            while True:
                batch_qs = base_qs.order_by("timestamp")[:10000]
                batch = _export_batch_to_s3(batch_qs, policy, batch_index)
                if batch is None:
                    break

                # Delete only the IDs we just archived
                archived_ids = list(
                    base_qs.order_by("timestamp").values_list("id", flat=True)[:10000]
                )
                deleted_count, _ = ContractEvent.objects.filter(id__in=archived_ids).delete()
                total_archived += batch.event_count
                total_deleted += deleted_count
                batch_index += 1

                logger.info(
                    "Archived batch %d for policy %d: %d events → s3://%s/%s",
                    batch_index,
                    policy.id,
                    batch.event_count,
                    policy.s3_bucket,
                    batch.s3_key,
                )

        except Exception as exc:
            err_msg = f"Policy {policy.id}: {exc}"
            errors.append(err_msg)
            logger.exception("archive_old_events failed for policy %d", policy.id)
            ArchivalAuditLog.objects.create(
                action=ArchivalAuditLog.ACTION_ARCHIVE,
                policy=policy,
                event_count=0,
                detail=f"ERROR: {str(exc)[:500]}",
            )

    elapsed = time.monotonic() - _start
    logger.info(
        "archive_old_events complete: archived=%d deleted=%d errors=%d elapsed=%.2fs",
        total_archived,
        total_deleted,
        len(errors),
        elapsed,
    )
    return {"archived": total_archived, "deleted": total_deleted, "errors": errors}


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
