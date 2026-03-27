"""
Management command: restore_contracts

Imports TrackedContract records from a JSON backup file.

Usage:
    python manage.py restore_contracts --input=backup.json
    python manage.py restore_contracts --input=backup.json --dry-run

Features:
    - Dry-run mode shows what will be imported without making changes
    - Handles duplicate contract IDs (skips existing, creates new)
"""
import json

from django.core.management.base import BaseCommand, CommandError

from soroscan.ingest.models import TrackedContract


class Command(BaseCommand):
    help = "Import tracked contracts from a JSON backup file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--input",
            required=True,
            help="Input file path (use - for stdin)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be imported without making changes",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Update existing contracts instead of skipping them",
        )

    def handle(self, *args, **options):
        input_path = options["input"]
        dry_run = options["dry_run"]
        force = options["force"]

        # Load backup data
        if input_path == "-":
            data = json.load(self.stdin)
        else:
            with open(input_path, "r", encoding="utf-8") as f:
                data = json.load(f)

        # Validate backup format
        if not isinstance(data, dict):
            raise CommandError("Invalid backup format: expected a JSON object")
        
        version = data.get("version")
        if version != 1:
            raise CommandError(f"Unsupported backup version: {version}. Expected version 1.")

        contracts_data = data.get("contracts", [])
        if not contracts_data:
            self.stdout.write("No contracts found in backup.")
            return

        self.stderr.write(f"Processing {len(contracts_data)} contracts from {input_path}")

        # Track results
        results = {
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
        }
        error_details = []

        # Process each contract
        for idx, contract_data in enumerate(contracts_data):
            try:
                result = self._process_contract(contract_data, dry_run, force)
                if result == "created":
                    results["created"] += 1
                elif result == "updated":
                    results["updated"] += 1
                elif result == "skipped":
                    results["skipped"] += 1
            except Exception as exc:
                results["errors"] += 1
                error_details.append(f"Row {idx + 1}: {exc}")

        # Print summary
        self.stdout.write("")
        if dry_run:
            self.stdout.write(self.style.SUCCESS("=== DRY RUN COMPLETE ==="))
        else:
            self.stdout.write(self.style.SUCCESS("=== RESTORE COMPLETE ==="))

        self.stdout.write(f"Would create: {results['created']}")
        self.stdout.write(f"Would update: {results['updated']}")
        self.stdout.write(f"Would skip:   {results['skipped']}")
        
        if results["errors"] > 0:
            self.stdout.write(self.style.ERROR(f"Errors: {results['errors']}"))
            for detail in error_details:
                self.stdout.write(f"  - {detail}")

        if not dry_run:
            self.stdout.write(self.style.SUCCESS(f"Successfully restored {results['created']} contracts"))

    def _process_contract(self, contract_data: dict, dry_run: bool, force: bool) -> str:
        """Process a single contract entry. Returns 'created', 'updated', or 'skipped'."""
        # Validate required fields
        contract_id = contract_data.get("contract_id", "").strip()
        if not contract_id:
            raise ValueError("Missing required field: contract_id")

        alias = contract_data.get("alias", "").strip()
        if not alias:
            raise ValueError("Missing required field: alias")

        settings = contract_data.get("settings", {})
        abi = contract_data.get("abi")
        metadata = contract_data.get("metadata", {})

        # Check if contract already exists
        existing = TrackedContract.objects.filter(contract_id=contract_id).first()

        if existing:
            if force:
                # Update existing contract
                if not dry_run:
                    existing.name = alias
                    existing.description = settings.get("description", "")
                    existing.is_active = settings.get("is_active", True)
                    existing.deprecation_status = settings.get("deprecation_status", "active")
                    existing.deprecation_reason = settings.get("deprecation_reason", "")
                    existing.abi_schema = abi
                    existing.save()
                return "updated"
            else:
                # Skip existing contract
                return "skipped"

        # Create new contract
        if not dry_run:
            TrackedContract.objects.create(
                contract_id=contract_id,
                name=alias,
                description=settings.get("description", ""),
                is_active=settings.get("is_active", True),
                deprecation_status=settings.get("deprecation_status", "active"),
                deprecation_reason=settings.get("deprecation_reason", ""),
                abi_schema=abi,
                last_indexed_ledger=metadata.get("last_indexed_ledger"),
            )
        return "created"