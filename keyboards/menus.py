"""Inline keyboard semua menu. Setiap menu selain Menu Utama punya tombol navigasi."""
from __future__ import annotations

from typing import Any

from analysis.multi_tf import MULTI_3TF_PRESETS, ONE_CLICK_2TF_KEY
from analysis.service import SINGLE_TIMEFRAMES
from config import SYMBOLS
from keyboards.callbacks import encode

Markup = dict[str, Any]


def _btn(text: str, sid: str, seq: int, action: str, arg: str = "") -> dict[str, str]:
    return {"text": text, "callback_data": encode(sid, seq, action, arg)}


def _nav(sid: str, seq: int) -> list[dict[str, str]]:
    return [
        _btn("Kembali", sid, seq, "bk"),
        _btn("Ganti Market", sid, seq, "chm"),
        _btn("Menu Utama", sid, seq, "home"),
    ]


def main_menu(sid: str, seq: int) -> Markup:
    return {"inline_keyboard": [[_btn(m, sid, seq, "mk", m) for m in SYMBOLS]]}


def model_menu(sid: str, seq: int) -> Markup:
    return {"inline_keyboard": [
        [_btn("Single Time Frame", sid, seq, "md", "single")],
        [_btn("Multi Time Frame", sid, seq, "md", "multi")],
        _nav(sid, seq),
    ]}


def single_menu(sid: str, seq: int) -> Markup:
    tfs = list(SINGLE_TIMEFRAMES)
    rows = [[_btn(tf, sid, seq, "tf", tf) for tf in tfs[i:i + 4]] for i in range(0, len(tfs), 4)]
    return {"inline_keyboard": rows + [_nav(sid, seq)]}


def multi_menu(sid: str, seq: int) -> Markup:
    rows: list[list[dict[str, str]]] = [
        [_btn("One klik 2 TF", sid, seq, "mt", ONE_CLICK_2TF_KEY)],
        [_btn(f"3 TF: {key}", sid, seq, "mt", key) for key in MULTI_3TF_PRESETS],
    ]
    return {"inline_keyboard": rows + [_nav(sid, seq)]}


def result_menu(sid: str, seq: int) -> Markup:
    return {"inline_keyboard": [
        [_btn("Refresh", sid, seq, "rf"), _btn("Ganti Model TF", sid, seq, "chtf")],
        [_btn("Kembali", sid, seq, "bk"), _btn("Menu Utama", sid, seq, "home")],
    ]}


def notice_menu(sid: str) -> Markup:
    """Untuk pesan 'tombol kedaluwarsa'. Menu Utama selalu berlaku (seq diabaikan)."""
    return {"inline_keyboard": [[_btn("Menu Utama", sid, 0, "home")]]}
