from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8-sig")


def test_r4_release_profile_is_turkish_public_authorized_osint():
    payload = json.loads(_text("release-version.json"))
    assert payload["distribution"] == "Gökdoğan Intelligence 1.0.0"
    assert payload["default_language"] == "tr"
    assert payload["release_profile"] == "public-authorized-osint"
    boundaries = payload["safety_boundaries"]
    assert boundaries["private_or_closed_camera_discovery"] is False
    assert boundaries["live_law_enforcement_tracking"] is False
    assert boundaries["hidden_military_location_discovery"] is False
    assert boundaries["sensitive_military_live_telemetry_aggregation"] is False
    assert boundaries["person_targeted_aircraft_or_yacht_watchlists"] is False


def test_distribution_contains_no_generated_secret_state_or_targeted_watchlists():
    forbidden = [
        "backend/data/secure_storage_secret.key",
        "backend/data/_domain_keys/gates.key",
        "backend/data/gates/gates.json",
        "backend/data/operator_handle.json",
        "backend/data/cctv.db",
        "backend/data/intelligence-core.db",
        "backend/data/plane_alert_db.json",
        "backend/data/tracked_names.json",
        "backend/data/yacht_alert_db.json",
        "backend/data/plan_ccg_vessels.json",
    ]
    for rel in forbidden:
        assert not (ROOT / rel).exists(), rel


def test_runtime_seed_allowlist_is_explicit_and_does_not_stage_sensitive_tracking_data():
    source = _text("desktop-shell/tauri-skeleton/scripts/build-backend-runtime.cjs")
    assert "runtimeSeedDataAllowlist" in source
    for rel in ["power_plants.json", "datacenters.json", "kiwisdr_directory.json", "release_digests.json"]:
        assert rel in source
    allowlist = source.split("const runtimeSeedDataAllowlist", 1)[1].split("]);", 1)[0]
    for forbidden in ["military_bases.json", "plane_alert_db.json", "tracked_names.json", "yacht_alert_db.json", "plan_ccg_vessels.json"]:
        assert forbidden not in allowlist


def test_ci_and_desktop_release_use_node_24():
    ci = _text(".github/workflows/ci.yml")
    release = _text(".github/workflows/desktop-release.yml")
    assert "node-version: 24.19.0" in ci
    assert "node-version: 24.19.0" in release


def test_turkish_only_ui_profile_and_r4_operations_tabs():
    i18n = _text("frontend/src/i18n/index.tsx")
    locale_block = i18n.split("export const LOCALES", 1)[1].split("const translations", 1)[0]
    assert "code: 'tr'" in locale_block
    assert "code: 'en'" not in locale_block
    assert "translations[locale] ?? translations.tr" in i18n

    panel = _text("frontend/src/components/PublicIntelPanel.tsx")
    for label in [
        "KÜRESEL HABER", "YEREL HABER", "DİPLOMASİ", "SINIRLAR", "KAMERALAR",
        "ARAÇLAR", "AFETLER", "ÇATIŞMALAR", "KAYNAK SAĞLIĞI",
    ]:
        assert label in panel
    assert "SİSTEM İÇİNDE ÖNİZLE" in panel
    assert "SİSTEM TARAYICISINDA KAYNAĞI AÇ" in panel


def test_public_intel_r4_routes_and_safety_contract():
    router = _text("backend/routers/public_intel.py")
    for route in [
        "/api/public-intel/breaking-news",
        "/api/public-intel/diplomacy",
        "/api/public-intel/public-cameras",
        "/api/public-intel/civilian-movement",
        "/api/public-intel/conflict-regions",
        "/api/public-intel/disasters",
        "/api/public-intel/borders",
    ]:
        assert route in router
    assert "özel/kapalı kamera" in router.lower() or "private cctv" in router.lower()
    assert "ticari/sivil" in router.lower()
    assert "taktik" in router.lower()


def test_external_links_leave_desktop_webview_through_native_bridge():
    bridge = _text("frontend/src/components/ExternalLinkBridge.tsx")
    assert "window.__SHADOWBROKER_DESKTOP__?.openExternal" in bridge
    assert "isExternalHttp" in bridge
    assert "document.addEventListener('click', handler, true)" in bridge


