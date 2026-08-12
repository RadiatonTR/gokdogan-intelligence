import json
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "WINDOWS-DESKTOP-ONE-CLICK.ps1"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_r24_release_gate_is_ci_aligned_and_not_bare_full_suite():
    source = _source(BUILDER)
    assert "Invoke-Native $testPython @('-m', 'pytest', '-q') $BackendDir" not in source
    for rel in (
        "tests\\mesh\\test_mesh_node_bootstrap_runtime.py",
        "tests\\mesh\\test_mesh_infonet_sync_support.py",
        "tests\\mesh\\test_mesh_canonical.py",
        "tests\\mesh\\test_mesh_merkle.py",
        "tests\\test_release_helper.py",
        "tests\\mesh\\test_privacy_core_startup_policy.py",
    ):
        assert rel in source
    assert "WINDOWS-DESKTOP-FULL-REGRESSION.bat" in source


def test_r24_privacy_core_is_built_before_stage6_and_attested_for_tests():
    source = _source(BUILDER)
    build_pos = source.index("Building pinned privacy-core release DLL before backend release tests")
    stage6_pos = source.index("Write-Stage 6 'Static checks and desktop contract typecheck'")
    assert build_pos < stage6_pos
    assert "@('build', '--release', '--locked', '--manifest-path', $privacyCoreManifest)" in source
    assert "privacy-core\\target\\release\\privacy_core.dll" in source
    assert "$env:PRIVACY_CORE_LIB = $privacyCoreDll" in source
    assert "$env:PRIVACY_CORE_ALLOWED_SHA256 = $privacyCoreSha" in source


def test_r24_backend_test_environment_is_isolated_and_root_aware():
    source = _source(BUILDER)
    assert "$testDataDir = Join-Path $BuildReportsDir '.desktop-test-data'" in source
    assert "$env:SB_DATA_DIR = $testDataDir" in source
    assert "$env:PYTHONPATH = $BackendDir" in source
    assert "$env:MESH_SECURE_STORAGE_SECRET = 'shadowbroker-r24-release-test-only-secret-7f6c52e1'" in source
    assert "Invoke-Native $testPython $smokeArgs $BackendDir" in source
    assert "Invoke-Native $testPython $regressionArgs $RepoRoot" in source
    assert "Remove-Item $testDataDir -Recurse -Force -ErrorAction SilentlyContinue" in source


def test_r24_reputation_secure_storage_uses_the_isolated_data_root():
    source = _source(ROOT / "backend/services/mesh/mesh_reputation.py")
    assert 'DATA_DIR = Path(os.environ.get("SB_DATA_DIR"' in source
    assert source.count("base_dir=DATA_DIR") >= 8


def test_r24_full_regression_is_separate_diagnostic_lane():
    ps = _source(ROOT / "WINDOWS-DESKTOP-FULL-REGRESSION.ps1")
    bat = _source(ROOT / "WINDOWS-DESKTOP-FULL-REGRESSION.bat")
    assert "backend\\tests" in ps
    assert "diagnostic, not a release blocker" in ps
    assert "PRIVACY_CORE_LIB" in ps
    assert "SB_DATA_DIR" in ps
    assert "WINDOWS-DESKTOP-FULL-REGRESSION.ps1" in bat


def test_r24_tauri_tests_prepare_late_generated_bundle_resource_roots():
    source = _source(BUILDER)
    assert "$tauriTestResourceRoots = @(" in source
    assert "(Join-Path $TauriDir 'companion-www')" in source
    assert "(Join-Path $TauriDir 'backend-runtime')" in source
    assert "$temporaryTauriTestResourceRoots += $resourceRoot" in source
    assert "Remove-Item -LiteralPath $resourceRoot -Recurse -Force" in source
    assert source.index("$tauriTestResourceRoots = @(") < source.index(
        "Invoke-Native 'cargo' @('test', '--locked'"
    )


def test_r24_async_tauri_self_test_command_returns_result():
    source = _source(
        ROOT / "desktop-shell/tauri-skeleton/src-tauri/src/main.rs"
    )
    start = source.index("#[tauri::command]\nasync fn desktop_self_test")
    end = source.index("fn sanitize_notification_text", start)
    command = source[start:end]
    assert ") -> Result<DesktopSelfTestResult, String> {" in command
    assert "Ok(perform_desktop_self_test(" in command
    assert ".await)" in command


