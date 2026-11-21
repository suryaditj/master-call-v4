import math
from datetime import datetime, timedelta, timezone

import pytest

import exness.client as client_mod
from analysis.formatter import format_result
from analysis.models import BUY, SELL, WAIT
from analysis.multi_tf import combine
from analysis.scoring import (
    MIN_CANDLES, SIGNAL_THRESHOLD, analyze_candles, build_levels,
)
from exness.candles import Candle
from exness.errors import ExnessRequestError, InsufficientDataError

# Semua data di bawah SINTETIS (untuk menguji kode, bukan data pasar).
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_candles(n, drift, amp=1.0, start=1000.0, vol=100.0):
    out, prev = [], start
    for i in range(n):
        close = start + drift * i + amp * math.sin(i / 2.0)
        o = prev
        h = max(o, close) + 0.3
        l = min(o, close) - 0.3
        out.append(Candle(T0 + timedelta(minutes=5 * i), o, h, l, close, vol))
        prev = close
    return out


def test_uptrend_gives_buy_with_valid_levels():
    r = analyze_candles("XAUUSD", "H1", make_candles(150, drift=2.0))
    assert r.direction == BUY and r.score >= SIGNAL_THRESHOLD
    assert r.sl < r.entry < r.tp1 < r.tp2 < r.tp3
    assert r.entry - r.sl == pytest.approx(1.0 * r.atr)
    assert (r.tp2 - r.entry) / (r.entry - r.sl) == pytest.approx(2.0)
    assert r.confidence == round(abs(r.score))
    assert r.reasons and r.summary and len(r.factors) == 7


def test_downtrend_gives_sell_with_mirrored_levels():
    r = analyze_candles("BTCUSD", "M15", make_candles(150, drift=-2.0, start=5000.0))
    assert r.direction == SELL and r.score <= -SIGNAL_THRESHOLD
    assert r.tp3 < r.tp2 < r.tp1 < r.entry < r.sl


def test_sideways_gives_wait_without_levels():
    r = analyze_candles("XAUUSD", "H1", make_candles(150, drift=0.0, amp=2.0))
    assert r.direction == WAIT
    assert r.entry is None and r.sl is None and r.tp1 is None and r.rr is None
    assert r.reasons  # alasan WAIT selalu dijelaskan


def test_choppy_market_is_forced_to_wait_for_any_phase():
    # Gelombang bolak-balik: tidak boleh ada BUY/SELL pada fase mana pun.
    for n in range(120, 150):
        r = analyze_candles("XAUUSD", "H1", make_candles(n, drift=0.0, amp=2.0))
        assert r.direction == WAIT, f"n={n} menghasilkan {r.direction}"
    assert "bolak-balik" in r.reasons[0]


def test_flat_zero_volatility_is_wait():
    flat = [Candle(T0 + timedelta(minutes=i), 5, 5, 5, 5, 10) for i in range(150)]
    r = analyze_candles("XAUUSD", "H1", flat)
    assert r.direction == WAIT and r.confidence == 0


def test_not_enough_candles_raises_no_fake_signal():
    with pytest.raises(InsufficientDataError):
        analyze_candles("XAUUSD", "H1", make_candles(MIN_CANDLES - 1, 1.0))


def test_factor_scores_stay_within_weights_and_sum_to_total():
    r = analyze_candles("XAUUSD", "H1", make_candles(150, drift=2.0))
    assert all(-f.weight <= f.score <= f.weight for f in r.factors)
    assert sum(f.weight for f in r.factors) == 100
    assert r.score == pytest.approx(sum(f.score for f in r.factors))


def test_build_levels_edge_cases():
    assert build_levels(WAIT, 100, 1)["entry"] is None
    assert build_levels(BUY, 100, 0)["sl"] is None


def _res(tf, direction, score, price=100.0, atr=1.0):
    from analysis.models import AnalysisResult
    return AnalysisResult("XAUUSD", "Single Time Frame", tf, "x", direction, score,
                          int(abs(score)), price=price, atr=atr)