def test_start_here_r4_has_double_bom_guard_and_no_bom_itself():
    path = ROOT / "START-HERE.bat"
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    source = raw.decode("utf-8")
    assert "GOKDOGAN INTELLIGENCE v1.0.0" in source
    assert "cift UTF-8 BOM" in source


def test_release_attestation_v2_includes_provenance_fields():
    generator = _text("scripts/generate_release_attestation.py")
    assert "gokdogan.release-attestation.v2" in generator
    assert "source_tree_fingerprint" in generator
    assert "GOKDOGAN_SOURCE_COMMIT" in generator
    assert '"release-version.json"' in generator


def test_sensitive_tracking_layers_are_not_enabled_by_default():
    backend = _text("backend/services/fetchers/_store.py")
    frontend = _text("frontend/src/lib/layerPreferences.ts")
    for token in ('"private": False', '"jets": False', '"military": False', '"tracked": False', '"ships_military": False', '"ships_tracked_yachts": False', '"military_bases": False'):
        assert token in backend
    for token in ('private: false', 'jets: false', 'military: false', 'tracked: false', 'ships_military: false', 'ships_tracked_yachts: false', 'military_bases: false'):
        assert token in frontend


def test_civilian_route_detail_endpoints_are_scoped_and_expose_observed_trails():
    router = _text("backend/routers/public_intel.py")
    assert "/api/public-intel/civilian-aircraft/{identifier}" in router
    assert "/api/public-intel/civilian-vessel/{identifier}" in router
    assert "_aircraft_is_sensitive_or_targeted" in router
    assert "_ship_is_sensitive_or_targeted" in router
    assert "observed_duration_seconds" in router
    assert "get_flight_trail" in router
    assert "get_vessel_trail" in router

    panel = _text("frontend/src/components/PublicIntelPanel.tsx")
    assert "ROTA KAYDI / DETAY" in panel
    assert "AYRINTILI ROTA KAYDI" in panel


def test_mesh_secure_storage_defaults_to_user_runtime_data_not_source_tree():
    source = _text("backend/services/mesh/mesh_secure_storage.py")
    runtime_paths = _text("backend/services/runtime_paths.py")
    assert "from services.runtime_paths import runtime_data_dir" in source
    assert "DATA_DIR = runtime_data_dir()" in source
    assert 'os.environ.get("SB_DATA_DIR"' in runtime_paths
    assert 'Path.home() / ".local" / "share" / "gokdogan-intelligence"' in runtime_paths
    assert 'DATA_DIR = Path(__file__).resolve().parents[2] / "data"' not in source


def test_release_builder_is_fail_closed_and_ci_has_provenance_signing_hooks():
    builder = _text("WINDOWS-DESKTOP-ONE-CLICK.ps1")
    assert "Invoke-NpmLockMetadataRepair" not in builder
    assert "Invoke-NpmSecurityLockRefresh" not in builder
    assert "will not rewrite package-lock.json" in builder
    assert "scripts\\validate-npm-locks.cjs" in builder

    workflow = _text(".github/workflows/desktop-release.yml")
    assert "actions/attest@v4" in workflow
    assert "attestations: write" in workflow
    assert "id-token: write" in workflow
    assert "GOKDOGAN_SOURCE_COMMIT: ${{ github.sha }}" in workflow
    assert "GOKDOGAN_WINDOWS_CERT_PFX_B64" in workflow
    assert "SHADOWBROKER_WINDOWS_CERT_THUMBPRINT" in workflow


def test_operator_handle_defaults_outside_source_tree():
    source = (ROOT / "backend/services/network_utils.py").read_text(encoding="utf-8")
    assert 'Path(__file__).parent.parent / "data" / "operator_handle.json"' not in source
    assert 'runtime_data_dir() / "operator_handle.json"' in source



def test_runtime_databases_default_outside_source_tree():
    cctv = (ROOT / "backend/services/cctv_pipeline.py").read_text(encoding="utf-8")
    intel = (ROOT / "backend/services/intelligence_core/storage.py").read_text(encoding="utf-8")
    assert 'runtime_data_dir() / "cctv.db"' in cctv
    assert 'runtime_data_dir() / "intelligence-core.db"' in intel
    assert 'parent.parent / "data" / "cctv.db"' not in cctv

