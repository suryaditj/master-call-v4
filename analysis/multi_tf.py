"""Penggabungan beberapa timeframe menjadi satu kesimpulan dengan syarat ketat."""
from __future__ import annotations

from typing import Sequence

from analysis.models import BUY, SELL, WAIT, AnalysisResult
from analysis.scoring import build_levels

MTF_THRESHOLD = 55.0
TOP_TF_MIN_SCORE = 40.0


def combine(market: str, results: Sequence[AnalysisResult]) -> AnalysisResult:
    """`results` harus berurutan dari timeframe terkecil ke terbesar."""
    if len(results) < 2:
        raise ValueError("Multi time frame butuh minimal 2 timeframe.")
    weights = list(range(1, len(results) + 1))
    combined = sum(w * r.score for w, r in zip(weights, results)) / sum(weights)
    dirs = [r.direction for r in results]
    top = results[-1]

    has_bearish_score = any(r.score < 0 for r in results)
    has_bullish_score = any(r.score > 0 for r in results)
    aligned_buy_count = sum(1 for r in results if r.direction == BUY)
    aligned_sell_count = sum(1 for r in results if r.direction == SELL)

    reasons: list[str] = []
    if (BUY in dirs and SELL in dirs) or (
        combined >= MTF_THRESHOLD and has_bearish_score
    ) or (
        combined <= -MTF_THRESHOLD and has_bullish_score
    ):
        direction = WAIT
        detail = ", ".join(f"{r.timeframe}={r.direction}({r.score:+.0f})" for r in results)
        reasons.append(f"Konflik arah antar timeframe ({detail}); tidak dipaksakan, hasil WAIT.")
    elif (
        combined >= MTF_THRESHOLD
        and top.direction == BUY
        and top.score >= TOP_TF_MIN_SCORE
        and aligned_buy_count >= 2
        and SELL not in dirs
    ):
        direction = BUY
        reasons.append(
            f"Skor gabungan {combined:+.0f} melewati ambang ±{MTF_THRESHOLD:.0f}; "
            f"timeframe tertinggi ({top.timeframe}) searah BUY dan minimal 2 TF terkonfirmasi."
        )
    elif (
        combined <= -MTF_THRESHOLD
        and top.direction == SELL
        and top.score <= -TOP_TF_MIN_SCORE
        and aligned_sell_count >= 2
        and BUY not in dirs
    ):
        direction = SELL
        reasons.append(
            f"Skor gabungan {combined:+.0f} melewati ambang ±{MTF_THRESHOLD:.0f}; "
            f"timeframe tertinggi ({top.timeframe}) searah SELL dan minimal 2 TF terkonfirmasi."
        )
    else:
        direction = WAIT
        reasons.append(
            f"Syarat ketat MTF belum terpenuhi (skor {combined:+.0f}, ambang ±{MTF_THRESHOLD:.0f}, "
            f"TF tertinggi {top.timeframe}={top.direction} skor {top.score:+.0f})."
        )

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
