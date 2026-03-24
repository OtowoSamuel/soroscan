from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


@pytest.mark.django_db
class TestReprocessEventsCommand:
    def test_command_rejects_non_positive_batch_size(self):
        with pytest.raises(CommandError, match="--batch-size must be greater than 0"):
            call_command(
                "reprocess_events",
                contract_id="C" + "A" * 55,
                batch_size=0,
            )

    def test_command_rejects_negative_checkpoint(self):
        with pytest.raises(CommandError, match="--checkpoint-id must be >= 0"):
            call_command(
                "reprocess_events",
                contract_id="C" + "A" * 55,
                checkpoint_id=-1,
            )

    def test_command_invokes_reprocessing_and_prints_summary(self, mocker, capsys):
        fake_result = SimpleNamespace(
            contract_id="C" + "A" * 55,
            total_events=10,
            processed_events=10,
            updated_events=7,
            failed_events=0,
            progress_percent=100,
            last_checkpoint_id=500,
            dry_run=True,
            rolled_back=True,
        )
        reprocess_mock = mocker.patch(
            "soroscan.ingest.management.commands.reprocess_events.reprocess_contract_events",
            return_value=fake_result,
        )

        call_command(
            "reprocess_events",
            contract_id=fake_result.contract_id,
            dry_run=True,
            batch_size=250,
            checkpoint_id=5,
            rollback_on_error=True,
        )

        captured = capsys.readouterr()
        assert "reprocess_events completed" in captured.out
        assert "processed=10/10" in captured.out
        assert "dry_run=True" in captured.out
        reprocess_mock.assert_called_once_with(
            fake_result.contract_id,
            dry_run=True,
            batch_size=250,
            checkpoint_id=5,
            rollback_on_error=True,
        )
