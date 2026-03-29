"""
Streaming export/import service for ContractEvent data.

Supports Parquet, CSV, JSON, and Avro formats with idempotent import
(deduplication via the unique_contract_ledger_event_index constraint).
"""
import csv
import json
import logging
from datetime import datetime, timezone
from typing import IO, Iterator

from soroscan.ingest.cache_utils import invalidate_event_count_cache
from soroscan.ingest.models import ContractEvent, TrackedContract

logger = logging.getLogger(__name__)

# Fields exported/imported for each event
EXPORT_FIELDS = [
    "contract_id",       # TrackedContract.contract_id (string)
    "event_type",
    "schema_version",
    "validation_status",
    "payload",           # JSON string in flat formats
    "payload_hash",
    "ledger",
    "event_index",
    "timestamp",         # ISO-8601 string
    "tx_hash",
    "raw_xdr",
    "decoded_payload",   # JSON string in flat formats
    "decoding_status",
    "signature_status",
]

CHUNK_SIZE = 500  # rows per DB query batch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _event_to_dict(event: ContractEvent) -> dict:
    return {
        "contract_id": event.contract.contract_id,
        "event_type": event.event_type,
        "schema_version": event.schema_version,
        "validation_status": event.validation_status,
        "payload": json.dumps(event.payload),
        "payload_hash": event.payload_hash,
        "ledger": event.ledger,
        "event_index": event.event_index,
        "timestamp": event.timestamp.isoformat(),
        "tx_hash": event.tx_hash,
        "raw_xdr": event.raw_xdr,
        "decoded_payload": json.dumps(event.decoded_payload) if event.decoded_payload is not None else None,
        "decoding_status": event.decoding_status,
        "signature_status": event.signature_status,
    }


def _iter_events(contract_id: str, start_ledger: int | None, end_ledger: int | None) -> Iterator[ContractEvent]:
    """Yield events in (ledger, event_index) order using pk-based pagination to avoid loading all rows."""
    qs = (
        ContractEvent.objects
        .filter(contract__contract_id=contract_id)
        .select_related("contract")
        .order_by("ledger", "event_index", "pk")
    )
    if start_ledger is not None:
        qs = qs.filter(ledger__gte=start_ledger)
    if end_ledger is not None:
        qs = qs.filter(ledger__lte=end_ledger)

    last_pk = 0
    while True:
        chunk = list(qs.filter(pk__gt=last_pk)[:CHUNK_SIZE])
        if not chunk:
            break
        for event in chunk:
            yield event
        last_pk = chunk[-1].pk


def _count_events(contract_id: str, start_ledger: int | None, end_ledger: int | None) -> int:
    qs = ContractEvent.objects.filter(contract__contract_id=contract_id)
    if start_ledger is not None:
        qs = qs.filter(ledger__gte=start_ledger)
    if end_ledger is not None:
        qs = qs.filter(ledger__lte=end_ledger)
    return qs.count()


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_json(contract_id: str, out: IO, start_ledger=None, end_ledger=None) -> int:
    """Stream events as a JSON array to *out*. Returns event count."""
    out.write("[\n")
    count = 0
    for event in _iter_events(contract_id, start_ledger, end_ledger):
        if count > 0:
            out.write(",\n")
        out.write(json.dumps(_event_to_dict(event)))
        count += 1
    out.write("\n]\n")
    return count


def export_csv(contract_id: str, out: IO, start_ledger=None, end_ledger=None) -> int:
    """Stream events as CSV to *out*. Returns event count."""
    writer = csv.DictWriter(out, fieldnames=EXPORT_FIELDS, lineterminator="\n")
    writer.writeheader()
    count = 0
    for event in _iter_events(contract_id, start_ledger, end_ledger):
        writer.writerow(_event_to_dict(event))
        count += 1
    return count


