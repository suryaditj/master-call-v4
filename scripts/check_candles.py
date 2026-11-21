"""Probe nama instrumen & endpoint candle Exness (Tahap 3).

Dokumentasi Exness tidak menyediakan daftar instrumen, jadi skrip ini mencoba
beberapa kandidat nama (dengan jeda agar tidak kena rate limit) dan mencetak
hasilnya. Hanya GET read-only. Tidak mencetak kredensial.

    python scripts/check_candles.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import ConfigError, load_exness_config  # noqa: E402
from exness.candles import to_exness_time  # noqa: E402
from exness.client import ExnessClient  # noqa: E402
from exness.errors import ExnessError, ExnessRequestError  # noqa: E402

# Kandidat nama. EURUSD/EURUSDm adalah pembanding: jika salah satunya berhasil
# tetapi emas/bitcoin tidak, masalahnya ada pada penamaan simbol, bukan akun.
CANDIDATES = [
    "XAUUSD", "XAU/USD", "XAUUSDm",
    "BTCUSD", "BTC/USD", "BTCUSDm",
    "EURUSD", "EURUSDm",
]
TIMEFRAME = "H1"
HOURS_BACK = 72
PAUSE_SECONDS = 2.0
RATE_LIMIT_WAIT = 10.0


def probe(client: ExnessClient, instrument: str, start: datetime, end: datetime):
    for attempt in (1, 2):
        try:
            return client.get_candles_raw(
                instrument, TIMEFRAME, to_exness_time(start),
                to=to_exness_time(end), price_type="bid",
            )
        except ExnessRequestError as exc:
            if exc.status == 429 and attempt == 1:
                print(f"  (rate limit, tunggu {RATE_LIMIT_WAIT:.0f} detik lalu coba lagi)")
                time.sleep(RATE_LIMIT_WAIT)
                continue
            raise
    return None


def main() -> int:
    try:
        client = ExnessClient(load_exness_config())
    except (ConfigError, ExnessError) as exc:
        print(f"GAGAL: {exc}", file=sys.stderr)
        return 1

    end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = end - timedelta(hours=HOURS_BACK)
    working: list[str] = []

    for name in CANDIDATES:
        print(f"\n--- {name} {TIMEFRAME} ---")
        try:
            data = probe(client, name, start, end)
        except ExnessRequestError as exc:
            print(f"  ditolak: HTTP {exc.status} code={exc.code} {exc.message}")
        except ExnessError as exc:
            print(f"  error: {exc}")
        else:
            candles = data.get("candles") if isinstance(data, dict) else None
            n = len(candles) if isinstance(candles, list) else "?"
            print(f"  OK: {n} candle")
            if candles:
                print("  candle pertama :", json.dumps(candles[0]))
                print("  candle terakhir:", json.dumps(candles[-1]))
            working.append(name)
        time.sleep(PAUSE_SECONDS)

    print("\nNama yang berhasil:", working if working else "(tidak ada)")
    return 0 if working else 1


if __name__ == "__main__":
    raise SystemExit(main())
