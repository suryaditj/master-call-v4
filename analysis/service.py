"""Mengambil candle terbaru dari Exness lalu menjalankan analisis.

Dipanggil oleh handler Telegram (Tahap 7). Setiap panggilan mengambil data
BARU dari API, tidak memakai hasil tersimpan (syarat tombol Refresh).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Sequence

from analysis.models import AnalysisResult
from analysis.multi_tf import combine
from analysis.scoring import ANALYSIS_CANDLES, analyze_candles
from config import SYMBOLS
from exness.candles import TF_SECONDS, fetch_candles

SINGLE_TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1")
MULTI_PRESETS: dict[str, tuple[str, ...]] = {
    "M1+M5+M15": ("M1", "M5", "M15"),
    "M30+H1+H4": ("M30", "H1", "H4"),
}
PAUSE_BETWEEN_FETCHES = 0.5  # detik, mengurangi risiko rate limit


def _symbol(market: str) -> str:
    try:
        return SYMBOLS[market]
    except KeyError:
        raise ValueError(f"Market tidak dikenal: {market!r}") from None


STALE_AFTER_CANDLES = 3  # candle terakhir lebih tua dari 3 x timeframe = data lama


def _flag_stale(result: AnalysisResult, timeframe: str, now: datetime) -> None:
    """Beri peringatan bila candle terakhir sudah lama (mis. pasar tutup akhir pekan)."""
    if result.as_of is None:
        return
    age = (now - result.as_of).total_seconds()
    if age > STALE_AFTER_CANDLES * TF_SECONDS[timeframe]:
        result.reasons.insert(
            0,
            f"Perhatian: candle terakhir berumur {age / 3600:.1f} jam "
            "(pasar kemungkinan tutup); hasil ini berdasarkan data lama.",
        )


def analyze_single(client: Any, market: str, timeframe: str) -> AnalysisResult:
    if timeframe not in SINGLE_TIMEFRAMES:
        raise ValueError(f"Timeframe tidak didukung: {timeframe!r}")
    candles = fetch_candles(client, _symbol(market), timeframe, ANALYSIS_CANDLES)
    result = analyze_candles(market, timeframe, candles)
    _flag_stale(result, timeframe, datetime.now(timezone.utc))
    return result


def analyze_multi(client: Any, market: str, timeframes: Sequence[str]) -> AnalysisResult:
    tfs = sorted(timeframes, key=lambda t: TF_SECONDS[t])  # kecil -> besar
    results = []
    for i, tf in enumerate(tfs):
        if i:
            time.sleep(PAUSE_BETWEEN_FETCHES)
        results.append(analyze_single(client, market, tf))
    combined = combine(market, results)
    # Peringatan data lama ikut ke hasil gabungan bila salah satu timeframe lama.
    for r in results:
        if r.reasons and r.reasons[0].startswith("Perhatian: candle terakhir"):
            combined.reasons.insert(0, r.reasons[0])
            break
    return combined
