from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.integration_readiness import IntegrationSpec, _feature_state


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_scheduled_live_data_becomes_stale_after_source_threshold():
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    state, count, latest = _feature_state(
        {"id": "demo", "env_key": None},
        IntegrationSpec(("rows",), "demo", stale_after_seconds=60),
        {"rows": [{"id": 1}]},
        {"rows": old},
    )
    assert state == "stale"
    assert count == 1
    assert latest == old


def test_scheduled_recent_data_is_live():
    recent = datetime.now(timezone.utc).isoformat()
    state, count, _ = _feature_state(
        {"id": "demo", "env_key": None},
        IntegrationSpec(("rows",), "demo", stale_after_seconds=300),
        {"rows": [{"id": 1}]},
        {"rows": recent},
    )
    assert state == "live"
    assert count == 1


def test_r3_provider_health_has_batch_probe_and_persistent_probe_snapshot():
    source = read("backend/routers/public_intel.py")
    assert "/api/public-intel/provider-test-all" in source
    assert "_PROBE_RESULTS" in source
    assert "ThreadPoolExecutor" in source
    assert '"stale": "BAYAT"' in source
    for integration_id in ("open_meteo", "rainviewer", "usgs_earthquakes", "nasa_eonet", "gdacs", "celestrak", "gdelt", "yfinance"):
        assert integration_id in source


def test_r3_health_panel_exposes_freshness_batch_test_and_capability_truth():
    source = read("frontend/src/components/PublicIntelPanel.tsx")
    for label in ("TÜM KAYNAKLARI TEST ET", "YETENEK SINIRLARI / HAZIRLIK", "son veri", "BAĞLANTIYI TEST ET"):
        assert label in source
    assert "item.state === 'stale'" in source
    assert "last_probe" in source


def test_r3_turkish_system_chrome_does_not_corrupt_http_methods():
    intel = read("frontend/src/components/IntelligenceCenterPanel.tsx")
    bridge = read("frontend/src/components/TurkishUiBridge.tsx")
    assert "method:'SİL'" not in intel
    assert 'method:"SİL"' not in intel
    assert "method:'DELETE'" in intel
    for label in ("YEREL YZ ANALİSTİ", "YEREL MODEL YÖNETİCİSİ", "ANALİST ÇALIŞMA ALANI ÖNAYARLARI", "GÜVENLİ KURAL OLUŞTURUCU"):
        assert label in intel or label in bridge
    assert "TASARIM GEREĞİ KAPALI" in bridge
    assert "DONANIM GEREKLİ" in bridge
    assert "KAYNAK SINIRLI" in bridge


def test_r3_is_wired_into_windows_stage06():
    source = read("WINDOWS-DESKTOP-ONE-CLICK.ps1")
    assert "test_gokdogan_gd1_r3_health_turkish.py" in source
