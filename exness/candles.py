"""Parser dan pengambil candle Exness.

Skema respons (dokumentasi resmi, price_type bid/ask):
    {"candles": [{"time", "open", "high", "low", "close", "volume"}, ...]}
`time` adalah waktu buka candle (date-time). Format `price_type=both`
(CandleBidAsk) berbeda dan SENGAJA tidak didukung di sini.

Catatan yang masih perlu dibuktikan dengan data asli (scripts/check_candles.py):
- format string `from`/`to` yang diterima server (di sini ISO 8601 UTC "+00:00"),
- batas jumlah candle per request (DEFAULT_MAX_WINDOW_CANDLES konservatif).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from exness.errors import CandleDataError, InsufficientDataError

TF_SECONDS: dict[str, int] = {
    "S1": 1, "S5": 5, "S15": 15,
    "M1": 60, "M3": 180, "M5": 300, "M10": 600, "M15": 900, "M30": 1800,
    "H1": 3600, "H2": 7200, "H4": 14400,
    "D1": 86400, "W1": 604800,
}  # "MN" tidak dimasukkan: panjang bulan tidak tetap.

DEFAULT_MAX_WINDOW_CANDLES = 1000


@dataclass(frozen=True)
class Candle:
    time: datetime  # waktu buka, UTC
    open: float
    high: float
    low: float
    close: float
    volume: float


def to_exness_time(dt: datetime) -> str:
    """Format waktu untuk parameter `from`/`to`."""
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00"


def parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise CandleDataError(f"Field 'time' bukan string: {type(value).__name__}")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CandleDataError("Field 'time' bukan tanggal-waktu ISO 8601.") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_candles(payload: Any) -> list[Candle]:
    """Ubah respons JSON menjadi daftar Candle (urut naik menurut waktu)."""
    if not isinstance(payload, dict) or not isinstance(payload.get("candles"), list):
        raise CandleDataError("Respons tidak memiliki daftar 'candles'.")
    out: list[Candle] = []
    for i, raw in enumerate(payload["candles"]):
        if not isinstance(raw, dict):
            raise CandleDataError(f"Candle ke-{i} bukan objek.")
        missing = [k for k in ("time", "open", "high", "low", "close", "volume") if k not in raw]
        if missing:
            raise CandleDataError(
                f"Candle ke-{i} kehilangan field: {', '.join(missing)} "
                "(format price_type=both tidak didukung)."
            )
        try:
            values = [float(raw[k]) for k in ("open", "high", "low", "close", "volume")]
        except (TypeError, ValueError) as exc:
            raise CandleDataError(f"Candle ke-{i} berisi angka tidak valid.") from exc
        o, h, l, c, v = values
        if h < l or h < max(o, c) or l > min(o, c):
            raise CandleDataError(f"Candle ke-{i} tidak konsisten (high/low).")
        out.append(Candle(parse_time(raw["time"]), o, h, l, c, v))
    out.sort(key=lambda c: c.time)
    return out


def fetch_candles(
    client: Any,
    symbol: str,
    timeframe: str,
    needed: int,
    *,
    now: datetime | None = None,
    price_type: str = "bid",
    max_window_candles: int = DEFAULT_MAX_WINDOW_CANDLES,
    closed_only: bool = True,
) -> list[Candle]:
    """Ambil `needed` candle terakhir yang sudah tutup.

    Rentang waktu diperlebar bertahap agar celah pasar tutup (akhir pekan)
    tidak membuat data kurang. Jika batas habis dan data tetap kurang,
    dilempar InsufficientDataError (tidak ada sinyal palsu).
    """
    if timeframe not in TF_SECONDS:
        raise ValueError(f"Timeframe tidak didukung untuk analisis: {timeframe!r}")
    if needed < 1:
        raise ValueError("needed harus >= 1")
    step = timedelta(seconds=TF_SECONDS[timeframe])
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    window = max(int(needed * 1.5), needed + 5)
    while True:
        window = min(window, max_window_candles)
        start = now - step * window
        payload = client.get_candles_raw(
            symbol, timeframe, to_exness_time(start),
            to=to_exness_time(now), price_type=price_type,
        )
        candles = parse_candles(payload)
        if closed_only:
            candles = [c for c in candles if c.time + step <= now]
        if len(candles) >= needed:
            return candles[-needed:]
        if window >= max_window_candles:
            raise InsufficientDataError(
                f"Data {symbol} {timeframe} kurang: dapat {len(candles)} candle, "
                f"butuh {needed}."
            )
        window *= 2
