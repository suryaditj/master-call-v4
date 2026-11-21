"""Sistem skor teknikal untuk satu timeframe.

Setiap faktor memberi skor antara -bobot dan +bobot (positif = bullish).
Jumlah bobot = 100, jadi skor total berada di -100..+100.

PENTING: ambang dan bobot di bawah adalah titik awal yang masuk akal, BELUM
divalidasi dengan backtest. "Confidence" adalah ukuran keselarasan indikator,
bukan probabilitas profit.
"""
from __future__ import annotations

from typing import Sequence

from analysis.models import BUY, SELL, WAIT, AnalysisResult, Factor
from exness.candles import Candle
from exness.errors import InsufficientDataError
from indicators import atr, detect_patterns, ema, nearest_levels, rsi, sma

MIN_CANDLES = 100          # minimum agar EMA50, RSI, ATR, dan S/R layak
ANALYSIS_CANDLES = 150     # jumlah candle yang diminta untuk analisis
SIGNAL_THRESHOLD = 35.0    # |skor| minimal untuk BUY/SELL
ER_WINDOW = 30             # jendela efisiensi tren (candle)
ER_MIN = 0.20              # di bawah ini = pasar bolak-balik -> WAIT
SL_ATR_MULT = 1.5          # jarak SL = 1.5 x ATR
TP_R_MULTIPLES = (1.0, 2.0, 3.0)

W_ALIGN, W_SLOPE, W_RSI, W_MOM, W_VOL, W_PATTERN, W_SR = 25, 10, 20, 15, 10, 10, 10


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _sgn(x: float) -> int:
    return (x > 0) - (x < 0)


def build_levels(direction: str, price: float, atr_value: float) -> dict[str, float | None]:
    """Entry = harga terakhir; SL = 1.5 ATR; TP = 1R, 2R, 3R."""
    if direction not in (BUY, SELL) or atr_value <= 0:
        return {"entry": None, "sl": None, "tp1": None, "tp2": None, "tp3": None, "rr": None}
    risk = SL_ATR_MULT * atr_value
    sign = 1 if direction == BUY else -1
    return {
        "entry": price,
        "sl": price - sign * risk,
        "tp1": price + sign * risk * TP_R_MULTIPLES[0],
        "tp2": price + sign * risk * TP_R_MULTIPLES[1],
        "tp3": price + sign * risk * TP_R_MULTIPLES[2],
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
        "Kemiringan EMA21", W_SLOPE * _clamp(slope / 0.5, -1, 1), W_SLOPE,
        f"EMA21 bergerak {slope:+.2f} ATR dalam 5 candle",
    ))

    # 3. RSI 14 (di atas 70 / di bawah 30 = zona jenuh, bobot dikurangi)
    if r >= 70:
        s = W_RSI * 0.5
    elif r >= 50:
        s = W_RSI * (r - 50) / 20
    elif r > 30:
        s = -W_RSI * (50 - r) / 20
    else:
        s = -W_RSI * 0.5
    zone = " (jenuh beli)" if r >= 70 else " (jenuh jual)" if r <= 30 else ""
    factors.append(Factor("RSI 14", s, W_RSI, f"RSI {r:.1f}{zone}"))

    # 4. Momentum harga 10 candle dalam satuan ATR
    mom = (closes[-1] - closes[-11]) / a
    factors.append(Factor(
        "Momentum", W_MOM * _clamp(mom / 3, -1, 1), W_MOM,
        f"harga bergerak {mom:+.2f} ATR dalam 10 candle",
    ))

    # 5. Volume (volume candle terakhir vs rata-rata 20)
    vs = vol_sma[-1]
    ratio = (vols[-1] / vs) if vs and vs > 0 else 1.0
    body_dir = _sgn(candles[-1].close - candles[-1].open)
    vscore = body_dir * W_VOL * _clamp((ratio - 1) / 0.5, 0, 1)
    factors.append(Factor("Volume", vscore, W_VOL, f"volume {ratio:.2f}x rata-rata 20 candle"))

    # 6. Pola candlestick
    pats = detect_patterns(candles)
    pscore = sum(W_PATTERN if p.direction == "bullish" else -W_PATTERN if p.direction == "bearish" else 0
                 for p in pats)
    names = ", ".join(p.name for p in pats) or "tidak ada pola"
    factors.append(Factor("Pola candle", _clamp(pscore, -W_PATTERN, W_PATTERN), W_PATTERN, names))

    # 7. Kedekatan support/resistance (dalam satuan ATR)
    support, resistance = nearest_levels(price, highs, lows, k=3, lookback=100)
    sr = 0.0
    parts = []
    if resistance is not None:
        d = (resistance - price) / a
        parts.append(f"resistance {_fmt(resistance)} ({d:.1f} ATR)")
        if d < 1:
            sr -= W_SR * (1 - d)
    if support is not None:
        d = (price - support) / a
        parts.append(f"support {_fmt(support)} ({d:.1f} ATR)")
        if d < 1:
            sr += W_SR * (1 - d)
    factors.append(Factor("Support/Resistance", _clamp(sr, -W_SR, W_SR), W_SR,
                          "; ".join(parts) or "tidak ada level terdeteksi"))

    total = sum(f.score for f in factors)

    # Keputusan: skor harus melewati ambang DAN susunan EMA tidak berlawanan.
    if total >= SIGNAL_THRESHOLD and align > 0:
        direction = BUY
    elif total <= -SIGNAL_THRESHOLD and align < 0:
        direction = SELL
    else:
        direction = WAIT

    # Filter pasar bolak-balik: efisiensi tren Kaufman atas ER_WINDOW candle.
    path = sum(abs(closes[i] - closes[i - 1]) for i in range(len(closes) - ER_WINDOW, len(closes)))
    er = abs(closes[-1] - closes[-1 - ER_WINDOW]) / path if path > 0 else 0.0
    choppy = er < ER_MIN
    if choppy and direction != WAIT:
        direction = WAIT

    reasons: list[str] = []
    if choppy:
        reasons.append(
            f"Pasar bolak-balik (efisiensi tren {er:.2f} < {ER_MIN:.2f}); sinyal tidak dipaksakan."
        )
    if direction == WAIT and not choppy:
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

    levels = build_levels(direction, price, a)
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
