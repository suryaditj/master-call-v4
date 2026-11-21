"""Cek koneksi dan autentikasi Exness API (Tahap 2).

Jalankan dengan environment variable terisi:
    python scripts/check_auth.py

Hanya memanggil endpoint GET read-only. Tidak mencetak kredensial.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import ConfigError, load_exness_config  # noqa: E402
from exness.client import ExnessClient  # noqa: E402
from exness.errors import ExnessError  # noqa: E402


def main() -> int:
    try:
        cfg = load_exness_config()
        client = ExnessClient(cfg)
        print("Config:", cfg)
        print("Access Point:", client.access_point())
        print("Detail akun:", json.dumps(client.get_account_details(), indent=2)[:1500])
        print("OK: autentikasi berhasil.")
        return 0
    except (ConfigError, ExnessError) as exc:
        print(f"GAGAL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
