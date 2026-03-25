"""
Management command: import_events

Imports ContractEvent rows from Parquet, CSV, or JSON files with:
  - Schema validation on each row
  - Idempotent upsert (re-importing the same file is safe)
  - Progress reporting

Usage examples:
    python manage.py import_events --file events.json --format json
    python manage.py import_events --file events.parquet --format parquet --dry-run
"""
from django.core.management.base import BaseCommand, CommandError

from soroscan.ingest.services.export_import import (
    ImportResult,
    import_csv,
    import_json,
    import_parquet,
)


class Command(BaseCommand):
    help = "Import contract events from Parquet, CSV, or JSON."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Input file path")
        parser.add_argument(
            "--format",
            choices=["parquet", "csv", "json"],
            default=None,
            help="Input format (auto-detected from extension if omitted)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate rows without writing to the database",
        )
        parser.add_argument(
            "--fail-fast",
            action="store_true",
            help="Abort on the first validation error",
        )

    def handle(self, *args, **options):
        path = options["file"]
        fmt = options["format"] or self._detect_format(path)
        dry_run = options["dry_run"]
        fail_fast = options["fail_fast"]

        if fmt is None:
            raise CommandError(
                "Cannot detect format from file extension. Use --format to specify it."
            )

        self.stderr.write(
            f"{'[DRY RUN] ' if dry_run else ''}Importing {fmt.upper()} from {path}"
        )

        result = ImportResult()
        try:
            result = self._do_import(fmt, path, result, dry_run)
        except ImportError as exc:
            raise CommandError(str(exc))
        except (ValueError, OSError) as exc:
            raise CommandError(f"Import failed: {exc}")

        if result.errors and fail_fast:
            raise CommandError(
                f"Import aborted: {result.errors} validation error(s).\n"
                + "\n".join(result.error_details[:10])
            )

        if result.errors:
            self.stderr.write(
                self.style.WARNING(
                    f"{result.errors} row(s) skipped due to errors:"
                )
            )
            for detail in result.error_details[:20]:
                self.stderr.write(f"  - {detail}")

        msg = (
            f"{'[DRY RUN] ' if dry_run else ''}"
            f"imported={result.imported} skipped_duplicates={result.skipped} errors={result.errors}"
        )
        self.stdout.write(self.style.SUCCESS(msg))

    def _do_import(self, fmt, path, result, dry_run) -> ImportResult:
        if fmt == "json":
            with open(path, "r", encoding="utf-8") as f:
                return import_json(f, result, dry_run=dry_run)
        elif fmt == "csv":
            with open(path, "r", encoding="utf-8", newline="") as f:
                return import_csv(f, result, dry_run=dry_run)
        elif fmt == "parquet":
            return import_parquet(path, result, dry_run=dry_run)
        raise CommandError(f"Unknown format: {fmt}")

    @staticmethod
    def _detect_format(path: str) -> str | None:
        lower = path.lower()
        if lower.endswith(".json"):
            return "json"
        if lower.endswith(".csv"):
            return "csv"
        if lower.endswith(".parquet"):
            return "parquet"
        return None
