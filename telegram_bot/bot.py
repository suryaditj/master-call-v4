"""Penerima update Telegram (long polling) dan pengarah ke Flow."""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

from handlers.flow import Flow
from telegram_bot.api import TelegramError

log = logging.getLogger(__name__)

MAX_CONSECUTIVE_ERRORS = 10


class TelegramBot:
    def __init__(self, api: Any, flow: Flow):
        self.api = api
        self.flow = flow

    def handle_update(self, update: dict[str, Any]) -> None:
        if "callback_query" in update:
            self.flow.on_callback(update["callback_query"])
            return
        msg = update.get("message")
        if not msg:
            return
        user = msg.get("from") or {}
        chat = msg.get("chat") or {}
        if "id" not in user or "id" not in chat:
            return
        # Perintah apa pun (/start, /menu) dan teks biasa membuka Menu Utama.
        self.flow.on_start(chat["id"], user["id"])

    def run_polling(
        self,
        max_seconds: float,
        poll_timeout: int = 25,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> int:
        """Polling sampai `max_seconds` habis (cocok untuk batas waktu GitHub Actions).

        Mengembalikan jumlah update yang diproses. Update yang sudah diproses
        dikonfirmasi ke Telegram sebelum keluar agar tidak diproses dua kali.
        """
        try:
            self.api.delete_webhook()
        except TelegramError as exc:
            log.warning("deleteWebhook gagal: %s", exc)

        deadline = clock() + max_seconds
        offset: int | None = None
        processed = errors = 0
        while True:
            remaining = deadline - clock()
            if remaining <= 0:
                break
            try:
                updates = self.api.get_updates(offset, timeout=int(max(1, min(poll_timeout, remaining))))
                errors = 0
            except TelegramError as exc:
                errors += 1
                log.warning("getUpdates gagal (%d): %s", errors, exc)
                if errors >= MAX_CONSECUTIVE_ERRORS:
                    raise
                sleep(min(5.0, max(0.0, remaining)))
                continue
            for update in updates:
                offset = update["update_id"] + 1
                try:
                    self.handle_update(update)
                except Exception as exc:  # noqa: BLE001 - satu update buruk tidak boleh menghentikan bot
                    log.error("Gagal memproses update: %s", type(exc).__name__)
                processed += 1

        if offset is not None:  # konfirmasi update terakhir
            try:
                self.api.get_updates(offset, timeout=0)
            except TelegramError as exc:
                log.warning("Konfirmasi update gagal: %s", exc)
        return processed
