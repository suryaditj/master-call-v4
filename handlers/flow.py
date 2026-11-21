"""Alur menu Telegram dan state per pengguna.

Aturan (dari spesifikasi):
- Semua menu dikirim sebagai pesan BARU (send_message). Tidak ada edit/hapus.
- Hanya tombol dari menu terbaru milik pengguna yang berlaku; tombol lama
  menampilkan pemberitahuan + tombol Menu Utama dan TIDAK mengubah sesi.
- Menu Utama selalu berlaku. Refresh selalu mengambil data baru dari Exness.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from html import escape
from typing import Any, Callable, Collection

from analysis.multi_tf import MULTI_3TF_PRESETS, ONE_CLICK_2TF_KEY
from analysis.service import SINGLE_TIMEFRAMES
from config import SYMBOLS
from exness.errors import (
    ExnessAuthError, ExnessError, ExnessNetworkError, ExnessRequestError, InsufficientDataError,
)
from handlers.analyzer import Analyzer
from keyboards import menus
from keyboards.callbacks import Callback, decode
from session.store import MAIN, MODEL, MULTI, RESULT, SINGLE, Session, SessionStore
from telegram_bot.format import format_html

log = logging.getLogger(__name__)

STALE_ALERT = "Tombol ini sudah tidak berlaku."
STALE_TEXT = "Menu ini sudah kedaluwarsa. Silakan kembali ke Menu Utama."
LOADING_TEXT = "⏳ Mengambil data terbaru dari Exness dan menghitung analisis..."

VALID_MULTI_KEYS = frozenset({ONE_CLICK_2TF_KEY, *MULTI_3TF_PRESETS.keys()})


class Flow:
    def __init__(
        self,
        api: Any,
        store: SessionStore,
        analyzer: Analyzer,
        allowed_users: Collection[int] = (),
        clock: Callable[[], datetime] | None = None,
    ):
        self.api = api
        self.store = store
        self.analyzer = analyzer
        self.allowed = frozenset(allowed_users)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    # ---- titik masuk ------------------------------------------------------
    def on_start(self, chat_id: int, user_id: int) -> None:
        if not self._allowed(user_id):
            self.api.send_message(chat_id, "Akses ditolak.")
            return
        self._show(chat_id, self.store.reset(user_id), MAIN)

    def on_callback(self, cq: dict[str, Any]) -> None:
        cq_id = cq["id"]
        user_id = cq["from"]["id"]
        chat_id = ((cq.get("message") or {}).get("chat") or {}).get("id")
        if chat_id is None:
            self.api.answer_callback_query(cq_id)
            return
        if not self._allowed(user_id):
            self.api.answer_callback_query(cq_id, "Akses ditolak.", show_alert=True)
            return

        cb = decode(cq.get("data"))
        if cb is None:
            self._stale(cq_id, chat_id, self.store.get(user_id))
            return

        if cb.action == "home":  # selalu berlaku, menjadikan sesi baru
            self.api.answer_callback_query(cq_id)
            self._show(chat_id, self.store.reset(user_id), MAIN)
            return

        session = self.store.get(user_id)
        if session is None or cb.sid != session.sid or cb.seq != session.seq:
            self._stale(cq_id, chat_id, session)
            return

        self.api.answer_callback_query(cq_id)
        if not self._dispatch(chat_id, session, cb):
            # Argumen tidak sah / urutan menu tidak masuk akal: perlakukan sebagai kedaluwarsa.
            self.api.send_message(chat_id, STALE_TEXT, reply_markup=menus.notice_menu(session.sid))

    # ---- logika ----------------------------------------------------------
    def _dispatch(self, chat_id: int, s: Session, cb: Callback) -> bool:
        a, arg = cb.action, cb.arg
        if a == "mk" and arg in SYMBOLS:
            s.market, s.model, s.timeframe = arg, None, None
            self._show(chat_id, s, MODEL)
        elif a == "md" and arg in ("single", "multi") and s.market:
            s.model, s.timeframe = arg, None
            self._show(chat_id, s, SINGLE if arg == "single" else MULTI)
        elif a == "tf" and s.market and s.model == "single" and arg in SINGLE_TIMEFRAMES:
            s.timeframe = arg
            self._run_analysis(chat_id, s)
        elif a == "mt" and s.market and s.model == "multi" and arg in VALID_MULTI_KEYS:
            s.timeframe = arg
            self._run_analysis(chat_id, s)
        elif a == "rf" and s.market and s.model and s.timeframe:
            self._run_analysis(chat_id, s)
        elif a == "bk":
            self._show(chat_id, s, self._back_target(s))
        elif a == "chm":
            s.market, s.model, s.timeframe = None, None, None
            self._show(chat_id, s, MAIN)
        elif a == "chtf" and s.market:
            s.model, s.timeframe = None, None
            self._show(chat_id, s, MODEL)
        else:
            return False
        return True

    @staticmethod
    def _back_target(s: Session) -> str:
        if s.menu == RESULT:
            return SINGLE if s.model == "single" else MULTI
        if s.menu in (SINGLE, MULTI):
            return MODEL
        return MAIN  # dari MODEL (atau MAIN) kembali ke pilih market

    def _run_analysis(self, chat_id: int, s: Session) -> None:
        s.requested_at = self._clock()
        self.api.send_message(chat_id, LOADING_TEXT)  # bukan menu, tanpa tombol
        try:
            if s.model == "single":
                result = self.analyzer.single(s.market, s.timeframe)
                text = format_html(result)
            elif s.timeframe == ONE_CLICK_2TF_KEY and hasattr(self.analyzer, "one_click_2tf"):
                _, text = self.analyzer.one_click_2tf(s.market)
            else:
                result = self.analyzer.multi(s.market, s.timeframe)
                text = format_html(result)
        except InsufficientDataError as exc:
            text = f"⚠️ Data tidak cukup: {escape(str(exc))}\nTidak ada sinyal yang dibuat."
        except ExnessAuthError:
            text = "⚠️ Autentikasi Exness bermasalah. Tidak ada sinyal yang dibuat."
        except (ExnessNetworkError, ExnessRequestError, ExnessError) as exc:
            text = f"⚠️ Exness API tidak dapat diakses: {escape(str(exc))}\nTidak ada sinyal yang dibuat."
        except Exception as exc:  # noqa: BLE001 - jangan bocorkan detail internal ke pengguna
            log.error("Kesalahan tak terduga saat analisis: %s", type(exc).__name__)
            text = "⚠️ Terjadi kesalahan internal. Tidak ada sinyal yang dibuat. Coba Refresh."
        self._show(chat_id, s, RESULT, text)

    # ---- tampilan --------------------------------------------------------
    def _text_for(self, s: Session, menu: str) -> str:
        if menu == MAIN:
            return "<b>Pilih Market</b>"
        if menu == MODEL:
            return f"<b>Pilih Model Time Frame</b>\nMarket: {escape(s.market or '-')}"
        if menu == SINGLE:
            return f"<b>Single Time Frame</b>\nMarket: {escape(s.market or '-')}\nPilih time frame:"
        return f"<b>Multi Time Frame</b>\nMarket: {escape(s.market or '-')}\nPilih kombinasi:"

    def _show(self, chat_id: int, s: Session, menu: str, text: str | None = None) -> None:
        """Kirim menu sebagai pesan baru dan jadikan generasi menu terbaru."""
        s.seq += 1
        s.previous_menu, s.menu = s.menu, menu
        builders = {MAIN: menus.main_menu, MODEL: menus.model_menu, SINGLE: menus.single_menu,
                    MULTI: menus.multi_menu, RESULT: menus.result_menu}
        self.api.send_message(
            chat_id, text if text is not None else self._text_for(s, menu),
            reply_markup=builders[menu](s.sid, s.seq),
        )

    def _stale(self, cq_id: str, chat_id: int, session: Session | None) -> None:
        self.api.answer_callback_query(cq_id, STALE_ALERT)
        sid = session.sid if session else "0000"
        # Pesan pemberitahuan TIDAK menaikkan seq: menu terbaru tetap berlaku.
        self.api.send_message(chat_id, STALE_TEXT, reply_markup=menus.notice_menu(sid))

    def _allowed(self, user_id: int) -> bool:
        return not self.allowed or user_id in self.allowed
