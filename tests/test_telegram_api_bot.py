import json

import pytest
import requests

from analysis.models import AnalysisResult
from config import ConfigError, load_telegram_config
from telegram_bot.api import TelegramAPI, TelegramError
from telegram_bot.bot import TelegramBot
from telegram_bot.format import format_html

TOKEN = "123456:SECRET-TOKEN-xyz"


class _Resp:
    def __init__(self, body, status=200):
        self._b, self.status_code = body, status

    def json(self):
        if self._b is None:
            raise ValueError
        return self._b


class _Sess:
    def __init__(self, resp=None, exc=None):
        self.resp, self.exc, self.calls = resp, exc, []

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json, timeout))
        if self.exc:
            raise self.exc
        return self.resp


def test_send_message_payload_and_no_edit_or_delete_methods():
    s = _Sess(_Resp({"ok": True, "result": {"message_id": 1}}))
    api = TelegramAPI(TOKEN, s)
    api.send_message(5, "halo", reply_markup={"inline_keyboard": []})
    url, payload, _ = s.calls[0]
    assert url.endswith("/sendMessage") and payload["chat_id"] == 5
    assert payload["parse_mode"] == "HTML" and payload["reply_markup"] == {"inline_keyboard": []}
    for name in ("edit_message_text", "editMessageText", "delete_message", "deleteMessage"):
        assert not hasattr(api, name)


def test_errors_never_leak_token():
    for sess in (
        _Sess(exc=requests.ConnectionError(f"https://api.telegram.org/bot{TOKEN}/x gagal")),
        _Sess(_Resp({"ok": False, "description": "Forbidden", "error_code": 403})),
        _Sess(_Resp(None, status=502)),
    ):
        with pytest.raises(TelegramError) as exc:
            TelegramAPI(TOKEN, sess).send_message(1, "x")
        assert TOKEN not in str(exc.value) and "SECRET" not in str(exc.value)
    assert TOKEN not in repr(TelegramAPI(TOKEN))


def test_telegram_config(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_IDS", raising=False)
    with pytest.raises(ConfigError):
        load_telegram_config()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "10, 20,")
    cfg = load_telegram_config()
    assert cfg.allowed_user_ids == {10, 20} and TOKEN not in repr(cfg) + str(cfg)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "abc")
    with pytest.raises(ConfigError):
        load_telegram_config()


class _PollAPI:
    def __init__(self, batches):
        self.batches, self.offsets, self.webhook = list(batches), [], 0

    def delete_webhook(self):
        self.webhook += 1

    def get_updates(self, offset, timeout):
        self.offsets.append((offset, timeout))
        if isinstance(self.batches[0] if self.batches else None, Exception):
            raise self.batches.pop(0)
        return self.batches.pop(0) if self.batches else []


class _Flow:
    def __init__(self):
        self.started, self.callbacks = [], []

    def on_start(self, chat, user):
        self.started.append((chat, user))

    def on_callback(self, cq):
        if cq.get("boom"):
            raise RuntimeError("rusak")
        self.callbacks.append(cq["id"])


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        self.t += 10.0
        return self.t


def test_polling_processes_updates_confirms_offset_and_survives_bad_update():
    updates = [[
        {"update_id": 5, "message": {"text": "/start", "from": {"id": 1}, "chat": {"id": 9}}},
        {"update_id": 6, "callback_query": {"id": "a", "boom": True}},
        {"update_id": 7, "callback_query": {"id": "b"}},
    ]]
    api, flow = _PollAPI(updates), _Flow()
    n = TelegramBot(api, flow).run_polling(60, clock=_Clock(), sleep=lambda s: None)
    assert n == 3 and flow.started == [(9, 1)] and flow.callbacks == ["b"]
    assert api.webhook == 1
    assert api.offsets[-1] == (8, 0)       # update terakhir dikonfirmasi sebelum keluar


def test_polling_retries_after_network_error_then_gives_up():
    api = _PollAPI([TelegramError("x"), []])
    TelegramBot(api, _Flow()).run_polling(60, clock=_Clock(), sleep=lambda s: None)
    assert len(api.offsets) >= 2
    api2 = _PollAPI([TelegramError("x")] * 12)
    with pytest.raises(TelegramError):
        TelegramBot(api2, _Flow()).run_polling(10_000, clock=lambda: 0.0, sleep=lambda s: None)


def _result(direction="BUY"):
    base = dict(market="XAUUSD", model="Single Time Frame", timeframe="H1", trend="Naik <x>",
                direction=direction, score=50.0, confidence=50, reasons=["a & b"], summary=["s"])
    if direction == "BUY":
        base.update(entry=3540.06, sl=3500.0, tp1=3580.0, tp2=3620.0, tp3=3660.0, rr=2.0)
    return AnalysisResult(**base)


def test_html_format_has_all_fields_and_escapes():
    text = format_html(_result("BUY"))
    for key in ("XAUUSD", "Single Time Frame", "H1", "Tren:", "BUY", "Entry:", "Stop Loss:",
                "TP1:", "TP2:", "TP3:", "Risk/Reward", "50/100", "Alasan", "Ringkasan indikator",
                "bukan peluang profit"):
        assert key in text
    assert "&lt;x&gt;" in text and "a &amp; b" in text
    wait = format_html(_result("WAIT"))
    assert "Entry:" not in wait and "WAIT" in wait


def test_html_format_is_truncated_to_telegram_limit():
    r = _result("WAIT")
    r.reasons = ["x" * 500] * 30
    assert len(format_html(r)) <= 3900
