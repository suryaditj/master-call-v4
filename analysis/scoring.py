"""Sistem skor teknikal untuk satu timeframe dengan acuan struktur swing & batas risiko."""
from __future__ import annotations

from typing import Sequence

from analysis.models import BUY, SELL, WAIT, AnalysisResult, Factor
from exness.candles import Candle
from exness.errors import InsufficientDataError
from indicators import atr, detect_patterns, ema, nearest_levels, rsi, sma

MIN_CANDLES = 100
ANALYSIS_CANDLES = 150
SIGNAL_THRESHOLD = 40.0     # lebih selektif agar tidak mudah memberi sinyal palsu
ER_WINDOW = 20
ER_MIN = 0.22               # pasar bolak-balik / sideways -> WAIT

MIN_SL_ATR = 0.60           # batas bawah jarak SL (anti terlalu sempit kena noise)
MAX_SL_ATR = 1.25           # batas atas jarak SL (anti terlalu lebar)
SWING_BUFFER_ATR = 0.15     # jarak aman di balik swing high/low
MAX_ENTRY_STRETCH_ATR = 0.75
TP_R_MULTIPLES = (1.0, 1.5, 2.0)

W_ALIGN, W_SLOPE, W_RSI, W_MOM, W_VOL, W_PATTERN, W_SR = 25, 13, 12, 18, 10, 8, 14


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _sgn(x: float) -> int:
    return (x > 0) - (x < 0)


def build_levels(
    direction: str,
    price: float,
    atr_value: float,
    *,
    ema_fast: float | None = None,
    swing_low: float | None = None,
    swing_high: float | None = None,
) -> dict[str, float | None]:
    """Hitung Entry pullback terukur dan SL berbasis struktur swing + batas ATR."""
    if direction not in (BUY, SELL) or atr_value <= 0 or price <= 0:
        return {"entry": None, "sl": None, "tp1": None, "tp2": None, "tp3": None, "rr": None}

    min_risk = MIN_SL_ATR * atr_value
    max_risk = MAX_SL_ATR * atr_value
    buf = SWING_BUFFER_ATR * atr_value

    if direction == BUY:
        # Target entry: kompromi antara harga sekarang dan EMA cepat (jika tersedia).
        if ema_fast is not None and ema_fast < price:
            raw_entry = 0.5 * (price + ema_fast)
            # Jangan terlalu jauh dari harga pasar saat ini
            entry = max(raw_entry, price - MAX_ENTRY_STRETCH_ATR * atr_value)
        else:
            entry = price - 0.20 * atr_value

        # Kandidat SL dari swing low terdekat di bawah entry
        if swing_low is not None and swing_low < entry:
            sl = swing_low - buf
        else:
            sl = entry - 0.85 * atr_value

        risk = entry - sl
        if risk < min_risk:
            sl = entry - min_risk
            risk = min_risk
        elif risk > max_risk:
            sl = entry - max_risk
            risk = max_risk

        if sl >= entry:
            return {"entry": None, "sl": None, "tp1": None, "tp2": None, "tp3": None, "rr": None}

        return {
            "entry": entry,
            "sl": sl,
            "tp1": entry + risk * TP_R_MULTIPLES[0],
            "tp2": entry + risk * TP_R_MULTIPLES[1],
            "tp3": entry + risk * TP_R_MULTIPLES[2],
            "rr": TP_R_MULTIPLES[1],
        }

    # direction == SELL
    if ema_fast is not None and ema_fast > price:
        raw_entry = 0.5 * (price + ema_fast)
        entry = min(raw_entry, price + MAX_ENTRY_STRETCH_ATR * atr_value)
    else:
        entry = price + 0.20 * atr_value

    if swing_high is not None and swing_high > entry:
        sl = swing_high + buf
    else:
        sl = entry + 0.85 * atr_value

    risk = sl - entry
    if risk < min_risk:
        sl = entry + min_risk
        risk = min_risk
    elif risk > max_risk:
        sl = entry + max_risk
        risk = max_risk

    if sl <= entry:
        return {"entry": None, "sl": None, "tp1": None, "tp2": None, "tp3": None, "rr": None}

    return {
        "entry": entry,
        "sl": sl,
        "tp1": entry - risk * TP_R_MULTIPLES[0],
        "tp2": entry - risk * TP_R_MULTIPLES[1],
        "tp3": entry - risk * TP_R_MULTIPLES[2],
        "rr": TP_R_MULTIPLES[1],
    }


