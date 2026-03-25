"""
Tests for export_events / import_events management commands and the
underlying export_import service.
"""
import csv
import io
import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from soroscan.ingest.models import ContractEvent
from soroscan.ingest.services.export_import import (
    ImportResult,
    export_csv,
    export_json,
    import_csv,
    import_json,
)
from soroscan.ingest.tests.factories import ContractEventFactory, TrackedContractFactory


@pytest.mark.django_db
class TestExportJSON:
    def test_exports_all_events(self):
        contract = TrackedContractFactory()
        ContractEventFactory.create_batch(3, contract=contract)

        buf = io.StringIO()
        from soroscan.ingest.services.export_import import export_json
        count = export_json(contract.contract_id, buf)

        assert count == 3
        data = json.loads(buf.getvalue())
        assert len(data) == 3
        assert data[0]["contract_id"] == contract.contract_id

    def test_exports_empty_contract(self):
        contract = TrackedContractFactory()
        buf = io.StringIO()
        count = export_json(contract.contract_id, buf)
        assert count == 0
        assert json.loads(buf.getvalue()) == []

    def test_ledger_range_filter(self):
        contract = TrackedContractFactory()
        ContractEventFactory(contract=contract, ledger=100, event_index=0)
        ContractEventFactory(contract=contract, ledger=200, event_index=0)
        ContractEventFactory(contract=contract, ledger=300, event_index=0)

        buf = io.StringIO()
        count = export_json(contract.contract_id, buf, start_ledger=150, end_ledger=250)
        assert count == 1
        data = json.loads(buf.getvalue())
        assert data[0]["ledger"] == 200


@pytest.mark.django_db
class TestExportCSV:
    def test_exports_header_and_rows(self):
        contract = TrackedContractFactory()
        ContractEventFactory.create_batch(2, contract=contract)

        buf = io.StringIO()
        count = export_csv(contract.contract_id, buf)

        assert count == 2
        buf.seek(0)
        reader = csv.DictReader(buf)
        rows = list(reader)
        assert len(rows) == 2
        assert "contract_id" in rows[0]
        assert "ledger" in rows[0]


@pytest.mark.django_db
class TestImportJSON:
    def test_import_creates_events(self):
        contract = TrackedContractFactory()
        # Export first
        buf = io.StringIO()
        ContractEventFactory.create_batch(3, contract=contract)
        export_json(contract.contract_id, buf)

        # Wipe and re-import
        ContractEvent.objects.all().delete()
        buf.seek(0)
        result = import_json(buf, ImportResult())

        assert result.imported == 3
        assert result.skipped == 0
        assert result.errors == 0
        assert ContractEvent.objects.count() == 3

    def test_import_is_idempotent(self):
        contract = TrackedContractFactory()
        ContractEventFactory.create_batch(3, contract=contract)

        buf = io.StringIO()
        export_json(contract.contract_id, buf)

        # First import: rows already exist in DB, all should be skipped as duplicates
        buf.seek(0)
        r1 = import_json(buf, ImportResult())
        assert r1.imported == 0
        assert r1.skipped == 3
        assert r1.errors == 0

        # Second import: same result
        buf.seek(0)
        r2 = import_json(buf, ImportResult())
        assert r2.imported == 0
        assert r2.skipped == 3

        assert ContractEvent.objects.count() == 3

    def test_import_missing_contract_records_error(self):
        bad_row = json.dumps([{
            "contract_id": "CNON_EXISTENT",
            "event_type": "test",
            "payload": "{}",
            "payload_hash": "abc",
            "ledger": 1,
            "event_index": 0,
            "timestamp": "2024-01-01T00:00:00+00:00",
            "tx_hash": "deadbeef",
            "raw_xdr": "",
            "schema_version": None,
            "validation_status": "passed",
            "decoded_payload": None,
            "decoding_status": "no_abi",
            "signature_status": "missing",
        }])
        result = import_json(io.StringIO(bad_row), ImportResult())
        assert result.errors == 1
        assert result.imported == 0


@pytest.mark.django_db
class TestImportCSV:
    def test_roundtrip_csv(self):
        contract = TrackedContractFactory()
        ContractEventFactory.create_batch(4, contract=contract)

        buf = io.StringIO()
        export_csv(contract.contract_id, buf)

        ContractEvent.objects.all().delete()
        buf.seek(0)
        result = import_csv(buf, ImportResult())

        assert result.imported == 4
        assert ContractEvent.objects.count() == 4


@pytest.mark.django_db
class TestExportCommand:
    def test_json_command(self, tmp_path):
        contract = TrackedContractFactory()
        ContractEventFactory.create_batch(2, contract=contract)
        out_file = str(tmp_path / "events.json")

        call_command(
            "export_events",
            contract_id=contract.contract_id,
            format="json",
            output=out_file,
        )
        data = json.loads(open(out_file).read())
        assert len(data) == 2

    def test_csv_command(self, tmp_path):
        contract = TrackedContractFactory()
        ContractEventFactory.create_batch(2, contract=contract)
        out_file = str(tmp_path / "events.csv")

        call_command(
            "export_events",
            contract_id=contract.contract_id,
            format="csv",
            output=out_file,
        )
        with open(out_file) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2

    def test_unknown_contract_raises(self):
        with pytest.raises(CommandError, match="No TrackedContract"):
            call_command(
                "export_events",
                contract_id="CNOPE",
                format="json",
                output="/tmp/nope.json",
            )

    def test_invalid_ledger_range_raises(self):
        contract = TrackedContractFactory()
        with pytest.raises(CommandError, match="--start-ledger"):
            call_command(
                "export_events",
                contract_id=contract.contract_id,
                format="json",
                output="/tmp/nope.json",
                start_ledger=500,
                end_ledger=100,
            )


@pytest.mark.django_db
class TestImportCommand:
    def test_json_import_command(self, tmp_path):
        contract = TrackedContractFactory()
        ContractEventFactory.create_batch(3, contract=contract)
        out_file = str(tmp_path / "events.json")

        call_command(
            "export_events",
            contract_id=contract.contract_id,
            format="json",
            output=out_file,
        )
        ContractEvent.objects.all().delete()

        call_command("import_events", file=out_file, format="json")
        assert ContractEvent.objects.count() == 3

    def test_dry_run_does_not_write(self, tmp_path):
        contract = TrackedContractFactory()
        ContractEventFactory.create_batch(2, contract=contract)
        out_file = str(tmp_path / "events.json")

        call_command(
            "export_events",
            contract_id=contract.contract_id,
            format="json",
            output=out_file,
        )
        ContractEvent.objects.all().delete()

        call_command("import_events", file=out_file, format="json", dry_run=True)
        assert ContractEvent.objects.count() == 0

    def test_format_autodetect(self, tmp_path):
        contract = TrackedContractFactory()
        ContractEventFactory.create_batch(2, contract=contract)
        out_file = str(tmp_path / "events.csv")

        call_command(
            "export_events",
            contract_id=contract.contract_id,
            format="csv",
            output=out_file,
        )
        ContractEvent.objects.all().delete()

        # No --format flag; should auto-detect from .csv extension
        call_command("import_events", file=out_file)
        assert ContractEvent.objects.count() == 2
