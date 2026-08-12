from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.fetchers.public_events import _normalize_eonet, _normalize_gdacs, _parse_cbp_rows


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_eonet_normalizer_keeps_real_source_geometry_and_url():
    rows = _normalize_eonet({"events": [{
        "id": "EONET_1",
        "title": "Wildfire Alpha",
        "categories": [{"id": "wildfires", "title": "Wildfires"}],
        "sources": [{"url": "https://example.gov/event"}],
        "geometry": [{"date": "2026-08-11T10:00:00Z", "coordinates": [29.0, 41.0]}],
    }]})
    assert len(rows) == 1
    assert rows[0]["provider"] == "NASA EONET"
    assert rows[0]["lat"] == 41.0 and rows[0]["lng"] == 29.0
    assert rows[0]["url"] == "https://example.gov/event"
    assert "Wildfires" in rows[0]["categories"]


def test_gdacs_normalizer_keeps_alert_level_and_geometry():
    rows = _normalize_gdacs({"features": [{
        "properties": {"eventtype": "EQ", "eventid": 123, "name": "Earthquake", "alertlevel": "Orange", "url": "https://gdacs.org/x"},
        "geometry": {"type": "Point", "coordinates": [35.5, 38.4]},
    }]})
    assert len(rows) == 1
    assert rows[0]["provider"] == "GDACS"
    assert rows[0]["alert_level"] == "ORANGE"
    assert rows[0]["lat"] == 38.4 and rows[0]["lng"] == 35.5


def test_cbp_parser_never_invents_wait_minutes():
    html = """<table><tr><th>Port</th><th>Status</th></tr>
    <tr><td>Port Alpha</td><td>20 minutes delay; 2 lanes open</td></tr>
    <tr><td>Port Beta</td><td>Update pending; lanes open</td></tr></table>"""
    rows = _parse_cbp_rows(html)
    assert rows[0]["wait_minutes"] == 20
    assert rows[1]["wait_minutes"] is None
    assert rows[0]["provider"] == "U.S. CBP Border Wait Times"


def test_public_events_explicitly_excludes_private_cctv_live_police_sensitive_military():
    source = read("backend/services/fetchers/public_events.py")
    assert "private CCTV" in source
    assert "live police-unit tracking" in source
    assert "non-public sensitive" in source and "military telemetry" in source


def test_public_intel_router_has_news_borders_disasters_health_provider_test_and_movement():
    source = read("backend/routers/public_intel.py")
    for route in (
        "/api/public-intel/breaking-news",
        "/api/public-intel/borders",
        "/api/public-intel/disasters",
        "/api/public-intel/provider-health",
        "/api/public-intel/provider-test/{integration_id}",
        "/api/public-intel/entity-movement",
    ):
        assert route in source


def test_public_intel_router_safety_scope_is_product_contract():
    source = read("backend/routers/public_intel.py")
    assert "private CCTV discovery" in source
    assert "live police-unit tracking" in source
    assert "non-public sensitive military telemetry" in source


def test_official_public_provider_registry_contains_disaster_and_border_sources():
    settings = read("backend/services/api_settings.py")
    readiness = read("backend/services/integration_readiness.py")
    for integration_id in ("nasa_eonet", "gdacs", "cbp_border_wait"):
        assert integration_id in settings
        assert integration_id in readiness


def test_dashboard_contract_contains_global_disaster_and_border_snapshots():
    backend_store = read("backend/services/fetchers/_store.py")
    frontend_types = read("frontend/src/types/dashboard.ts")
    for key in ("global_disasters", "border_status"):
        assert key in backend_store
        assert key in frontend_types
    assert "GlobalDisasterEvent" in frontend_types


def test_slow_api_exports_global_disasters_and_border_status():
    source = read("backend/routers/data.py")
    assert '"global_disasters"' in source
    assert '"border_status"' in source


def test_startup_preloads_global_disasters_and_border_status():
    source = read("backend/services/data_fetcher.py")
    assert "fetch_global_disasters" in source
    assert "fetch_border_status" in source
    assert source.count("fetch_global_disasters") >= 3
    assert source.count("fetch_border_status") >= 3


def test_weather_r2_exposes_extended_forecast_air_quality_and_marine():
    source = read("backend/routers/weather_traffic.py")
    assert '"forecast_days": "16"' in source or '"forecast_days": 16' in source
    assert "/api/weather/air-quality" in source
    assert "/api/weather/marine" in source
    assert "cloud_cover_low" in source and "cloud_cover_high" in source
    assert "wave_height" in source and "european_aqi" in source


