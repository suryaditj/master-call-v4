"""Penggabungan beberapa timeframe menjadi satu kesimpulan dengan syarat ketat."""
from __future__ import annotations

from html import escape
from typing import Sequence

from analysis.models import BUY, SELL, WAIT, AnalysisResult
from analysis.scoring import build_levels

MTF_THRESHOLD = 55.0
TOP_TF_MIN_SCORE = 40.0

ONE_CLICK_2TF_PRESETS: dict[str, tuple[str, ...]] = {
    "H4+M15": ("H4", "M15"),
    "H1+M5": ("H1", "M5"),
    "M30+M5": ("M30", "M5"),
}

MULTI_3TF_PRESETS: dict[str, tuple[str, ...]] = {
    "H4+H1+M15": ("H4", "H1", "M15"),
    "H1+M30+M5": ("H1", "M30", "M5"),
}

ONE_CLICK_2TF_KEY = "ONE_CLICK_2TF"


def _dir_label(direction: str) -> str:
    if direction == BUY:
        return "Naik"
    if direction == SELL:
        return "Turun"
    return "Netral"


def _combine_2tf(market: str, results: Sequence[AnalysisResult]) -> AnalysisResult:
    """2 TF dibaca kiri ke kanan (bias -> eksekusi), wajib searah penuh, level dari TF kedua."""
    bias_res, exec_res = results[0], results[1]
    combined = round((bias_res.score + exec_res.score) / 2.0, 2)
    dirs = [r.direction for r in results]
    both_buy = bias_res.direction == BUY and exec_res.direction == BUY and SELL not in dirs
    both_sell = bias_res.direction == SELL and exec_res.direction == SELL and BUY not in dirs

    reasons: list[str] = []
    arah_line = f"Arah: {bias_res.timeframe} {_dir_label(bias_res.direction)} • {exec_res.timeframe} {_dir_label(exec_res.direction)}"

    if both_buy and combined >= MTF_THRESHOLD:
        direction = BUY
        reasons.append(
            f"Skor gabungan {combined:+.0f} melewati ambang ±{MTF_THRESHOLD:.0f} • "
            f"Searah penuh {bias_res.timeframe} dan {exec_res.timeframe} • Acuan level {exec_res.timeframe}."
        )
    elif both_sell and combined <= -MTF_THRESHOLD:
        direction = SELL
        reasons.append(
            f"Skor gabungan {combined:+.0f} melewati ambang ±{MTF_THRESHOLD:.0f} • "
            f"Searah penuh {bias_res.timeframe} dan {exec_res.timeframe} • Acuan level {exec_res.timeframe}."
        )
    else:
        direction = WAIT
        if BUY in dirs and SELL in dirs:
            reasons.append(
                f"Konflik arah {bias_res.timeframe}={bias_res.direction} • "
                f"{exec_res.timeframe}={exec_res.direction} • Belum searah penuh • Hindari risiko SL."
            )
        else:
            reasons.append(
                f"Belum searah penuh atau skor {combined:+.0f} belum mencapai ambang ±{MTF_THRESHOLD:.0f} • "
                f"Hindari risiko SL."
            )

    reasons.append(arah_line)
    for r in results:
        reasons.append(f"{r.timeframe}: {r.direction} • skor {r.score:+.0f} • tren {r.trend}")

    levels = build_levels(direction, exec_res.price or 0.0, exec_res.atr or 0.0)
    if direction in (BUY, SELL):
        reasons.append(f"Level dihitung dari ATR timeframe terakhir {exec_res.timeframe}.")

    trends = " • ".join(f"{r.timeframe}: {r.trend}" for r in results)
    tf_name = "+".join(r.timeframe for r in results)
    return AnalysisResult(
        market=market,
        model="Multi Time Frame",
        timeframe=tf_name,
        trend=trends,
        direction=direction,
        score=combined,
        confidence=int(round(min(abs(combined), 100))),
        price=exec_res.price,
        atr=exec_res.atr,
        reasons=reasons,
        summary=exec_res.summary,
        factors=[],
        sub_results=list(results),
        as_of=exec_res.as_of,
        **levels,
    )


