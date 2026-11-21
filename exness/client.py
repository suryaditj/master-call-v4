"""Klien Exness Trader API (khusus baca / read-only).

Klien ini sengaja hanya memiliki metode GET. Tidak ada fungsi untuk
menempatkan order atau mengubah posisi.

Catatan verifikasi (Tahap 2):
- Path /v1/configuration/accounts/{id}/account dan /limits berasal dari
  dokumentasi resmi.
- Endpoint penemuan Access Point (/v1/trading/access-point?account_id=...)
  dan nama field "access_point" pada responsnya BELUM diverifikasi terhadap
  spesifikasi YAML resminya. Jika Anda sudah punya EXN_API_BASE_URL
  (Access Point), penemuan dilewati.
- Parameter query endpoint candle diisi pada Tahap 3 setelah spesifikasi
  OpenAPI dibaca. Tidak ada tebakan di sini.
"""
from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlencode

import requests

from config import ExnessConfig
from exness.errors import (
    ExnessAuthError,
    ExnessError,
    ExnessNetworkError,
    ExnessRequestError,
)
from exness.signing import build_signed_headers, load_private_key

log = logging.getLogger(__name__)

AUTH_CODES = {1000, 1001, 1002}

# Batas rate limit tidak disebut di dokumentasi; HTTP 429 (kode 3015) diulang
# dengan jeda bertambah. Tanda tangan dibuat ulang di setiap percobaan.
RATE_LIMIT_RETRIES = 2
RATE_LIMIT_WAIT = 3.0
_sleep = time.sleep

# Nilai pilihan dari dokumentasi resmi (dropdown halaman "Get candle history").
TIMEFRAMES = (
    "S1", "S5", "S15", "M1", "M3", "M5", "M10", "M15", "M30",
    "H1", "H2", "H4", "D1", "W1", "MN",
)
PRICE_TYPES = ("bid", "ask", "both")


def build_path(path: str, params: dict[str, Any] | None = None) -> str:
    """Susun path + query. String ini yang ditandatangani DAN dikirim."""
    if not params:
        return path
    for name, value in params.items():
        if value is None:
            raise ValueError(f"Parameter query {name!r} bernilai None.")
    return f"{path}?{urlencode(params, doseq=False)}"


class ExnessClient:
    def __init__(self, config: ExnessConfig, session: requests.Session | None = None):
        self._config = config
        self._key = load_private_key(config.private_key)
        self._session = session or requests.Session()
        self._access_point: str | None = config.api_base_url

    # ---- inti HTTP -------------------------------------------------------
    def _signed_get(self, base_url: str, path_with_query: str) -> Any:
        """GET bertanda tangan; ulangi bila kena rate limit (HTTP 429)."""
        for attempt in range(RATE_LIMIT_RETRIES + 1):
            try:
                return self._signed_get_once(base_url, path_with_query)
            except ExnessRequestError as exc:
                if exc.status != 429 or attempt == RATE_LIMIT_RETRIES:
                    raise
                log.warning("Rate limit Exness, tunggu %.0f detik", RATE_LIMIT_WAIT * (attempt + 1))
                _sleep(RATE_LIMIT_WAIT * (attempt + 1))
        raise ExnessError("unreachable")  # pragma: no cover

    def _signed_get_once(self, base_url: str, path_with_query: str) -> Any:
        headers = build_signed_headers(
            api_key=self._config.api_key,
            private_key=self._key,
            method="GET",
            path_with_query=path_with_query,
        )
        url = base_url.rstrip("/") + path_with_query
        try:
            resp = self._session.get(url, headers=headers, timeout=self._config.timeout)
        except requests.RequestException as exc:
            raise ExnessNetworkError(f"Gagal menghubungi Exness API: {type(exc).__name__}") from exc

        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError as exc:
                raise ExnessError("Respons 200 bukan JSON yang valid.") from exc

        code: Any = None
        message: str | None = None
        try:
            body = resp.json()
            err = body.get("error") if isinstance(body, dict) else None
            if isinstance(err, dict):
                code = err.get("code")
            elif isinstance(body, dict):
                code = body.get("code")
            if isinstance(body, dict):
                message = body.get("error_message") or (
                    err.get("message") if isinstance(err, dict) else None
                )
        except ValueError:
            pass

        if resp.status_code in (401, 403) or code in AUTH_CODES:
            raise ExnessAuthError(
                f"Autentikasi ditolak (HTTP {resp.status_code}, code={code}, {message}). "
                "Periksa API key, private key, scope Read-only, akun, dan IP."
            )
        raise ExnessRequestError(resp.status_code, str(code) if code is not None else None, message)

    # ---- penemuan Access Point ------------------------------------------
    def access_point(self, force: bool = False) -> str:
        if self._access_point and not force:
            return self._access_point
        if not self._config.discovery_base_url:
            raise ExnessError("EXN_DISCOVERY_BASE_URL belum diisi dan EXN_API_BASE_URL kosong.")
        path = build_path("/v1/trading/access-point", {"account_id": self._config.account_id})
        data = self._signed_get(self._config.discovery_base_url, path)
        ap = data.get("access_point") if isinstance(data, dict) else None
        if not isinstance(ap, str) or not ap.startswith("http"):
            raise ExnessError(
                "Respons penemuan Access Point tidak berisi field 'access_point'. "
                "Setel EXN_API_BASE_URL secara manual lalu cek spesifikasi resminya."
            )
        self._access_point = ap.rstrip("/")
        return self._access_point

    # ---- endpoint read-only yang terdokumentasi --------------------------
    def get_account_details(self) -> Any:
        path = f"/v1/configuration/accounts/{self._config.account_id}/account"
        return self._signed_get(self.access_point(), path)

    def get_limits(self) -> Any:
        path = f"/v1/configuration/accounts/{self._config.account_id}/limits"
        return self._signed_get(self.access_point(), path)

    def get_candles_raw(
        self,
        instrument: str,
        timeframe: str,
        from_: str,
        *,
        count: int | None = None,
        to: str | None = None,
        price_type: str | None = None,
    ) -> Any:
        """GET /v1/market-data/accounts/{account_id}/candles (respons mentah).

        Parameter query dari dokumentasi resmi: instrument, timeframe, from
        (wajib); price_type, to, count (opsional; count tidak boleh bersama to).
        Format nilai `from`/`to` dan struktur respons diverifikasi lewat
        scripts/check_candles.py sebelum parser ditulis.
        """
        if timeframe not in TIMEFRAMES:
            raise ValueError(f"Timeframe tidak dikenal: {timeframe!r}")
        if price_type is not None and price_type not in PRICE_TYPES:
            raise ValueError(f"price_type tidak dikenal: {price_type!r}")
        if to is not None and count is not None:
            raise ValueError("'count' tidak boleh dipakai bersama 'to'.")
        if to is None and count is None:
            raise ValueError("Isi salah satu: 'count' atau 'to'.")

        params: dict[str, Any] = {
            "instrument": instrument,
            "timeframe": timeframe,
            "from": from_,
        }
        if price_type is not None:
            params["price_type"] = price_type
        if to is not None:
            params["to"] = to
        if count is not None:
            params["count"] = count
        path = f"/v1/market-data/accounts/{self._config.account_id}/candles"
        return self._signed_get(self.access_point(), build_path(path, params))

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET bertanda tangan ke Access Point. Hanya GET, tidak ada metode tulis."""
        return self._signed_get(self.access_point(), build_path(path, params))
