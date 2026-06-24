"""Webhook signature verification helpers for SoroScan SDK consumers."""
from __future__ import annotations

import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

_SIGNATURE_PREFIX = "ed25519="


def verify_webhook_signature(
    payload: bytes,
    signature_header: str,
    public_key_b64: str,
) -> bool:
    """
    Verify an Ed25519 webhook payload using the X-Signature header value.

    Args:
        payload: Raw request body bytes exactly as received.
        signature_header: Value of the X-Signature header (``ed25519=<base64>``).
        public_key_b64: Base64-encoded raw Ed25519 public key from the API.
    """
    try:
        if not signature_header.startswith(_SIGNATURE_PREFIX):
            return False
        signature = base64.b64decode(signature_header[len(_SIGNATURE_PREFIX) :])
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(public_key_b64)
        )
        public_key.verify(signature, payload)
        return True
    except Exception:
        return False
