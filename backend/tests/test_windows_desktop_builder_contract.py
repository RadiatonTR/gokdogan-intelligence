"""Static contract checks for the Windows self-contained desktop builder."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILDER = REPO_ROOT / "WINDOWS-DESKTOP-ONE-CLICK.ps1"


def test_portable_python_uses_target_site_packages():
    source = BUILDER.read_text(encoding="utf-8-sig")
    assert "'Lib\\site-packages'" in source
    assert "'--target', $portableSitePackages" in source
    assert "scripts\\windows\\validate_portable_runtime.py" in source
    validator = (REPO_ROOT / "scripts" / "windows" / "validate_portable_runtime.py").read_text(encoding="utf-8")
    assert "Portable Python runtime OK" in validator


def test_builder_does_not_mutate_uv_managed_python_directly():
    source = BUILDER.read_text(encoding="utf-8-sig")
    legacy = "@('pip', 'install', '--python', $portablePython, $BackendDir)"
    assert legacy not in source


def test_webview2_detection_uses_official_evergreen_client_id_and_is_idempotent():
    source = BUILDER.read_text(encoding="utf-8-sig")
    assert "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" in source
    assert "{F1E7E359-7A65-4F5C-9E74-8CFD389B7D09}" not in source
    assert "Test-WingetPackageInstalled 'Microsoft.EdgeWebView2Runtime'" in source
    assert 'but WebView2 Runtime is installed; continuing.' in source


def test_builder_does_not_assign_powershell_automatic_args():
    import re
    source = BUILDER.read_text(encoding="utf-8-sig")
    assert re.search(r"(?mi)^\s*\$args\s*=", source) is None
    assert "$npmArgs = @(" in source
    assert "& npm @npmArgs" in source
    assert "$wingetArgs = @(" in source


def test_r17_default_runtime_excludes_optional_meshtastic_sdk():
    pyproject = (REPO_ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    core = pyproject.split("[project.optional-dependencies]", 1)[0]
    assert "meshtastic" not in core.lower()
    assert "mesh-hardware = [" in pyproject
    assert '"meshtastic==2.7.8"' in pyproject


def test_r17_builder_uses_frozen_lock_and_network_resilience():
    source = BUILDER.read_text(encoding="utf-8-sig")
    assert "'export', '--frozen', '--python', $portablePython" in source
    assert "'export', '--frozen', '--python', $portablePython" in source
    assert "$env:UV_HTTP_RETRIES = '8'" in source
    assert "$env:UV_HTTP_TIMEOUT = '120'" in source
    assert "$env:UV_HTTP_CONNECT_TIMEOUT = '30'" in source
    assert "Invoke-UvNetworkResilient" in source


def test_r17_mesh_hardware_is_explicit_build_opt_in():
    source = BUILDER.read_text(encoding="utf-8-sig")
    assert "$IncludeMeshHardware = ($env:SB_INCLUDE_MESH_HARDWARE -eq '1')" in source
    assert "$runtimeExportArgs += @('--extra', 'mesh-hardware')" in source
    assert "Pattern '^meshtastic=='" in source
    assert (REPO_ROOT / "WINDOWS-DESKTOP-BUILD-WITH-MESH-HARDWARE.bat").exists()
    assert (REPO_ROOT / "WINDOWS-DESKTOP-BUILD-WITH-MESH-HARDWARE.ps1").exists()


def test_r17_uv_lock_keeps_meshtastic_out_of_core_backend_dependencies():
    lock = (REPO_ROOT / "uv.lock").read_text(encoding="utf-8")
    start = lock.index('name = "backend"\nversion = "0.10.3"')
    end = lock.index("[[package]]", start + 20)
    backend = lock[start:end]
    core = backend.split("[package.optional-dependencies]", 1)[0]
    assert '{ name = "meshtastic" }' not in core
    assert "mesh-hardware = [" in backend
    assert '{ name = "meshtastic" }' in backend
    assert 'marker = "extra == \'mesh-hardware\'", specifier = "==2.7.8"' in backend


def test_r17_tauri_cli_probe_bootstraps_missing_cli_without_executing_missing_subcommand():
    source = BUILDER.read_text(encoding="utf-8-sig")
    assert "Test-Command 'cargo-tauri'" in source
    assert "Get-PinnedTauriCliVersion" in source
    assert "Invoke-NativeWithRetry 'cargo' @('install', 'tauri-cli', '--version', $RequiredTauriCli, '--locked', '--force')" in source
    assert "$env:CARGO_NET_RETRY = '8'" in source
    assert "$env:CARGO_HTTP_TIMEOUT = '120'" in source
    assert "cargo tauri -V" not in source


def test_r17_nested_tauri_wrapper_avoids_automatic_args_and_unsafe_probe():
    source = (REPO_ROOT / "desktop-shell" / "tauri-skeleton" / "build.ps1").read_text(encoding="utf-8-sig")
    assert "$commandArgs = @()" in source
    assert "& $exe @commandArgs" in source
    assert "$args =" not in source
    assert 'Get-Command "cargo-tauri" -ErrorAction SilentlyContinue' in source
    assert "cargo tauri -V" not in source


def test_r17_other_windows_helpers_do_not_assign_automatic_args():
    for rel in [
        "WINDOWS-DESKTOP-REPAIR.ps1",
        "scripts/start-dm-test-nodes.ps1",
        "scripts/run-dm-two-node-selftest.ps1",
    ]:
        source = (REPO_ROOT / rel).read_text(encoding="utf-8-sig")
        assert "$args =" not in source
        assert "$args=" not in source


def test_r18_stage5_cargo_commands_use_explicit_src_tauri_manifest_path():
    source = BUILDER.read_text(encoding="utf-8-sig")
    assert "$cargoManifestPath = Join-Path $TauriDir 'Cargo.toml'" in source
    assert "@('generate-lockfile', '--manifest-path', $cargoManifestPath)" in source
    assert "@('metadata','--manifest-path',$cargoManifestPath,'--locked','--format-version','1','--no-deps')" in source
    assert "cargo tree --manifest-path $cargoManifestPath --locked -p shadowbroker-tauri-shell" in source
    stage5 = source.split("Write-Stage 5 'Tauri CLI and Rust desktop toolchain'", 1)[1].split("Write-Stage 6 'Static checks and desktop contract typecheck'", 1)[0]
    assert "(Join-Path $DesktopDir 'tauri-skeleton')" not in stage5
    assert "& cargo metadata --locked --format-version 1 --no-deps" not in stage5


def test_r18_stage5_prechecks_exact_tauri_lock_pins_before_refresh():
    source = BUILDER.read_text(encoding="utf-8-sig")
    assert "$requiredCargoPackages = @(" in source
    assert "@{ Name = 'tauri'; Version = '2.11.5' }" in source
    assert "@{ Name = 'tauri-plugin-single-instance'; Version = '2.4.3' }" in source
    assert "@{ Name = 'tauri-plugin-notification'; Version = '2.3.3' }" in source
    assert "@{ Name = 'tauri-plugin-updater'; Version = '2.10.1' }" in source
    assert "@{ Name = 'tauri-plugin-process'; Version = '2.3.1' }" in source
    assert "$cargoLockNeedsRefresh" in source


def test_r19_static_python_gate_excludes_bundled_and_generated_runtime_trees():
    source = BUILDER.read_text(encoding="utf-8-sig")
    assert "scripts\\compile_backend_sources.py" in source
    assert "'-m', 'compileall', '-q', 'backend'" not in source
    helper = (REPO_ROOT / "scripts" / "compile_backend_sources.py").read_text(encoding="utf-8")
    for token in [".desktop-python", ".desktop-browsers", "node_modules", "target", "dist", "__pycache__", ".pytest_cache"]:
        assert token in helper
    assert 'compile(source, str(path), "exec"' in helper


def test_r20_rust_toolchain_bootstrap_is_offline_first_and_install_is_conditional():
    source = BUILDER.read_text(encoding="utf-8-sig")
    probe = source.index("rustup toolchain list")
    install = source.index("@('toolchain', 'install', $RequiredRust")
    assert probe < install
    assert "skipping rustup network sync/install" in source
    assert "--no-self-update" in source
    assert "RUSTUP_MAX_RETRIES" in source
    assert "static.rust-lang.org" in source
    assert "rustup run $RequiredRust rustc --version" in source
    assert "Invoke-Native 'rustup' @('toolchain', 'install', $RequiredRust, '--profile', 'minimal')" not in source


def test_r21_backend_pytest_gate_uses_isolated_portable_python_312():
    source = BUILDER.read_text(encoding="utf-8-sig")
    assert "$testVenvDir = Join-Path $BuildReportsDir '.desktop-test-venv'" in source
    assert "$testPython = Join-Path $testVenvDir 'Scripts\\python.exe'" in source
    assert "'export', '--frozen', '--python', $portablePython, '--package', 'backend', '--group', 'dev', '--no-emit-project'" in source
    assert "'venv', '--python', $portablePython, '--no-python-downloads', '--clear', $testVenvDir" in source
    assert "'pip', 'install', '--python', $testPython, '--compile-bytecode', '--require-hashes', '-r', $testRequirements" in source
    assert "Invoke-Native $testPython @('-m', 'pytest', '-q') $BackendDir" not in source
    assert "Invoke-Native $testPython $smokeArgs $BackendDir" in source
    assert "Invoke-Native $testPython $regressionArgs $RepoRoot" in source
    assert "$env:PYTHONPATH = $BackendDir" in source
    assert "uv run --frozen" not in source
    assert (REPO_ROOT / ".python-version").read_text(encoding="utf-8").strip() == "3.12"
    root_pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    backend_pyproject = (REPO_ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    assert 'requires-python = ">=3.11"' in root_pyproject
    assert 'requires-python = ">=3.11"' in backend_pyproject
    runtime_validator = (REPO_ROOT / "scripts" / "windows" / "validate_portable_runtime.py").read_text(encoding="utf-8")
    assert "sys.version_info[:2] != (3, 12)" in runtime_validator


def test_r22_stage6_build_reports_path_is_strictmode_safe_and_cleanup_is_guarded():
    source = BUILDER.read_text(encoding="utf-8-sig")
    assert "$BuildReportsDir = Join-Path $RepoRoot 'build-reports'" in source
    assert "$BuildReportDir" not in source
    assert "New-Item -ItemType Directory -Path $BuildReportsDir -Force | Out-Null" in source
    assert "$testVenvDir = Join-Path $BuildReportsDir '.desktop-test-venv'" in source
    assert "$testRequirements = Join-Path $BuildReportsDir 'backend-test-requirements.lock.txt'" in source
    assert 'Isolated backend test Python was not created' in source
    assert 'Remove-Item $testVenvDir -Recurse -Force -ErrorAction SilentlyContinue' in source