def test_r24_tauri_bundle_retries_transient_wix_and_nsis_downloads():
    source = _source(ROOT / "desktop-shell/tauri-skeleton/build.ps1")
    assert "$tauriBundleAttempts = 4" in source
    assert "for ($bundleAttempt = 1; $bundleAttempt -le $tauriBundleAttempts; $bundleAttempt++)" in source
    assert "cargo tauri build --bundles nsis -- --locked" in source
    assert "Tauri NSIS bundle attempt" in source
    assert "retrying with the verified tool cache" in source
    assert "SHADOWBROKER_TAURI_TOOLS_GITHUB_MIRROR" in source
    assert "TAURI_BUNDLER_TOOLS_GITHUB_MIRROR" in source
    assert "must be an absolute HTTPS URL" in source
    assert "Test-TransientTauriToolFailure $lastBundleOutput" in source
    assert "automatic retry skipped" in source
    assert "NSIS build failed after $completedBundleAttempts" in source


def test_r24_windows_powershell_does_not_treat_cargo_info_stderr_as_fatal():
    source = _source(ROOT / "desktop-shell/tauri-skeleton/build.ps1")
    assert "Windows PowerShell 5.1" in source
    assert "NativeCommandError" in source
    assert '$bundleErrorActionPreference = $ErrorActionPreference' in source
    assert '$ErrorActionPreference = "Continue"' in source
    assert "$_ -is [System.Management.Automation.ErrorRecord]" in source
    assert "$_.Exception.Message" in source
    assert "System.Management.Automation.RemoteException" in source
    assert "[void]$bundleOutputLines.Add($bundleLine)" in source
    assert "Write-Host $bundleLine" in source
    assert "$bundleExitCode = $LASTEXITCODE" in source
    assert "$ErrorActionPreference = $bundleErrorActionPreference" in source
    assert "Tee-Object -Variable bundleOutput" not in source
    save = source.index("$bundleErrorActionPreference = $ErrorActionPreference")
    scoped_continue = source.index('$ErrorActionPreference = "Continue"', save)
    cargo = source.index("& cargo tauri build --bundles nsis -- --locked", scoped_continue)
    exit_code = source.index("$bundleExitCode = $LASTEXITCODE", cargo)
    restore = source.index("$ErrorActionPreference = $bundleErrorActionPreference", exit_code)
    assert save < scoped_continue < cargo < exit_code < restore


def test_r24_nsis_resources_use_short_physical_sources_and_stable_targets():
    source = _source(ROOT / "desktop-shell/tauri-skeleton/build.ps1")
    assert '$shortResourceRoot = Join-Path $env:LOCALAPPDATA "SB-R24"' in source
    assert '$companionDir = Join-Path $shortResourceRoot "companion-www"' in source
    assert '$backendRuntimeDir = Join-Path $shortResourceRoot "backend-runtime"' in source
    assert '$resourceMap[(Convert-ToTauriResourceSource $companionDir)] = "companion-www/"' in source
    assert '$resourceMap[(Convert-ToTauriResourceSource $backendRuntimeDir)] = "backend-runtime/"' in source
    assert "$tauriConfig.bundle.resources = $resourceMap" in source
    assert "$maxResourcePathLength -ge 240" in source
    assert "NSIS resource source path preflight: PASS" in source


def test_r24_short_runtime_override_is_guarded_restored_and_cleaned():
    stage = _source(
        ROOT / "desktop-shell/tauri-skeleton/scripts/build-backend-runtime.cjs"
    )
    build = _source(ROOT / "desktop-shell/tauri-skeleton/build.ps1")
    wrapper = _source(BUILDER)
    assert "SHADOWBROKER_BACKEND_RUNTIME_OUTPUT" in stage
    assert "path.basename(outputDir).toLowerCase() !== 'backend-runtime'" in stage
    assert "outputSegments.length < 2" in stage
    assert "$originalBackendRuntimeOutput" in build
    assert "Remove-Item Env:SHADOWBROKER_BACKEND_RUNTIME_OUTPUT" in build
    assert "Remove-Item -LiteralPath $shortResourceRoot -Recurse -Force" in build
    assert "(Join-Path $env:LOCALAPPDATA 'SB-R24')" in wrapper


