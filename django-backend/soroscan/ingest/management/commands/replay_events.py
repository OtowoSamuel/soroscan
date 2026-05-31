"""
Management command: replay_events

Replay ContractEvent records through webhook delivery for debugging and retesting.

Usage:
    python manage.py replay_events --contract=CA7N...
    python manage.py replay_events --contract=CA7N... --event-type=swap
    python manage.py replay_events --contract=CA7N... --from-ledger=100 --to-ledger=200
    python manage.py replay_events --contract=CA7N... --dry-run
    python manage.py replay_events --contract=CA7N... --limit=10

Options:
    --contract          Contract ID (required)
    --event-type        Filter by event type
    --from-ledger       Start ledger (inclusive)
    --to-ledger         End ledger (inclusive)
    --from-date         Start date (ISO format)
    --to-date           End date (ISO format)
    --limit             Max events to replay (default: 100, 0=all)
    --dry-run           Preview without dispatching webhooks
    --webhook-id        Replay only to specific webhook subscription ID
    --output-json       Write delivery report to JSON file instead of stdout
"""
import json
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from soroscan.ingest.models import (
    ContractEvent,
    TrackedContract,
    WebhookSubscription,
    WebhookDeliveryLog,
)


class Command(BaseCommand):
    help = "Replay contract events through webhook delivery for debugging."

    def add_arguments(self, parser):
        parser.add_argument(
            "--contract",
            required=True,
            help="Contract ID to replay events for",
        )
        parser.add_argument(
            "--event-type",
            default=None,
            help="Filter by event type",
        )
        parser.add_argument(
            "--from-ledger",
            type=int,
            default=None,
            help="Include events from this ledger (inclusive)",
        )
        parser.add_argument(
            "--to-ledger",
            type=int,
            default=None,
            help="Include events up to this ledger (inclusive)",
        )
        parser.add_argument(
            "--from-date",
            default=None,
            help="Include events from this date (ISO format)",
        )
        parser.add_argument(
            "--to-date",
            default=None,
            help="Include events up to this date (ISO format)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Max events to replay (default: 100, 0 = all)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview replay plan without dispatching",
        )
        parser.add_argument(
            "--webhook-id",
            type=int,
            default=None,
            help="Replay only to specific webhook subscription ID",
        )
        parser.add_argument(
            "--output-json",
            default=None,
            help="Write delivery report to a JSON file",
        )

    def handle(self, *args, **options):
        contract_id = options["contract"]
        event_type = options["event_type"]
        from_ledger = options["from_ledger"]
        to_ledger = options["to_ledger"]
        from_date = options["from_date"]
        to_date = options["to_date"]
        limit = options["limit"]
        dry_run = options["dry_run"]
        webhook_id = options["webhook_id"]
        output_json = options["output_json"]

        if not TrackedContract.objects.filter(contract_id=contract_id).exists():
            raise CommandError(f"No TrackedContract found with contract_id={contract_id!r}")

        qs = (
            ContractEvent.objects.filter(contract__contract_id=contract_id)
            .select_related("contract")
            .order_by("ledger", "event_index", "timestamp")
        )

        if event_type:
            qs = qs.filter(event_type=event_type)
        if from_ledger is not None:
            qs = qs.filter(ledger__gte=from_ledger)
        if to_ledger is not None:
            qs = qs.filter(ledger__lte=to_ledger)
        if from_date:
            try:
                from_dt = datetime.fromisoformat(from_date)
                if timezone.is_naive(from_dt):
                    from_dt = timezone.make_aware(from_dt)
                qs = qs.filter(timestamp__gte=from_dt)
            except ValueError as exc:
                raise CommandError(f"Invalid --from-date: {exc}")
        if to_date:
            try:
                to_dt = datetime.fromisoformat(to_date)
                if timezone.is_naive(to_dt):
                    to_dt = timezone.make_aware(to_dt)
                qs = qs.filter(timestamp__lte=to_dt)
            except ValueError as exc:
                raise CommandError(f"Invalid --to-date: {exc}")

        total = qs.count()
        if limit > 0:
            qs = qs[:limit]

        events = list(qs)
        if not events:
            self.stdout.write("No events found matching the filters.")
            return

        self.stderr.write(f"Found {total} matching events, replaying {len(events)}...")

        if webhook_id:
            try:
                single_webhook = WebhookSubscription.objects.get(pk=webhook_id)
            except WebhookSubscription.DoesNotExist:
                raise CommandError(f"No WebhookSubscription found with id={webhook_id}")
            if str(single_webhook.contract.contract_id) != str(contract_id):
                raise CommandError(f"Webhook {webhook_id} does not belong to contract {contract_id}")
            webhooks = [single_webhook]
        else:
            webhooks = list(
                WebhookSubscription.objects.filter(
                    contract__contract_id=contract_id,
                    is_active=True,
                )
            )
            if not webhooks:
                self.stdout.write("No active webhooks found for this contract. Nothing to replay.")
                return

        report = {
            "contract_id": contract_id,
            "mode": "dry-run" if dry_run else "live",
            "filters": {
                "event_type": event_type,
                "from_ledger": from_ledger,
                "to_ledger": to_ledger,
                "from_date": from_date,
                "to_date": to_date,
                "limit": limit,
                "webhook_id": webhook_id,
            },
            "summary": {
                "events_processed": 0,
                "webhook_dispatches": 0,
                "successes": 0,
                "failures": 0,
                "skipped": 0,
            },
            "deliveries": [],
        }

        for event in events:
            report["summary"]["events_processed"] += 1
            for webhook in webhooks:
                if event_type and webhook.event_type and webhook.event_type != event_type:
                    continue
                if not webhook.should_ingest_event(event.event_type):
                    report["summary"]["skipped"] += 1
                    continue

                if dry_run:
                    self.stdout.write(
                        f"  [DRY-RUN] Would dispatch event {event.id} ({event.event_type}) "
                        f"to webhook {webhook.id} -> {webhook.target_url}"
                    )
                    report["summary"]["webhook_dispatches"] += 1
                    report["deliveries"].append({
                        "event_id": event.id,
                        "event_type": event.event_type,
                        "ledger": event.ledger,
                        "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                        "webhook_id": webhook.id,
                        "webhook_url": webhook.target_url,
                        "status": "dry-run",
                    })
                else:
                    dispatch_result = self._replay_dispatch(webhook, event)
                    report["summary"]["webhook_dispatches"] += 1
                    if dispatch_result["success"]:
                        report["summary"]["successes"] += 1
                    else:
                        report["summary"]["failures"] += 1
                    report["deliveries"].append({
                        "event_id": event.id,
                        "event_type": event.event_type,
                        "ledger": event.ledger,
                        "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                        "webhook_id": webhook.id,
                        "webhook_url": webhook.target_url,
                        **dispatch_result,
                    })

        # Print summary
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== Replay Summary ==="))
        self.stdout.write(f"Mode:             {'DRY RUN' if dry_run else 'LIVE'}")
        self.stdout.write(f"Events processed: {report['summary']['events_processed']}")
        self.stdout.write(f"Webhook dispatches: {report['summary']['webhook_dispatches']}")
        self.stdout.write(f"Successes:        {report['summary']['successes']}")
        self.stdout.write(f"Failures:         {report['summary']['failures']}")
        self.stdout.write(f"Skipped:          {report['summary']['skipped']}")

        if output_json:
            self._write_report(report, output_json)
        elif not dry_run:
            self.stdout.write("")
            self.stdout.write("Detailed delivery log (last 10):")
            for delivery in report["deliveries"][-10:]:
                status = delivery["status"]
                status_code = delivery.get("status_code")
                if "success" in status:
                    style = self.style.SUCCESS
                elif "fail" in status or (status_code and status_code >= 400):
                    style = self.style.ERROR
                else:
                    def style(x): return x
                self.stdout.write(
                    f"  Event {delivery['event_id']} ({delivery['event_type']}@{delivery['ledger']}) "
                    f"-> Webhook {delivery['webhook_id']}: {style(status)} {status_code or ''}".rstrip()
                )

    def _replay_dispatch(self, webhook: WebhookSubscription, event: ContractEvent) -> dict:
        try:
            from soroscan.ingest.tasks import dispatch_webhook
        except ImportError:
            return {"success": False, "status": "error", "status_code": None, "error": "Celery tasks unavailable"}

        try:
            result = dispatch_webhook.apply(args=[webhook.id, event.id])
            if result.successful():
                return {"success": True, "status": "success", "status_code": None, "error": ""}
            else:
                exc = result.result
                error_msg = str(exc) if exc else "Task failed"
                attempt = WebhookDeliveryLog.objects.filter(
                    subscription=webhook,
                    event=event,
                ).order_by("-attempt_number").first()
                status_code = getattr(attempt, "status_code", None)
                return {"success": False, "status": "failed", "status_code": status_code, "error": error_msg}
        except Exception as exc:
            return {"success": False, "status": "error", "status_code": None, "error": str(exc)}

    def _write_report(self, report: dict, path: str):
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        self.stdout.write(self.style.SUCCESS(f"Report written to {out_path}"))
