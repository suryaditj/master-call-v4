from __future__ import annotations

from datetime import datetime, timezone

from analysis.models import BUY, WAIT, AnalysisResult, Factor
from telegram_bot.bot import TelegramBot
from telegram_bot.format import format_html


class DummyAPI:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self._updates: list[dict] = []
        self.fail_edit = False

    def queue_updates(self, *updates: dict) -> None:
        self._updates.extend(updates)

    def _call(self, method: str, **params) -> dict:
        self.calls.append((method, params))
        if method == "getUpdates":
            out, self._updates = self._updates, []
            return {"ok": True, "result": out}
        if method == "editMessageText" and self.fail_edit:
            return {"ok": False, "description": "Bad Request: message is not modified"}
        return {"ok": True, "result": {"message_id": 55}}

    def close(self) -> None:
        pass


class DummyAnalyzer:
    def analyze_single(self, market: str, tf: str) -> AnalysisResult:
        return AnalysisResult(
            market=market, model="Single Time Frame", timeframe=tf,
            trend="Naik", direction=BUY, score=65.0, confidence=65,
            price=2500.0, atr=10.0, entry=2500.0, sl=2490.0,
            tp1=2510.0, tp2=2520.0, tp3=2530.0, rr=2.0,
            reasons=["Skor +65, melewati ambang ±55."],
            summary=["Harga 2,500.00 | ATR14 10.00"],
            as_of=datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc),
        )

    def analyze_multi(self, market: str, tfs: list[str]) -> AnalysisResult:
        r = self.analyze_single(market, "+".join(tfs))
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
    api.queue_updates(
        {"update_id": 1, "message": {"chat": {"id": 10}, "from": {"id": 20}, "text": "/start"}},
        {"update_id": 2, "callback_query": {
            "id": "cb1", "from": {"id": 20},
            "message": {"chat": {"id": 10}, "message_id": 55},
            "data": "m:XAUUSD",
        }},
        {"update_id": 3, "callback_query": {
            "id": "cb2", "from": {"id": 20},
            "message": {"chat": {"id": 10}, "message_id": 55},
            "data": "tf:single",
        }},
        {"update_id": 4, "callback_query": {
            "id": "cb3", "from": {"id": 20},
            "message": {"chat": {"id": 10}, "message_id": 55},
            "data": "s:H1",
        }},
    )
    bot = TelegramBot(api, DummyAnalyzer())
    n = bot.poll_once()
    assert n == 4
    methods = [m for m, _ in api.calls]
    assert "sendMessage" in methods and "editMessageText" in methods and "answerCallbackQuery" in methods
    assert bot.offset == 5
