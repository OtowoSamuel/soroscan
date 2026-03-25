"""
Management command: export_events

Streams ContractEvent rows to Parquet, CSV, JSON, or Avro without loading
all events into memory.

Usage examples:
    python manage.py export_events --contract-id CXXX --format json --output events.json
    python manage.py export_events --contract-id CXXX --format parquet --output events.parquet \
        --start-ledger 1000000 --end-ledger 2000000
"""
from django.core.management.base import BaseCommand, CommandError

from soroscan.ingest.models import TrackedContract
from soroscan.ingest.services.export_import import (
    _count_events,
    export_avro,
    export_csv,
    export_json,
    export_parquet,
)


class Command(BaseCommand):
    help = "Export contract events to Parquet, CSV, JSON, or Avro."

    def add_arguments(self, parser):
        parser.add_argument("--contract-id", required=True, help="Contract ID to export")
        parser.add_argument(
            "--format",
            choices=["parquet", "csv", "json", "avro"],
            default="json",
            help="Output format (default: json)",
        )
        parser.add_argument("--output", required=True, help="Output file path (use - for stdout on csv/json)")
        parser.add_argument("--start-ledger", type=int, default=None, help="Export events from this ledger (inclusive)")
        parser.add_argument("--end-ledger", type=int, default=None, help="Export events up to this ledger (inclusive)")
        parser.add_argument("--batch-size", type=int, default=500, help="Internal streaming batch size (default: 500)")

    def handle(self, *args, **options):
        contract_id = options["contract_id"]
        fmt = options["format"]
        output = options["output"]
        start_ledger = options["start_ledger"]
        end_ledger = options["end_ledger"]

        if not TrackedContract.objects.filter(contract_id=contract_id).exists():
            raise CommandError(f"No TrackedContract found with contract_id={contract_id!r}")

        if start_ledger is not None and end_ledger is not None and start_ledger > end_ledger:
            raise CommandError("--start-ledger must be <= --end-ledger")

        total = _count_events(contract_id, start_ledger, end_ledger)
        self.stderr.write(f"Exporting {total} events from contract {contract_id} as {fmt} → {output}")

        try:
            count = self._do_export(fmt, contract_id, output, start_ledger, end_ledger)
        except ImportError as exc:
            raise CommandError(str(exc))

        self.stdout.write(self.style.SUCCESS(f"Exported {count} events to {output}"))

    def _do_export(self, fmt, contract_id, output, start_ledger, end_ledger) -> int:
        if fmt == "json":
            if output == "-":
                return export_json(contract_id, self.stdout, start_ledger, end_ledger)
            with open(output, "w", encoding="utf-8") as f:
                return export_json(contract_id, f, start_ledger, end_ledger)

        elif fmt == "csv":
            if output == "-":
                return export_csv(contract_id, self.stdout, start_ledger, end_ledger)
            with open(output, "w", encoding="utf-8", newline="") as f:
                return export_csv(contract_id, f, start_ledger, end_ledger)

        elif fmt == "parquet":
            if output == "-":
                raise CommandError("Parquet format cannot be written to stdout; provide a file path.")
            return export_parquet(contract_id, output, start_ledger, end_ledger)

        elif fmt == "avro":
            if output == "-":
                raise CommandError("Avro format cannot be written to stdout; provide a file path.")
            return export_avro(contract_id, output, start_ledger, end_ledger)

        raise CommandError(f"Unknown format: {fmt}")
