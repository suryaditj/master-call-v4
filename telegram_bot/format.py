"""Format hasil analisis untuk Telegram (HTML). Semua teks dinamis di-escape."""
from __future__ import annotations

from html import escape

from analysis.models import AnalysisResult

MAX_LEN = 3900  # batas Telegram 4096 karakter, sisakan ruang
_ICON = {"BUY": "🟢", "SELL": "🔴", "WAIT": "🟡"}


def _p(x: float | None) -> str:
    if x is None:
        return "-"
    return f"{x:,.2f}" if abs(x) >= 100 else f"{x:.5f}"


def format_html(r: AnalysisResult) -> str:
    e = escape
    lines = [
        f"<b>{e(r.market)}</b> | {e(r.model)} | <b>{e(r.timeframe)}</b>",
        f"Tren: {e(r.trend)}",
        f"Sinyal: {_ICON.get(r.direction, '')} <b>{e(r.direction)}</b>",
    ]
    if r.direction != "WAIT":
        lines += [
            f"Entry: <code>{_p(r.entry)}</code>",
            f"Stop Loss: <code>{_p(r.sl)}</code>",
            f"TP1: <code>{_p(r.tp1)}</code>",
            f"TP2: <code>{_p(r.tp2)}</code>",
            f"TP3: <code>{_p(r.tp3)}</code>",
            f"Risk/Reward: 1:1 / 1:2 / 1:3 (TP2 = 1:{r.rr:g})" if r.rr else "Risk/Reward: -",
        ]
    lines.append(f"Skor keyakinan: <b>{r.confidence}/100</b> (skor indikator, bukan peluang profit)")
    lines.append("")
    lines.append("<b>Alasan</b>")
    lines += [f"• {e(x)}" for x in r.reasons]
    if r.summary:
        lines.append("")
        lines.append("<b>Ringkasan indikator</b>")
        lines += [f"• {e(x)}" for x in r.summary]
    if r.as_of:
        lines.append("")
        lines.append(f"Candle tertutup terakhir: {r.as_of:%Y-%m-%d %H:%M} UTC")
    lines.append("<i>Analisis teknikal otomatis, bukan nasihat keuangan.</i>")
    text = "\n".join(lines)
    return text if len(text) <= MAX_LEN else text[: MAX_LEN - 1] + "…"