def export_parquet(contract_id: str, path: str, start_ledger=None, end_ledger=None) -> int:
    """Write events to a Parquet file at *path*. Returns event count."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        raise ImportError("pyarrow is required for Parquet export: pip install pyarrow")

    schema = pa.schema([
        pa.field("contract_id", pa.string()),
        pa.field("event_type", pa.string()),
        pa.field("schema_version", pa.int64()),
        pa.field("validation_status", pa.string()),
        pa.field("payload", pa.string()),
        pa.field("payload_hash", pa.string()),
        pa.field("ledger", pa.int64()),
        pa.field("event_index", pa.int32()),
        pa.field("timestamp", pa.string()),
        pa.field("tx_hash", pa.string()),
        pa.field("raw_xdr", pa.string()),
        pa.field("decoded_payload", pa.string()),
        pa.field("decoding_status", pa.string()),
        pa.field("signature_status", pa.string()),
    ])

    writer = pq.ParquetWriter(path, schema)
    count = 0
    batch: list[dict] = []

    def _flush(rows):
        arrays = {f: [r[f] for r in rows] for f in EXPORT_FIELDS}
        table = pa.table(arrays, schema=schema)
        writer.write_table(table)

    for event in _iter_events(contract_id, start_ledger, end_ledger):
        batch.append(_event_to_dict(event))
        count += 1
        if len(batch) >= CHUNK_SIZE:
            _flush(batch)
            batch = []

    if batch:
        _flush(batch)

    writer.close()
    return count


def export_avro(contract_id: str, path: str, start_ledger=None, end_ledger=None) -> int:
    """Write events to an Avro file at *path*. Returns event count."""
    try:
        import fastavro
    except ImportError:
        raise ImportError("fastavro is required for Avro export: pip install fastavro")

    avro_schema = {
        "type": "record",
        "name": "ContractEvent",
        "fields": [
            {"name": "contract_id", "type": "string"},
            {"name": "event_type", "type": "string"},
            {"name": "schema_version", "type": ["null", "long"], "default": None},
            {"name": "validation_status", "type": "string"},
            {"name": "payload", "type": "string"},
            {"name": "payload_hash", "type": "string"},
            {"name": "ledger", "type": "long"},
            {"name": "event_index", "type": "int"},
            {"name": "timestamp", "type": "string"},
            {"name": "tx_hash", "type": "string"},
            {"name": "raw_xdr", "type": "string"},
            {"name": "decoded_payload", "type": ["null", "string"], "default": None},
            {"name": "decoding_status", "type": "string"},
            {"name": "signature_status", "type": "string"},
        ],
    }
    parsed_schema = fastavro.parse_schema(avro_schema)

    count = 0
    records = []
    for event in _iter_events(contract_id, start_ledger, end_ledger):
        records.append(_event_to_dict(event))
        count += 1
        if len(records) >= CHUNK_SIZE:
            with open(path, "ab") as f:
                fastavro.writer(f, parsed_schema, records)
            records = []

    if records:
        mode = "ab" if count > len(records) else "wb"
        with open(path, mode) as f:
            fastavro.writer(f, parsed_schema, records)

    return count


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

class ImportResult:
    def __init__(self):
        self.imported = 0
        self.skipped = 0   # duplicates
        self.errors = 0
        self.error_details: list[str] = []


def _parse_dt(val: str) -> datetime:
    """Parse ISO-8601 datetime string; make timezone-aware (UTC) if naive."""
    dt = datetime.fromisoformat(val)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _row_to_event(row: dict, contracts: dict[str, TrackedContract]) -> ContractEvent:
    """Convert a flat row dict to an unsaved ContractEvent. Raises ValueError on bad data."""
    cid = row.get("contract_id", "").strip()
    if not cid:
        raise ValueError("Missing contract_id")

    contract = contracts.get(cid)
    if contract is None:
        contract = TrackedContract.objects.filter(contract_id=cid).first()
        if contract is None:
            raise ValueError(f"TrackedContract not found: {cid}")
        contracts[cid] = contract

    def _parse_json(val):
        if val is None or val == "":
            return None
        if isinstance(val, (dict, list)):
            return val
        return json.loads(val)

    def _parse_int(val):
        return int(val) if val not in (None, "") else None

    return ContractEvent(
        contract=contract,
        event_type=row["event_type"],
        schema_version=_parse_int(row.get("schema_version")),
        validation_status=row.get("validation_status", "passed"),
        payload=_parse_json(row["payload"]),
        payload_hash=row.get("payload_hash", ""),
        ledger=int(row["ledger"]),
        event_index=int(row.get("event_index", 0)),
        timestamp=_parse_dt(row["timestamp"]),
        tx_hash=row.get("tx_hash", ""),
        raw_xdr=row.get("raw_xdr", ""),
        decoded_payload=_parse_json(row.get("decoded_payload")),
        decoding_status=row.get("decoding_status", "no_abi"),
        signature_status=row.get("signature_status", "missing"),
    )


def _import_batch(batch: list[dict], contracts: dict, result: ImportResult, dry_run: bool):
    events = []
    for row in batch:
        try:
            events.append(_row_to_event(row, contracts))
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            result.errors += 1
            result.error_details.append(str(exc))

    if dry_run or not events:
        # In dry-run mode we validate but don't write; count as "would import"
        if dry_run:
            result.imported += len(events)
        return

    # Use ignore_conflicts for idempotent import (unique_contract_ledger_event_index).
    # bulk_create with ignore_conflicts=True on PostgreSQL returns all objects with PKs
    # set (both inserted and skipped), so we can't use len(created) to count inserts.
    # Instead, snapshot the count before and after to get the true insert count.
    contract_pks = {e.contract_id for e in events}
    before = ContractEvent.objects.filter(contract_id__in=contract_pks).count()
    ContractEvent.objects.bulk_create(events, ignore_conflicts=True)
    after = ContractEvent.objects.filter(contract_id__in=contract_pks).count()

    # Invalidate event count cache for affected contracts
    for contract_id in contract_pks:
        invalidate_event_count_cache(contract_id)

    actually_inserted = after - before
    result.imported += actually_inserted
    result.skipped += len(events) - actually_inserted


def import_json(src: IO, result: ImportResult, dry_run: bool = False) -> ImportResult:
    data = json.load(src)
    if not isinstance(data, list):
        raise ValueError("JSON import expects a top-level array")
    contracts: dict[str, TrackedContract] = {}
    batch = []
    for row in data:
        batch.append(row)
        if len(batch) >= CHUNK_SIZE:
            _import_batch(batch, contracts, result, dry_run)
            batch = []
    if batch:
        _import_batch(batch, contracts, result, dry_run)
    return result


def import_csv(src: IO, result: ImportResult, dry_run: bool = False) -> ImportResult:
    reader = csv.DictReader(src)
    contracts: dict[str, TrackedContract] = {}
    batch = []
    for row in reader:
        batch.append(dict(row))
        if len(batch) >= CHUNK_SIZE:
            _import_batch(batch, contracts, result, dry_run)
            batch = []
    if batch:
        _import_batch(batch, contracts, result, dry_run)
    return result


def import_parquet(path: str, result: ImportResult, dry_run: bool = False) -> ImportResult:
    try:
        import pyarrow.parquet as pq
    except ImportError:
        raise ImportError("pyarrow is required for Parquet import: pip install pyarrow")

    contracts: dict[str, TrackedContract] = {}
    pf = pq.ParquetFile(path)
    for batch in pf.iter_batches(batch_size=CHUNK_SIZE):
        rows = batch.to_pydict()
        n = len(next(iter(rows.values())))
        dicts = [{k: (rows[k][i] if rows[k][i] is not None else None) for k in rows} for i in range(n)]
        _import_batch(dicts, contracts, result, dry_run)
    return result
