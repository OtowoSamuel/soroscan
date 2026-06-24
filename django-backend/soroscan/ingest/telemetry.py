"""Small tracing and payload-compression helpers for ingest flows."""

from __future__ import annotations

import json
import zlib
from typing import Any

from opentelemetry import propagate, trace
from opentelemetry.sdk.trace import TracerProvider

from .metrics import event_payload_compression_ratio

if trace.get_tracer_provider().__class__.__name__ == "ProxyTracerProvider":
    trace.set_tracer_provider(TracerProvider())

tracer = trace.get_tracer("soroscan.ingest")


def payload_compression_ratio(payload: dict[str, Any]) -> float | None:
    """Observe and return the zlib compression ratio for a JSON payload."""
    if not isinstance(payload, dict) or not payload:
        return None

    raw_payload = json.dumps(
        payload,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    ).encode("utf-8")
    if not raw_payload:
        return None

    compressed_payload = zlib.compress(raw_payload)
    ratio = len(compressed_payload) / len(raw_payload)
    event_payload_compression_ratio.observe(ratio)
    return ratio


def inject_trace_headers(headers: dict[str, str]) -> None:
    """Inject the current trace context into an outbound HTTP header map."""
    propagate.inject(headers)