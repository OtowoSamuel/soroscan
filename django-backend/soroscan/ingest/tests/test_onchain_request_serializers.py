import pytest
from stellar_sdk import StrKey

from soroscan.ingest.serializers import (
    AddIndexerRequestSerializer,
    RecordEventRequestSerializer,
    StructuredEventRequestSerializer,
)


VALID_CONTRACT_ID = StrKey.encode_contract(bytes(32))
VALID_INDEXER_ADDRESS = StrKey.encode_ed25519_public_key(bytes(32))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("contract_id", "not-a-contract"),
        ("contract_id", "C" + "A" * 55),
        ("payload_hash", "g" * 64),
        ("payload_hash", "a" * 63),
    ],
)
def test_record_event_rejects_invalid_contract_id_and_hash(field, value):
    data = {
        "contract_id": VALID_CONTRACT_ID,
        "event_type": "transfer",
        "payload_hash": "a" * 64,
    }
    data[field] = value

    serializer = RecordEventRequestSerializer(data=data)

    assert not serializer.is_valid()
    assert field in serializer.errors


def test_record_event_accepts_valid_contract_and_normalizes_hash():
    serializer = RecordEventRequestSerializer(
        data={
            "contract_id": VALID_CONTRACT_ID,
            "event_type": "transfer",
            "payload_hash": "A" * 64,
        }
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["contract_id"] == VALID_CONTRACT_ID
    assert serializer.validated_data["payload_hash"] == "a" * 64


@pytest.mark.parametrize("value", ["not-an-address", "C" + "A" * 55])
def test_add_indexer_rejects_invalid_or_unsupported_address(value):
    serializer = AddIndexerRequestSerializer(data={"indexer_address": value})

    assert not serializer.is_valid()
    assert "indexer_address" in serializer.errors


def test_add_indexer_accepts_valid_account_address():
    serializer = AddIndexerRequestSerializer(
        data={"indexer_address": VALID_INDEXER_ADDRESS}
    )

    assert serializer.is_valid(), serializer.errors


@pytest.mark.parametrize("value", ["z" * 64, "a" * 63])
def test_structured_event_rejects_invalid_correlation_id(value):
    serializer = StructuredEventRequestSerializer(
        data={
            "contract_id": VALID_CONTRACT_ID,
            "event_type": "transfer",
            "payload_hash": "a" * 64,
            "schema_version": 1,
            "correlation_id": value,
        }
    )

    assert not serializer.is_valid()
    assert "correlation_id" in serializer.errors


def test_structured_event_normalizes_correlation_id():
    serializer = StructuredEventRequestSerializer(
        data={
            "contract_id": VALID_CONTRACT_ID,
            "event_type": "transfer",
            "payload_hash": "a" * 64,
            "schema_version": 1,
            "correlation_id": "B" * 64,
        }
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["correlation_id"] == "b" * 64
