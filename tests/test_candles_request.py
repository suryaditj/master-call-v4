import base64
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from config import load_exness_config
from exness.client import PRICE_TYPES, TIMEFRAMES, ExnessClient


def _unb64(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class _Resp:
    status_code = 200

    def json(self):
        return {"ok": True}


class _Sess:
    def __init__(self):
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, headers))
        return _Resp()


@pytest.fixture
def client(monkeypatch):
    key = Ed25519PrivateKey.generate()
    seed = key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    monkeypatch.setenv("EXN_API_KEY", "exnsk_x")
    monkeypatch.setenv("EXN_PRIVATE_KEY", seed.hex())
    monkeypatch.setenv("EXN_ACCOUNT_ID", "42")
    monkeypatch.setenv("EXN_API_BASE_URL", "https://ap.example")
    monkeypatch.delenv("EXN_DISCOVERY_BASE_URL", raising=False)
    sess = _Sess()
    return ExnessClient(load_exness_config(), session=sess), sess


def test_timeframes_cover_required_set():
    for tf in ("M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"):
        assert tf in TIMEFRAMES
    assert set(PRICE_TYPES) == {"bid", "ask", "both"}


def test_candle_request_url_and_signed_path_match(client):
    c, sess = client
    c.get_candles_raw(
        "XAUUSDm", "M5", "2026-11-21T05:00:00+00:00", count=5, price_type="bid"
    )
    url, headers = sess.calls[0]
    signed_path = json.loads(_unb64(headers["EXN-DATA"]))["path"]
    assert url == "https://ap.example" + signed_path
    assert signed_path.startswith("/v1/market-data/accounts/42/candles?")
    assert "instrument=XAUUSDm" in signed_path
    assert "timeframe=M5" in signed_path
    assert "from=2026-11-21T05%3A00%3A00%2B00%3A00" in signed_path
    assert "price_type=bid" in signed_path
    assert "count=5" in signed_path
    assert "to=" not in signed_path


def test_candle_param_validation(client):
    c, _ = client
    with pytest.raises(ValueError):
        c.get_candles_raw("XAUUSDm", "H3", "x", count=1)  # timeframe tidak ada
    with pytest.raises(ValueError):
        c.get_candles_raw("XAUUSDm", "M5", "x", count=1, price_type="mid")
    with pytest.raises(ValueError):
        c.get_candles_raw("XAUUSDm", "M5", "x", count=1, to="y")  # count + to
    with pytest.raises(ValueError):
        c.get_candles_raw("XAUUSDm", "M5", "x")  # tanpa count/to
