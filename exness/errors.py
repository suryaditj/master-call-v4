"""Exception khusus untuk lapisan Exness API."""
from __future__ import annotations


class ExnessError(Exception):
    """Basis semua error Exness."""


class ExnessAuthError(ExnessError):
    """Kunci/signature ditolak (kode 1000/1001/1002)."""


class ExnessRequestError(ExnessError):
    """Server mengembalikan error (4xx/5xx) dengan kode publik."""

    def __init__(self, status: int, code: str | None, message: str | None):
        self.status = status
        self.code = code
        self.message = message
        super().__init__(f"HTTP {status} code={code} message={message}")


class ExnessNetworkError(ExnessError):
    """Gagal terhubung / timeout."""


class ExnessKeyError(ExnessError):
    """Format private key tidak dikenali."""


class CandleDataError(ExnessError):
    """Respons candle tidak sesuai skema yang diharapkan."""


class InsufficientDataError(ExnessError):
    """Jumlah candle yang tersedia kurang untuk analisis."""
