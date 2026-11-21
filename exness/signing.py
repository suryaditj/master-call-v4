"""Penandatanganan request Exness API (Ed25519, header EXN-*).

Mengikuti dokumentasi resmi Exness API Developer Portal:
- EXN-DATA  = base64url (tanpa padding) dari JSON payload bertanda tangan.
- EXN-SIGN  = base64url (tanpa padding) dari tanda tangan Ed25519 atas
              byte payload JSON (bukan atas string base64url-nya).
- Untuk GET: idempotency_key = "" dan body_hash = SHA-256 dari string kosong.
- Query string harus ditandatangani persis seperti yang dikirim.

Modul ini tidak pernah mencetak atau menyimpan private key.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from exness.errors import ExnessKeyError

SIGN_VERSION = 1
_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


def b64url_nopad(raw: bytes) -> str:
    """base64url tanpa padding '='."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def load_private_key(text: str) -> Ed25519PrivateKey:
    """Muat private key Ed25519 dari teks.

    Format yang didukung:
    - Hex 128 karakter: 32 byte seed + 32 byte public key (kunci buatan Exness).
    - Hex 64 karakter: 32 byte seed saja.
    - PEM PKCS#8 (hasil `openssl genpkey -algorithm ED25519`).
    Pesan error tidak pernah memuat isi kunci.
    """
    value = (text or "").strip()
    if not value:
        raise ExnessKeyError("Private key kosong.")

    # GitHub Secrets kadang menyimpan PEM dengan "\n" literal.
    if "BEGIN" in value:
        value = value.replace("\\n", "\n")
        try:
            key = serialization.load_pem_private_key(value.encode(), password=None)
        except Exception as exc:  # noqa: BLE001
            raise ExnessKeyError("PEM private key tidak dapat dibaca.") from exc
        if not isinstance(key, Ed25519PrivateKey):
            raise ExnessKeyError("PEM bukan kunci Ed25519.")
        return key

    if _HEX_RE.match(value) and len(value) in (64, 128):
        seed = bytes.fromhex(value)[:32]
        try:
            return Ed25519PrivateKey.from_private_bytes(seed)
        except Exception as exc:  # noqa: BLE001
            raise ExnessKeyError("Seed Ed25519 tidak valid.") from exc

    raise ExnessKeyError(
        "Format private key tidak dikenali. Gunakan hex 128 karakter "
        "(dari Exness) atau PEM PKCS#8."
    )


def build_signed_headers(
    *,
    api_key: str,
    private_key: Ed25519PrivateKey,
    method: str,
    path_with_query: str,
    body: bytes = b"",
    idempotency_key: str = "",
    timestamp_ms: int | None = None,
) -> dict[str, str]:
    """Bangun header EXN-* untuk satu request. Buat ulang untuk tiap request."""
    ts = int(time.time() * 1000) if timestamp_ms is None else int(timestamp_ms)
    payload = {
        "api_key": api_key,
        "idempotency_key": idempotency_key,
        "timestamp": ts,
        "sign_version": SIGN_VERSION,
        "method": method.upper(),
        "path": path_with_query,
        "body_hash": b64url_nopad(hashlib.sha256(body).digest()),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = private_key.sign(payload_bytes)
    return {
        "EXN-API-KEY": api_key,
        "EXN-IDEMPOTENCY-KEY": idempotency_key,
        "EXN-TIMESTAMP": str(ts),
        "EXN-SIGN-VERSION": str(SIGN_VERSION),
        "EXN-DATA": b64url_nopad(payload_bytes),
        "EXN-SIGN": b64url_nopad(signature),
    }
