"""Pola candlestick sederhana pada candle terakhir.

Fungsi ini hanya MENDETEKSI bentuk. Bobot dan konteks (tren, level) ditentukan
oleh lapisan analisis, bukan di sini.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class Pattern:
    name: str
    direction: str  # "bullish" | "bearish" | "neutral"


def _parts(c: Any) -> tuple[float, float, float, float]:
    body = abs(c.close - c.open)
    upper = c.high - max(c.open, c.close)
    lower = min(c.open, c.close) - c.low
    rng = c.high - c.low
    return body, upper, lower, rng


def detect_patterns(candles: Sequence[Any]) -> list[Pattern]:
    """Deteksi pola pada candle terakhir (butuh candle sebelumnya untuk engulfing)."""
    found: list[Pattern] = []
    if not candles:
        return found
    cur = candles[-1]
    body, upper, lower, rng = _parts(cur)
    if rng <= 0:
        return found

    # Bentuk ekor panjang diperiksa lebih dulu: badan sangat kecil dengan satu
    # ekor panjang adalah Hammer/Shooting Star, bukan Doji biasa.
    if lower >= 2 * body and upper <= 0.5 * body:
        found.append(Pattern("Hammer", "bullish"))
    elif upper >= 2 * body and lower <= 0.5 * body:
        found.append(Pattern("Shooting Star", "bearish"))
    elif body <= 0.1 * rng:
        found.append(Pattern("Doji", "neutral"))

    if len(candles) >= 2:
        prev = candles[-2]
        pbody = abs(prev.close - prev.open)
        if (
            prev.close < prev.open and cur.close > cur.open
            and cur.open <= prev.close and cur.close >= prev.open and body > pbody
        ):
            found.append(Pattern("Bullish Engulfing", "bullish"))
        if (
            prev.close > prev.open and cur.close < cur.open
            and cur.open >= prev.close and cur.close <= prev.open and body > pbody
        ):
            found.append(Pattern("Bearish Engulfing", "bearish"))
    return found
