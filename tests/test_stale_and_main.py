from datetime import datetime, timedelta, timezone

from analysis.models import AnalysisResult
from analysis.service import _flag_stale

NOW = datetime(2026, 11, 21, 10, 0, tzinfo=timezone.utc)


def _r(age_hours):
    return AnalysisResult("XAUUSD", "Single Time Frame", "H1", "Turun", "SELL", -50.0, 50,
                          as_of=NOW - timedelta(hours=age_hours), reasons=["alasan"])


def test_stale_data_gets_warning_first():
    r = _r(13.0)
    _flag_stale(r, "H1", NOW)
    assert r.reasons[0].startswith("Perhatian: candle terakhir berumur 13.0 jam")
    assert r.reasons[1] == "alasan"


def test_fresh_data_has_no_warning():
    r = _r(2.0)
    _flag_stale(r, "H1", NOW)
    assert r.reasons == ["alasan"]


def test_main_returns_1_without_config(monkeypatch):
    import main
    for n in ("EXN_API_KEY", "EXN_PRIVATE_KEY", "EXN_ACCOUNT_ID", "TELEGRAM_BOT_TOKEN",
              "EXN_DISCOVERY_BASE_URL", "EXN_API_BASE_URL"):
        monkeypatch.delenv(n, raising=False)
    assert main.main() == 1