def test_multi_conflict_gives_wait_and_explains():
    out = combine("XAUUSD", [_res("M1", BUY, 60), _res("M5", WAIT, 5), _res("M15", SELL, -50)])
    assert out.direction == WAIT and out.entry is None
    assert any("Konflik" in x for x in out.reasons)


def test_multi_agreement_gives_buy_with_levels_from_middle_tf():
    mid = _res("M5", BUY, 50, price=200.0, atr=2.0)
    out = combine("XAUUSD", [_res("M1", BUY, 40), mid, _res("M15", BUY, 60)])
    assert out.direction == BUY
    assert out.timeframe == "M1+M5+M15"
    assert out.entry == 200.0 and out.sl == pytest.approx(198.0)
    assert len(out.sub_results) == 3


def test_multi_top_timeframe_must_not_oppose():
    out = combine("XAUUSD", [_res("M1", BUY, 80), _res("M5", BUY, 60), _res("M15", WAIT, -5)])
    assert out.direction == WAIT


def test_multi_needs_two_timeframes():
    with pytest.raises(ValueError):
        combine("XAUUSD", [_res("M1", BUY, 50)])


def test_formatter_buy_and_wait():
    buy = analyze_candles("XAUUSD", "H1", make_candles(150, drift=2.0))
    text = format_result(buy)
    for key in ("Sinyal: BUY", "Entry:", "Stop Loss:", "TP1:", "Risk/Reward", "bukan peluang profit"):
        assert key in text
    wait = analyze_candles("XAUUSD", "H1", make_candles(150, drift=0.0, amp=2.0))
    assert "Entry:" not in format_result(wait)


# ---- retry rate limit pada klien -------------------------------------------
class _R:
    def __init__(self, status, body):
        self.status_code, self._b = status, body

    def json(self):
        return self._b


class _S:
    def __init__(self, seq):
        self.seq, self.n = seq, 0

    def get(self, url, headers=None, timeout=None):
        r = self.seq[min(self.n, len(self.seq) - 1)]
        self.n += 1
        return r


def _make_client(monkeypatch, seq):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from config import load_exness_config
    seed = Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    monkeypatch.setenv("EXN_API_KEY", "k")
    monkeypatch.setenv("EXN_PRIVATE_KEY", seed.hex())
    monkeypatch.setenv("EXN_ACCOUNT_ID", "1")
    monkeypatch.setenv("EXN_API_BASE_URL", "https://ap.example")
    monkeypatch.delenv("EXN_DISCOVERY_BASE_URL", raising=False)
    waits = []
    monkeypatch.setattr(client_mod, "_sleep", waits.append)
    sess = _S(seq)
    return client_mod.ExnessClient(load_exness_config(), session=sess), sess, waits


def test_client_retries_on_429_then_succeeds(monkeypatch):
    rl = _R(429, {"error": {"code": 3015}, "error_message": "REQUEST_RATE_LIMIT"})
    c, sess, waits = _make_client(monkeypatch, [rl, rl, _R(200, {"ok": 1})])
    assert c.get("/v1/x") == {"ok": 1}
    assert sess.n == 3 and waits == [3.0, 6.0]


def test_client_gives_up_after_retries(monkeypatch):
    rl = _R(429, {"error": {"code": 3015}})
    c, sess, _ = _make_client(monkeypatch, [rl])
    with pytest.raises(ExnessRequestError) as exc:
        c.get("/v1/x")
    assert exc.value.status == 429 and sess.n == 3


def test_client_does_not_retry_other_errors(monkeypatch):
    c, sess, waits = _make_client(monkeypatch, [_R(404, {"error": {"code": 4000}})])
    with pytest.raises(ExnessRequestError):
        c.get("/v1/x")
    assert sess.n == 1 and waits == []