def test_r24_privacy_core_suppresses_only_benign_msvc_linker_info_lint():
    source = _source(ROOT / "privacy-core/src/lib.rs")
    assert '#![cfg_attr(target_env = "msvc", allow(linker_messages))]' in source
    assert "creating import library" in source
    assert "Keep every other warning enabled" in source


def test_r24_distributable_excludes_historical_update_documents():
    builder = _source(BUILDER)
    for token in (
        "LOG-ANALYSIS.txt",
        "VALIDATION-REPORT.txt",
        "README-FIRST.txt",
        "IMPLEMENTATION.md",
    ):
        assert token not in builder
    assert "SBOM-R24.cdx.json" in builder
    assert "R24-IMPLEMENTATION-MANIFEST.json" in builder


def test_r24_tauri_retry_restores_bundle_type_marker_before_repatching():
    source = _source(ROOT / "desktop-shell/tauri-skeleton/build.ps1")
    assert "$tauriReleaseExe = Join-Path $srcTauriDir" in source
    assert "Remove-Item -LiteralPath $tauriReleaseExe -Force" in source
    assert "cargo build --release --locked" in source
    assert "Failed to restore the unpatched Rust release executable" in source
    assert "Cargo reported success but the restored Rust release executable is missing" in source
    assert "__TAURI_BUNDLE_TYPE variable not found" in source


def test_r24_windows_release_uses_single_nsis_installer_not_wix_msi():
    build = _source(ROOT / "desktop-shell/tauri-skeleton/build.ps1")
    wrapper = _source(BUILDER)
    installer = _source(ROOT / "WINDOWS-DESKTOP-INSTALL-AND-VERIFY.ps1")
    assert "cargo tauri build --bundles nsis -- --locked" in build
    assert "cargo tauri build -- --locked" not in build
    assert "single NSIS installer" in wrapper
    assert "elseif ($nsis.Count -gt 0)" in installer
    assert "Start-Process -FilePath $installer.FullName" in installer


def test_r24_desktop_next_build_has_no_experimental_warning_banner():
    source = _source(ROOT / "frontend/next.config.ts")
    for deprecated_experiment in (
        "webpackBuildWorker",
        "parallelServerCompiles",
        "parallelServerBuildTraces",
        "workerThreads",
    ):
        assert deprecated_experiment not in source


def test_r24_start_here_builds_installs_verifies_and_opens_app():
    start_here = _source(ROOT / "START-HERE.bat")
    build_wrapper = _source(ROOT / "WINDOWS-DESKTOP-ONE-CLICK.bat")
    installer = _source(ROOT / "WINDOWS-DESKTOP-INSTALL-AND-VERIFY.ps1")
    verifier = _source(ROOT / "WINDOWS-DESKTOP-VERIFY-INSTALL.ps1")
    assert 'set "SB_NO_PAUSE=1"' in start_here
    assert 'if not defined SB_NO_PAUSE pause' in build_wrapper
    assert 'if not "%BUILD_EXIT%"=="0" (' in start_here
    assert 'DERLEME BASARISIZ. Bu pencere acik kalacak.' in start_here
    assert 'if not defined SHADOWBROKER_NO_FINAL_PAUSE pause' in start_here
    assert 'dist\\windows\\WINDOWS-DESKTOP-INSTALL-AND-VERIFY.bat' in start_here
    assert 'call "%INSTALL_VERIFY%"' in start_here
    assert '-File $verify -LaunchAfterVerify' in installer
    assert '[switch]$LaunchAfterVerify' in verifier
    assert 'Start-Process -FilePath $exe' in verifier


