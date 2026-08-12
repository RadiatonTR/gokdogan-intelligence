from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_intelligence_center_uses_resilient_api_key_persistence():
    src = (_root() / "frontend/src/components/IntelligenceCenterPanel.tsx").read_text(encoding="utf-8")
    assert "saveApiKeysResilient" in src
    assert "const saved = await saveApiKeysResilient({ [key]: value });" in src
    assert "row:any" not in src
    assert "API anahtarı kaydedildi ancak çalışan backend üzerinde doğrulanamadı." in src


def test_settings_exposes_api_system_diagnostics_button():
    src = (_root() / "frontend/src/components/SettingsPanel.tsx").read_text(encoding="utf-8")
    assert "/api/settings/api-keys/diagnostics" in src
    assert "API SİSTEMİNİ TEST ET" in src
    assert "zorunlu eksik:" in src
    assert "isteğe bağlı eksik:" in src


def test_backend_exposes_secret_free_api_diagnostics_route():
    admin = (_root() / "backend/routers/admin.py").read_text(encoding="utf-8")
    service = (_root() / "backend/services/api_settings.py").read_text(encoding="utf-8")
    assert '@router.get("/api/settings/api-keys/diagnostics"' in admin
    assert "def get_api_key_diagnostics()" in service
    assert '"configured_env_keys"' in service
    assert '"persistent_store"' in service


def test_native_external_link_failure_has_non_navigation_fallback():
    src = (_root() / "desktop-shell/tauri-skeleton/src-tauri/src/main.rs").read_text(encoding="utf-8")
    assert "Harici bağlantı yerel tarayıcıda açılamadı" in src
    assert "_browserWindowOpen(parsed.href, '_blank', 'noopener,noreferrer')" in src
    assert '"/api/settings/api-keys/diagnostics"' in src
    assert "api_key_system: bool" in src
    assert "window.location.assign" not in src


def test_r46_release_identity_is_consistent():
    root = _root()
    release = (root / "release-version.json").read_text(encoding="utf-8")
    start = (root / "START-HERE.bat").read_text(encoding="utf-8")
    one_click = (root / "WINDOWS-DESKTOP-ONE-CLICK.ps1").read_text(encoding="utf-8-sig")
    assert '"package_revision": "1.0.0"' in release
    assert "GOKDOGAN INTELLIGENCE v1.0.0" in start
    assert "Gokdogan-Intelligence-v1.0.0-OFFLINE-USB.zip" in one_click
    assert "test_gokdogan_r46_api_system_stability.py" in one_click
    verify = (root / "WINDOWS-DESKTOP-VERIFY-INSTALL.ps1").read_text(encoding="utf-8-sig")
    assert "api_key_system" in verify


def test_runtime_api_diagnostics_never_returns_secret_values(monkeypatch, tmp_path):
    from services import api_settings

    secret = "r46-secret-must-never-leak"
    monkeypatch.setattr(api_settings, "OPERATOR_KEYS_ENV_PATH", tmp_path / "operator_api_keys.env")
    monkeypatch.setenv("AIS_API_KEY", secret)
    result = api_settings.get_api_key_diagnostics()
    assert result["registry_count"] >= 1
    assert "AIS_API_KEY" in result["configured_env_keys"]
    assert secret not in repr(result)
    assert result["persistent_store"]["parent_writable"] is True
