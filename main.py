"""MASTER CALL V4.0 - titik masuk bot Telegram.

Environment (GitHub Secrets):
    EXN_API_KEY, EXN_PRIVATE_KEY, EXN_ACCOUNT_ID,
    EXN_DISCOVERY_BASE_URL (atau EXN_API_BASE_URL), TELEGRAM_BOT_TOKEN
Opsional:
    TELEGRAM_ALLOWED_USER_IDS   daftar ID pengguna yang boleh memakai bot (pisah koma)
    BOT_MAX_RUNTIME_SECONDS     lama polling sebelum keluar (default 300)
"""
from __future__ import annotations

import logging
import os
import sys

from config import ConfigError, load_exness_config, load_telegram_config
from exness.client import ExnessClient
from exness.errors import ExnessError
from handlers.analyzer import ServiceAnalyzer
from handlers.flow import Flow
from session.store import SessionStore
from telegram_bot.api import TelegramAPI, TelegramError
from telegram_bot.bot import TelegramBot
from utils.log import setup_logging

log = logging.getLogger("master_call")


def main() -> int:
    setup_logging()
    try:
        exness_cfg = load_exness_config()
        tg_cfg = load_telegram_config()
        max_seconds = float(os.environ.get("BOT_MAX_RUNTIME_SECONDS", "300"))
        client = ExnessClient(exness_cfg)
    except (ConfigError, ExnessError, ValueError) as exc:
        log.error("Konfigurasi tidak valid: %s", exc)
        return 1

    api = TelegramAPI(tg_cfg.token)
    flow = Flow(api, SessionStore(), ServiceAnalyzer(client), tg_cfg.allowed_user_ids)
    bot = TelegramBot(api, flow)
    log.info("Bot dimulai (maks %.0f detik). Config: %s", max_seconds, tg_cfg)
    try:
        processed = bot.run_polling(max_seconds)
    except TelegramError as exc:
        log.error("Polling berhenti: %s", exc)
        return 1
    log.info("Selesai. Update diproses: %d", processed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