def test_public_intel_panel_has_four_live_operations_tabs_and_provider_test():
    source = read("frontend/src/components/PublicIntelPanel.tsx")
    for label in ("SON DAKİKA", "SINIRLAR", "AFETLER", "SAĞLIK", "BAĞLANTIYI TEST ET", "HARİTADA GÖSTER"):
        assert label in source
    assert "/api/public-intel/provider-test/" in source
    assert "/api/public-intel/provider-refresh/" in source
    assert "VERİYİ YENİLE" in source
    assert "Gerçek kaynak • sahte/demo veri yok" in source


def test_weather_traffic_panel_has_forecast_air_quality_marine_and_traffic():
    source = read("frontend/src/components/WeatherTrafficPanel.tsx")
    for endpoint in ("/api/weather/forecast", "/api/weather/air-quality", "/api/weather/marine", "/api/traffic/status"):
        assert endpoint in source
    for label in ("16 GÜNLÜK HAVA TABLOSU", "HAVA KALİTESİ", "DENİZ DURUMU", "KARA TRAFİĞİ & OLAYLAR"):
        assert label in source


def test_global_disasters_are_rendered_through_existing_global_incident_layer():
    builder = read("frontend/src/components/map/geoJSONBuilders.ts")
    worker = read("frontend/src/components/map/staticMapLayers.worker.ts")
    viewer = read("frontend/src/components/MaplibreViewer.tsx")
    assert "buildGlobalDisastersGeoJSON" in builder
    assert "type: 'global_disaster'" in builder
    assert "globalDisasters?: GlobalDisasterEvent[]" in worker
    assert "buildGlobalDisastersGeoJSON(staticData.globalDisasters" in worker
    assert "data?.global_disasters?.events" in viewer


def test_entity_movement_detail_is_visible_for_aircraft_and_vessels():
    block = read("frontend/src/components/MovementHistoryBlock.tsx")
    news = read("frontend/src/components/NewsFeed.tsx")
    assert "/api/public-intel/entity-movement" in block
    assert "CANLI ROTA & HAREKET KAYDI" in block
    assert 'entityType="aircraft"' in news
    assert 'entityType="ship"' in news


def test_global_disaster_selection_has_turkish_detail_card_and_external_source():
    source = read("frontend/src/components/NewsFeed.tsx")
    assert "selectedEntity?.type === 'global_disaster'" in source
    assert "KÜRESEL AFET OLAYI" in source
    assert "RESMÎ / KAYNAK SAYFASINI AÇ" in source


def test_external_link_bridge_still_has_native_and_browser_fallbacks():
    source = read("frontend/src/components/ExternalLinkBridge.tsx")
    assert "openExternal" in source
    assert "window.open" in source
    assert "window.location" in source


def test_camera_contract_remains_public_authorized_only():
    source = read("backend/services/cctv_pipeline.py")
    assert "public_access_confirmed" in source
    lowered = source.lower()
    assert "private" in lowered or "loopback" in lowered or "localhost" in lowered


def test_r2_regression_is_wired_into_windows_stage06():
    source = read("WINDOWS-DESKTOP-ONE-CLICK.ps1")
    assert "test_gokdogan_gd1_r2_public_ops.py" in source



def test_local_breaking_news_has_turkish_public_rss_sources_and_geocoding():
    feeds = read("backend/services/news_feed_config.py")
    news = read("backend/services/fetchers/news.py")
    router = read("backend/routers/public_intel.py")
    assert "https://www.trthaber.com/sondakika.rss" in feeds
    assert "https://www.aa.com.tr/tr/rss/default?cat=guncel" in feeds
    assert '"türkiye": (39.000, 35.000)' in news
    assert "local_providers" in router and "trt haber" in router and "anadolu ajansı" in router


def test_readiness_explains_public_camera_and_sensitive_tracking_boundaries():
    source = read("backend/services/integration_readiness.py")
    for capability in ("public_cameras", "live_police_tracking", "sensitive_military_telemetry", "submarine_live_positions"):
        assert f'"id": "{capability}"' in source
    assert "disabled_by_design" in source
    assert "source_limited" in source

def test_final_start_banner_has_no_hotfix_history():
    source = read("START-HERE.bat")
    assert "GOKDOGAN INTELLIGENCE v1.0.0" in source
    assert "HF18" not in source
