from __future__ import annotations

from datetime import datetime, timezone

from analysis.models import BUY, WAIT, AnalysisResult, Factor
from handlers.flow import Flow
from session.store import SessionStore
from telegram_bot.bot import TelegramBot
from telegram_bot.format import format_html


class DummyAPI:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self._updates: list[dict] = []
        self._seq: int = 0

    def queue_updates(self, *updates: dict) -> None:
        self._updates.extend(updates)

    def delete_webhook(self) -> dict:
        self.calls.append(("deleteWebhook", {}))
        return {"ok": True, "result": True}

    def get_updates(self, offset: int | None = None, timeout: int = 25) -> list[dict]:
        self.calls.append(("getUpdates", {"offset": offset, "timeout": timeout}))
        if timeout == 0:
            return []
        out, self._updates = self._updates, []
        return out

    def send_message(self, chat_id: int, text: str, reply_markup: dict | None = None) -> dict:
        self._seq += 1
        params = {"chat_id": chat_id, "text": text, "reply_markup": reply_markup}
        self.calls.append(("sendMessage", params))
        return {"ok": True, "result": {"message_id": self._seq, **params}}

    def answer_callback_query(self, callback_query_id: str, text: str | None = None, show_alert: bool = False) -> dict:
        params = {"callback_query_id": callback_query_id, "text": text, "show_alert": show_alert}
        self.calls.append(("answerCallbackQuery", params))
        return {"ok": True, "result": True}

    def close(self) -> None:
        pass


class DummyAnalyzer:
    def single(self, market: str, tf: str) -> AnalysisResult:
        return AnalysisResult(
            market=market, model="Single Time Frame", timeframe=tf,
            trend="Naik", direction=BUY, score=65.0, confidence=65,
            price=2500.0, atr=10.0, entry=2500.0, sl=2490.0,
            tp1=2510.0, tp2=2520.0, tp3=2530.0, rr=2.0,
            reasons=["Skor +65, melewati ambang ±55."],
            summary=["Harga 2,500.00 | ATR14 10.00"],
            as_of=datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc),
        )

    def multi(self, market: str, preset: str) -> AnalysisResult:
        r = self.single(market, preset)
        r.model = "Multi Time Frame"
        return r


def _result(direction: str) -> AnalysisResult:
    return AnalysisResult(
        market="XAUUSD", model="Single Time Frame", timeframe="H1",
        trend="Naik <x>", direction=direction, score=50.0, confidence=50,
        price=3540.0, atr=12.5,
        entry=3540.0 if direction != WAIT else None,
        sl=3527.5 if direction != WAIT else None,
        tp1=3552.5 if direction != WAIT else None,
        tp2=3565.0 if direction != WAIT else None,
        tp3=3577.5 if direction != WAIT else None,
        rr=2.0 if direction != WAIT else None,
        reasons=["Skor uji: alasan <x>"],
        summary=["s"],
        factors=[Factor("EMA", 25.0, 25.0, "Naik <x>")],
        as_of=datetime(2026, 4, 17, 10, 30, tzinfo=timezone.utc),
    )


def test_html_format_has_all_fields_and_escapes():
    text = format_html(_result("BUY"))
    for key in ("XAUUSD", "Single Time Frame", "H1", "Tren:", "BUY", "Entry:", "Stop Loss:",
                "TP1:", "TP2:", "TP3:", "Risk/Reward", "50%", "Alasan", "Ringkasan indikator",
                "Ini hanya analisa"):
        assert key in text
    assert "&lt;x&gt;" in text and "<x>" not in text


def test_html_format_wait_hides_entry_sl_tp():
    text = format_html(_result(WAIT))
    assert "WAIT" in text
    for hidden in ("Entry:", "Stop Loss:", "TP1:", "TP2:", "TP3:"):
        assert hidden not in text


def test_bot_polls_message_and_callback_and_edits_message():
    api = DummyAPI()
    store = SessionStore()
    flow = Flow(api, store, DummyAnalyzer())
    sess = store.reset(20)
    seq_after_start = sess.seq + 1
    seq_after_mk = sess.seq + 2
    seq_after_md = sess.seq + 3

    api.queue_updates(
        {"update_id": 1, "message": {"chat": {"id": 10}, "from": {"id": 20}, "text": "/start"}},
        {"update_id": 2, "callback_query": {
            "id": "cb1", "from": {"id": 20},
            "message": {"chat": {"id": 10}, "message_id": 55},
            "data": f"mk:{sess.sid}:{seq_after_start}:XAUUSD",
        }},
        {"update_id": 3, "callback_query": {
            "id": "cb2", "from": {"id": 20},
            "message": {"chat": {"id": 10}, "message_id": 55},
            "data": f"md:{sess.sid}:{seq_after_mk}:single",
        }},
        {"update_id": 4, "callback_query": {
            "id": "cb3", "from": {"id": 20},
            "message": {"chat": {"id": 10}, "message_id": 55},
            "data": f"tf:{sess.sid}:{seq_after_md}:H1",
        }},
    )
    bot = TelegramBot(api, flow)
    n = bot.run_polling(max_seconds=1.0, poll_timeout=1)
    assert n == 4
    methods = [m for m, _ in api.calls]
    assert "sendMessage" in methods and "answerCallbackQuery" in methods
