"""Penghubung handler dengan layanan analisis (dapat diganti saat pengujian)."""
from __future__ import annotations

from typing import Any, Protocol

from analysis.models import AnalysisResult
from analysis.service import MULTI_PRESETS, analyze_multi, analyze_single


class Analyzer(Protocol):
    def single(self, market: str, timeframe: str) -> AnalysisResult: ...
    def multi(self, market: str, preset: str) -> AnalysisResult: ...


class ServiceAnalyzer:
    """Setiap panggilan mengambil candle BARU dari Exness (dipakai juga oleh Refresh)."""

    def __init__(self, client: Any):
        self._client = client

    def single(self, market: str, timeframe: str) -> AnalysisResult:
        return analyze_single(self._client, market, timeframe)

    def multi(self, market: str, preset: str) -> AnalysisResult:
        return analyze_multi(self._client, market, MULTI_PRESETS[preset])
