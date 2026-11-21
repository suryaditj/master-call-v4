from types import SimpleNamespace as C

import pytest

from indicators import atr, detect_patterns, ema, nearest_levels, rsi, sma, swing_highs, swing_lows


def test_sma_basic():
    assert sma([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]


def test_ema_known_values():
    # nilai 1..10, period 3: seed = SMA(1,2,3) = 2, k = 0.5 -> ema[i] = i
    out = ema(list(range(1, 11)), 3)
    assert out[:2] == [None, None]
    assert out[2:] == pytest.approx([2, 3, 4, 5, 6, 7, 8, 9])


def test_ema_short_input_returns_all_none():
    assert ema([1, 2], 3) == [None, None]


def test_rsi_matches_published_wilder_example():
    # Contoh StockCharts (RSI 14): RSI pertama = 70.53
    closes = [44.3389, 44.0902, 44.1497, 43.6124, 44.3278, 44.8264, 45.0955,
              45.4245, 45.8433, 46.0826, 45.8931, 46.0328, 45.6140, 46.2820, 46.2820]
    out = rsi(closes, 14)
    assert out[14] == pytest.approx(70.53, abs=0.1)
    assert all(v is None for v in out[:14])


def test_rsi_extremes():
    up = rsi(list(range(1, 40)), 14)
    down = rsi(list(range(40, 1, -1)), 14)
    flat = rsi([5.0] * 30, 14)
    assert up[-1] == 100.0
    assert down[-1] == pytest.approx(0.0)
    assert flat[-1] == 50.0


def test_atr_constant_range():
    h, l, c = [11.0] * 30, [9.0] * 30, [10.0] * 30
    out = atr(h, l, c, 14)
    assert out[12] is None
    assert out[13:] == pytest.approx([2.0] * 17)


def test_atr_uses_gap_from_previous_close():
    h = [10, 12]
    l = [9, 11.5]
    c = [9.5, 12]
    # TR[1] = max(0.5, |12-9.5|, |11.5-9.5|) = 2.5 ; TR[0] = 1
    assert atr(h, l, c, 2)[1] == pytest.approx((1 + 2.5) / 2)


def test_atr_length_mismatch():
    with pytest.raises(ValueError):
        atr([1, 2], [1], [1, 2])


def test_swings_and_nearest_levels():
    highs = [1, 2, 3, 2, 1, 2, 5, 2, 1, 2, 3, 2, 1]
    lows = [h - 0.5 for h in highs]
    assert (6, 5) in swing_highs(highs, 2)
    assert swing_lows([5, 4, 3, 4, 5, 4, 1, 4, 5], 2) == [(2, 3), (6, 1)]
    support, resistance = nearest_levels(2.2, highs, lows, k=2)
    assert support is not None and support < 2.2
    assert resistance is not None and resistance > 2.2
    assert nearest_levels(100.0, [1, 1, 1], [1, 1, 1]) == (None, None)


def _c(o, h, l, c):
    return C(open=o, high=h, low=l, close=c)


def test_pattern_hammer_and_shooting_star_and_doji():
    names = lambda cs: [p.name for p in detect_patterns(cs)]
    assert names([_c(10, 10.1, 8, 10.1)]) == ["Hammer"]
    assert names([_c(10, 12, 10, 10.1)]) == ["Shooting Star"]
    assert names([_c(10, 11, 9, 10.05)]) == ["Doji"]
    assert detect_patterns([_c(5, 5, 5, 5)]) == []
    assert detect_patterns([]) == []


def test_pattern_engulfing():
    bull = [_c(10, 10.2, 8.9, 9), _c(8.8, 10.6, 8.7, 10.5)]
    bear = [_c(9, 10.2, 8.9, 10), _c(10.2, 10.3, 8.5, 8.8)]
    assert "Bullish Engulfing" in [p.name for p in detect_patterns(bull)]
    assert "Bearish Engulfing" in [p.name for p in detect_patterns(bear)]
