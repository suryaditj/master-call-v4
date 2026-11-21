"""Klien tipis Telegram Bot API.

Sengaja HANYA berisi: getUpdates, sendMessage, answerCallbackQuery, deleteWebhook.
Tidak ada editMessageText maupun deleteMessage (aturan menu: pesan lama tetap
terlihat). Token ada di URL, jadi pesan error TIDAK PERNAH memuat URL/token.
"""
from __future__ import annotations

from typing import Any

import requests


class TelegramError(Exception):
    pass


class TelegramAPI:
    def __init__(self, token: str, session: requests.Session | None = None):
        self._base = f"https://api.telegram.org/bot{token}/"
        self._session = session or requests.Session()

    def __repr__(self) -> str:
        return "TelegramAPI()"

    def _call(self, method: str, payload: dict[str, Any], timeout: float = 15.0) -> Any:
        try:
            resp = self._session.post(self._base + method, json=payload, timeout=timeout)
        except requests.RequestException as exc:
            raise TelegramError(f"{method}: gagal terhubung ({type(exc).__name__})") from None
        try:
            body = resp.json()
        except ValueError:
            raise TelegramError(f"{method}: respons bukan JSON (HTTP {resp.status_code})") from None
        if not body.get("ok"):
            desc = body.get("description", "tanpa deskripsi")
            raise TelegramError(f"{method}: {desc} (kode {body.get('error_code')})")
        return body.get("result")

    def get_updates(self, offset: int | None, timeout: int) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            payload["offset"] = offset
        return self._call("getUpdates", payload, timeout=timeout + 10) or []

    def send_message(
        self, chat_id: int, text: str, reply_markup: dict[str, Any] | None = None,
        parse_mode: str | None = "HTML",
    ) -> Any:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text,
                                   "disable_web_page_preview": True}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return self._call("sendMessage", payload)

    def answer_callback_query(
        self, callback_query_id: str, text: str | None = None, show_alert: bool = False
    ) -> Any:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
            payload["show_alert"] = show_alert
        return self._call("answerCallbackQuery", payload)

    def delete_webhook(self) -> Any:
        """Perlu agar getUpdates tidak bentrok dengan webhook lama."""
        return self._call("deleteWebhook", {"drop_pending_updates": False})
