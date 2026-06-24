from soroscan.webhook_verification import verify_webhook_signature
from soroscan.webhook_signing import build_x_signature_header, public_key_base64


def test_sdk_verify_webhook_signature():
    payload = b'{"hello":"world"}'
    header = build_x_signature_header(payload)
    assert verify_webhook_signature(payload, header, public_key_base64())
