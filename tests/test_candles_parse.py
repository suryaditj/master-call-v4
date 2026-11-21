from datetime import datetime, timedelta, timezone

import pytest

from exness.candles import fetch_candles, parse_candles, parse_time, to_exness_time
from exness.errors import CandleDataError, InsufficientDataError

# Data di bawah ini SINTETIS untuk menguji kode, bukan data pasar.


def _raw(t, o=10.0, h=11.0, l=9.0, c=10.5, v=100.0):
    return {"time": t, "open": o, "high": h, "low": l, "close": c, "volume": v}


def test_parse_candles_sorts_and_converts():
    payload = {"candles": [_raw("2026-11-21T01:05:00+00:00"), _raw("2026-11-21T01:00:00Z")]}
    out = parse_candles(payload)
    assert [c.time.minute for c in out] == [0, 5]
    assert out[0].time.tzinfo is not None and out[0].close == 10.5


@pytest.mark.parametrize("bad", [
    None, {}, {"candles": "x"}, {"candles": [1]},
    {"candles": [{"time": "2026-11-21T01:00:00Z", "open": 1}]},   # field kurang / bid-ask
    {"candles": [_raw("kemarin")]},
    {"candles": [_raw("2026-11-21T01:00:00Z", h=8.0)]},            # high < low
    {"candles": [_raw("2026-11-21T01:00:00Z", o="abc")]},
])
def test_parse_candles_rejects_bad_payloads(bad):
    with pytest.raises(CandleDataError):
        parse_candles(bad)


def test_parse_time_naive_is_utc():
    assert parse_time("2026-11-21T01:00:00").tzinfo == timezone.utc


def test_to_exness_time_format():
    dt = datetime(2026, 11, 21, 8, 0, tzinfo=timezone(timedelta(hours=7)))
    assert to_exness_time(dt) == "2026-11-21T01:00:00+00:00"


class _FakeClient:
    """Menghasilkan candle M5 dalam [from, to) kecuali di rentang 'pasar tutup'."""

    def __init__(self, closed_from, closed_to):
        self.closed = (closed_from, closed_to)
        self.requests = []

    def get_candles_raw(self, symbol, timeframe, from_, *, to=None, count=None, price_type=None):
        self.requests.append((from_, to))
        start, end = parse_time(from_), parse_time(to)
        out, t = [], start
        while t < end:
            if not (self.closed[0] <= t < self.closed[1]):
                out.append(_raw(to_exness_time(t)))
            t += timedelta(minutes=5)
        return {"candles": out}


NOW = datetime(2026, 11, 21, 12, 3, tzinfo=timezone.utc)


def test_fetch_widens_window_over_market_gap():
    gap = (NOW - timedelta(hours=10), NOW)  # 10 jam terakhir tanpa candle
    client = _FakeClient(*gap)
    out = fetch_candles(client, "XAUUSDm", "M5", 50, now=NOW, max_window_candles=2000)
    assert len(out) == 50
    assert len(client.requests) > 1  # jendela diperlebar


def test_fetch_drops_unclosed_candle():
    client = _FakeClient(NOW + timedelta(days=1), NOW + timedelta(days=2))
    out = fetch_candles(client, "BTCUSDm", "M5", 10, now=NOW)
    assert out[-1].time + timedelta(minutes=5) <= NOW


def test_fetch_raises_when_data_never_enough():
    client = _FakeClient(NOW - timedelta(days=30), NOW + timedelta(days=1))
    with pytest.raises(InsufficientDataError):
        fetch_candles(client, "XAUUSDm", "M5", 50, now=NOW, max_window_candles=200)


def test_fetch_rejects_unknown_timeframe():
    with pytest.raises(ValueError):
        fetch_candles(_FakeClient(NOW, NOW), "XAUUSDm", "MN", 10, now=NOW)