def _fmt(x: float) -> str:
    return f"{x:,.2f}" if abs(x) >= 100 else f"{x:.5f}"


def analyze_candles(market: str, timeframe: str, candles: Sequence[Candle]) -> AnalysisResult:
    """Analisis satu timeframe dari candle TERTUTUP (urut naik menurut waktu)."""
    if len(candles) < MIN_CANDLES:
        raise InsufficientDataError(
            f"Data {market} {timeframe} kurang: {len(candles)} candle, butuh {MIN_CANDLES}."
        )
    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    vols = [c.volume for c in candles]

    e9, e21, e50 = ema(closes, 9), ema(closes, 21), ema(closes, 50)
    rsi_v = rsi(closes, 14)
    atr_v = atr(highs, lows, closes, 14)
    vol_sma = sma(vols, 20)

    price = closes[-1]
    a = atr_v[-1]
    r = rsi_v[-1]
    if a is None or r is None or e50[-1] is None or e21[-6] is None:
        raise InsufficientDataError("Indikator belum dapat dihitung dari data yang ada.")
    as_of = candles[-1].time

    if a <= 0:
        return AnalysisResult(
            market=market, model="Single Time Frame", timeframe=timeframe,
            trend="Tidak diketahui", direction=WAIT, score=0.0, confidence=0,
            price=price, atr=a, as_of=as_of,
            reasons=["Volatilitas nol (ATR = 0); data datar, tidak ada sinyal."],
        )

    factors: list[Factor] = []

    # 1. Susunan EMA 9/21/50
    align = (W_ALIGN / 2) * _sgn(e9[-1] - e21[-1]) + (W_ALIGN / 2) * _sgn(e21[-1] - e50[-1])
    if align == W_ALIGN:
        trend, tnote = "Naik", "EMA 9 > EMA 21 > EMA 50"
    elif align == -W_ALIGN:
        trend, tnote = "Turun", "EMA 9 < EMA 21 < EMA 50"
    else:
        trend, tnote = "Sideways / transisi", "susunan EMA 9/21/50 belum searah"
    factors.append(Factor("Susunan EMA", align, W_ALIGN, tnote))

    # 2. Kemiringan EMA 21 (5 candle) dalam satuan ATR
    slope = (e21[-1] - e21[-6]) / a
    factors.append(Factor(
        "Kemiringan EMA21", W_SLOPE * _clamp(slope / 0.45, -1, 1), W_SLOPE,
        f"EMA21 bergerak {slope:+.2f} ATR dalam 5 candle",
    ))

    # 3. RSI 14 (hindari mendorong sinyal saat sudah jenuh ekstrem)
    if r > 75:
        s = W_RSI * 0.25
    elif r >= 50:
        s = W_RSI * min((r - 50) / 25, 1.0)
    elif r >= 25:
        s = -W_RSI * min((50 - r) / 25, 1.0)
    else:
        s = -W_RSI * 0.25
    zone = " (jenuh beli ekstrem)" if r > 75 else " (jenuh jual ekstrem)" if r < 25 else ""
    factors.append(Factor("RSI 14", s, W_RSI, f"RSI {r:.1f}{zone}"))

    # 4. Momentum harga 8 candle terakhir dalam satuan ATR
    lookback_mom = min(8, len(closes) - 1)
    mom = (closes[-1] - closes[-1 - lookback_mom]) / a
    factors.append(Factor(
        "Momentum", W_MOM * _clamp(mom / 2.2, -1, 1), W_MOM,
        f"harga bergerak {mom:+.2f} ATR dalam {lookback_mom} candle",
    ))

    # 5. Volume
    vs = vol_sma[-1]
    ratio = (vols[-1] / vs) if vs and vs > 0 else 1.0
    body_dir = _sgn(candles[-1].close - candles[-1].open)
    vscore = body_dir * W_VOL * _clamp((ratio - 1) / 0.5, 0, 1)
    factors.append(Factor("Volume", vscore, W_VOL, f"volume {ratio:.2f}x rata-rata 20 candle"))

    # 6. Pola candlestick
    pats = detect_patterns(candles)
    pscore = sum(
        W_PATTERN if p.direction == "bullish" else -W_PATTERN if p.direction == "bearish" else 0
        for p in pats
    )
    names = ", ".join(p.name for p in pats) or "tidak ada pola"
    factors.append(Factor("Pola candle", _clamp(pscore, -W_PATTERN, W_PATTERN), W_PATTERN, names))

    # 7. Support / Resistance berbasis swing terdekat
    support, resistance = nearest_levels(price, highs, lows, k=3, lookback=100)
    sr = 0.0
    parts = []
    if resistance is not None:
        d = (resistance - price) / a
        parts.append(f"resistance {_fmt(resistance)} ({d:.1f} ATR)")
        if d < 0.8:
            sr -= W_SR * (1 - d / 0.8)
    if support is not None:
        d = (price - support) / a
        parts.append(f"support {_fmt(support)} ({d:.1f} ATR)")
        if d < 0.8:
            sr += W_SR * (1 - d / 0.8)
    factors.append(Factor(
        "Support/Resistance", _clamp(sr, -W_SR, W_SR), W_SR,
        "; ".join(parts) or "tidak ada level terdeteksi",
    ))

    total = sum(f.score for f in factors)

    if total >= SIGNAL_THRESHOLD and align > 0:
        direction = BUY
    elif total <= -SIGNAL_THRESHOLD and align < 0:
        direction = SELL
    else:
        direction = WAIT

    # Filter pasar bolak-balik (Kaufman Efficiency Ratio)
    path = sum(abs(closes[i] - closes[i - 1]) for i in range(len(closes) - ER_WINDOW, len(closes)))
    er = abs(closes[-1] - closes[-1 - ER_WINDOW]) / path if path > 0 else 0.0
    choppy = er < ER_MIN
    if choppy and direction != WAIT:
        direction = WAIT

    # Cegah entry saat harga sudah terlalu jauh melompat dari EMA9 (rawan koreksi balik)
    stretched = False
    if direction == BUY and e9[-1] is not None and (price - e9[-1]) > MAX_ENTRY_STRETCH_ATR * a:
        stretched = True
        direction = WAIT
    elif direction == SELL and e9[-1] is not None and (e9[-1] - price) > MAX_ENTRY_STRETCH_ATR * a:
        stretched = True
        direction = WAIT

    reasons: list[str] = []
    if choppy:
        reasons.append(
            f"Pasar bolak-balik (efisiensi tren {er:.2f} < {ER_MIN:.2f}); sinyal tidak dipaksakan."
        )
    elif stretched:
        reasons.append(
            f"Harga terlalu jauh dari EMA9 (jarak > {MAX_ENTRY_STRETCH_ATR:.2f} ATR); tunggu pullback agar tidak kena SL."
        )

    if direction == WAIT and not choppy and not stretched:
        if abs(total) < SIGNAL_THRESHOLD:
            reasons.append(f"Skor {total:+.0f} belum melewati ambang ±{SIGNAL_THRESHOLD:.0f}.")
        else:
            reasons.append(f"Skor {total:+.0f} kuat tetapi susunan EMA belum searah; menunggu konfirmasi.")
    elif direction != WAIT:
        want = 1 if direction == BUY else -1
        reasons.append(f"Skor {total:+.0f}, melewati ambang ±{SIGNAL_THRESHOLD:.0f}.")
        for f in sorted(factors, key=lambda x: -abs(x.score)):
            if _sgn(f.score) == want and abs(f.score) >= 0.3 * f.weight:
                reasons.append(f"{f.name}: {f.note}")

    levels = build_levels(
        direction,
        price,
        a,
        ema_fast=e9[-1],
        swing_low=support,
        swing_high=resistance,
    )
    if direction == BUY and resistance is not None and levels["tp1"] and resistance < levels["tp1"]:
        reasons.append(f"Perhatian: resistance {_fmt(resistance)} berada sebelum TP1.")
    if direction == SELL and support is not None and levels["tp1"] and support > levels["tp1"]:
        reasons.append(f"Perhatian: support {_fmt(support)} berada sebelum TP1.")

    summary = [
        f"Harga {_fmt(price)} | ATR14 {_fmt(a)}",
        f"EMA9 {_fmt(e9[-1])} | EMA21 {_fmt(e21[-1])} | EMA50 {_fmt(e50[-1])}",
        f"RSI14 {r:.1f} | Volume {ratio:.2f}x | Efisiensi tren {er:.2f}",
    ]

    return AnalysisResult(
        market=market, model="Single Time Frame", timeframe=timeframe, trend=trend,
        direction=direction, score=total, confidence=int(round(min(abs(total), 100))),
        price=price, atr=a, reasons=reasons, summary=summary, factors=factors,
        as_of=as_of, **levels,
    )
