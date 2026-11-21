"""Jalankan analisis nyata (Tahap 5) untuk XAUUSD dan BTCUSD."""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from analysis.formatter import format_result  # noqa: E402
from analysis.service import MULTI_PRESETS, analyze_multi, analyze_single  # noqa: E402
from config import ConfigError, load_exness_config  # noqa: E402
from exness.client import ExnessClient  # noqa: E402
from exness.errors import ExnessError  # noqa: E402


def main() -> int:
    try:
        client = ExnessClient(load_exness_config())
    except (ConfigError, ExnessError) as exc:
        print(f"GAGAL: {exc}", file=sys.stderr)
        return 1

    failures = 0
    jobs = [("single", "H1"), ("multi", "M30+H1+H4")]
    for market in ("XAUUSD", "BTCUSD"):
        for kind, tf in jobs:
            print(f"\n{'=' * 8} {market} {kind} {tf} {'=' * 8}")
            try:
                if kind == "single":
                    result = analyze_single(client, market, tf)
                else:
                    result = analyze_multi(client, market, MULTI_PRESETS[tf])
                print(format_result(result))
            except ExnessError as exc:
                failures += 1
                print(f"GAGAL: {exc}")
            time.sleep(1.0)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
