"""Teks hasil analisis (polos, tanpa markup). Versi Telegram dibuat di Tahap 6/7."""
from __future__ import annotations

from analysis.models import AnalysisResult


def _p(x: float | None) -> str:
    if x is None:
        return "-"
    return f"{x:,.2f}" if abs(x) >= 100 else f"{x:.5f}"


def format_result(r: AnalysisResult) -> str:
    lines = [
        f"{r.market} | {r.model} | {r.timeframe}",
        f"Tren: {r.trend}",
        f"Sinyal: {r.direction}",
    ]
    if r.direction != "WAIT":
        lines += [
            f"Entry: {_p(r.entry)}",
            f"Stop Loss: {_p(r.sl)}",
            f"TP1: {_p(r.tp1)} | TP2: {_p(r.tp2)} | TP3: {_p(r.tp3)}",
            f"Risk/Reward: 1:1 / 1:2 / 1:3 (TP2 = 1:{r.rr:g})" if r.rr else "Risk/Reward: -",
        ]
    lines.append(f"Skor keyakinan: {r.confidence}/100 (skor indikator, bukan peluang profit)")
    lines.append("Alasan:")
    lines += [f"- {x}" for x in r.reasons]
    if r.summary:
        lines.append("Ringkasan indikator:")
        lines += [f"- {x}" for x in r.summary]
    if r.as_of:
        lines.append(f"Candle tertutup terakhir: {r.as_of:%Y-%m-%d %H:%M} UTC")
    return "\n".join(lines)
