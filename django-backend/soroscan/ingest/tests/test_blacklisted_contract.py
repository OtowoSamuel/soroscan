"""
Tests for BlacklistedContract model and ingestion-loop skip logic (issue #470).
"""
import logging
from unittest.mock import MagicMock, patch

import pytest
from django.core.exceptions import ValidationError

from soroscan.ingest.models import BlacklistedContract, TrackedContract
from soroscan.ingest.tests.factories import TrackedContractFactory, UserFactory

VALID_ID = "C" + "A" * 55


# ── Model tests ───────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestBlacklistedContractModel:
    def test_create_with_valid_address(self):
        entry = BlacklistedContract.objects.create(
            contract_id=VALID_ID,
            reason="emits spam events",
        )
        assert entry.pk is not None
        assert str(entry).startswith("Blacklisted(")

    def test_duplicate_contract_id_raises(self):
        BlacklistedContract.objects.create(contract_id=VALID_ID)
        with pytest.raises(Exception):  # IntegrityError / unique violation
            BlacklistedContract.objects.create(contract_id=VALID_ID)

    def test_invalid_address_rejected(self):
        entry = BlacklistedContract(contract_id="GABCDEFGHIJKLMNOPQRSTUVWXYZ234567ABCDEFGHIJKLMNOPQRSTU")
        with pytest.raises(ValidationError):
            entry.full_clean()

    def test_reason_is_optional(self):
        entry = BlacklistedContract.objects.create(contract_id=VALID_ID)
        assert entry.reason == ""

    def test_added_by_nullable(self):
        entry = BlacklistedContract.objects.create(contract_id=VALID_ID)
        assert entry.added_by is None

    def test_added_by_links_user(self):
        user = UserFactory()
        entry = BlacklistedContract.objects.create(contract_id=VALID_ID, added_by=user)
        assert entry.added_by == user


# ── Ingestion skip logic tests ────────────────────────────────────────────────

@pytest.mark.django_db
class TestIngestionBlacklistSkip:
    """
    Verify that ingest_latest_events excludes blacklisted contract_ids from
    the RPC query and emits a log entry for each skipped contract.
    """

    def _make_contract(self, **kwargs) -> TrackedContract:
        return TrackedContractFactory(**kwargs)

    def test_blacklisted_contract_excluded_from_rpc_query(self, caplog):
        contract = self._make_contract()
        BlacklistedContract.objects.create(
            contract_id=contract.contract_id,
            reason="test spam",
        )

        mock_server = MagicMock()
        mock_server.get_events.return_value = MagicMock(events=[])

        with patch("soroscan.ingest.tasks.SorobanServer", return_value=mock_server), \
             patch("soroscan.ingest.tasks.IndexerState.objects.get_or_create",
                   return_value=(MagicMock(value="100"), True)):
            from soroscan.ingest.tasks import ingest_latest_events
            ingest_latest_events()

        call_kwargs = mock_server.get_events.call_args
        if call_kwargs:
            filters = call_kwargs[1].get("filters") or call_kwargs[0][1]
            queried_ids = filters[0]["contractIds"] if filters else []
            assert contract.contract_id not in queried_ids

    def test_blacklisted_contract_logged(self, caplog):
        contract = self._make_contract()
        BlacklistedContract.objects.create(
            contract_id=contract.contract_id,
            reason="known malicious",
        )

        mock_server = MagicMock()
        mock_server.get_events.return_value = MagicMock(events=[])

        with caplog.at_level(logging.INFO, logger="soroscan.ingest.tasks"), \
             patch("soroscan.ingest.tasks.SorobanServer", return_value=mock_server), \
             patch("soroscan.ingest.tasks.IndexerState.objects.get_or_create",
                   return_value=(MagicMock(value="100"), True)):
            from soroscan.ingest.tasks import ingest_latest_events
            ingest_latest_events()

        assert any(
            "blacklisted" in r.message.lower() and contract.contract_id in r.message
            for r in caplog.records
        )

    def test_non_blacklisted_contract_included(self):
        contract = self._make_contract()

        mock_server = MagicMock()
        mock_server.get_events.return_value = MagicMock(events=[])

        with patch("soroscan.ingest.tasks.SorobanServer", return_value=mock_server), \
             patch("soroscan.ingest.tasks.IndexerState.objects.get_or_create",
                   return_value=(MagicMock(value="100"), True)):
            from soroscan.ingest.tasks import ingest_latest_events
            ingest_latest_events()

        call_kwargs = mock_server.get_events.call_args
        if call_kwargs:
            filters = call_kwargs[1].get("filters") or call_kwargs[0][1]
            queried_ids = filters[0]["contractIds"] if filters else []
            assert contract.contract_id in queried_ids

    def test_multiple_blacklisted_all_excluded(self, caplog):
        contracts = [self._make_contract() for _ in range(3)]
        for c in contracts:
            BlacklistedContract.objects.create(contract_id=c.contract_id)

        mock_server = MagicMock()
        mock_server.get_events.return_value = MagicMock(events=[])

        with caplog.at_level(logging.INFO, logger="soroscan.ingest.tasks"), \
             patch("soroscan.ingest.tasks.SorobanServer", return_value=mock_server), \
             patch("soroscan.ingest.tasks.IndexerState.objects.get_or_create",
                   return_value=(MagicMock(value="100"), True)):
            from soroscan.ingest.tasks import ingest_latest_events
            ingest_latest_events()

        # All three should be logged as blacklisted
        blacklisted_messages = [
            r.message for r in caplog.records if "blacklisted" in r.message.lower()
        ]
        for c in contracts:
            assert any(c.contract_id in msg for msg in blacklisted_messages)
