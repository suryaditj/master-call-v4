import pytest

from analysis.models import AnalysisResult
from exness.errors import ExnessNetworkError, InsufficientDataError
from handlers.flow import STALE_ALERT, Flow
from keyboards.callbacks import decode, encode
from session.store import SessionStore
from telegram_bot.bot import TelegramBot

CHAT = 100


class FakeAPI:
    """Hanya punya send_message & answer_callback_query: tidak ada edit/hapus."""

    def __init__(self):
        self.sent, self.answers = [], []

    def send_message(self, chat_id, text, reply_markup=None, parse_mode="HTML"):
        self.sent.append({"chat": chat_id, "text": text, "kb": reply_markup})

    def answer_callback_query(self, cq_id, text=None, show_alert=False):
        self.answers.append((cq_id, text, show_alert))


class FakeAnalyzer:
    def __init__(self):
        self.calls = []
        self.error = None

    def _result(self, market, tf, model):
        return AnalysisResult(market, model, tf, "Naik", "BUY", 50.0, 50, price=100.0, atr=1.0,
                              entry=100.0, sl=98.5, tp1=101.5, tp2=103.0, tp3=104.5, rr=2.0,
                              reasons=["alasan <uji>"], summary=["ringkasan"])

    def single(self, market, tf):
        self.calls.append(("single", market, tf))
        if self.error:
            raise self.error
        return self._result(market, tf, "Single Time Frame")

    def multi(self, market, preset):
        self.calls.append(("multi", market, preset))
        if self.error:
            raise self.error
        return self._result(market, preset, "Multi Time Frame")


@pytest.fixture
def env():
    api, analyzer = FakeAPI(), FakeAnalyzer()
    flow = Flow(api, SessionStore(), analyzer)
    return api, analyzer, flow, TelegramBot(api, flow)


_cq = iter(range(1, 10_000))


def buttons(msg):
    return [b for row in msg["kb"]["inline_keyboard"] for b in row]


def press(flow, msg, label, user=1):
    btn = next(b for b in buttons(msg) if b["text"] == label)
    flow.on_callback({"id": f"q{next(_cq)}", "from": {"id": user}, "data": btn["callback_data"],
                      "message": {"chat": {"id": CHAT}}})


def labels(msg):
    return [b["text"] for b in buttons(msg)]


def test_start_shows_main_menu(env):
    api, _, flow, bot = env
    bot.handle_update({"message": {"text": "/start", "from": {"id": 1}, "chat": {"id": CHAT}}})
    msg = api.sent[-1]
    assert "<b>Pilih Market</b>" in msg["text"]
    assert labels(msg) == ["XAUUSD", "BTCUSD"]


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
    assert "XAUUSD" in result["text"] and "&lt;uji&gt;" in result["text"]  # di-escape


def test_multi_menu_buttons_and_analysis(env):
    api, an, flow, _ = env
    flow.on_start(CHAT, 1)
    press(flow, api.sent[-1], "BTCUSD")
    press(flow, api.sent[-1], "Multi Time Frame")
    m = api.sent[-1]
    assert labels(m)[:2] == ["MultiTF [M1+M5+M15]", "MultiTF [M30+H1+H4]"]
    press(flow, m, "MultiTF [M30+H1+H4]")
    assert an.calls == [("multi", "BTCUSD", "M30+H1+H4")]


def test_refresh_fetches_fresh_data_and_sends_new_message(env):
    api, an, flow, _ = env
    flow.on_start(CHAT, 1)
    press(flow, api.sent[-1], "XAUUSD")
    press(flow, api.sent[-1], "Single Time Frame")
    press(flow, api.sent[-1], "M5")
    n = len(api.sent)
    press(flow, api.sent[-1], "Refresh")
    press(flow, api.sent[-1], "Refresh")
    assert an.calls == [("single", "XAUUSD", "M5")] * 3   # dihitung ulang, bukan cache
    assert len(api.sent) > n + 2                           # selalu pesan baru
    assert not hasattr(api, "edit_message_text") and not hasattr(api, "delete_message")


@pytest.mark.parametrize("model,tf_button,back_to", [
    ("Single Time Frame", "H4", "H1"),
    ("Multi Time Frame", "MultiTF [M1+M5+M15]", "MultiTF [M30+H1+H4]"),
])
def test_back_from_result_returns_matching_tf_menu(env, model, tf_button, back_to):
    api, _, flow, _ = env
    flow.on_start(CHAT, 1)
    press(flow, api.sent[-1], "XAUUSD")
    press(flow, api.sent[-1], model)
    press(flow, api.sent[-1], tf_button)
    press(flow, api.sent[-1], "Kembali")
    assert back_to in labels(api.sent[-1])


def test_back_chain_and_change_buttons(env):
    api, _, flow, _ = env
    flow.on_start(CHAT, 1)
    press(flow, api.sent[-1], "XAUUSD")
    press(flow, api.sent[-1], "Single Time Frame")
    press(flow, api.sent[-1], "Kembali")
    assert "Pilih Model Time Frame" in api.sent[-1]["text"]
    press(flow, api.sent[-1], "Kembali")
    assert "Pilih Market" in api.sent[-1]["text"]
    press(flow, api.sent[-1], "BTCUSD")
    press(flow, api.sent[-1], "Ganti Market")
    assert "Pilih Market" in api.sent[-1]["text"]
    press(flow, api.sent[-1], "BTCUSD")
    press(flow, api.sent[-1], "Single Time Frame")
    press(flow, api.sent[-1], "H1")
    press(flow, api.sent[-1], "Ganti Model TF")
    assert "Pilih Model Time Frame" in api.sent[-1]["text"] and "BTCUSD" in api.sent[-1]["text"]


