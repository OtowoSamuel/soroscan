"""
Celery tasks for SoroScan background processing.
"""
import hashlib
import hmac
import logging
from datetime import datetime
from typing import Any

import jsonschema
import requests
from celery import shared_task
from django.utils import timezone

from .models import ContractEvent, EventSchema, TrackedContract, WebhookSubscription, IndexerState

logger = logging.getLogger(__name__)


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


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def dispatch_webhook(self, event_data: dict[str, Any], webhook_id: int) -> bool:
    """
    Send event data to a webhook subscriber.

    Args:
        event_data: The event payload to send
        webhook_id: ID of the WebhookSubscription

    Returns:
        True if successful, False otherwise
    """
    try:
        webhook = WebhookSubscription.objects.get(id=webhook_id, is_active=True)
    except WebhookSubscription.DoesNotExist:
        logger.warning(f"Webhook {webhook_id} not found or inactive")
        return False

    # Generate HMAC signature
    payload_str = str(event_data).encode("utf-8")
    signature = hmac.new(
        webhook.secret.encode("utf-8"),
        msg=payload_str,
        digestmod=hashlib.sha256,
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-SoroScan-Signature": signature,
        "X-SoroScan-Timestamp": datetime.utcnow().isoformat(),
    }

    try:
        response = requests.post(
            webhook.target_url,
            json=event_data,
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()

        # Update success state
        webhook.last_triggered = timezone.now()
        webhook.failure_count = 0
        webhook.save(update_fields=["last_triggered", "failure_count"])

        logger.info(f"Webhook {webhook_id} delivered successfully")
        return True

    except requests.RequestException as exc:
        # Update failure count
        webhook.failure_count += 1
        webhook.save(update_fields=["failure_count"])

        # Disable webhook after too many failures
        if webhook.failure_count >= 10:
            webhook.is_active = False
            webhook.save(update_fields=["is_active"])
            logger.error(f"Webhook {webhook_id} disabled after {webhook.failure_count} failures")
            return False

        logger.warning(f"Webhook {webhook_id} failed, retrying: {exc}")
        raise self.retry(exc=exc)


@shared_task
def process_new_event(event_data: dict[str, Any]) -> None:
    """
    Process a newly indexed event and trigger webhooks.

    Args:
        event_data: Decoded event data from the ledger
    """
    contract_id = event_data.get("contract_id")
    event_type = event_data.get("event_type")

    if not contract_id:
        logger.warning("Event missing contract_id")
        return

    # Find matching webhooks
    webhooks = WebhookSubscription.objects.filter(
        contract__contract_id=contract_id,
        is_active=True,
    ).filter(
        # Match specific event type or all events (blank event_type)
        event_type__in=[event_type, ""]
    )

    # Dispatch to all matching webhooks
    for webhook in webhooks:
        dispatch_webhook.delay(event_data, webhook.id)

    logger.info(f"Dispatched event to {webhooks.count()} webhooks")


@shared_task
def sync_events_from_horizon() -> int:
    """
    Sync events from Horizon/Soroban RPC.

    This task runs periodically to fetch new events from the ledger
    and store them in the database.

    Returns:
        Number of new events indexed
    """
    from stellar_sdk import SorobanServer
    from django.conf import settings

    # Get last processed cursor
    cursor_state, _ = IndexerState.objects.get_or_create(
        key="horizon_cursor",
        defaults={"value": "now"},
    )
    cursor = cursor_state.value

    server = SorobanServer(settings.SOROBAN_RPC_URL)
    new_events = 0

    try:
        # Get list of tracked contract IDs
        contract_ids = list(
            TrackedContract.objects.filter(is_active=True).values_list("contract_id", flat=True)
        )

        if not contract_ids:
            logger.info("No active contracts to index")
            return 0

        # Fetch events from Soroban RPC
        # Note: Actual implementation depends on stellar-sdk version
        # This is a simplified example
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

        for event in events_response.events:
            # Find the tracked contract
            try:
                contract = TrackedContract.objects.get(contract_id=event.contract_id)
            except TrackedContract.DoesNotExist:
                continue

            payload = event.value  # Decoded payload
            passed, version_used = validate_event_payload(
                contract, event.type, payload, ledger=event.ledger
            )
            validation_status = "passed" if passed else "failed"
            schema_version = version_used

            # Create or get event record
            event_record, created = ContractEvent.objects.get_or_create(
                tx_hash=event.tx_hash,
                ledger=event.ledger,
                event_type=event.type,
                defaults={
                    "contract": contract,
                    "payload": payload,
                    "timestamp": timezone.now(),  # Should parse from ledger
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
                # Trigger webhooks for new events
                process_new_event.delay(
                    {
                        "contract_id": contract.contract_id,
                        "event_type": event_record.event_type,
                        "payload": event_record.payload,
                        "ledger": event_record.ledger,
                        "tx_hash": event_record.tx_hash,
                    }
                )

        # Update cursor
        if events_response.events:
            cursor_state.value = str(events_response.events[-1].ledger)
            cursor_state.save()

        logger.info(f"Indexed {new_events} new events")
        return new_events

    except Exception as e:
        logger.exception("Failed to sync events from Horizon")
        return 0