def test_r24_stale_generated_runtime_is_cleaned_before_source_gates():
    builder = _source(BUILDER)
    assert "function Clear-StaleGeneratedReleaseArtifacts" in builder
    for generated in (
        "(Join-Path $TauriDir 'backend-runtime')",
        "(Join-Path $TauriDir 'companion-www')",
        "(Join-Path $FrontendDir 'out')",
        "(Join-Path $RepoRoot '.desktop-export-build')",
    ):
        assert generated in builder
    cleanup_call = builder.index("    Clear-StaleGeneratedReleaseArtifacts")
    stage2 = builder.index("Write-Stage 2 'Build prerequisites'")
    stage6 = builder.index("Write-Stage 6 'Static checks and desktop contract typecheck'")
    assert cleanup_call < stage2 < stage6


def test_r24_source_secret_scan_ignores_bundled_runtime_false_positives(tmp_path, capsys):
    scanner = _load_script(
        "r24_secret_scanner_test", ROOT / "scripts/check_source_secrets.py"
    )
    scanner.ROOT = tmp_path
    source = tmp_path / "backend" / "app.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 'safe'\n", encoding="utf-8")
    generated = (
        tmp_path
        / "desktop-shell/tauri-skeleton/src-tauri/backend-runtime/python-runtime/Lib/site-packages/vendor.py"
    )
    generated.parent.mkdir(parents=True)
    generated.write_text("-----BEGIN PRIVATE KEY-----\n", encoding="utf-8")
    assert scanner.main() == 0
    assert "1 production text files scanned" in capsys.readouterr().out


def test_r24_source_compile_ignores_generated_python_trees(tmp_path, capsys):
    compiler = _load_script(
        "r24_source_compiler_test", ROOT / "scripts/compile_backend_sources.py"
    )
    compiler.ROOT = tmp_path
    compiler.BACKEND = tmp_path / "backend"
    source = compiler.BACKEND / "app.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = True\n", encoding="utf-8")
    generated = compiler.BACKEND / "backend-runtime/python-runtime/Lib/broken.py"
    generated.parent.mkdir(parents=True)
    generated.write_text("this is not valid python !!!\n", encoding="utf-8")
    assert compiler.main() == 0
    assert "files=1" in capsys.readouterr().out


def test_r24_release_build_suppresses_intentional_migration_flag_warning():
    source = _source(
        ROOT / "desktop-shell/tauri-skeleton/src-tauri/src/local_custody.rs"
    )
    marker = source.index("pub migrated: bool")
    annotation = source[max(0, marker - 240):marker]
    assert "#[allow(dead_code)]" in annotation
    assert "migration regression tests and diagnostics" in annotation


def test_r24_frontend_lint_is_warning_free_and_release_blocking():
    source = _source(BUILDER)
    package = _source(ROOT / "frontend/package.json")
    assert "Invoke-Native 'npm' @('--prefix', 'frontend', 'run', 'lint')" in source
    assert '"lint": "eslint --max-warnings=0"' in package


def test_r24_private_lane_rejects_development_override():
    source = _source(ROOT / "backend/services/privacy_core_attestation.py")
    block = source[source.index("def validate_privacy_core_startup"):]
    assert 'if state == "attested_current":' in block
    assert 'state in {"attested_current", "development_override"}' not in block


def test_r24_safety_defaults_remain_disabled():
    import json
    manifest = json.loads(_source(ROOT / "R24-IMPLEMENTATION-MANIFEST.json"))
    assert manifest["safety_defaults"] == {
        "active_recon": False,
        "host_shell": False,
        "experimental_privacy": False,
    }
    runtime = _source(ROOT / "desktop-shell/tauri-skeleton/src-tauri/src/backend_runtime.rs")
    assert "SB_ALLOW_ACTIVE_RECON" in runtime
    assert "SB_ALLOW_AGENT_SHELL" in runtime
    assert "SB_ENABLE_EXPERIMENTAL_PRIVACY" in runtime


def test_r24_release_smoke_preserves_repository_ci_contract():
    builder = _source(BUILDER)
    ci = _source(ROOT / ".github/workflows/ci.yml")
    maintained = (
        "tests/mesh/test_mesh_node_bootstrap_runtime.py",
        "tests/mesh/test_mesh_infonet_sync_support.py",
        "tests/mesh/test_mesh_canonical.py",
        "tests/mesh/test_mesh_merkle.py",
        "tests/test_release_helper.py",
    )
    for unix_rel in maintained:
        assert unix_rel in ci
        assert unix_rel.replace("/", "\\") in builder
    assert 'python-version: "3.12"' in ci