def test_old_buttons_are_stale_and_do_not_break_session(env):
    api, an, flow, _ = env
    flow.on_start(CHAT, 1)
    old_main = api.sent[-1]
    press(flow, old_main, "XAUUSD")
    model_menu = api.sent[-1]
    press(flow, old_main, "BTCUSD")                      # tombol lama
    assert api.answers[-1][1] == STALE_ALERT
    notice = api.sent[-1]
    assert "kedaluwarsa" in notice["text"] and labels(notice) == ["Menu Utama"]
    press(flow, model_menu, "Single Time Frame")         # menu terbaru tetap berlaku
    assert "Single Time Frame" in api.sent[-1]["text"] and "XAUUSD" in api.sent[-1]["text"]
    assert an.calls == []


def test_menu_utama_always_works_and_resets(env):
    api, _, flow, _ = env
    flow.on_start(CHAT, 1)
    press(flow, api.sent[-1], "XAUUSD")
    press(flow, api.sent[-1], "Single Time Frame")
    press(flow, api.sent[-1], "H1")
    press(flow, api.sent[-1], "Kembali")
    stale_notice_target = api.sent[-1]
    press(flow, stale_notice_target, "Menu Utama")
    assert "Pilih Market" in api.sent[-1]["text"]
    assert flow.store.get(1).market is None


def test_two_users_have_independent_sessions(env):
    api, an, flow, _ = env
    flow.on_start(11, 1)
    a_main = api.sent[-1]
    flow.on_start(22, 2)
    b_main = api.sent[-1]
    press(flow, a_main, "XAUUSD", user=1)
    a_model = api.sent[-1]
    press(flow, b_main, "BTCUSD", user=2)
    b_model = api.sent[-1]
    press(flow, a_model, "Single Time Frame", user=1)
    press(flow, api.sent[-1], "H1", user=1)
    press(flow, b_model, "Single Time Frame", user=2)
    press(flow, api.sent[-1], "M15", user=2)
    assert an.calls == [("single", "XAUUSD", "H1"), ("single", "BTCUSD", "M15")]
    assert flow.store.get(1).market == "XAUUSD" and flow.store.get(2).market == "BTCUSD"


def test_user_cannot_use_another_users_buttons(env):
    api, an, flow, _ = env
    flow.on_start(11, 1)
    a_main = api.sent[-1]
    flow.on_start(22, 2)
    press(flow, a_main, "XAUUSD", user=2)    # tombol milik user 1 dipencet user 2
    assert api.answers[-1][1] == STALE_ALERT
    assert flow.store.get(2).market is None


@pytest.mark.parametrize("error,expected", [
    (InsufficientDataError("kurang 10 candle"), "Data tidak cukup"),
    (ExnessNetworkError("timeout"), "tidak dapat diakses"),
    (RuntimeError("rahasia-internal-123"), "kesalahan internal"),
])
def test_errors_show_clear_message_without_fake_signal(env, error, expected):
    api, an, flow, _ = env
    an.error = error
    flow.on_start(CHAT, 1)
    press(flow, api.sent[-1], "XAUUSD")
    press(flow, api.sent[-1], "Single Time Frame")
    press(flow, api.sent[-1], "H1")
    msg = api.sent[-1]
    assert expected in msg["text"] and "Tidak ada sinyal" in msg["text"]
    assert "BUY" not in msg["text"] and "rahasia-internal-123" not in msg["text"]
    assert labels(msg) == ["Refresh", "Ganti Model TF", "Kembali", "Menu Utama"]


def test_invalid_arguments_never_reach_analyzer(env):
    api, an, flow, _ = env
    flow.on_start(CHAT, 1)
    s = flow.store.get(1)
    for action, arg in [("mk", "EURUSD"), ("tf", "H1"), ("rf", ""), ("md", "multi")]:
        flow.on_callback({"id": "x", "from": {"id": 1}, "message": {"chat": {"id": CHAT}},
                          "data": encode(s.sid, s.seq, action, arg)})
    assert an.calls == [] and s.market is None


def test_allowed_users_whitelist():
    api, an = FakeAPI(), FakeAnalyzer()
    flow = Flow(api, SessionStore(), an, allowed_users={7})
    flow.on_start(CHAT, 8)
    assert api.sent[-1]["text"] == "Akses ditolak." and flow.store.get(8) is None
    flow.on_start(CHAT, 7)
    assert "Pilih Market" in api.sent[-1]["text"]


def test_every_callback_is_within_64_bytes_and_decodes(env):
    api, _, flow, _ = env
    flow.on_start(CHAT, 1)
    press(flow, api.sent[-1], "XAUUSD")
    press(flow, api.sent[-1], "Multi Time Frame")
    press(flow, api.sent[-1], "MultiTF [M30+H1+H4]")
    for msg in api.sent:
        if msg["kb"]:
            for b in buttons(msg):
                assert len(b["callback_data"].encode()) <= 64
                assert decode(b["callback_data"]) is not None
    assert decode("sampah") is None and decode("m1:a:x:rf") is None and decode(None) is None


def test_every_non_main_menu_has_navigation(env):
    api, _, flow, _ = env
    flow.on_start(CHAT, 1)
    press(flow, api.sent[-1], "XAUUSD")
    press(flow, api.sent[-1], "Single Time Frame")
    press(flow, api.sent[-1], "H1")
    for msg in api.sent:
        if msg["kb"] and "Pilih Market" not in msg["text"]:
            assert "Menu Utama" in labels(msg)
