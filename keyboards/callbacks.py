"""Format callback_data tombol: m1:<sid>:<seq>:<aksi>[:<argumen>] (maks. 64 byte)."""
from __future__ import annotations

from dataclasses import dataclass

PREFIX = "m1"
MAX_BYTES = 64

# mk=pilih market, md=model TF, tf=single TF, mt=multi TF, rf=refresh,
# bk=kembali, chm=ganti market, chtf=ganti model TF, home=menu utama
ACTIONS = frozenset({"mk", "md", "tf", "mt", "rf", "bk", "chm", "chtf", "home"})


@dataclass(frozen=True)
class Callback:
    sid: str
    seq: int
    action: str
    arg: str = ""


def encode(sid: str, seq: int, action: str, arg: str = "") -> str:
    if action not in ACTIONS:
        raise ValueError(f"Aksi tidak dikenal: {action!r}")
    data = f"{PREFIX}:{sid}:{seq}:{action}" + (f":{arg}" if arg else "")
    if len(data.encode("utf-8")) > MAX_BYTES:
        raise ValueError("callback_data melebihi 64 byte")
    return data


def decode(data: str | None) -> Callback | None:
    if not data:
        return None
    parts = data.split(":", 4)
    if len(parts) < 4 or parts[0] != PREFIX:
        return None
    try:
        seq = int(parts[2])
    except ValueError:
        return None
    if parts[3] not in ACTIONS:
        return None
    return Callback(parts[1], seq, parts[3], parts[4] if len(parts) == 5 else "")