def test_r24_hf6_prunes_python_package_test_trees_before_integrity_manifest():
    stage = _source(ROOT / "desktop-shell/tauri-skeleton/scripts/build-backend-runtime.cjs")
    staged_validator = _source(ROOT / "scripts/validate_staged_desktop_runtime.py")
    assert "function prunePythonRuntimeTestArtifacts" in stage
    assert "lower === 'tests' || lower === 'test'" in stage
    copy_pos = stage.index("fs.cpSync(portablePythonDir, dest, { recursive: true })")
    prune_pos = stage.index("prunePythonRuntimeTestArtifacts(dest)", copy_pos)
    manifest_pos = stage.index("writeRuntimeIntegrityManifest()")
    assert copy_pos < prune_pos < manifest_pos
    assert "validate_no_packaged_python_test_trees" in staged_validator
    assert 'python_test_only_tree_present' in staged_validator
    for module in ("pandas", "scipy", "yfinance", "reverse_geocoder"):
        assert module in staged_validator
    assert "numpy_runtime_probe_failed" in staged_validator
    assert "pandas_runtime_probe_failed" in staged_validator


def test_r24_hf6_same_version_hotfix_resyncs_on_runtime_manifest_change():
    runtime = _source(ROOT / "desktop-shell/tauri-skeleton/src-tauri/src/backend_runtime.rs")
    assert "let bundled_manifest = fs::read(bundled_root.join(RUNTIME_INTEGRITY_MANIFEST_FILE))" in runtime
    assert "let installed_manifest = fs::read(install_root.join(RUNTIME_INTEGRITY_MANIFEST_FILE)).ok();" in runtime
    assert "let manifest_changed = installed_manifest.as_deref() != Some(bundled_manifest.as_slice());" in runtime
    assert "|| manifest_changed;" in runtime
    assert "if verify_runtime_integrity(&install_root).is_ok()" in runtime


def test_r24_hf6_install_verifier_targets_gokdogan_not_legacy_shadowbroker():
    verifier = _source(ROOT / "WINDOWS-DESKTOP-VERIFY-INSTALL.ps1")
    installer = _source(ROOT / "WINDOWS-DESKTOP-INSTALL-AND-VERIFY.ps1")
    assert "Find-GokdoganExe" in verifier
    assert "Gokdogan Intelligence Desktop*" in verifier
    assert "com.gokdogan.desktop" in verifier
    assert "will not fall back to a legacy ShadowBroker install" in verifier
    assert "com.shadowbroker.desktop" not in verifier
    assert "com.gokdogan.desktop" in installer
    assert "product = 'Gokdogan Intelligence Desktop'" in installer


def test_r24_hf7_optional_sqlite_virtual_tables_do_not_fail_integrity(tmp_path):
    from services.intelligence_core.storage import IntelligenceStore

    store = IntelligenceStore(tmp_path / "intelligence-core.db")
    with store.connect() as con:
        # Virtual indexes are optional by contract. Simulate a portable SQLite
        # runtime where they are unavailable while mandatory tables remain sound.
        for name in ("search_fts", "observation_geo", "geofence_geo"):
            try:
                con.execute(f"DROP TABLE IF EXISTS {name}")
            except Exception:
                pass
    report = store.integrity_report()
    assert report["quick_check"] == ["ok"]
    assert report["missing_tables"] == []
    assert report["ok"] is True
    assert report["optional_storage_degraded"] is True
    assert set(report["missing_virtual_tables"]) == {"search_fts", "observation_geo", "geofence_geo"}


def test_r24_hf7_installed_verifier_surfaces_self_test_diagnostics():
    root = Path(__file__).resolve().parents[2]
    text = (root / "WINDOWS-DESKTOP-VERIFY-INSTALL.ps1").read_text(encoding="utf-8-sig")
    assert "RedirectStandardOutput" in text
    assert "RedirectStandardError" in text
    assert "desktop-self-test.stdout.log" in text
    assert "desktop-self-test.stderr.log" in text
    assert "result.failures" in text
    assert "backend_stderr.log" in text
    assert "backend_stdout.log" in text


