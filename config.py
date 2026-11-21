"""Konfigurasi MASTER CALL V4.0.

Semua nilai rahasia dibaca dari environment variable (GitHub Secrets).
Modul ini TIDAK PERNAH mencetak nilai rahasia.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

# Nama instrumen di API Exness (terbukti lewat scripts/check_candles.py; akhiran "m" ditolak).
SYMBOLS: dict[str, str] = {
    "XAUUSD": "XAUUSD",
    "BTCUSD": "BTCUSD",
}

DEFAULT_TIMEOUT_SECONDS = 15


class ConfigError(RuntimeError):
    """Konfigurasi tidak lengkap atau tidak valid."""


@dataclass(frozen=True)
class ExnessConfig:
    api_key: str = field(repr=False)
    private_key: str = field(repr=False)
    account_id: str
    discovery_base_url: str | None
    api_base_url: str | None
    timeout: float = DEFAULT_TIMEOUT_SECONDS

    def __repr__(self) -> str:  # jangan bocorkan kredensial di log
        return (
            f"ExnessConfig(account_id={self.account_id!r}, "
            f"discovery_base_url={self.discovery_base_url!r}, "
            f"api_base_url={self.api_base_url!r})"
        )


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def load_exness_config() -> ExnessConfig:
    """Baca konfigurasi Exness dari environment.

    Wajib: EXN_API_KEY, EXN_PRIVATE_KEY, EXN_ACCOUNT_ID
    Salah satu wajib: EXN_DISCOVERY_BASE_URL (host Gateway dari widget DNS)
                      atau EXN_API_BASE_URL (Access Point langsung).
    """
    missing = [
        name
        for name in ("EXN_API_KEY", "EXN_PRIVATE_KEY", "EXN_ACCOUNT_ID")
        if not _env(name)
    ]
    if missing:
        raise ConfigError("Environment variable belum diisi: " + ", ".join(missing))

    discovery = _env("EXN_DISCOVERY_BASE_URL")
    api_base = _env("EXN_API_BASE_URL")
    if not discovery and not api_base:
        raise ConfigError(
            "Isi EXN_DISCOVERY_BASE_URL (host Gateway dari widget DNS di "
            "Key Management) atau EXN_API_BASE_URL (Access Point)."
        )

    return ExnessConfig(
        api_key=_env("EXN_API_KEY"),  # type: ignore[arg-type]
        private_key=_env("EXN_PRIVATE_KEY"),  # type: ignore[arg-type]
        account_id=_env("EXN_ACCOUNT_ID"),  # type: ignore[arg-type]
        discovery_base_url=discovery.rstrip("/") if discovery else None,
        api_base_url=api_base.rstrip("/") if api_base else None,
    )


@dataclass(frozen=True)
class TelegramConfig:
    token: str = field(repr=False)
    allowed_user_ids: frozenset[int]

    def __repr__(self) -> str:  # jangan bocorkan token di log
        return f"TelegramConfig(allowed_user_ids={sorted(self.allowed_user_ids)})"


def load_telegram_config() -> TelegramConfig:
    """Wajib: TELEGRAM_BOT_TOKEN. Opsional: TELEGRAM_ALLOWED_USER_IDS (pisah koma).

    Jika daftar ID diisi, hanya pengguna itu yang boleh memakai bot.
    """
    token = _env("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ConfigError("Environment variable belum diisi: TELEGRAM_BOT_TOKEN")
    raw = _env("TELEGRAM_ALLOWED_USER_IDS") or ""
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            raise ConfigError("TELEGRAM_ALLOWED_USER_IDS harus berisi angka dipisah koma.") from None
    return TelegramConfig(token=token, allowed_user_ids=frozenset(ids))
