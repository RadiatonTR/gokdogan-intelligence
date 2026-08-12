from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8-sig")


def test_weather_and_traffic_router_is_registered_and_uses_current_public_apis():
    registry = text("backend/router_registry.py")
    source = text("backend/routers/weather_traffic.py")
    assert "weather_traffic" in registry
    assert "https://api.open-meteo.com/v1/forecast" in source
    assert "/api/weather/forecast" in source
    assert "/api/weather/radar/tile/{z}/{x}/{y}.png" in source
    assert "/maps/orbis/traffic/flow/raster/tile/" in source
    assert "/maps/orbis/traffic/incidents/raster/tile/" in source
    assert "/maps/orbis/traffic/incidents/details" in source
    assert '"TomTom-Api-Key"' in source
    assert '"Attributes": attributes' in source
    assert "police-unit" in source


def test_weather_and_traffic_integrations_are_operator_visible_and_secret_safe():
    api = text("backend/services/api_settings.py")
    readiness = text("backend/services/integration_readiness.py")
    runtime = text("desktop-shell/tauri-skeleton/src-tauri/src/backend_runtime.rs")
    assert '"id": "open_meteo"' in api
    assert '"env_key": "TOMTOM_API_KEY"' in api
    assert '"open_meteo": IntegrationSpec' in readiness
    assert '"tomtom_api_key": IntegrationSpec' in readiness
    assert '"TOMTOM_API_KEY"' in runtime


def test_frontend_has_live_weather_traffic_panel_and_raster_layers():
    panel = text("frontend/src/components/WeatherTrafficPanel.tsx")
    traffic = text("frontend/src/components/map/TrafficRasterOverlay.tsx")
    radar = text("frontend/src/components/map/WeatherRadarOverlay.tsx")
    page = text("frontend/src/app/page.tsx")
    map_source = text("frontend/src/components/MaplibreViewer.tsx")
    defaults = text("frontend/src/lib/layerPreferences.ts")
    assert "HAVA & KARA TRAFİĞİ" in panel
    assert "/api/weather/forecast" in panel
    assert "/api/traffic/incidents" in panel
    assert "SICAKLIK DEĞİŞİMİ" in panel
    assert "YAKLAŞAN 6 SAAT" in panel
    assert "/api/traffic/tile/flow/" in traffic
    assert "/api/traffic/tile/incidents/" in traffic
    assert "/api/weather/radar/tile/" in radar
    assert "<WeatherTrafficPanel" in page
    assert "<WeatherRadarOverlay" in map_source
    assert "<TrafficRasterOverlay" in map_source
    assert "weather_radar: true" in defaults
    assert "road_traffic: true" in defaults


def test_api_key_save_has_native_and_loopback_fallback_paths():
    helper = text("frontend/src/lib/apiKeyPersistence.ts")
    admin = text("backend/routers/admin.py")
    assert "native.setSecrets" in helper
    assert "native.setSecret" in helper
    assert "backend-persistent" in helper
    assert "/api/settings/api-keys/runtime" in helper
    assert "/api/settings/api-keys'" in helper
    assert '@router.put("/api/settings/api-keys/runtime"' in admin


def test_external_links_have_native_and_browser_fallback():
    bridge = text("frontend/src/components/ExternalLinkBridge.tsx")
    layout = text("frontend/src/app/layout.tsx")
    permission = text("desktop-shell/tauri-skeleton/src-tauri/permissions/gokdogan-main-native.toml")
    assert "openExternal" in bridge
    assert "window.open" in bridge
    assert "window.location.href" in bridge
    assert "<ExternalLinkBridge />" in layout
    assert '"desktop_open_external"' in permission


def test_market_fallback_is_not_presented_as_an_error():
    ticker = text("frontend/src/components/GlobalTicker.tsx")
    assert "FINNHUB ANAHTARI YOK" not in ticker
    assert "YAHOO FINANCE • FINNHUB İSTEĞE BAĞLI" in ticker
    assert "CircleCheck" in ticker


def test_visible_alert_chrome_is_turkish_without_modifying_source_headlines():
    markers = text("frontend/src/components/map/MapMarkers.tsx")
    bridge = text("frontend/src/components/TurkishUiBridge.tsx")
    assert "!! UYARI SEVİYESİ {score} !!" in markers
    assert "BÖLGEDE AKTİF TEHDİT" in markers
    assert "!! ALERT LVL {score} !!" not in markers
    for token in ("'HIGH': 'YÜKSEK'", "'MEDIUM': 'ORTA'", "'LOW': 'DÜŞÜK'", "'INFO': 'BİLGİ'"):
        assert token in bridge


def test_active_layer_contract_contains_weather_radar_and_road_traffic():
    types = text("frontend/src/types/dashboard.ts")
    tr = json.loads(text("frontend/src/i18n/translations/tr.json"))
    assert "weather_radar: boolean" in types
    assert "road_traffic: boolean" in types
    assert tr["layers"]["weatherRadar"] == "Hava Radarı"
    assert tr["layers"]["roadTraffic"] == "Kara Trafiği"


def test_no_live_police_tracking_or_private_camera_discovery_added_by_r1():
    source = text("backend/routers/weather_traffic.py").lower()
    assert "provide or infer live police-unit locations" in source
    assert "police_location" not in source
    assert "discover_private_camera" not in source


def test_windows_stage06_runs_r1_final_contract():
    builder = text("WINDOWS-DESKTOP-ONE-CLICK.ps1")
    assert "test_gokdogan_gd1_r1_final.py" in builder
