"""Ed25519 signing helpers for outbound webhook deliveries."""
from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from django.conf import settings

_SIGNATURE_PREFIX = "ed25519="


def _seed_bytes() -> bytes:
    seed_hex = getattr(settings, "WEBHOOK_ED25519_SIGNING_SEED", "") or ""
    if not seed_hex:
        raise ValueError("WEBHOOK_ED25519_SIGNING_SEED is not configured")
    seed = bytes.fromhex(seed_hex)
    if len(seed) != 32:
        raise ValueError("WEBHOOK_ED25519_SIGNING_SEED must be 32 bytes (64 hex chars)")
    return seed


def get_signing_private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_seed_bytes())


def get_signing_public_key() -> Ed25519PublicKey:
    return get_signing_private_key().public_key()


def public_key_base64() -> str:
    raw = get_signing_public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def build_x_signature_header(payload_bytes: bytes) -> str:
    signature = get_signing_private_key().sign(payload_bytes)
    encoded = base64.b64encode(signature).decode("ascii")
    return f"{_SIGNATURE_PREFIX}{encoded}"


def parse_x_signature_header(header_value: str) -> bytes:
    value = (header_value or "").strip()
    if not value.startswith(_SIGNATURE_PREFIX):
        raise ValueError("Unsupported X-Signature format")
    return base64.b64decode(value[len(_SIGNATURE_PREFIX) :])


def verify_webhook_payload(
    payload_bytes: bytes,
    signature_header: str,
    *,
    public_key_b64: str | None = None,
) -> bool:
    """
    Verify an Ed25519 webhook signature from the X-Signature header.

    When *public_key_b64* is omitted the configured platform public key is used.
    """
    try:
        signature = parse_x_signature_header(signature_header)
        if public_key_b64:
            public_key = Ed25519PublicKey.from_public_bytes(
                base64.b64decode(public_key_b64)
            )
        else:
            public_key = get_signing_public_key()
        public_key.verify(signature, payload_bytes)
        return True
    except Exception:
        return False
