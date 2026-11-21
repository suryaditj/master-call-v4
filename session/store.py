"""Session per pengguna Telegram (disimpan di memori proses).

Satu pengguna = satu Session, dikunci oleh user_id. Pengguna lain tidak dapat
memengaruhi pilihan market/timeframe pengguna ini.

`sid`  : identitas sesi (berganti saat /start atau Menu Utama).
`seq`  : nomor generasi menu. Hanya tombol dari menu TERBARU yang berlaku.
Sesi hilang saat proses bot berhenti; tombol lama lalu dianggap kedaluwarsa.
"""
from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

MAIN, MODEL, SINGLE, MULTI, RESULT = "MAIN", "MODEL", "SINGLE", "MULTI", "RESULT"


@dataclass
class Session:
    user_id: int
    sid: str
    seq: int = 0
    menu: str = MAIN
    previous_menu: str | None = None
    market: str | None = None
    model: str | None = None        # "single" | "multi"
    timeframe: str | None = None    # "H1" atau kunci preset "M30+H1+H4"
    requested_at: datetime | None = None


class SessionStore:
    def __init__(self, sid_factory: Callable[[], str] | None = None):
        self._sessions: dict[int, Session] = {}
        self._lock = threading.Lock()
        self._sid = sid_factory or (lambda: secrets.token_hex(2))

    def get(self, user_id: int) -> Session | None:
        with self._lock:
            return self._sessions.get(user_id)

    def reset(self, user_id: int) -> Session:
        """Sesi baru (sid baru, semua pilihan dikosongkan)."""
        with self._lock:
            session = Session(user_id=user_id, sid=self._sid())
            self._sessions[user_id] = session
            return session

    def __len__(self) -> int:
        return len(self._sessions)
