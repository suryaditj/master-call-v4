"""Formatter pesan HTML Telegram untuk hasil analisis (Single TF & Multi TF)."""
from __future__ import annotations

import re
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


def _clean_trend_label(trend: str, direction: str) -> str:
    cleaned = re.sub(r"\s*/\s*transisi", "", trend or "", flags=re.IGNORECASE).strip()
    if not cleaned:
        d = (direction or "").upper()
        if d in (BUY, "NAIK", "UP", "BULLISH"):
            return "Naik"
        if d in (SELL, "TURUN", "DOWN", "BEARISH"):
            return "Turun"
        return "Sideways"
    return cleaned


def _dir_arrow(direction: str, trend_label: str = "") -> str:
    d = (direction or "").upper()
    t = (trend_label or "").lower()
    if d in (BUY, "NAIK", "UP", "BULLISH") or "naik" in t or "bull" in t or "up" in t:
        return "⬆️"
    if d in (SELL, "TURUN", "DOWN", "BEARISH") or "turun" in t or "bear" in t or "down" in t:
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
    """Selisih jarak dalam pip bulat tanpa koma (contoh: 56pip)."""
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
            label = _clean_trend_label(sub.trend, sub.direction)
            arrow = _dir_arrow(sub.direction, label)
            parts.append(f"{escape(sub.timeframe)}: {escape(label)} {arrow}")
        return "Tren: " + " • ".join(parts)
    label = _clean_trend_label(res.trend, res.direction)
    arrow = _dir_arrow(res.direction, label)
    return f"Tren: {escape(label)} {arrow}"


def _format_reasons(res: AnalysisResult) -> list[str]:
    lines = ["📌 <b>Alasan Entry</b>"]
    if res.direction not in (BUY, SELL):
        lines.append("• Belum memenuhi syarat")
        if res.sub_results:
            for sub in res.sub_results:
                label = _clean_trend_label(sub.trend, sub.direction)
                arrow = _dir_arrow(sub.direction, label)
                lines.append(f"• {escape(sub.timeframe)}: {escape(label)} {arrow}")
        else:
            label = _clean_trend_label(res.trend, res.direction)
            arrow = _dir_arrow(res.direction, label)
            lines.append(f"• {escape(res.timeframe)}: {escape(label)} {arrow}")
        return lines

    if res.reasons:
        for r in res.reasons:
            if r.startswith("Arah:") or r.startswith("Level dihitung"):
                continue
            lines.append(f"• {escape(r)}")
    else:
        lines.append(f"• Searah sinyal {res.direction} pada {escape(res.timeframe)}")
    return lines


def _extract_num(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text, flags=re.IGNORECASE)
    if not m:
        return None
    raw = m.group(1).replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


def _build_beginner_summary(res: AnalysisResult) -> list[str]:
    """Menghasilkan tepat 2 poin bahasa pemula yang mudah dipahami."""
    joined = " | ".join(res.summary or [])
    price = _extract_num(r"Harga\s+([\d,]+(?:\.\d+)?)", joined)
    ema21 = _extract_num(r"EMA21\s+([\d,]+(?:\.\d+)?)", joined)
    ema50 = _extract_num(r"EMA50\s+([\d,]+(?:\.\d+)?)", joined)
    rsi = _extract_num(r"RSI14\s+([\d,]+(?:\.\d+)?)", joined)

    # Poin 1: posisi harga terhadap rata-rata pergerakan (EMA) & arah pergerakan
    ref_ema = ema50 if ema50 is not None else ema21
    if price is not None and ref_ema is not None:
        if price > ref_ema:
            p1 = "Harga masih berada di atas area rata-rata acuan, jadi kecenderungan arah masih punya peluang naik meski bisa tarik-ulur."
        elif price < ref_ema:
            p1 = "Harga masih berada di bawah area rata-rata acuan, jadi tekanan jual masih perlu diwaspadai sebelum ambil posisi."
        else:
            p1 = "Harga menempel di area rata-rata acuan, menandakan pasar sedang mencari arah baru."
    elif res.direction == BUY:
        p1 = "Pergerakan mulai menunjukkan dorongan naik, tapi tetap perlu konfirmasi agar tidak terjebak pantulan palsu."
    elif res.direction == SELL:
        p1 = "Pergerakan mulai menunjukkan tekanan turun, namun perhatikan area pantulan terdekat sebelum masuk posisi."
    else:
        p1 = "Pergerakan antar timeframe belum kompak, sehingga arah besar masih belum jelas untuk langsung entry."

    # Poin 2: kondisi tenaga pasar (RSI) & kesiapan peluang
    if rsi is not None:
        if rsi >= 70:
            p2 = "Tenaga beli sudah cukup tinggi (jenuh beli), jadi rawan koreksi atau melambat dalam jangka pendek."
        elif rsi <= 30:
            p2 = "Tenaga jual sudah cukup dalam (jenuh jual), jadi ada peluang pantulan balik sewaktu-waktu."
        elif res.direction not in (BUY, SELL):
            p2 = "Tenaga pasar masih berada di zona tengah dan belum cukup kuat, paling aman bersabar menunggu momen yang lebih jelas."
        else:
            p2 = "Tenaga pergerakan masih wajar dan belum ekstrem, tetap pasang batas rugi dan atur ukuran lot dengan aman."
    elif res.direction not in (BUY, SELL):
        p2 = "Kondisi pasar belum memenuhi syarat masuk aman, lebih baik tunggu konfirmasi lanjutan daripada terburu-buru."
    else:
        p2 = "Pastikan tetap memakai batas rugi (SL) yang disiplin karena pergerakan pasar bisa berubah cepat."

    return [p1, p2]


def _format_summary(res: AnalysisResult) -> list[str]:
    lines = ["📋 <b>Ringkasan indikator</b>"]
    for point in _build_beginner_summary(res)[:2]:
        lines.append(f"• {escape(point)}")
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
