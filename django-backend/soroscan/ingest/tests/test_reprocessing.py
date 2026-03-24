import pytest
from django.core.exceptions import ObjectDoesNotExist

from soroscan.ingest.models import AdminAction, ContractEvent
from soroscan.ingest.reprocessing import _progress, reprocess_contract_events

from .factories import ContractEventFactory, TrackedContractFactory


@pytest.mark.django_db
class TestProgress:
    def test_progress_zero_total(self):
        assert _progress(0, 0) == 100

    def test_progress_ratio(self):
        assert _progress(25, 100) == 25


@pytest.mark.django_db
class TestReprocessContractEvents:
    def test_reprocess_updates_fields_and_audits(self, mocker):
        contract = TrackedContractFactory()
        event = ContractEventFactory(
            contract=contract,
            validation_status="passed",
            schema_version=1,
            signature_status="missing",
        )

        mocker.patch("soroscan.ingest.reprocessing.validate_event_payload", return_value=(False, 2))
        mocker.patch("soroscan.ingest.reprocessing.resolve_signature_status", return_value="valid")
        decode_mock = mocker.patch("soroscan.ingest.reprocessing._try_decode_event")

        result = reprocess_contract_events(contract.contract_id, batch_size=10)

        event.refresh_from_db()
        assert event.validation_status == "failed"
        assert event.schema_version == 2
        assert event.signature_status == "valid"

        assert result.contract_id == contract.contract_id
        assert result.total_events == 1
        assert result.processed_events == 1
        assert result.updated_events == 1
        assert result.failed_events == 0
        assert result.progress_percent == 100
        assert result.dry_run is False
        assert result.rolled_back is False

        decode_mock.assert_called_once()
        assert AdminAction.objects.filter(action="reprocess_events_started").exists()
        assert AdminAction.objects.filter(action="reprocess_events_completed").exists()

    def test_reprocess_dry_run_rolls_back_event_changes(self, mocker):
        contract = TrackedContractFactory()
        event = ContractEventFactory(
            contract=contract,
            validation_status="passed",
            schema_version=1,
            signature_status="missing",
        )

        mocker.patch("soroscan.ingest.reprocessing.validate_event_payload", return_value=(False, 3))
        mocker.patch("soroscan.ingest.reprocessing.resolve_signature_status", return_value="invalid")
        mocker.patch("soroscan.ingest.reprocessing._try_decode_event")

        result = reprocess_contract_events(contract.contract_id, dry_run=True)

        event.refresh_from_db()
        # Event stays unchanged because dry-run marks transaction rollback.
        assert event.validation_status == "passed"
        assert event.schema_version == 1
        assert event.signature_status == "missing"

        assert result.dry_run is True
        assert result.rolled_back is True
        assert AdminAction.objects.filter(action="reprocess_events_completed").exists()

    def test_reprocess_with_checkpoint_only_processes_newer_events(self, mocker):
        contract = TrackedContractFactory()
        older = ContractEventFactory(contract=contract)
        newer = ContractEventFactory(contract=contract)

        mocker.patch("soroscan.ingest.reprocessing.validate_event_payload", return_value=(True, None))
        mocker.patch("soroscan.ingest.reprocessing.resolve_signature_status", return_value="missing")
        decode_mock = mocker.patch("soroscan.ingest.reprocessing._try_decode_event")

        result = reprocess_contract_events(contract.contract_id, checkpoint_id=older.id)

        assert result.total_events == 1
        assert result.processed_events == 1
        assert result.last_checkpoint_id == newer.id
        assert decode_mock.call_count == 1

    def test_reprocess_logs_failed_action_when_exception(self, mocker):
        contract = TrackedContractFactory()
        ContractEventFactory(contract=contract)

        mocker.patch("soroscan.ingest.reprocessing.validate_event_payload", return_value=(True, None))
        mocker.patch("soroscan.ingest.reprocessing.resolve_signature_status", return_value="missing")
        mocker.patch("soroscan.ingest.reprocessing._try_decode_event", side_effect=RuntimeError("decode failed"))

        with pytest.raises(RuntimeError):
            reprocess_contract_events(contract.contract_id)

        assert AdminAction.objects.filter(action="reprocess_events_started").exists()
        assert AdminAction.objects.filter(action="reprocess_events_failed").exists()

    def test_reprocess_missing_contract_raises(self):
        with pytest.raises(ObjectDoesNotExist):
            reprocess_contract_events("C" + "A" * 55)
