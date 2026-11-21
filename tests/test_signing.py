import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from config import ConfigError, load_exness_config
from exness.client import ExnessClient, build_path
from exness.errors import ExnessAuthError, ExnessKeyError
from exness.signing import b64url_nopad, build_signed_headers, load_private_key

# Nilai resmi dari dokumentasi Exness untuk body kosong.
EMPTY_BODY_HASH = "47DEQpj8HBSa-_TImW-5JCeuQeRkm5NMpJWZG3hSuFU"


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _key_and_hex():
    key = Ed25519PrivateKey.generate()
    seed = key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    pub = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return key, (seed + pub).hex()


def test_empty_body_hash_matches_official_value():
    assert b64url_nopad(hashlib.sha256(b"").digest()) == EMPTY_BODY_HASH


def test_headers_and_payload_for_get():
    key, _ = _key_and_hex()
    h = build_signed_headers(
        api_key="exnsk_test",
        private_key=key,
        method="get",
        path_with_query="/v1/configuration/accounts/123456/account",
        timestamp_ms=1773656070123,
    )
    assert h["EXN-API-KEY"] == "exnsk_test"
    assert h["EXN-IDEMPOTENCY-KEY"] == ""
    assert h["EXN-TIMESTAMP"] == "1773656070123"
    assert h["EXN-SIGN-VERSION"] == "1"
    assert "=" not in h["EXN-DATA"] and "=" not in h["EXN-SIGN"]

    payload = json.loads(_unb64(h["EXN-DATA"]))
    assert payload == {
        "api_key": "exnsk_test",
        "idempotency_key": "",
        "timestamp": 1773656070123,
        "sign_version": 1,
        "method": "GET",
        "path": "/v1/configuration/accounts/123456/account",
        "body_hash": EMPTY_BODY_HASH,
    }


def test_signature_verifies_over_decoded_payload_bytes():
    key, _ = _key_and_hex()
    h = build_signed_headers(
        api_key="k", private_key=key, method="GET", path_with_query="/v1/x?a=1"
    )
    key.public_key().verify(_unb64(h["EXN-SIGN"]), _unb64(h["EXN-DATA"]))


def test_signature_fails_if_path_changes():
    key, _ = _key_and_hex()
    h = build_signed_headers(
        api_key="k", private_key=key, method="GET", path_with_query="/v1/x", timestamp_ms=1
    )
    tampered = _unb64(h["EXN-DATA"]).replace(b"/v1/x", b"/v1/y")
    with pytest.raises(Exception):
        key.public_key().verify(_unb64(h["EXN-SIGN"]), tampered)


def test_load_hex128_hex64_and_pem_give_same_signing_key():
    key, hex128 = _key_and_hex()
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    msg = b"hello"
    expected = key.sign(msg)  # Ed25519 deterministik
    assert load_private_key(hex128).sign(msg) == expected
    assert load_private_key(hex128[:64]).sign(msg) == expected
    assert load_private_key(pem).sign(msg) == expected
    assert load_private_key(pem.replace("\n", "\\n")).sign(msg) == expected


@pytest.mark.parametrize("bad", ["", "   ", "not-a-key", "abcd", "z" * 128])
def test_bad_private_key_raises_without_leaking(bad):
    with pytest.raises(ExnessKeyError) as exc:
        load_private_key(bad)
    if bad.strip():
        assert bad not in str(exc.value)


def test_build_path_is_exactly_what_is_sent():
    p = build_path("/v1/a", {"from": "2026-01-01T00:00:00Z", "n": 5})
    assert p == "/v1/a?from=2026-01-01T00%3A00%3A00Z&n=5"
    assert build_path("/v1/a") == "/v1/a"
    with pytest.raises(ValueError):
        build_path("/v1/a", {"x": None})


def test_config_requires_values_and_hides_secrets(monkeypatch):
    for name in ("EXN_API_KEY", "EXN_PRIVATE_KEY", "EXN_ACCOUNT_ID",
                 "EXN_DISCOVERY_BASE_URL", "EXN_API_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ConfigError):
        load_exness_config()

    _, hex128 = _key_and_hex()
    monkeypatch.setenv("EXN_API_KEY", "exnsk_secretkey")
    monkeypatch.setenv("EXN_PRIVATE_KEY", hex128)
    monkeypatch.setenv("EXN_ACCOUNT_ID", "123456")
    with pytest.raises(ConfigError):  # belum ada host
        load_exness_config()
    monkeypatch.setenv("EXN_API_BASE_URL", "https://ap.example/")
    cfg = load_exness_config()
    text = repr(cfg) + str(cfg)
    assert "exnsk_secretkey" not in text and hex128 not in text
    assert cfg.api_base_url == "https://ap.example"


class _FakeResp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


class _FakeSession:
    def __init__(self, resp):
        self.resp = resp
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, headers))
        return self.resp


def _client(resp, monkeypatch):
    _, hex128 = _key_and_hex()
    monkeypatch.setenv("EXN_API_KEY", "exnsk_x")
    monkeypatch.setenv("EXN_PRIVATE_KEY", hex128)
    monkeypatch.setenv("EXN_ACCOUNT_ID", "42")
    monkeypatch.setenv("EXN_API_BASE_URL", "https://ap.example")
    monkeypatch.delenv("EXN_DISCOVERY_BASE_URL", raising=False)
    sess = _FakeSession(resp)
    return ExnessClient(load_exness_config(), session=sess), sess


def test_client_sends_signed_get_to_documented_path(monkeypatch):
    client, sess = _client(_FakeResp(200, {"account_id": 42}), monkeypatch)
    assert client.get_account_details() == {"account_id": 42}
    url, headers = sess.calls[0]
    assert url == "https://ap.example/v1/configuration/accounts/42/account"
    payload = json.loads(_unb64(headers["EXN-DATA"]))
    assert payload["path"] == "/v1/configuration/accounts/42/account"
    assert payload["method"] == "GET"


def test_client_maps_auth_errors(monkeypatch):
    body = {"error": {"code": 1001}, "error_message": "AUTH_INVALID_SIGNATURE"}
    client, _ = _client(_FakeResp(401, body), monkeypatch)
    with pytest.raises(ExnessAuthError):
        client.get_account_details()


def test_client_has_no_write_methods(monkeypatch):
    client, _ = _client(_FakeResp(200, {}), monkeypatch)
    for name in ("post", "put", "delete", "place_order", "open_position"):
        assert not hasattr(client, name)