def test_r24_hf7_staged_runtime_probes_intelligence_store():
    root = Path(__file__).resolve().parents[2]
    text = (root / "scripts" / "validate_staged_desktop_runtime.py").read_text(encoding="utf-8")
    assert "IntelligenceStore" in text
    assert "intelligence_store_integrity_failed" in text
    assert "intelligence_store_ok" in text


def test_r24_hf8_python_bytecode_cache_is_never_integrity_managed():
    stage = _source(ROOT / "desktop-shell/tauri-skeleton/scripts/build-backend-runtime.cjs")
    runtime = _source(ROOT / "desktop-shell/tauri-skeleton/src-tauri/src/backend_runtime.rs")
    staged_validator = _source(ROOT / "scripts/validate_staged_desktop_runtime.py")
    assert "function prunePythonBytecodeCaches" in stage
    assert "lower === '__pycache__'" in stage
    assert "lower.endsWith('.pyc')" in stage
    assert "prunePythonBytecodeCaches(dest)" in stage
    assert "relParts.some((part) => part.toLowerCase() === '__pycache__')" in stage
    assert '.arg("-B")' in runtime
    assert '.env("PYTHONDONTWRITEBYTECODE", "1")' in runtime
    assert "validate_no_python_bytecode_caches" in staged_validator
    assert '[str(python), "-B", str(smoke)]' in staged_validator
    assert 'env["PYTHONDONTWRITEBYTECODE"] = "1"' in staged_validator
    build_ps1 = _source(ROOT / "desktop-shell/tauri-skeleton/build.ps1")
    assert '@($stagedPython, "-B", $stagedRuntimeValidator' in build_ps1
    assert '$env:PYTHONDONTWRITEBYTECODE = "1"' in build_ps1
    assert "sys.flags.dont_write_bytecode" in staged_validator
    assert staged_validator.count("validate_integrity_manifest(runtime)") >= 2
    assert "post_smoke_integrity" in staged_validator


def test_r24_hf9_frontend_build_is_offline_font_deterministic():
    layout = _source(ROOT / "frontend/src/app/layout.tsx")
    globals_css = _source(ROOT / "frontend/src/app/globals.css")
    tauri = _source(ROOT / "desktop-shell/tauri-skeleton/src-tauri/tauri.conf.json")
    frontend_sources = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in (ROOT / "frontend/src").rglob("*")
        if path.is_file()
        and "__tests__" not in path.parts
        and path.suffix.lower() in {".ts", ".tsx", ".css", ".scss"}
    )
    assert "next/font/google" not in frontend_sources
    assert "fonts.googleapis.com" not in frontend_sources
    assert "fonts.gstatic.com" not in frontend_sources
    assert "JetBrains_Mono(" not in layout
    assert "Cascadia Mono" in globals_css
    assert "Consolas" in globals_css
    assert "fonts.googleapis.com" not in tauri
    assert "fonts.gstatic.com" not in tauri


def test_r24_native_desktop_bridge_has_tauri_global_and_safe_invoke_guard():
    config = json.loads(_source(ROOT / "desktop-shell/tauri-skeleton/src-tauri/tauri.conf.json"))
    assert config["app"]["withGlobalTauri"] is True
    main = _source(ROOT / "desktop-shell/tauri-skeleton/src-tauri/src/main.rs")
    assert "function _nativeInvoke(command, args)" in main
    assert "native_tauri_api_unavailable" in main
    assert "window.__TAURI__.core.invoke" not in main
    for command in (
        "invoke_local_control",
        "desktop_secret_vault_status",
        "desktop_secret_set",
        "desktop_secret_delete",
        "desktop_self_test",
        "desktop_notify",
        "desktop_local_custody_status",
    ):
        assert f"_nativeInvoke('{command}'" in main


def test_r24_onboarding_native_vault_error_is_operator_readable():
    source = _source(ROOT / "frontend/src/components/OnboardingModal.tsx")
    assert "native_tauri_api_unavailable" in source
    assert "Masaüstü güvenli kasa bağlantısı hazır değil" in source
