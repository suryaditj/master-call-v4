"""Pengaturan logging yang aman (tidak membocorkan URL berisi token)."""
from __future__ import annotations

import logging


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # requests/urllib3 dapat mencatat URL lengkap (termasuk token Telegram).
    for noisy in ("urllib3", "requests", "chardet", "charset_normalizer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
