from pathlib import Path

from services import api_settings

ROOT = Path(__file__).resolve().parents[2]
MAIN_RS = ROOT / "desktop-shell/tauri-skeleton/src-tauri/src/main.rs"
BACKEND_RUNTIME_RS = ROOT / "desktop-shell/tauri-skeleton/src-tauri/src/backend_runtime.rs"
BACKEND_MAIN = ROOT / "backend/main.py"
DESKTOP_BRIDGE = ROOT / "frontend/src/lib/desktopBridge.ts"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def test_native_desktop_has_backend_discovery_and_direct_api_fallback():
    source = _read(MAIN_RS)
    assert "async fn desktop_backend_status" in source
    assert ") -> Result<DesktopBackendStatus, String>" in source
    assert "desktop_backend_status," in source
    assert "getBackendStatus: function()" in source
    assert "var _nativeFetch" in source
    assert "_apiPathFromInput" in source
    assert "_directBackendFetch" in source
    assert "response.status !== 502" in source
    assert "http://127.0.0.1:" in source


def test_native_desktop_external_links_use_os_browser_and_reject_other_schemes():
    source = _read(MAIN_RS)
    assert "fn desktop_open_external" in source
    assert '"http" | "https"' in source
    assert "external_url_scheme_not_allowed" in source
    assert "open::that" in source
    assert "document.addEventListener('click'" in source
    assert "window.open = function" in source
    assert "desktop_open_external," in source


def test_frontend_bridge_contract_exposes_backend_status_and_external_opener():
    source = _read(DESKTOP_BRIDGE)
    assert "getBackendStatus?" in source
    assert "openExternal?" in source


def test_backend_cors_allows_only_dynamic_loopback_or_tauri_desktop_origins():
    source = _read(BACKEND_MAIN)
    assert "allow_origin_regex=" in source
    assert r"127\.0\.0\.1|localhost" in source
    assert "tauri://localhost" in source
    assert "http://tauri\\.localhost" in source


def test_native_vault_allowlist_covers_all_actively_wired_configurable_providers():
    source = _read(BACKEND_RUNTIME_RS)
    required = {
        "OPENSKY_CLIENT_ID",
        "OPENSKY_CLIENT_SECRET",
        "AIS_API_KEY",
        "AISHUB_USERNAME",
        "GFW_API_TOKEN",
        "FIRMS_MAP_KEY",
        "AIRFRAMES_API_KEY",
        "SHODAN_API_KEY",
        "FINNHUB_API_KEY",
        "SENTINEL_CLIENT_ID",
        "SENTINEL_CLIENT_SECRET",
        "LTA_ACCOUNT_KEY",
        "OPENAQ_API_KEY",
        "WINDY_API_KEY",
        "ALERTS_IN_UA_TOKEN",
        "NUFORC_MAPBOX_TOKEN",
        "FRED_API_KEY",
        "BLS_API_KEY",
        "EIA_API_KEY",
        "RELIEFWEB_APPNAME",
        "OPENCTI_URL",
        "OPENCTI_TOKEN",
        "OPENCTI_CONNECTOR_ID",
    }
    for key in required:
        assert f'"{key}"' in source, key


def test_api_registry_exposes_actively_wired_provider_credentials():
    keys = {entry["env_key"] for entry in api_settings.API_REGISTRY if entry.get("env_key")}
    expected = {
        "OPENSKY_CLIENT_ID",
        "OPENSKY_CLIENT_SECRET",
        "AIS_API_KEY",
        "AISHUB_USERNAME",
        "GFW_API_TOKEN",
        "FIRMS_MAP_KEY",
        "AIRFRAMES_API_KEY",
        "SHODAN_API_KEY",
        "FINNHUB_API_KEY",
        "SENTINEL_CLIENT_ID",
        "SENTINEL_CLIENT_SECRET",
        "LTA_ACCOUNT_KEY",
        "OPENAQ_API_KEY",
        "WINDY_API_KEY",
        "ALERTS_IN_UA_TOKEN",
        "NUFORC_MAPBOX_TOKEN",
        "FRED_API_KEY",
        "BLS_API_KEY",
        "EIA_API_KEY",
        "RELIEFWEB_APPNAME",
        "OPENCTI_URL",
        "OPENCTI_TOKEN",
        "OPENCTI_CONNECTOR_ID",
    }
    assert expected <= keys
    assert expected <= api_settings.ALLOWED_ENV_KEYS


def test_api_settings_write_path_accepts_new_hf12_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(api_settings, "OPERATOR_KEYS_ENV_PATH", tmp_path / "operator.env")
    monkeypatch.setattr(api_settings, "ENV_PATH", tmp_path / ".env")
    # Bu test yalnız yazma/persist sözleşmesini doğrular. Sahte test anahtarlarıyla
    # gerçek sağlayıcılara arka plan HTTP çağrısı başlatılması release testini
    # nondeterministik yapar ve 401/uyarı gürültüsü üretir.
    monkeypatch.setattr(api_settings, "_activate_api_keys", lambda clean: [])
    updates = {
        "AIS_API_KEY": "ais-test",
        "GFW_API_TOKEN": "gfw-test",
        "WINDY_API_KEY": "windy-test",
        "OPENAQ_API_KEY": "openaq-test",
        "FRED_API_KEY": "fred-test",
    }
    for key in updates:
        monkeypatch.delenv(key, raising=False)
    result = api_settings.save_api_keys(updates)
    assert result["ok"] is True
    assert set(updates) <= set(result["updated"])
    saved = (tmp_path / "operator.env").read_text(encoding="utf-8")
    for key in updates:
        assert f"{key}=" in saved


def test_turkish_bridge_covers_primary_desktop_chrome_without_duplicate_exact_keys():
    source = _read(ROOT / "frontend/src/components/TurkishUiBridge.tsx")
    for label in (
        "MISSION BRIEFING",
        "FIRST-TIME SETUP",
        "DATA LAYERS",
        "MESHTASTIC CHAT",
        "TIME MACHINE",
        "GLOBAL THREAT INTERCEPT",
        "SAVE KEYS LOCALLY",
    ):
        assert f"'{label}':" in source
    import re
    keys = re.findall(r"^\s*'([^']+)':", source, flags=re.MULTILINE)
    assert len(keys) == len(set(keys))


def test_turkish_backend_offline_message_is_desktop_specific_not_container_jargon():
    source = _read(ROOT / "frontend/src/i18n/translations/tr.json")
    assert "YEREL VERİ MOTORU BAĞLANTISI KESİLDİ" in source
    assert "BACKEND_URL" not in source
    assert "kapsayıcısının" not in source


def test_native_secret_vault_hot_applies_registered_keys_without_losing_offline_saves():
    source = _read(ROOT / "desktop-shell/tauri-skeleton/src-tauri/src/secret_vault.rs")
    assert "pub async fn desktop_secret_set" in source
    assert "save(&app, &vault)?;" in source
    assert '"/api/settings/api-keys/runtime"' in source
    assert "reqwest::Method::PUT" in source
    assert "let _ = crate::http_client::call_backend_json" in source
    assert "updates.insert(key.clone()" in source
