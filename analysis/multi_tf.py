"""Penggabungan beberapa timeframe menjadi satu kesimpulan.

Aturan:
- Timeframe lebih tinggi diberi bobot lebih besar (urutan kecil -> besar = bobot 1, 2, 3).
- Jika ada timeframe BUY dan SELL sekaligus -> WAIT (konflik dijelaskan).
- BUY/SELL hanya jika skor gabungan melewati ambang DAN timeframe tertinggi
  tidak berlawanan arah.
- Level Entry/SL/TP dihitung dari ATR timeframe tengah.
"""
from __future__ import annotations

from typing import Sequence

from analysis.models import BUY, SELL, WAIT, AnalysisResult
from analysis.scoring import build_levels

MTF_THRESHOLD = 30.0


def combine(market: str, results: Sequence[AnalysisResult]) -> AnalysisResult:
    """`results` harus berurutan dari timeframe terkecil ke terbesar."""
    if len(results) < 2:
        raise ValueError("Multi time frame butuh minimal 2 timeframe.")
    weights = list(range(1, len(results) + 1))
    combined = sum(w * r.score for w, r in zip(weights, results)) / sum(weights)
    dirs = [r.direction for r in results]
    top = results[-1]

    reasons: list[str] = []
    if BUY in dirs and SELL in dirs:
        direction = WAIT
        detail = ", ".join(f"{r.timeframe}={r.direction}" for r in results)
        reasons.append(f"Konflik arah antar timeframe ({detail}); tidak dipaksakan, hasil WAIT.")
    elif combined >= MTF_THRESHOLD and top.score > 0 and SELL not in dirs:
        direction = BUY
        reasons.append(f"Skor gabungan {combined:+.0f} melewati ambang ±{MTF_THRESHOLD:.0f}; "
                       f"timeframe tertinggi ({top.timeframe}) searah.")
    elif combined <= -MTF_THRESHOLD and top.score < 0 and BUY not in dirs:
        direction = SELL
        reasons.append(f"Skor gabungan {combined:+.0f} melewati ambang ±{MTF_THRESHOLD:.0f}; "
                       f"timeframe tertinggi ({top.timeframe}) searah.")
    else:
        direction = WAIT
        reasons.append(f"Skor gabungan {combined:+.0f} belum cukup kuat atau timeframe "
                       f"tertinggi ({top.timeframe}) belum searah.")

    for r in results:
        reasons.append(f"{r.timeframe}: {r.direction} (skor {r.score:+.0f}, tren {r.trend})")

    base = results[len(results) // 2]
    levels = build_levels(direction, base.price or 0.0, base.atr or 0.0)
    if direction in (BUY, SELL):
        reasons.append(f"Level dihitung dari ATR timeframe {base.timeframe}.")

    trends = " | ".join(f"{r.timeframe}: {r.trend}" for r in results)
    tf_name = "+".join(r.timeframe for r in results)
    return AnalysisResult(
        market=market, model="Multi Time Frame", timeframe=tf_name, trend=trends,
        direction=direction, score=combined, confidence=int(round(min(abs(combined), 100))),
        price=base.price, atr=base.atr, reasons=reasons, summary=base.summary,
        factors=[], sub_results=list(results), as_of=base.as_of, **levels,
    )
