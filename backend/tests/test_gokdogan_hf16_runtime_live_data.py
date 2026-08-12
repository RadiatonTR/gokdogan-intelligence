from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str, encoding: str = "utf-8") -> str:
    return (ROOT / rel).read_text(encoding=encoding)


def test_companion_proxy_forces_identity_encoding_for_json_runtime():
    source = _read("desktop-shell/tauri-skeleton/src-tauri/src/companion_server.rs")
    assert '"accept-encoding"' in source.split("const STRIP_REQ", 1)[1].split("];", 1)[0]
    assert '.header("accept-encoding", "identity")' in source
    assert '"content-encoding"' in source.split("const STRIP_RESP", 1)[1].split("];", 1)[0]


def test_windows_local_custody_replaces_existing_protected_file_safely():
    source = _read("desktop-shell/tauri-skeleton/src-tauri/src/local_custody.rs")
    assert 'target.with_extension("replace-backup")' in source
    assert "native_local_custody_backup_rotate_failed" in source
    assert "if let Err(e) = fs::rename(&tmp_path, target)" in source
    assert "let _ = fs::rename(&backup_path, target);" in source


def test_native_vault_supports_atomic_multi_key_onboarding():
    vault = _read("desktop-shell/tauri-skeleton/src-tauri/src/secret_vault.rs")
    main = _read("desktop-shell/tauri-skeleton/src-tauri/src/main.rs")
    onboarding = _read("frontend/src/components/OnboardingModal.tsx")
    helper = _read("frontend/src/lib/apiKeyPersistence.ts")
    types = _read("frontend/src/lib/desktopBridge.ts")
    assert "pub async fn desktop_secret_set_many" in vault
    assert "desktop_secret_set_many," in main
    assert "setSecrets: function(values)" in main
    assert "saveApiKeysResilient" in onboarding
    assert "native?.setSecrets" in helper
    assert "native?.setSecret" in helper
    assert "backend-persistent" in helper
    assert "setSecrets?(values: Record<string, string>)" in types


def test_managed_desktop_starts_passive_live_data_and_financial_feed_by_default():
    source = _read("desktop-shell/tauri-skeleton/src-tauri/src/backend_runtime.rs")
    assert 'key: "GOKDOGAN_LIVE_DATA"' in source
    assert 'key: "FINANCIAL_ENABLED"' in source
    assert 'key: "MESH_MQTT_ENABLED"' in source


def test_financial_data_is_part_of_initial_desktop_preload():
    source = _read("backend/services/data_fetcher.py")
    startup = source.split("if startup_mode:", 1)[1].split("if not meshtastic_seeded", 1)[0]
    assert "fetch_financial_markets" in startup
    assert "next_run_time=datetime.utcnow() + timedelta(seconds=30)" in source


def test_gokdogan_start_here_packages_meshtastic_hardware_sdk_by_default():
    source = _read("START-HERE.bat", encoding="utf-8-sig")
    assert 'if not defined SB_INCLUDE_MESH_HARDWARE set "SB_INCLUDE_MESH_HARDWARE=1"' in source
    builder = _read("WINDOWS-DESKTOP-ONE-CLICK.ps1", encoding="utf-8-sig")
    assert "$runtimeExportArgs += @('--extra', 'mesh-hardware')" in builder


def test_local_meshtastic_radio_bridge_is_exposed_and_mqtt_fallback_remains():
    service = _read("backend/services/meshtastic_local_device.py")
    router = _read("backend/routers/data.py")
    transport = _read("backend/services/mesh/mesh_router.py")
    assert "SerialInterface" in service
    assert "sendText" in service
    assert '"/api/sigint/meshtastic/device/connect"' in router
    assert '"/api/sigint/meshtastic/device/disconnect"' in router
    assert "local_meshtastic_device.send_text" in transport
    assert "client.publish(topic, payload, qos=1)" in transport


def test_turkish_bridge_translates_general_dashboard_containers():
    source = _read("frontend/src/components/TurkishUiBridge.tsx")
    assert "span,p,div,a,li" in source
    assert "'NO NEWS ITEMS LOADED': 'HENÜZ HABER YÜKLENMEDİ'" in source
    assert "'COMMAND LINE': 'KOMUT SATIRI'" in source
