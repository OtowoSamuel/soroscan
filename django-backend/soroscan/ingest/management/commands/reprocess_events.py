from django.core.management.base import BaseCommand, CommandError

from soroscan.ingest.reprocessing import reprocess_contract_events


class Command(BaseCommand):
    help = "Reprocess historical events (decode, validation, signature verification)."

    def add_arguments(self, parser):
        parser.add_argument("--contract-id", required=True, help="Target tracked contract ID")
        parser.add_argument("--dry-run", action="store_true", help="Run without committing changes")
        parser.add_argument("--batch-size", type=int, default=500, help="Batch size for processing")
        parser.add_argument(
            "--checkpoint-id",
            type=int,
            default=0,
            help="Resume from events with id > checkpoint-id",
        )
        parser.add_argument(
            "--rollback-on-error",
            action="store_true",
            help="Rollback current batch and abort on first processing error",
        )

    def handle(self, *args, **options):
        contract_id = options["contract_id"]
        dry_run = options["dry_run"]
        batch_size = options["batch_size"]
        checkpoint_id = options["checkpoint_id"]
        rollback_on_error = options["rollback_on_error"]

        if batch_size <= 0:
            raise CommandError("--batch-size must be greater than 0")
        if checkpoint_id < 0:
            raise CommandError("--checkpoint-id must be >= 0")

        result = reprocess_contract_events(
            contract_id,
            dry_run=dry_run,
            batch_size=batch_size,
            checkpoint_id=checkpoint_id,
            rollback_on_error=rollback_on_error,
        )

        self.stdout.write(
            self.style.SUCCESS(
                "reprocess_events completed: "
                f"contract={result.contract_id} "
                f"processed={result.processed_events}/{result.total_events} "
                f"updated={result.updated_events} "
                f"failed={result.failed_events} "
                f"progress={result.progress_percent}% "
                f"checkpoint={result.last_checkpoint_id} "
                f"dry_run={result.dry_run} "
                f"rolled_back={result.rolled_back}"
            )
        )
