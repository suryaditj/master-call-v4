from __future__ import annotations

from datetime import datetime, timezone

import pytest

from analysis.models import BUY, SELL, WAIT, AnalysisResult
from analysis.multi_tf import combine
from analysis.scoring import SIGNAL_THRESHOLD, analyze_candles
from exness.candles import Candle
from exness.errors import InsufficientDataError


def make_candles(n: int, drift: float = 0.0, amp: float = 0.0, start: float = 1000.0) -> list[Candle]:
    t0 = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp())
    out: list[Candle] = []
    price = start
    for i in range(n):
        wave = amp * (1.0 if i % 2 == 0 else -1.0)
        o = price
        c = max(1.0, start + i * drift + wave)
        h = max(o, c) + max(0.2, abs(drift) * 0.4 + amp * 0.3)
        l = max(0.5, min(o, c) - max(0.2, abs(drift) * 0.4 + amp * 0.3))
        vol = 100.0 + (i % 5) * 10.0
        out.append(Candle(time=t0 + i * 60, open=o, high=h, low=l, close=c, volume=vol))
        price = c
    return out


def test_insufficient_candles_raises():
    with pytest.raises(InsufficientDataError):
        analyze_candles("XAUUSD", "M5", make_candles(50))


def test_uptrend_gives_buy_with_valid_levels():
    r = analyze_candles("XAUUSD", "H1", make_candles(150, drift=2.0))
    assert r.direction == BUY and r.score >= SIGNAL_THRESHOLD
    assert r.sl < r.entry < r.tp1 < r.tp2 < r.tp3
    assert r.entry - r.sl == pytest.approx(1.0 * r.atr)
    assert r.tp2 - r.entry == pytest.approx(2.0 * (r.entry - r.sl))
    assert r.rr == pytest.approx(2.0)


def test_downtrend_gives_sell_with_mirrored_levels():
    r = analyze_candles("BTCUSD", "M15", make_candles(150, drift=-2.0, start=5000.0))
    assert r.direction == SELL and r.score <= -SIGNAL_THRESHOLD
    assert r.tp3 < r.tp2 < r.tp1 < r.entry < r.sl


def test_sideways_gives_wait_without_levels():
    r = analyze_candles("XAUUSD", "H1", make_candles(150, drift=0.0, amp=2.0))
    assert r.direction == WAIT
    assert r.entry is None and r.sl is None and r.tp1 is None


def test_choppy_market_is_forced_to_wait_for_any_phase():
    for n in range(120, 150):
        r = analyze_candles("XAUUSD", "H1", make_candles(n, drift=0.0, amp=2.0))
        assert r.direction == WAIT, f"n={n} menghasilkan {r.direction}"


def test_flat_zero_atr_gives_wait():
    t0 = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp())
    flat = [Candle(time=t0 + i * 60, open=100.0, high=100.0, low=100.0, close=100.0, volume=10.0)
            for i in range(120)]
    r = analyze_candles("XAUUSD", "M5", flat)
    assert r.direction == WAIT and r.entry is None


def test_score_is_bounded_minus_100_to_plus_100():
    for drift in (-5.0, -1.0, 0.0, 1.0, 5.0):
        r = analyze_candles("XAUUSD", "M15", make_candles(150, drift=drift, amp=0.5))
        assert -100.0 <= r.score <= 100.0
        assert 0 <= r.confidence <= 100


def _res(tf: str, direction: str, score: float, price: float = 100.0, atr: float = 1.0) -> AnalysisResult:
    return AnalysisResult(
        market="XAUUSD", model="Single Time Frame", timeframe=tf,
        trend="x", direction=direction, score=score, confidence=int(abs(score)),
        price=price, atr=atr,
    )


def test_multi_requires_at_least_two_tfs():
    with pytest.raises(ValueError):
        combine("XAUUSD", [_res("M5", BUY, 60)])


def test_multi_conflict_gives_wait():
    out = combine("XAUUSD", [_res("M1", BUY, 60), _res("M5", SELL, -60), _res("M15", BUY, 60)])
    assert out.direction == WAIT and out.entry is None


def test_multi_agreement_gives_buy_with_levels_from_middle_tf():
    mid = _res("M5", BUY, 65, price=200.0, atr=2.0)
    out = combine("XAUUSD", [_res("M1", BUY, 60), mid, _res("M15", BUY, 70)])
    assert out.direction == BUY
    assert out.timeframe == "M1+M5+M15"
    assert out.entry == 200.0 and out.sl == pytest.approx(198.0)


def test_multi_weak_score_gives_wait():
    out = combine("XAUUSD", [_res("M1", WAIT, 10), _res("M5", WAIT, 15), _res("M15", WAIT, 5)])
    assert out.direction == WAIT
