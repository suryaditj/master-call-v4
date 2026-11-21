"""Support/Resistance dari swing high/low (fraktal k kiri, k kanan)."""
from __future__ import annotations

from typing import Sequence


def swing_highs(highs: Sequence[float], k: int = 3) -> list[tuple[int, float]]:
    out = []
    for i in range(k, len(highs) - k):
        left = highs[i - k:i]
        right = highs[i + 1:i + k + 1]
        if all(highs[i] > x for x in left) and all(highs[i] > x for x in right):
            out.append((i, highs[i]))
    return out


def swing_lows(lows: Sequence[float], k: int = 3) -> list[tuple[int, float]]:
    out = []
    for i in range(k, len(lows) - k):
        left = lows[i - k:i]
        right = lows[i + 1:i + k + 1]
        if all(lows[i] < x for x in left) and all(lows[i] < x for x in right):
            out.append((i, lows[i]))
    return out


def nearest_levels(
    price: float,
    highs: Sequence[float],
    lows: Sequence[float],
    k: int = 3,
    lookback: int = 150,
) -> tuple[float | None, float | None]:
    """(support terdekat di bawah harga, resistance terdekat di atas harga).

    Hanya memakai `lookback` candle terakhir. None jika tidak ada level.
    """
    h = list(highs)[-lookback:]
    l = list(lows)[-lookback:]
    below = [p for _, p in swing_lows(l, k) if p < price]
    above = [p for _, p in swing_highs(h, k) if p > price]
    support = max(below) if below else None
    resistance = min(above) if above else None
    return support, resistance