def _combine_3tf(market: str, results: Sequence[AnalysisResult]) -> AnalysisResult:
    """3 TF dibaca kiri ke kanan (bias -> struktur -> eksekusi), level dari TF terakhir."""
    weights = list(range(len(results), 0, -1))
    combined = round(sum(w * r.score for w, r in zip(weights, results)) / sum(weights), 2)
    dirs = [r.direction for r in results]
    lead_tf = results[0]
    exec_tf = results[-1]

    has_bearish_score = any(r.score < 0 for r in results)
    has_bullish_score = any(r.score > 0 for r in results)
    aligned_buy_count = sum(1 for r in results if r.direction == BUY)
    aligned_sell_count = sum(1 for r in results if r.direction == SELL)

    reasons: list[str] = []
    arah_line = "Arah: " + " • ".join(f"{r.timeframe} {_dir_label(r.direction)}" for r in results)

    if (
        (BUY in dirs and SELL in dirs)
        or (combined >= MTF_THRESHOLD and has_bearish_score)
        or (combined <= -MTF_THRESHOLD and has_bullish_score)
    ):
        direction = WAIT
        detail = " • ".join(f"{r.timeframe}={r.direction} {r.score:+.0f}" for r in results)
        reasons.append(f"Konflik arah antar timeframe • {detail} • tidak dipaksakan • hasil WAIT.")
    elif (
        combined >= MTF_THRESHOLD
        and lead_tf.direction == BUY
        and lead_tf.score >= TOP_TF_MIN_SCORE
        and aligned_buy_count >= 2
        and SELL not in dirs
    ):
        direction = BUY
        reasons.append(
            f"Skor gabungan {combined:+.0f} melewati ambang ±{MTF_THRESHOLD:.0f} • "
            f"bias {lead_tf.timeframe} BUY dan minimal 2 TF searah • acuan level {exec_tf.timeframe}."
        )
    elif (
        combined <= -MTF_THRESHOLD
        and lead_tf.direction == SELL
        and lead_tf.score <= -TOP_TF_MIN_SCORE
        and aligned_sell_count >= 2
        and BUY not in dirs
    ):
        direction = SELL
        reasons.append(
            f"Skor gabungan {combined:+.0f} melewati ambang ±{MTF_THRESHOLD:.0f} • "
            f"bias {lead_tf.timeframe} SELL dan minimal 2 TF searah • acuan level {exec_tf.timeframe}."
        )
    else:
        direction = WAIT
        reasons.append(
            f"Syarat ketat MTF belum terpenuhi • skor {combined:+.0f} • ambang ±{MTF_THRESHOLD:.0f} • "
            f"bias {lead_tf.timeframe}={lead_tf.direction} skor {lead_tf.score:+.0f}."
        )

    reasons.append(arah_line)
    for r in results:
        reasons.append(f"{r.timeframe}: {r.direction} • skor {r.score:+.0f} • tren {r.trend}")

    levels = build_levels(direction, exec_tf.price or 0.0, exec_tf.atr or 0.0)
    if direction in (BUY, SELL):
        reasons.append(f"Level dihitung dari ATR timeframe terakhir {exec_tf.timeframe}.")

    trends = " • ".join(f"{r.timeframe}: {r.trend}" for r in results)
    tf_name = "+".join(r.timeframe for r in results)
    return AnalysisResult(
        market=market,
        model="Multi Time Frame",
        timeframe=tf_name,
        trend=trends,
        direction=direction,
        score=combined,
        confidence=int(round(min(abs(combined), 100))),
        price=exec_tf.price,
        atr=exec_tf.atr,
        reasons=reasons,
        summary=exec_tf.summary,
        factors=[],
        sub_results=list(results),
        as_of=exec_tf.as_of,
        **levels,
    )


def combine(market: str, results: Sequence[AnalysisResult]) -> AnalysisResult:
    """Gabungkan `results` sesuai urutan baca kiri ke kanan (2 TF atau 3+ TF)."""
    if len(results) < 2:
        raise ValueError("Multi time frame butuh minimal 2 timeframe.")
    if len(results) == 2:
        return _combine_2tf(market, results)
    return _combine_3tf(market, results)


def format_one_click_2tf_html(market: str, pair_results: Sequence[AnalysisResult]) -> str:
    """Format hasil One Klik 2 TF menjadi blok terpisah per pasangan dengan simbol dan pemisah •."""
    blocks: list[str] = [f"<b>One Klik 2 TF • {escape(market)}</b>"]
    for res in pair_results:
        if res.direction == BUY:
            badge = "🟢 <b>BUY</b>"
        elif res.direction == SELL:
            badge = "🔴 <b>SELL</b>"
        else:
            badge = "🟡 <b>WAIT</b>"

        arah_line = next((line for line in res.reasons if line.startswith("Arah:")), "")
        lines = [
            f"🔹 <b>{escape(res.timeframe)}</b> • {badge} • Skor {res.score:+.0f}",
        ]
        if arah_line:
            lines.append(escape(arah_line))

        if res.direction in (BUY, SELL) and res.entry is not None and res.sl is not None:
            lines.append(f"Entry: {res.entry:.2f} • SL: {res.sl:.2f}")
            tp_items: list[str] = []
            if res.tp1 is not None:
                tp_items.append(f"TP1: {res.tp1:.2f}")
            if res.tp2 is not None:
                tp_items.append(f"TP2: {res.tp2:.2f}")
            if res.tp3 is not None:
                tp_items.append(f"TP3: {res.tp3:.2f}")
            if tp_items:
                lines.append(" • ".join(tp_items))
            lines.append(f"Alasan: Searah penuh • Acuan {escape(res.timeframe.split('+')[-1])}")
        else:
            lines.append("Alasan: Belum searah penuh • Hindari risiko SL")

        blocks.append("\n".join(lines))

    return "\n──────────\n".join(blocks)
