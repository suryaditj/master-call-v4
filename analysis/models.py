"""Struktur data hasil analisis."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

BUY, SELL, WAIT = "BUY", "SELL", "WAIT"


@dataclass(frozen=True)
class Factor:
    name: str
    score: float   # -weight .. +weight (positif = bullish)
    weight: float
    note: str


@dataclass
class AnalysisResult:
    market: str
    model: str                 # "Single Time Frame" | "Multi Time Frame"
    timeframe: str             # "H1" atau "M30+H1+H4"
    trend: str
    direction: str             # BUY | SELL | WAIT
    score: float               # -100 .. +100 (skor indikator, BUKAN probabilitas profit)
    confidence: int            # 0..100 = |score| dibulatkan
    price: float | None = None
    atr: float | None = None
    entry: float | None = None
    sl: float | None = None
    tp1: float | None = None
    tp2: float | None = None
    tp3: float | None = None
    rr: float | None = None    # rasio reward:risk ke TP2
    reasons: list[str] = field(default_factory=list)
    summary: list[str] = field(default_factory=list)
    factors: list[Factor] = field(default_factory=list)
    sub_results: list["AnalysisResult"] = field(default_factory=list)
    as_of: datetime | None = None  # waktu buka candle tertutup terakhir (UTC)
