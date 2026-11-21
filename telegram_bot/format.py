"""Format hasil analisis untuk Telegram (HTML) sesuai format yang telah disepakati."""
from __future__ import annotations

from datetime import timedelta, timezone
from html import escape

from analysis.models import AnalysisResult

MAX_LEN = 3900
WIB = timezone(timedelta(hours=7))

_ICON = {"BUY": "🟢", "SELL": "🔴", "WAIT": "🟡"}
_MARKET_ICON = {"XAUUSD": "🥇", "BTCUSD": "🪙"}


def _trend_icon(trend: str) -> str:
    t = trend.lower()
    if "naik" in t or "bull" in t:
        return "📈"
    if "turun" in t or "bear" in t:
        return "📉"
    return "↔️"


def _p(x: float | None) -> str:
    if x is None:
        return "-"
    return f"{x:,.2f}" if abs(x) >= 100 else f"{x:.5f}"


def _pips_text(entry: float | None, target: float | None, price_ref: float | None) -> str:
    if entry is None or target is None:
        return "-"
    diff = abs(target - entry)
    ref = price_ref if price_ref is not None else abs(entry)
    scale = 100.0 if ref >= 100 else 10_000.0
    pips = int(round(diff * scale))
    return f"{pips:,} pips"


def _parse_sub_tf_lines(r: AnalysisResult) -> list[str]:
    """Ubah sub_results atau baris alasan TF menjadi format `M1: 📈 Naik`."""
    if r.sub_results:
        return [f"• {escape(sub.timeframe)}: {_trend_icon(sub.trend)} {escape(sub.trend)}" for sub in r.sub_results]
    out: list[str] = []
    for item in r.reasons:
        if ":" in item and ("BUY" in item or "SELL" in item or "WAIT" in item) and "tren " in item:
            tf_part, rest = item.split(":", 1)
            if "tren " in rest:
                trend_raw = rest.split("tren ", 1)[1].rstrip(")")
                out.append(f"• {escape(tf_part.strip())}: {_trend_icon(trend_raw)} {escape(trend_raw.strip())}")
    return out


def format_html(r: AnalysisResult) -> str:
    e = escape
    m_icon = _MARKET_ICON.get(r.market.upper(), "📊")
    header_trend_icon = _trend_icon(r.trend)
    sig_icon = _ICON.get(r.direction, "")

    lines: list[str] = [
        f"{m_icon} <b>{e(r.market)}</b> | {e(r.model)} | <b>{e(r.timeframe)}</b>",
        f"Tren: {e(r.trend)}{header_trend_icon}",
        "",
    ]

    if r.direction != "WAIT":
        lines.append(f"Sinyal: {sig_icon} <b>{e(r.direction)}</b> • 🎯Entry: <code>{_p(r.entry)}</code>")
        lines.append("")
        lines.append(f"🛑 Stop Loss: <code>{_p(r.sl)}</code>")
        lines.append(f"✅ TP1: <code>{_p(r.tp1)}</code> | {_pips_text(r.entry, r.tp1, r.price)}")
        lines.append(f"✅ TP2: <code>{_p(r.tp2)}</code> | {_pips_text(r.entry, r.tp2, r.price)}")
        lines.append(f"✅ TP3: <code>{_p(r.tp3)}</code> | {_pips_text(r.entry, r.tp3, r.price)}")
        lines.append("")
    else:
        lines.append(f"Sinyal: {sig_icon} <b>{e(r.direction)}</b>")
        lines.append("")

    rr_str = f"1:1 / 1:2 / 1:3 (TP2 = 1:{r.rr:g})" if r.rr else "-"
    lines.append(f"⚖️ Risk/Reward: {e(rr_str)}")
    lines.append(f"📊 Skor Analisa : <b>{r.confidence}%</b>")
    lines.append("")

    lines.append("🧠 Alasan Entry")
    for reason in r.reasons:
        if reason.startswith("Skor gabungan") or reason.startswith("Skor ") or reason.startswith("Level dihitung") or reason.startswith("Konflik") or reason.startswith("Syarat") or reason.startswith("Pasar") or reason.startswith("Perhatian"):
            lines.append(f"• {e(reason)}")

    sub_lines = _parse_sub_tf_lines(r)
    if sub_lines:
        lines.extend(sub_lines)
    elif r.model == "Single Time Frame":
        lines.append(f"• {e(r.timeframe)}: {header_trend_icon} {e(r.trend)}")

    for reason in r.reasons:
        if reason.startswith("Level dihitung") or reason.startswith("Perhatian"):
            line_fmt = f"• {e(reason)}"
            if line_fmt not in lines:
                lines.append(line_fmt)

    if r.summary:
        lines.append("📋 Ringkasan indikator")
        lines += [f"• {e(x)}" for x in r.summary]

    if r.as_of:
        wib_dt = r.as_of.astimezone(WIB)
        lines.append(f"🕒 Candle tertutup terakhir: {wib_dt:%Y-%m-%d %H:%M} WIB")

    lines.append("⚠️ <i>Catatan : Ini hanya analisa, pergerakan ditentukan oleh market.</i>")

    text = "\n".join(lines)
    return text if len(text) <= MAX_LEN else text[: MAX_LEN - 1] + "…"
