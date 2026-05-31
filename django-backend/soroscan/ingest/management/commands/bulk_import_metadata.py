"""
Management command: bulk_import_metadata

Import contract metadata in bulk from CSV or JSON files.

Supported fields:
    contract_id       Stellar contract address (C...) — REQUIRED
    name              Contract display name
    description       Free-text description
    tags              Comma-separated tags (CSV) or JSON array (JSON)
    documentation_url
    github_repo
    team_email

CSV format:
    contract_id,name,description,tags,documentation_url,github_repo,team_email
    CAAAA...,Stablecoin Swap,An AMM,"defi,amm,swap",https://...,https://...,team@acme.example.com

JSON format:
    {
      "metadata": [
        { "contract_id": "CAAAA...", "name": "...", "tags": ["defi"] }
      ]
    }

Features:
    - Validation before import (dry-run)
    - Rollback on first error (default) or skip-and-continue
    - Detailed import report (created, updated, skipped, errors)

Usage:
    python manage.py bulk_import_metadata --input=contracts.csv --format=csv
    python manage.py bulk_import_metadata --input=contracts.json --format=json
    python manage.py bulk_import_metadata --input=contracts.csv --dry-run
    python manage.py bulk_import_metadata --input=contracts.csv --on-error=skip
"""
import csv
import io
import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from soroscan.ingest.models import ContractMetadata, TrackedContract


