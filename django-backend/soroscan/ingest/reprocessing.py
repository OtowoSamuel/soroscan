"""Event reprocessing helpers for historical decode and validation updates."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db import transaction

from .models import AdminAction, ContractEvent, TrackedContract
from .tasks import _try_decode_event, resolve_signature_status, validate_event_payload

logger = logging.getLogger(__name__)


@dataclass
class ReprocessResult:
    contract_id: str
    total_events: int
    processed_events: int
    updated_events: int
    failed_events: int
    last_checkpoint_id: int
    progress_percent: int
    dry_run: bool
    rolled_back: bool


def _progress(processed: int, total: int) -> int:
    if total <= 0:
        return 100
    return int((processed / total) * 100)


def reprocess_contract_events(
    contract_id: str,
    *,
    dry_run: bool = False,
    batch_size: int = 500,
    checkpoint_id: int = 0,
    rollback_on_error: bool = True,
) -> ReprocessResult:
    """
    Re-run decode/validation/signature checks on historical events in batches.

    Does not pause live indexing. Reprocessing runs in bounded transactions with
    checkpoints so progress can be resumed safely.
    """
    contract = TrackedContract.objects.get(contract_id=contract_id)

    queryset = ContractEvent.objects.filter(contract=contract).order_by("id")
    if checkpoint_id > 0:
        queryset = queryset.filter(id__gt=checkpoint_id)

    total_events = queryset.count()
    processed = 0
    updated = 0
    failed = 0
    last_checkpoint = checkpoint_id
    rolled_back = False

    AdminAction.objects.create(
        user=None,
        action="reprocess_events_started",
        object_type="tracked_contract",
        object_id=str(contract.pk),
        ip_address="0.0.0.0",
        changes={
            "contract_id": contract.contract_id,
            "dry_run": dry_run,
            "batch_size": batch_size,
            "checkpoint_id": checkpoint_id,
        },
    )

    try:
        outer_ctx = transaction.atomic()
        with outer_ctx:
            while True:
                batch = list(queryset.filter(id__gt=last_checkpoint)[:batch_size])
                if not batch:
                    break

                try:
                    with transaction.atomic():
                        for event in batch:
                            changed_fields: list[str] = []

                            passed, schema_version = validate_event_payload(
                                contract,
                                event.event_type,
                                event.payload,
                                ledger=event.ledger,
                            )
                            new_validation_status = "passed" if passed else "failed"
                            if event.validation_status != new_validation_status:
                                event.validation_status = new_validation_status
                                changed_fields.append("validation_status")

                            if event.schema_version != schema_version:
                                event.schema_version = schema_version
                                changed_fields.append("schema_version")

                            payload_dict = event.payload if isinstance(event.payload, dict) else {}
                            signature_status = resolve_signature_status(
                                contract,
                                {"signature": payload_dict.get("signature")},
                                payload_dict,
                            )
                            if event.signature_status != signature_status:
                                event.signature_status = signature_status
                                changed_fields.append("signature_status")

                            if changed_fields:
                                event.save(update_fields=changed_fields)
                                updated += 1

                            # Re-run ABI decoding with latest ABI.
                            _try_decode_event(event, contract, event.event_type, event.raw_xdr)

                            processed += 1
                            last_checkpoint = event.id

                except Exception:
                    logger.warning(
                        "Reprocessing batch failed for contract=%s at checkpoint=%s",
                        contract.contract_id,
                        last_checkpoint,
                        exc_info=True,
                    )
                    failed += len(batch)
                    if rollback_on_error:
                        rolled_back = True
                        raise

            if dry_run:
                transaction.set_rollback(True)
    except Exception as exc:
        AdminAction.objects.create(
            user=None,
            action="reprocess_events_failed",
            object_type="tracked_contract",
            object_id=str(contract.pk),
            ip_address="0.0.0.0",
            changes={
                "contract_id": contract.contract_id,
                "last_checkpoint_id": last_checkpoint,
                "error": str(exc),
            },
        )
        raise

    result = ReprocessResult(
        contract_id=contract.contract_id,
        total_events=total_events,
        processed_events=processed,
        updated_events=updated,
        failed_events=failed,
        last_checkpoint_id=last_checkpoint,
        progress_percent=_progress(processed, total_events),
        dry_run=dry_run,
        rolled_back=rolled_back or dry_run,
    )

    AdminAction.objects.create(
        user=None,
        action="reprocess_events_completed",
        object_type="tracked_contract",
        object_id=str(contract.pk),
        ip_address="0.0.0.0",
        changes={
            "contract_id": result.contract_id,
            "total_events": result.total_events,
            "processed_events": result.processed_events,
            "updated_events": result.updated_events,
            "failed_events": result.failed_events,
            "last_checkpoint_id": result.last_checkpoint_id,
            "progress_percent": result.progress_percent,
            "dry_run": result.dry_run,
            "rolled_back": result.rolled_back,
        },
    )

    return result
