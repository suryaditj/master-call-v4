"""Probe endpoint candle Exness (Tahap 3).

Tujuan: melihat respons MENTAH dan memastikan format `from` yang diterima,
sebelum parser ditulis. Hanya GET read-only. Tidak mencetak kredensial.

    python scripts/check_candles.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import SYMBOLS, ConfigError, load_exness_config  # noqa: E402
from exness.client import ExnessClient  # noqa: E402
from exness.errors import ExnessError, ExnessRequestError  # noqa: E402

# (simbol, timeframe, berapa jam ke belakang)
# BTC trading 24/7; emas libur akhir pekan, jadi pakai H1 dengan rentang lebih jauh.
CASES = [
    ("BTCUSD", "M5", 2),
    ("XAUUSD", "H1", 72),
]


def iso_formats(dt: datetime) -> list[tuple[str, str]]:
    return [
        ("ISO +00:00", dt.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00"),
        ("ISO Z", dt.strftime("%Y-%m-%dT%H:%M:%S") + "Z"),
    ]


def main() -> int:
    try:
        client = ExnessClient(load_exness_config())
    except (ConfigError, ExnessError) as exc:
        print(f"GAGAL: {exc}", file=sys.stderr)
        return 1

    ok = False
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    for market, tf, hours in CASES:
        symbol = SYMBOLS[market]
        start = now - timedelta(hours=hours)
        print(f"\n=== {symbol} {tf} ===")
        for label, from_value in iso_formats(start):
            try:
                data = client.get_candles_raw(
                    symbol, tf, from_value, count=5, price_type="bid"
                )
            except ExnessRequestError as exc:
                print(f"[{label}] ditolak: HTTP {exc.status} code={exc.code} {exc.message}")
                continue
            except ExnessError as exc:
                print(f"[{label}] error: {exc}")
                continue
            print(f"[{label}] OK. Respons mentah (dipotong 2500 karakter):")
            print(json.dumps(data, indent=2)[:2500])
            ok = True
            break

    print("\nSELESAI." if ok else "\nTidak ada permintaan yang berhasil.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