class Command(BaseCommand):
    help = "Bulk import contract metadata from CSV or JSON."

    def add_arguments(self, parser):
        parser.add_argument(
            "--input",
            required=True,
            help="Input file path (use - for stdin)",
        )
        parser.add_argument(
            "--format",
            choices=["csv", "json"],
            default=None,
            help="Input format (auto-detected from extension if omitted)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate all rows without modifying the database",
        )
        parser.add_argument(
            "--on-error",
            choices=["rollback", "skip"],
            default="rollback",
            help="Behavior on validation error: rollback entire batch or skip row",
        )
        parser.add_argument(
            "--encoding",
            default="utf-8",
            help="File encoding (default: utf-8)",
        )
        parser.add_argument(
            "--report",
            default=None,
            help="Write import report JSON to this file",
        )

    def handle(self, *args, **options):
        input_path = options["input"]
        fmt = options["format"]
        dry_run = options["dry_run"]
        on_error = options["on_error"]
        encoding = options["encoding"]
        report_path = options["report"]

        fmt = self._detect_format(input_path, fmt)
        raw = self._load_input(input_path, encoding)
        rows = self._parse_rows(raw, fmt)

        if not rows:
            self.stdout.write("No metadata rows to import.")
            return

        report = self._import_rows(rows, dry_run, on_error)

        self._print_report(report)
        if report_path:
            self._write_report(report, report_path)

    def _detect_format(self, input_path: str, fmt: str | None) -> str:
        if fmt:
            return fmt
        if input_path == "-":
            raise CommandError("--format is required when reading from stdin (-).")
        ext = Path(input_path).suffix.lower()
        if ext == ".csv":
            return "csv"
        if ext == ".json":
            return "json"
        raise CommandError(
            f"Cannot auto-detect format for {input_path}. Use --format=csv or --format=json."
        )

    def _load_input(self, input_path: str, encoding: str) -> str:
        if input_path == "-":
            return self.stdin.read()
        try:
            with open(input_path, "r", encoding=encoding, newline="") as f:
                return f.read()
        except OSError as exc:
            raise CommandError(f"Cannot read input file {input_path}: {exc}")

    def _parse_rows(self, raw: str, fmt: str) -> list[dict[str, Any]]:
        if fmt == "csv":
            return self._parse_csv(raw)
        return self._parse_json(raw)

    def _parse_csv(self, raw: str) -> list[dict[str, Any]]:
        try:
            reader = csv.DictReader(io.StringIO(raw))
            rows = list(reader)
        except csv.Error as exc:
            raise CommandError(f"CSV parse error: {exc}")
        if not rows or "contract_id" not in (reader.fieldnames or []):
            raise CommandError("CSV file must have a 'contract_id' column.")
        normalized = []
        for row in rows:
            contract_id = (row.get("contract_id") or "").strip()
            if not contract_id:
                continue
            tags_raw = (row.get("tags") or "").strip()
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []
            normalized.append({
                "contract_id": contract_id,
                "name": (row.get("name") or "").strip(),
                "description": (row.get("description") or "").strip(),
                "tags": tags,
                "documentation_url": (row.get("documentation_url") or "").strip(),
                "github_repo": (row.get("github_repo") or "").strip(),
                "team_email": (row.get("team_email") or "").strip(),
            })
        return normalized

    def _parse_json(self, raw: str) -> list[dict[str, Any]]:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CommandError(f"JSON parse error: {exc}")
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("metadata") or data.get("items") or []
        else:
            raise CommandError("JSON must be an array or an object with 'metadata' key.")
        if not isinstance(items, list):
            raise CommandError("Expected a list of metadata entries in JSON.")
        normalized = []
        for item in items:
            if not isinstance(item, dict):
                continue
            contract_id = str(item.get("contract_id") or "").strip()
            if not contract_id:
                continue
            tags = item.get("tags", [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            normalized.append({
                "contract_id": contract_id,
                "name": str(item.get("name") or "").strip(),
                "description": str(item.get("description") or "").strip(),
                "tags": tags,
                "documentation_url": str(item.get("documentation_url") or "").strip(),
                "github_repo": str(item.get("github_repo") or "").strip(),
                "team_email": str(item.get("team_email") or "").strip(),
            })
        return normalized

    def _import_rows(self, rows: list[dict[str, Any]], dry_run: bool, on_error: str) -> dict:
        report = {
            "mode": "dry-run" if dry_run else "live",
            "on_error": on_error,
            "total_rows": len(rows),
            "created": 0,
            "updated": 0,
            "skipped_no_contract": 0,
            "skipped_on_error": 0,
            "errors": 0,
            "error_details": [],
        }
        created_objs: list[ContractMetadata] = []
        updated_objs: list[tuple[ContractMetadata, dict]] = []

        for idx, row in enumerate(rows, start=1):
            try:
                contract = TrackedContract.objects.filter(contract_id=row["contract_id"]).first()
                if not contract:
                    report["skipped_no_contract"] += 1
                    report["error_details"].append({
                        "row": idx,
                        "contract_id": row["contract_id"],
                        "error": "TrackedContract not found",
                    })
                    if on_error == "rollback":
                        self._rollback_created(created_objs, updated_objs)
                        raise CommandError(
                            f"Row {idx}: TrackedContract not found for {row['contract_id']}. "
                            "Rolling back."
                        )
                    continue

                validated = self._validate_row(row)
                if dry_run:
                    report["created" if not hasattr(contract, "contractmetadata") else "updated"] += 1
                    continue

                defaults = {
                    "name": validated["name"],
                    "description": validated["description"],
                    "tags": validated["tags"],
                    "documentation_url": validated["documentation_url"] or None,
                    "github_repo": validated["github_repo"] or None,
                    "team_email": validated["team_email"] or None,
                }
                meta, created = ContractMetadata.objects.update_or_create(
                    contract=contract,
                    defaults=defaults,
                )
                if created:
                    report["created"] += 1
                    created_objs.append(meta)
                else:
                    report["updated"] += 1
                    updated_objs.append((meta, defaults))
            except CommandError:
                raise
            except Exception as exc:
                report["errors"] += 1
                report["error_details"].append({
                    "row": idx,
                    "contract_id": row.get("contract_id"),
                    "error": str(exc),
                })
                if on_error == "rollback":
                    self._rollback_created(created_objs, updated_objs)
                    raise CommandError(
                        f"Row {idx}: {exc}. Rolling back import."
                    ) from exc

        return report

    def _validate_row(self, row: dict[str, Any]) -> dict[str, Any]:
        validated = dict(row)
        if not validated.get("contract_id"):
            raise ValueError("contract_id is required")
        if not validated.get("name"):
            validated["name"] = validated["contract_id"]
        if len(validated.get("name", "")) > 256:
            raise ValueError("name exceeds max length of 256")
        if len(validated.get("description", "")) > 5000:
            raise ValueError("description exceeds max length of 5000")
        tags = validated.get("tags", [])
        if not isinstance(tags, list):
            raise ValueError("tags must be a list")
        if len(tags) > 100:
            raise ValueError("tags exceeds max length of 100")
        for field in ("documentation_url", "github_repo"):
            value = validated.get(field, "")
            if value and len(value) > 2048:
                raise ValueError(f"{field} exceeds max length of 2048")
        if validated.get("team_email") and len(validated["team_email"]) > 254:
            raise ValueError("team_email exceeds max length of 254")
        return validated

    def _rollback_created(self, created_objs: list, updated_objs: list):
        for meta in reversed(created_objs):
            try:
                contract_id = meta.contract.contract_id
                meta.delete()
                self.stdout.write(self.style.WARNING(f"  Rolled back created metadata for {contract_id}"))
            except Exception:
                pass
        for meta, old_values in updated_objs:
            try:
                ContractMetadata.objects.filter(pk=meta.pk).update(**old_values)
                self.stdout.write(
                    self.style.WARNING(f"  Rolled back updated metadata for {meta.contract.contract_id}")
                )
            except Exception:
                pass

    def _print_report(self, report: dict):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== Import Report ==="))
        self.stdout.write(f"Mode:                         {report['mode']}")
        self.stdout.write(f"Total rows:                   {report['total_rows']}")
        self.stdout.write(f"Created:                      {report['created']}")
        self.stdout.write(f"Updated:                      {report['updated']}")
        self.stdout.write(f"Skipped (no contract):        {report['skipped_no_contract']}")
        self.stdout.write(f"Skipped (on error):           {report['skipped_on_error']}")
        self.stdout.write(f"Errors:                       {report['errors']}")
        if report["error_details"]:
            self.stdout.write("")
            self.stdout.write(self.style.ERROR("Errors:"))
            for err in report["error_details"]:
                self.stdout.write(
                    f"  Row {err['row']} ({err.get('contract_id', '?')}): {err['error']}"
                )

    def _write_report(self, report: dict, path: str):
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Report written to {out}"))
