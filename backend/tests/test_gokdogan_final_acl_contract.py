from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TAURI = ROOT / "desktop-shell" / "tauri-skeleton" / "src-tauri"


def _registered_commands() -> set[str]:
    source = (TAURI / "src" / "main.rs").read_text(encoding="utf-8")
    match = re.search(r"\.invoke_handler\(tauri::generate_handler!\[(.*?)\]\)", source, re.S)
    assert match, "Tauri invoke_handler block missing"
    return set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*,?", match.group(1)))


def test_loopback_capability_grants_explicit_gokdogan_native_permission_only():
    capability = json.loads((TAURI / "capabilities" / "main.json").read_text(encoding="utf-8"))
    assert capability["windows"] == ["main"]
    assert capability["permissions"] == ["core:default", "gokdogan-main-native"]
    assert capability["remote"]["urls"] == ["http://127.0.0.1:*/*"]


def test_native_permission_allows_every_registered_application_command_exactly_once():
    permission_path = TAURI / "permissions" / "gokdogan-main-native.toml"
    data = tomllib.loads(permission_path.read_text(encoding="utf-8"))
    permissions = data.get("permission") or []
    assert len(permissions) == 1
    permission = permissions[0]
    assert permission["identifier"] == "gokdogan-main-native"
    allowed = permission["commands"]["allow"]
    assert len(allowed) == len(set(allowed))
    assert set(allowed) == _registered_commands()


def test_api_vault_external_links_and_infonet_commands_are_acl_granted():
    data = tomllib.loads((TAURI / "permissions" / "gokdogan-main-native.toml").read_text(encoding="utf-8"))
    allowed = set(data["permission"][0]["commands"]["allow"])
    assert {
        "desktop_secret_set_many",
        "desktop_secret_set",
        "desktop_secret_vault_status",
        "desktop_open_external",
        "invoke_local_control",
    } <= allowed


def test_windows_stage06_runs_final_acl_contract_before_packaging():
    builder = (ROOT / "WINDOWS-DESKTOP-ONE-CLICK.ps1").read_text(encoding="utf-8-sig")
    assert "test_gokdogan_final_acl_contract.py" in builder


def test_final_builder_excludes_obsolete_distribution_clutter():
    obsolete = (
        "Makefile",
        "THIRD-PARTY-INTEGRATION-NOTES.md",
        "docker-compose.build.yml",
        "docker-compose.gitlab.yml",
        "docker-compose.relay.yml",
        "compose.sh",
        "kill_wormhole.bat",
        "kill_wormhole.sh",
        "killwormhole.bat",
        "killwormhole.sh",
        "wormhole-start.bat",
        "wormhole-start.sh",
        "frontend/README.md",
        "docs/OUTBOUND_DATA.md",
        "docs/contributor-map.md",
        "docs/production-hardening.md",
    )
    assert not [name for name in obsolete if (ROOT / name).exists()]


def test_installed_verifier_hides_only_known_benign_webview2_shutdown_noise():
    verifier = (ROOT / "WINDOWS-DESKTOP-VERIFY-INSTALL.ps1").read_text(encoding="utf-8-sig")
    assert "Failed to unregister class Chrome_WidgetWin_0\\. Error = 1412" in verifier
    assert "all other stderr remains visible" in verifier


def test_windows_packager_never_strips_native_permission_when_updater_mode_changes():
    build = (ROOT / "desktop-shell" / "tauri-skeleton" / "build.ps1").read_text(encoding="utf-8-sig")
    assert '$capability.permissions = @("core:default", "gokdogan-main-native")' in build
    assert '$capability.permissions = @("core:default", "gokdogan-main-native", "updater:default", "process:default")' in build


def test_managed_runtime_merges_manifest_owned_seed_data_into_persistent_data_directory():
    runtime = (TAURI / "src" / "backend_runtime.rs").read_text(encoding="utf-8")
    assert "fn sync_manifest_owned_data" in runtime
    assert "sync_manifest_owned_data(bundled_root, &install_root)?;" in runtime
    assert "sync_manifest_owned_data(install_root, previous_root)?;" in runtime
    assert "sync_manifest_owned_data(&previous_root, &install_root)?;" in runtime
    stage = (ROOT / "desktop-shell" / "tauri-skeleton" / "scripts" / "build-backend-runtime.cjs").read_text(encoding="utf-8")
    assert "aisstream_spki_pins.json" in stage


def test_r44_every_registry_secret_is_injected_from_native_vault_on_restart():
    import ast
    api_path = ROOT / "backend" / "services" / "api_settings.py"
    tree = ast.parse(api_path.read_text(encoding="utf-8"))
    registry = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "API_REGISTRY" for t in node.targets):
            registry = ast.literal_eval(node.value)
            break
    assert registry is not None
    registry_keys = {str(row["env_key"]) for row in registry if row.get("env_key")}
    runtime = (ROOT / "desktop-shell" / "tauri-skeleton" / "src-tauri" / "src" / "backend_runtime.rs").read_text(encoding="utf-8")
    section = runtime.split("fn backend_vault_secret_allowed", 1)[1].split("fn ", 1)[0]
    missing = {key for key in registry_keys if f'"{key}"' not in section}
    assert not missing, f"API keys not restored from native vault on restart: {sorted(missing)}"


def test_r44_external_link_bridge_never_navigates_native_webview_as_fallback():
    bridge = (ROOT / "frontend" / "src" / "components" / "ExternalLinkBridge.tsx").read_text(encoding="utf-8")
    assert "window.__SHADOWBROKER_DESKTOP__?.openExternal" in bridge
    assert "await native(href)" in bridge
    assert "window.location.assign(href)" in bridge
    native_block = bridge.split("if (native) {", 1)[1].split("const opened", 1)[0]
    assert "window.location" not in native_block
