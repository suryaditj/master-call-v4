"""Formatter pesan HTML Telegram untuk hasil analisis (Single TF & Multi TF)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape
from typing import Sequence

from analysis.models import BUY, SELL, AnalysisResult

WIB = timezone(timedelta(hours=7))


def _market_icon(market: str) -> str:
    m = market.upper()
    if "BTC" in m:
        return "🪙"
    if "XAU" in m or "GOLD" in m:
        return "🟡"
    return "📈"


def _dir_arrow(direction: str) -> str:
    d = direction.upper()
    if d in (BUY, "NAIK", "UP", "BULLISH"):
        return "⬆️"
    if d in (SELL, "TURUN", "DOWN", "BEARISH"):
        return "⬇️"
    return "↔️"


def _fmt_price(val: float | None, market: str) -> str:
    if val is None:
        return "-"
    decimals = 2 if ("BTC" in market.upper() or abs(val) >= 500) else 2
    return f"{val:,.{decimals}f}"


def _pip_size(market: str) -> float:
    """Ukuran 1 pip per pair: XAUUSD = 0.10, BTCUSD = 1.00."""
    m = market.upper()
    if "XAU" in m or "GOLD" in m:
        return 0.10
    if "BTC" in m:
        return 1.00
    return 0.01


def _fmt_pip_diff(a: float | None, b: float | None, market: str) -> str:
    """Selisih jarak dalam pip bulat tanpa koma (contoh: 405pip)."""
    if a is None or b is None:
        return "0pip"
    pip_val = _pip_size(market)
    pips = int(round(abs(a - b) / pip_val))
    return f"{pips}pip"


def _fmt_time(as_of: datetime | None) -> str:
    if as_of is None:
        return "-"
    dt = as_of if as_of.tzinfo is not None else as_of.replace(tzinfo=timezone.utc)
    return f"{dt.astimezone(WIB).strftime('%Y-%m-%d %H:%M')} WIB"


def _format_trend_line(res: AnalysisResult) -> str:
    if res.sub_results:
        parts: list[str] = []
        for sub in res.sub_results:
            arrow = _dir_arrow(sub.direction)
            parts.append(f"{escape(sub.timeframe)}: {escape(sub.trend)} {arrow}")
        return "Tren: " + " • ".join(parts)
    return f"Tren: {escape(res.trend)} {_dir_arrow(res.direction)}"


def _format_reasons(res: AnalysisResult) -> list[str]:
    lines = ["📌 <b>Alasan Entry</b>"]
    if res.direction not in (BUY, SELL):
        lines.append("• Belum memenuhi syarat")
        if res.sub_results:
            for sub in res.sub_results:
                lines.append(f"• {escape(sub.timeframe)}: {escape(sub.trend)} {_dir_arrow(sub.direction)}")
        else:
            lines.append(f"• {escape(res.timeframe)}: {escape(res.trend)} {_dir_arrow(res.direction)}")
        return lines

    if res.reasons:
        for r in res.reasons:
            if r.startswith("Arah:") or r.startswith("Level dihitung"):
                continue
            clean = r.replace(" • ", " • ")
            lines.append(f"• {escape(clean)}")
    else:
        lines.append(f"• Searah sinyal {res.direction} pada {escape(res.timeframe)}")
    return lines


def _format_summary(res: AnalysisResult) -> list[str]:
    lines = ["📋 <b>Ringkasan indikator</b>"]
    if res.summary:
        for item in res.summary:
            lines.append(f"• {escape(item)}")
    else:
        lines.append("• Pergerakan harga dan momentum masih dipantau sesuai kondisi pasar saat ini.")
    return lines


def format_html(res: AnalysisResult) -> str:
    icon = _market_icon(res.market)
    header = f"{icon} <b>{escape(res.market)} • {escape(res.model)} • {escape(res.timeframe)}</b>"
    trend_line = _format_trend_line(res)

    score_pct = int(round(abs(res.score)))
    as_of_str = _fmt_time(res.as_of)

    if res.direction == BUY:
        signal_line = f"Sinyal: 🟢 <b>BUY</b> • 🎯 Entry: <b>{_fmt_price(res.entry, res.market)}</b>"
        sl_pip = _fmt_pip_diff(res.entry, res.sl, res.market)
        tp1_pip = _fmt_pip_diff(res.tp1, res.entry, res.market)
        tp2_pip = _fmt_pip_diff(res.tp2, res.entry, res.market)
        tp3_pip = _fmt_pip_diff(res.tp3, res.entry, res.market)

        level_lines = [
            f"🛑 Stop Loss: {_fmt_price(res.sl, res.market)} • {sl_pip}",
            f"✅ TP1: {_fmt_price(res.tp1, res.market)} • {tp1_pip}",
            f"✅ TP2: {_fmt_price(res.tp2, res.market)} • {tp2_pip}",
            f"✅ TP3: {_fmt_price(res.tp3, res.market)} • {tp3_pip}",
        ]
        rr_text = f"1:1 • 1:2 • 1:3 • TP2 1:{res.rr:g}" if res.rr else "1:1 • 1:2 • 1:3"
    elif res.direction == SELL:
        signal_line = f"Sinyal: 🔴 <b>SELL</b> • 🎯 Entry: <b>{_fmt_price(res.entry, res.market)}</b>"
        sl_pip = _fmt_pip_diff(res.sl, res.entry, res.market)
        tp1_pip = _fmt_pip_diff(res.entry, res.tp1, res.market)
        tp2_pip = _fmt_pip_diff(res.entry, res.tp2, res.market)
        tp3_pip = _fmt_pip_diff(res.entry, res.tp3, res.market)

        level_lines = [
            f"🛑 Stop Loss: {_fmt_price(res.sl, res.market)} • {sl_pip}",
            f"✅ TP1: {_fmt_price(res.tp1, res.market)} • {tp1_pip}",
            f"✅ TP2: {_fmt_price(res.tp2, res.market)} • {tp2_pip}",
            f"✅ TP3: {_fmt_price(res.tp3, res.market)} • {tp3_pip}",
        ]
        rr_text = f"1:1 • 1:2 • 1:3 • TP2 1:{res.rr:g}" if res.rr else "1:1 • 1:2 • 1:3"
    else:
        signal_line = "Sinyal: 🟡 <b>WAIT • NO ENTRY</b>"
        level_lines = []
        rr_text = "-"

    parts: list[str] = [header, trend_line, "", signal_line]
    if level_lines:
        parts.append("")
        parts.extend(level_lines)

    parts.extend([
        "",
        f"⚖️ Risk/Reward: {rr_text}",
        f"📊 Skor Analisa: {score_pct}%",
        "",
        *_format_reasons(res),
        "",
        *_format_summary(res),
        "",
        f"🕒 Candle tertutup terakhir: {as_of_str}",
        "⚠️ Catatan: Ini hanya analisa • pergerakan ditentukan oleh transaksi market.",
    ])
    return "\n".join(parts)


def format_list_html(results: Sequence[AnalysisResult]) -> str:
    return "\n\n──────────\n\n".join(format_html(r) for r in results)
