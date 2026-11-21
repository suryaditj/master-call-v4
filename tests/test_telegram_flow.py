from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from analysis.models import BUY, AnalysisResult
from handlers.flow import Flow
from telegram_bot.bot import TelegramBot


@dataclass
class FakeAPI:
    sent: list[dict]
    edited: list[dict]
    answered: list[dict]
    _seq: int = 0

    def __init__(self):
        self.sent, self.edited, self.answered, self._seq = [], [], [], 0

    def _call(self, method: str, **params) -> dict:
        self._seq += 1
        if method == "sendMessage":
            row = {"message_id": self._seq, **params}
            self.sent.append(row)
            return {"ok": True, "result": row}
        if method == "editMessageText":
            self.edited.append(params)
            for m in self.sent:
                if m["chat_id"] == params["chat_id"] and m["message_id"] == params["message_id"]:
                    m.update(params)
            return {"ok": True, "result": params}
        if method == "answerCallbackQuery":
            self.answered.append(params)
            return {"ok": True, "result": True}
        raise AssertionError(f"Method tak terduga: {method}")


class FakeAnalyzer:
    def __init__(self):
        self.calls: list[tuple] = []

    def _result(self, model: str, tf: str, market: str) -> AnalysisResult:
        return AnalysisResult(
            market=market, model=model, timeframe=tf, trend="Naik", direction=BUY,
            score=70.0, confidence=70, price=100.0, atr=2.0,
            entry=100.0, sl=98.0, tp1=102.0, tp2=104.0, tp3=106.0, rr=2.0,
            reasons=["Skor uji: alasan <uji>"], summary=["ringkasan"],
        )

    def analyze_single(self, market: str, tf: str) -> AnalysisResult:
        self.calls.append(("single", market, tf))
        return self._result("Single Time Frame", tf, market)

    def analyze_multi(self, market: str, tfs: list[str]) -> AnalysisResult:
        self.calls.append(("multi", market, tuple(tfs)))
        return self._result("Multi Time Frame", "+".join(tfs), market)


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
    flow.on_callback(
        cb_id=f"cb-{label}",
        chat_id=msg["chat_id"],
        message_id=msg["message_id"],
        user_id=user_id,
        data=match["callback_data"],
    )


@pytest.fixture
def env():
    api = FakeAPI()
    an = FakeAnalyzer()
    flow = Flow(api, an)
    bot = TelegramBot(api, an, flow=flow)
    return api, an, flow, bot


CHAT = 5001


def test_full_single_flow_and_menus(env):
    api, an, flow, _ = env
    flow.on_start(CHAT, 1)
    press(flow, api.sent[-1], "XAUUSD")
    m = api.sent[-1]
    assert "Pilih Model Time Frame" in m["text"]
    assert labels(m) == ["Single Time Frame", "Multi Time Frame", "Kembali", "Ganti Market", "Menu Utama"]
    press(flow, m, "Single Time Frame")
    m = api.sent[-1]
    assert labels(m) == ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1",
                         "Kembali", "Ganti Market", "Menu Utama"]
    press(flow, m, "H1")
    result = api.sent[-1]
    assert an.calls == [("single", "XAUUSD", "H1")]
    assert labels(result) == ["Refresh", "Ganti Model TF", "Kembali", "Menu Utama"]
    assert "XAUUSD" in result["text"] and "&lt;uji&gt;" in result["text"]


def test_full_multi_flow_refresh_and_back_navigation(env):
    api, an, flow, _ = env
    flow.on_start(CHAT, 1)
    press(flow, api.sent[-1], "BTCUSD")
    press(flow, api.sent[-1], "Multi Time Frame")
    m = api.sent[-1]
    assert "Multi Time Frame" in m["text"]
    assert labels(m) == ["M1+M5+M15", "M15+H1+H4", "H1+H4+D1", "Kembali", "Ganti Market", "Menu Utama"]
    press(flow, m, "M15+H1+H4")
    assert an.calls == [("multi", "BTCUSD", ("M15", "H1", "H4"))]
    press(flow, api.sent[-1], "Refresh")
    assert an.calls[-1] == ("multi", "BTCUSD", ("M15", "H1", "H4"))
    press(flow, api.sent[-1], "Kembali")
    assert labels(api.sent[-1]) == ["M15+H1+H4", "M15+H1+H4", "H1+H4+D1", "Kembali", "Ganti Market", "Menu Utama"] if False else (
        labels(api.sent[-1]) == ["M1+M5+M15", "M15+H1+H4", "H1+H4+D1", "Kembali", "Ganti Market", "Menu Utama"]
    )


def test_ganti_market_and_menu_utama(env):
    api, _, flow, _ = env
    flow.on_start(CHAT, 1)
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
    flow.on_start(CHAT, 1)
    stale_msg = dict(api.sent[-1])
    flow.on_start(CHAT, 1)
    press(flow, stale_msg, "XAUUSD")
    assert api.answered[-1]["text"]


def test_unauthorized_user_ignored_when_allowlist_set(env):
    api, _, _, bot = env
    bot.allowed_user_ids = {999}
    update = {"update_id": 10, "message": {"chat": {"id": CHAT}, "from": {"id": 123}, "text": "/start"}}
    flow_called = False
    orig = bot.flow.on_start

    def spy(*a, **kw):
        nonlocal flow_called
        flow_called = True
        return orig(*a, **kw)

    bot.flow.on_start = spy
    bot._handle_update(update)
    assert not flow_called
    assert api.sent == []
