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

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET bertanda tangan ke Access Point. Hanya GET, tidak ada metode tulis."""
        return self._signed_get(self.access_point(), build_path(path, params))
