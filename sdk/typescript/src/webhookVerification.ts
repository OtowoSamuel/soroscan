/**
 * Verify SoroScan webhook Ed25519 signatures from the X-Signature header.
 */
import { createPublicKey, verify } from "node:crypto";

const SIGNATURE_PREFIX = "ed25519=";

export function verifyWebhookSignature(
  payload: Buffer | string,
  signatureHeader: string,
  publicKeyBase64: string
): boolean {
  try {
    if (!signatureHeader.startsWith(SIGNATURE_PREFIX)) {
      return false;
    }

    const signature = Buffer.from(
      signatureHeader.slice(SIGNATURE_PREFIX.length),
      "base64"
    );
    const rawPublicKey = Buffer.from(publicKeyBase64, "base64");

    const publicKey = createPublicKey({
      key: Buffer.concat([
        Buffer.from("302a300506032b6570032100", "hex"),
        rawPublicKey,
      ]),
      format: "der",
      type: "spki",
    });

    const body = typeof payload === "string" ? Buffer.from(payload) : payload;
    return verify(null, body, publicKey, signature);
  } catch {
    return false;
  }
}
