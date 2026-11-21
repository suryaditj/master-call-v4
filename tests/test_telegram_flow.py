from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from analysis.models import BUY, AnalysisResult
from handlers.flow import Flow
from session.store import SessionStore
from telegram_bot.bot import TelegramBot


@dataclass
class FakeAPI:
    sent: list[dict] = field(default_factory=list)
    answered: list[dict] = field(default_factory=list)
    _seq: int = 0

    def send_message(self, chat_id: int, text: str, reply_markup: dict | None = None) -> dict:
        self._seq += 1
        row = {"message_id": self._seq, "chat_id": chat_id, "text": text, "reply_markup": reply_markup}
        self.sent.append(row)
        return {"ok": True, "result": row}

    def answer_callback_query(self, callback_query_id: str, text: str | None = None, show_alert: bool = False) -> dict:
        row = {"callback_query_id": callback_query_id, "text": text, "show_alert": show_alert}
        self.answered.append(row)
        return {"ok": True, "result": True}


class FakeAnalyzer:
    def __init__(self):
        self.calls: list[tuple] = []

    def _result(self, model: str, tf: str, market: str) -> AnalysisResult:
        return AnalysisResult(
            market=market, model=model, timeframe=tf, trend="Naik", direction=BUY,
            score=70.0, confidence=70, price=100.0, atr=2.0,
            entry=100.0, sl=98.0, tp1=102.0, tp2=104.0, tp3=106.0, rr=2.0,
            reasons=["Skor uji: alasan <uji>"], summary=["ringkasan"],
            as_of=datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc),
        )

    def single(self, market: str, tf: str) -> AnalysisResult:
        self.calls.append(("single", market, tf))
        return self._result("Single Time Frame", tf, market)

    def multi(self, market: str, preset: str) -> AnalysisResult:
        self.calls.append(("multi", market, preset))
        return self._result("Multi Time Frame", preset, market)

    def one_click_2tf(self, market: str) -> tuple[list[AnalysisResult], str]:
        self.calls.append(("one_click_2tf", market))
        items = [self._result("Multi Time Frame", p, market) for p in ("H4+M15", "H1+M5", "M30+M5")]
        return items, f"<b>One Klik 2 TF • {market}</b>"


def buttons(msg: dict) -> list[dict]:
    rm = msg.get("reply_markup")
    if not rm:
        return []
    kb = json.loads(rm) if isinstance(rm, str) else rm
    return [b for row in kb["inline_keyboard"] for b in row]


def labels(msg: dict) -> list[str]:
    return [b["text"] for b in buttons(msg)]


def press(flow: Flow, msg: dict, label: str, user_id: int = 77) -> None:
    match = next((b for b in buttons(msg) if b["text"] == label), None)
    assert match is not None, f"Tombol {label!r} tidak ada di {[b['text'] for b in buttons(msg)]}"
    flow.on_callback({
        "id": f"cb-{label}",
        "from": {"id": user_id},
        "message": {"chat": {"id": msg["chat_id"]}, "message_id": msg["message_id"]},
        "data": match["callback_data"],
    })


@pytest.fixture
def env():
    api = FakeAPI()
    store = SessionStore()
    an = FakeAnalyzer()
    flow = Flow(api, store, an)
    bot = TelegramBot(api, flow)
    return api, an, flow, bot


CHAT = 5001


def test_full_single_flow_and_menus(env):
    api, an, flow, _ = env
    flow.on_start(CHAT, 77)
    press(flow, api.sent[-1], "XAUUSD")
    m = api.sent[-1]
    assert "Pilih Model Time Frame" in m["text"]
    assert "Single Time Frame" in labels(m) and "Multi Time Frame" in labels(m)
    press(flow, m, "Single Time Frame")
    m = api.sent[-1]
    assert "H1" in labels(m)
    press(flow, m, "H1")
    result = api.sent[-1]
    assert an.calls == [("single", "XAUUSD", "H1")]
    assert "Refresh" in labels(result)
    assert "XAUUSD" in result["text"] and "&lt;uji&gt;" in result["text"]


def test_full_multi_flow_refresh_and_back_navigation(env):
    api, an, flow, _ = env
    flow.on_start(CHAT, 77)
    press(flow, api.sent[-1], "BTCUSD")
    press(flow, api.sent[-1], "Multi Time Frame")
    m = api.sent[-1]
    assert "Multi Time Frame" in m["text"]
    assert "One klik 2 TF" in labels(m)
    assert "3 TF: H4+H1+M15" in labels(m)
    assert "3 TF: H1+M30+M5" in labels(m)
    press(flow, m, "3 TF: H4+H1+M15")
    assert an.calls == [("multi", "BTCUSD", "H4+H1+M15")]
    press(flow, api.sent[-1], "Refresh")
    assert an.calls[-1] == ("multi", "BTCUSD", "H4+H1+M15")
    press(flow, api.sent[-1], "Kembali")
    assert "3 TF: H4+H1+M15" in labels(api.sent[-1])


def test_one_click_2tf_flow(env):
    api, an, flow, _ = env
    flow.on_start(CHAT, 77)
    press(flow, api.sent[-1], "XAUUSD")
    press(flow, api.sent[-1], "Multi Time Frame")
    press(flow, api.sent[-1], "One klik 2 TF")
    assert an.calls == [("one_click_2tf", "XAUUSD")]
    assert "One Klik 2 TF • XAUUSD" in api.sent[-1]["text"]


def test_ganti_market_and_menu_utama(env):
    api, _, flow, _ = env
    flow.on_start(CHAT, 77)
    press(flow, api.sent[-1], "XAUUSD")
    press(flow, api.sent[-1], "Single Time Frame")
    press(flow, api.sent[-1], "Ganti Market")
    assert "Pilih Market" in api.sent[-1]["text"]
    press(flow, api.sent[-1], "BTCUSD")
    press(flow, api.sent[-1], "Single Time Frame")
    press(flow, api.sent[-1], "Menu Utama")
    assert "Pilih Market" in api.sent[-1]["text"]


def test_stale_callback_after_restart_is_handled_gracefully(env):
    api, _, flow, _ = env
    flow.on_start(CHAT, 77)
    stale_msg = dict(api.sent[-1])
    flow.on_start(CHAT, 77)
    press(flow, stale_msg, "XAUUSD")
    assert api.answered[-1]["text"]


def test_unauthorized_user_ignored_when_allowlist_set(env):
    api, _, flow, bot = env
    flow.allowed = frozenset({999})
    update = {"update_id": 10, "message": {"chat": {"id": CHAT}, "from": {"id": 123}, "text": "/start"}}
    show_called = False
    orig = flow._show

    def spy(*a, **kw):
        nonlocal show_called
        show_called = True
        return orig(*a, **kw)

    flow._show = spy
    bot.handle_update(update)
    assert not show_called
    assert api.sent[-1]["text"] == "Akses ditolak."
