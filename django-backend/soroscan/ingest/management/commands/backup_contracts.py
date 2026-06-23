"""
Management command: backup_contracts

Exports all TrackedContract records to a JSON backup file.

Usage:
    python manage.py backup_contracts --output=backup.json
"""
import json
from datetime import datetime, timezone

from django.core.management.base import BaseCommand

from soroscan.ingest.models import TrackedContract


class Command(BaseCommand):
    help = "Export all tracked contracts to a JSON backup file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            required=True,
            help="Output file path (use - for stdout)",
        )

    def handle(self, *args, **options):
        output = options["output"]

        contracts = TrackedContract.objects.all()
        count = contracts.count()

        self.stderr.write(f"Exporting {count} contracts to {output}")

        backup_data = {
            "version": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "contracts": [],
        }

        for contract in contracts:
            backup_data["contracts"].append({
                "contract_id": contract.contract_id,
                "alias": contract.name,
                "settings": {
                    "is_active": contract.is_active,
                    "deprecation_status": contract.deprecation_status,
                    "deprecation_reason": contract.deprecation_reason or "",
                    "description": contract.description or "",
                },
                "abi": contract.abi_schema,
                "metadata": {
                    "last_indexed_ledger": contract.last_indexed_ledger,
                    "created_at": contract.created_at.isoformat() if contract.created_at else None,
                    "updated_at": contract.updated_at.isoformat() if contract.updated_at else None,
                },
            })

        if output == "-":
            self.stdout.write(json.dumps(backup_data, indent=2))
        else:
            with open(output, "w", encoding="utf-8") as f:
                json.dump(backup_data, f, indent=2)

        self.stdout.write(self.style.SUCCESS(f"Exported {count} contracts to {output}"))