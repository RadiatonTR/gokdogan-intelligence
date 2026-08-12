#!/usr/bin/env python3
from __future__ import annotations
import ast, json, re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAILURES=[]; NOTES=[]
GENERATED_PYTHON_PARTS={
    '.desktop-python','.desktop-browsers','backend-runtime','python-runtime',
    'site-packages','build-reports','.venv','venv','__pycache__','.pytest_cache',
}
def fail(m): FAILURES.append(m)
def require(c,m):
    if not c: fail(m)
def read(rel):
    p=ROOT/rel
    if not p.exists(): fail(f"missing:{rel}"); return ""
    return p.read_text(encoding='utf-8-sig',errors='replace')
def j(rel):
    try: return json.loads((ROOT/rel).read_text(encoding='utf-8-sig'))
    except Exception as e: fail(f"json_invalid:{rel}:{e}"); return {}
def generated_python_path(path):
    return any(part.casefold() in GENERATED_PYTHON_PARTS for part in path.parts)
def route_scan():
    seen=defaultdict(list)
    for p in (ROOT/'backend').rglob('*.py'):
        if generated_python_path(p): continue
        try: tree=ast.parse(p.read_text(encoding='utf-8',errors='replace'),filename=str(p))
        except SyntaxError as e: fail(f"python_syntax:{p.relative_to(ROOT)}:{e.lineno}:{e.msg}"); continue
        prefixes={}
        for top in tree.body:
            if not isinstance(top,(ast.Assign,ast.AnnAssign)): continue
            value=top.value
            if not isinstance(value,ast.Call): continue
            callee=value.func.id if isinstance(value.func,ast.Name) else (value.func.attr if isinstance(value.func,ast.Attribute) else '')
            if callee!='APIRouter': continue
            prefix=''
            for kw in value.keywords:
                if kw.arg=='prefix' and isinstance(kw.value,ast.Constant) and isinstance(kw.value.value,str): prefix=kw.value.value.rstrip('/')
            targets=top.targets if isinstance(top,ast.Assign) else [top.target]
            for target in targets:
                if isinstance(target,ast.Name): prefixes[target.id]=prefix
        for node in ast.walk(tree):
            if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)): continue
            for dec in node.decorator_list:
                if not isinstance(dec,ast.Call) or not isinstance(dec.func,ast.Attribute): continue
                method=dec.func.attr.lower()
                if method not in {'get','post','put','patch','delete','options','head'}: continue
                if not dec.args or not isinstance(dec.args[0],ast.Constant) or not isinstance(dec.args[0].value,str): continue
                route=dec.args[0].value
                if not route.startswith('/'): continue
                rn=dec.func.value.id if isinstance(dec.func.value,ast.Name) else ''
                seen[(method.upper(),(prefixes.get(rn,'')+route) or route)].append(f"{p.relative_to(ROOT)}:{node.lineno}")
    dup={k:v for k,v in seen.items() if len(v)>1}
    for (method,route),owners in list(dup.items())[:20]: fail(f"duplicate_route:{method}:{route}:{'|'.join(owners)}")
    return len(seen),len(dup)
def compile_python():
    n=0
    for p in (ROOT/'backend').rglob('*.py'):
        if generated_python_path(p): continue
        try: compile(p.read_text(encoding='utf-8',errors='replace'),str(p),'exec'); n+=1
        except SyntaxError as e: fail(f"python_compile:{p.relative_to(ROOT)}:{e.lineno}:{e.msg}")
    return n

def main():
    manifest=j('R24-IMPLEMENTATION-MANIFEST.json'); tauri=j('desktop-shell/tauri-skeleton/src-tauri/tauri.conf.json')
    cap=j('desktop-shell/tauri-skeleton/src-tauri/capabilities/main.json')
    builder=read('WINDOWS-DESKTOP-ONE-CLICK.ps1'); build=read('desktop-shell/tauri-skeleton/build.ps1')
    runtime=read('desktop-shell/tauri-skeleton/src-tauri/src/backend_runtime.rs'); cargo=read('desktop-shell/tauri-skeleton/src-tauri/Cargo.toml')
    router=read('backend/routers/intelligence_core.py'); storage=read('backend/services/intelligence_core/storage.py')
    service=read('backend/services/intelligence_core/service.py'); fusion=read('backend/services/intelligence_core/fusion.py')
    localai=read('backend/services/intelligence_core/local_ai.py'); task_queue=read('backend/services/intelligence_core/task_queue.py'); moving_budget=read('frontend/src/components/map/hooks/useMovingEntityBudget.ts'); retry=read('backend/services/fetchers/retry.py'); store=read('backend/services/fetchers/_store.py'); legacy_bridge=read('backend/services/intelligence_core/legacy_bridge.py')
    audit=read('scripts/evaluate-npm-audits.cjs'); secret_scan=read('scripts/check_source_secrets.py'); staged=read('scripts/validate_staged_desktop_runtime.py'); backend_stage=read('desktop-shell/tauri-skeleton/scripts/build-backend-runtime.cjs')
    bundle_validator=read('scripts/validate_windows_bundle.ps1'); arch_budget=read('scripts/check_architecture_budgets.py')
    main_rs=read('desktop-shell/tauri-skeleton/src-tauri/src/main.rs'); companion_rs=read('desktop-shell/tauri-skeleton/src-tauri/src/companion.rs'); privacy_lib=read('privacy-core/src/lib.rs'); i18n=read('frontend/src/i18n/index.tsx'); telegram_translate=read('backend/services/telegram_translate.py')
    layout_tsx=read('frontend/src/app/layout.tsx'); globals_css=read('frontend/src/app/globals.css'); tauri_conf=read('desktop-shell/tauri-skeleton/src-tauri/tauri.conf.json')
    source_health=read('backend/services/intelligence_core/source_health.py'); data_fetcher=read('backend/services/data_fetcher.py'); alert_hook=read('frontend/src/hooks/useIntelligenceAlertNotifications.ts'); page_tsx=read('frontend/src/app/page.tsx'); keyboard_hook=read('frontend/src/hooks/useKeyboardShortcuts.ts'); intel_panel=read('frontend/src/components/IntelligenceCenterPanel.tsx')
    backend_config=read('backend/services/config.py'); fleet_defaults=read('backend/services/mesh/mesh_fleet_defaults.py'); compose=read('docker-compose.yml'); compose_override=read('docker-compose.override.yml'); meshnode_sh=read('meshnode.sh'); meshnode_bat=read('meshnode.bat')
    uv_lock=read('uv.lock'); root_pyproject=read('pyproject.toml'); backend_pyproject=read('backend/pyproject.toml')
    require(manifest.get('revision')=='R24','manifest_revision_not_r23'); require(manifest.get('base_version')=='0.10.3','manifest_version_not_0_10_2')
    sd=manifest.get('safety_defaults',{}); require(sd.get('active_recon') is False,'active_recon_not_false'); require(sd.get('host_shell') is False,'host_shell_not_false'); require(sd.get('experimental_privacy') is False,'experimental_privacy_not_false')
    require("$BuildRevision = 'R24'" in builder,'builder_revision_not_r23');
    require((ROOT/'.python-version').read_text(encoding='utf-8').strip()=='3.12','python_version_file_not_3_12')
    require("sys.version_info[:2] != (3, 12)" in read('scripts/windows/validate_portable_runtime.py'),'portable_runtime_python_312_guard_missing')
    require("$testVenvDir = Join-Path $BuildReportsDir '.desktop-test-venv'" in builder,'backend_test_venv_missing')
    require('$BuildReportDir' not in builder,'singular_build_report_dir_regression')
    require('New-Item -ItemType Directory -Path $BuildReportsDir -Force | Out-Null' in builder,'stage6_build_reports_dir_not_ensured')
    require('finally {' in builder and 'Remove-Item $testVenvDir -Recurse -Force -ErrorAction SilentlyContinue' in builder,'stage6_test_venv_cleanup_not_finally_guarded')
    require('Isolated backend test Python was not created' in builder,'stage6_test_python_existence_guard_missing')
    require("'export', '--frozen', '--python', $portablePython, '--package', 'backend', '--group', 'dev', '--no-emit-project'" in builder,'backend_test_requirements_not_frozen_export')
    require("'venv', '--python', $portablePython, '--no-python-downloads', '--clear', $testVenvDir" in builder,'backend_test_venv_not_portable_python')
    require("'pip', 'install', '--python', $testPython, '--compile-bytecode', '--require-hashes', '-r', $testRequirements" in builder,'backend_test_requirements_not_hash_locked')
    require("Invoke-Native $testPython @('-m', 'pytest', '-q') $BackendDir" not in builder,'bare_full_backend_pytest_release_gate_regression')
    for token in ['tests\\mesh\\test_mesh_node_bootstrap_runtime.py','tests\\mesh\\test_mesh_infonet_sync_support.py','tests\\mesh\\test_mesh_canonical.py','tests\\mesh\\test_mesh_merkle.py','tests\\test_release_helper.py','tests\\mesh\\test_privacy_core_startup_policy.py']:
        require(token in builder,f'release_smoke_missing:{token}')
    require("Invoke-Native $testPython $smokeArgs $BackendDir" in builder,'release_smoke_not_backend_cwd')
    require("Invoke-Native $testPython $regressionArgs $RepoRoot" in builder,'desktop_regression_not_repo_root_cwd')
    require("$env:PYTHONPATH = $BackendDir" in builder,'desktop_regression_pythonpath_missing')
    require("$testDataDir = Join-Path $BuildReportsDir '.desktop-test-data'" in builder and "$env:SB_DATA_DIR = $testDataDir" in builder,'isolated_test_data_dir_missing')
    mesh_reputation=read('backend/services/mesh/mesh_reputation.py')
    require('os.environ.get("SB_DATA_DIR"' in mesh_reputation,'mesh_reputation_ignores_isolated_data_dir')
    require(mesh_reputation.count('base_dir=DATA_DIR') >= 8,'mesh_reputation_secure_storage_ignores_isolated_data_dir')
    require("$tauriTestResourceRoots = @(" in builder and "(Join-Path $TauriDir 'companion-www')" in builder and "(Join-Path $TauriDir 'backend-runtime')" in builder,'tauri_test_resource_roots_missing')
    require('$temporaryTauriTestResourceRoots += $resourceRoot' in builder and 'Remove-Item -LiteralPath $resourceRoot -Recurse -Force' in builder,'tauri_test_resource_cleanup_missing')
    self_test_command = main_rs[main_rs.find('#[tauri::command]\nasync fn desktop_self_test'):main_rs.find('fn sanitize_notification_text')]
    require(') -> Result<DesktopSelfTestResult, String> {' in self_test_command and 'Ok(perform_desktop_self_test(' in self_test_command and '.await)' in self_test_command,'tauri_async_self_test_command_must_return_result')
    local_custody=read('desktop-shell/tauri-skeleton/src-tauri/src/local_custody.rs')
    require('#[allow(dead_code)]\n    pub migrated: bool' in local_custody,'tauri_release_migration_flag_warning_not_suppressed')
    require('$tauriBundleAttempts = 4' in build and 'for ($bundleAttempt = 1; $bundleAttempt -le $tauriBundleAttempts; $bundleAttempt++)' in build,'tauri_bundle_retry_loop_missing')
    require('cargo tauri build --bundles nsis -- --locked' in build and 'cargo tauri build -- --locked' not in build,'tauri_single_nsis_installer_contract_missing')
    require('Tauri NSIS bundle attempt' in build and 'retrying with the verified tool cache' in build,'tauri_bundle_retry_diagnostic_missing')
    require('$shortResourceRoot = Join-Path $env:LOCALAPPDATA "SB-R24"' in build and '$env:SHADOWBROKER_BACKEND_RUNTIME_OUTPUT = $backendRuntimeDir' in build,'nsis_short_physical_resource_root_missing')
    require('$resourceMap[(Convert-ToTauriResourceSource $companionDir)] = "companion-www/"' in build and '$resourceMap[(Convert-ToTauriResourceSource $backendRuntimeDir)] = "backend-runtime/"' in build and '$tauriConfig.bundle.resources = $resourceMap' in build,'tauri_resource_source_target_map_missing')
    require('$maxResourcePathLength -ge 240' in build and 'NSIS resource source path preflight: PASS' in build,'nsis_source_path_preflight_missing')
    require('Test-TransientTauriToolFailure $lastBundleOutput' in build and 'automatic retry skipped' in build and 'NSIS build failed after $completedBundleAttempts' in build,'tauri_retry_error_classification_missing')
    require('Windows PowerShell 5.1' in build and 'NativeCommandError' in build and '$bundleErrorActionPreference = $ErrorActionPreference' in build and '$ErrorActionPreference = "Continue"' in build and '$_ -is [System.Management.Automation.ErrorRecord]' in build and '$_.Exception.Message' in build and 'System.Management.Automation.RemoteException' in build and '$ErrorActionPreference = $bundleErrorActionPreference' in build and 'Tee-Object -Variable bundleOutput' not in build,'powershell_native_stderr_capture_can_terminate_cargo_info')
    require('SHADOWBROKER_BACKEND_RUNTIME_OUTPUT' in backend_stage and "path.basename(outputDir).toLowerCase() !== 'backend-runtime'" in backend_stage and 'outputSegments.length < 2' in backend_stage,'backend_runtime_output_override_guard_missing')
    require("(Join-Path $env:LOCALAPPDATA 'SB-R24')" in builder,'short_resource_root_stale_cleanup_missing')
    require('#![cfg_attr(target_env = "msvc", allow(linker_messages))]' in privacy_lib and 'Keep every other warning enabled' in privacy_lib,'privacy_core_msvc_linker_info_lint_not_narrowly_suppressed')
    obsolete_release_doc_tokens = ('LOG-ANALYSIS.txt', 'VALIDATION-REPORT.txt', 'README-FIRST.txt', 'IMPLEMENTATION.md')
    require(all(token not in builder for token in obsolete_release_doc_tokens),'historical_release_documents_still_collected')
    require("'SBOM-R24.cdx.json'" in builder and "'R24-IMPLEMENTATION-MANIFEST.json'" in builder,'current_release_artifacts_not_collected')
    require('$tauriReleaseExe = Join-Path $srcTauriDir' in build and 'Remove-Item -LiteralPath $tauriReleaseExe -Force' in build and 'cargo build --release --locked' in build,'tauri_bundle_retry_does_not_restore_unpatched_binary')
    require('__TAURI_BUNDLE_TYPE variable not found' in build,'tauri_bundle_type_retry_warning_contract_missing')
    require('SHADOWBROKER_TAURI_TOOLS_GITHUB_MIRROR' in build and 'TAURI_BUNDLER_TOOLS_GITHUB_MIRROR' in build and 'must be an absolute HTTPS URL' in build,'tauri_bundle_https_mirror_contract_missing')
    next_config=read('frontend/next.config.ts')
    require(all(token not in next_config for token in ['webpackBuildWorker','parallelServerCompiles','parallelServerBuildTraces','workerThreads']),'desktop_next_experimental_warning_banner_present')
    require("Invoke-Native 'npm' @('--prefix', 'frontend', 'run', 'lint')" in builder,'warning_free_frontend_lint_gate_missing')
    require('eslint --max-warnings=0' in read('frontend/package.json'),'frontend_lint_warning_budget_not_zero')
    require("WINDOWS-DESKTOP-FULL-REGRESSION.bat" in builder,'full_regression_diagnostic_reference_missing')
    require((ROOT/'WINDOWS-DESKTOP-FULL-REGRESSION.ps1').exists() and (ROOT/'WINDOWS-DESKTOP-FULL-REGRESSION.bat').exists(),'full_regression_diagnostic_wrapper_missing')
    require("privacy-core\\target\\release\\privacy_core.dll" in builder,'privacy_core_pretest_dll_missing')
    require("@('build', '--release', '--locked', '--manifest-path', $privacyCoreManifest)" in builder,'privacy_core_pretest_build_missing')
    require("$env:PRIVACY_CORE_LIB = $privacyCoreDll" in builder and "$env:PRIVACY_CORE_ALLOWED_SHA256 = $privacyCoreSha" in builder,'privacy_core_test_attestation_env_missing')
    attestation_policy=read('backend/services/privacy_core_attestation.py')
    require('if state == "attested_current":' in attestation_policy,'private_lane_dev_override_rejection_missing')
    require('state in {"attested_current", "development_override"}' not in attestation_policy,'private_lane_dev_override_still_accepted')
    source_compile=read('scripts/compile_backend_sources.py')
    require("scripts\\compile_backend_sources.py" in builder,'source_only_compile_gate_not_wired')
    require("'-m', 'compileall', '-q', 'backend'" not in builder,'unsafe_compileall_backend_runtime_traversal_present')
    for token in ['.desktop-python','.desktop-browsers','node_modules','target','dist','backend-runtime','python-runtime','site-packages','__pycache__','.pytest_cache']:
        require(token in source_compile,f'source_compile_exclusion_missing:{token}')
    for token in ['backend-runtime','python-runtime','companion-www','site-packages','.desktop-export-build']:
        require(token in secret_scan,f'source_secret_generated_exclusion_missing:{token}')
    require("Clear-StaleGeneratedReleaseArtifacts" in builder and builder.find('Clear-StaleGeneratedReleaseArtifacts') < builder.find("Write-Stage 2 'Build prerequisites'"),'stale_generated_runtime_not_cleaned_before_release_gates')
    require('compile(source, str(path), "exec"' in source_compile,'source_compile_uses_no_source_compile_contract')
    require("$RequiredNodeMajor = 24" in builder,'node_major_pin_missing'); require("$RequiredRust = '1.97.1'" in builder,'rust_pin_missing'); require("$RequiredTauriCli = '2.11.4'" in builder,'tauri_cli_pin_missing')
    require('rustup toolchain list' in builder,'r23_local_rust_toolchain_probe_missing')
    require('skipping rustup network sync/install' in builder,'r23_local_rust_offline_message_missing')
    require("@('toolchain', 'install', $RequiredRust, '--profile', 'minimal', '--no-self-update')" in builder,'r23_missing_only_rust_install_contract_missing')
    require("rustup run $RequiredRust rustc --version" in builder,'r23_explicit_pinned_rust_version_check_missing')
    require('RUSTUP_MAX_RETRIES' in builder,'r23_rustup_retry_contract_missing')
    require('static.rust-lang.org' in builder,'r23_rust_dns_diagnostic_missing')
    rust_probe_pos = builder.find('rustup toolchain list')
    rust_install_pos = builder.find("@('toolchain', 'install', $RequiredRust")
    require(rust_probe_pos >= 0 and rust_install_pos > rust_probe_pos,'r23_rust_install_occurs_before_local_probe')
    unconditional = "Invoke-Native 'rustup' @('toolchain', 'install', $RequiredRust, '--profile', 'minimal')"
    require(unconditional not in builder,'r23_unconditional_rustup_install_regression')
    npm_lock_validator=read('scripts/validate-npm-locks.cjs'); frontend_lock=read('frontend/package-lock.json')
    start_here=read('START-HERE.bat')
    require('Invoke-NpmCiResilient' in builder and '.desktop-npm-cache' in builder,'npm_resilient_ci_missing')
    require("--source-pre-refresh" in npm_lock_validator,'npm_source_prerefresh_validation_mode_missing')
    require('if not defined SB_INCLUDE_MESH_HARDWARE set "SB_INCLUDE_MESH_HARDWARE=1"' in start_here,'gokdogan_start_here_mesh_hardware_default_missing')
    require('set "SB_NO_PAUSE=1"' in start_here and 'if not "%BUILD_EXIT%"=="0" (' in start_here,'start_here_build_to_install_guard_missing')
    require('DERLEME BASARISIZ. Bu pencere acik kalacak.' in start_here and 'if not defined SHADOWBROKER_NO_FINAL_PAUSE pause' in start_here,'start_here_failure_visibility_contract_missing')
    require('chcp 65001 >nul' in start_here and '[Console]::OutputEncoding = $utf8NoBom' in builder,'windows_console_utf8_contract_missing')
    require('dist\\windows\\WINDOWS-DESKTOP-INSTALL-AND-VERIFY.bat' in start_here and 'call "%INSTALL_VERIFY%"' in start_here,'start_here_auto_install_verify_missing')
    require('if not defined SB_NO_PAUSE pause' in read('WINDOWS-DESKTOP-ONE-CLICK.bat'),'one_click_noninteractive_handoff_missing')
    install_verify=read('WINDOWS-DESKTOP-INSTALL-AND-VERIFY.ps1'); installed_verify=read('WINDOWS-DESKTOP-VERIFY-INSTALL.ps1')
    require('-File $verify -LaunchAfterVerify' in install_verify and '[switch]$LaunchAfterVerify' in installed_verify and 'Start-Process -FilePath $exe' in installed_verify,'installed_app_launch_handoff_missing')
    require(re.search(r'(?mi)^\s*\$args\s*=', builder) is None,'powershell_automatic_args_assignment_present')
    require("Test-Command 'cargo-tauri'" in builder and 'Get-PinnedTauriCliVersion' in builder,'tauri_cli_safe_probe_missing')
    require("Invoke-NativeWithRetry 'cargo' @('install', 'tauri-cli', '--version', $RequiredTauriCli, '--locked', '--force')" in builder,'tauri_cli_bootstrap_missing')
    require("$env:CARGO_NET_RETRY = '8'" in builder and "$env:CARGO_HTTP_TIMEOUT = '120'" in builder,'tauri_cli_cargo_network_resilience_missing')
    require('cargo tauri -V' not in builder,'unsafe_missing_tauri_probe_present')
    ps_files = [ROOT/'WINDOWS-DESKTOP-REPAIR.ps1', ROOT/'desktop-shell/tauri-skeleton/build.ps1', ROOT/'scripts/start-dm-test-nodes.ps1', ROOT/'scripts/run-dm-two-node-selftest.ps1']
    for _ps in ps_files:
        _txt=_ps.read_text(encoding='utf-8-sig',errors='replace')
        require(re.search(r'(?mi)^\s*\$args\s*=', _txt) is None,f'powershell_automatic_args_assignment_present:{_ps.relative_to(ROOT)}')
    require('Get-Command "cargo-tauri" -ErrorAction SilentlyContinue' in build,'nested_tauri_safe_probe_missing')
    require('cargo tauri -V' not in build,'nested_unsafe_tauri_probe_present')
    require('$commandArgs = @()' in build and '& $exe @commandArgs' in build,'nested_build_argument_splat_fix_missing')
    require("Invoke-Native 'node' @('scripts\\validate-npm-locks.cjs') $RepoRoot" in builder,'npm_lock_preflight_missing')
    require('$wingetArgs = @(' in builder and "Invoke-Native 'winget' $wingetArgs" in builder,'winget_argument_variable_fix_missing')
    require('tr46_6_0_0_integrity_regression' in npm_lock_validator,'npm_tr46_regression_contract_missing')
    require('semver_6_3_1_integrity_regression' in npm_lock_validator,'npm_semver_regression_contract_missing')
    require('Invoke-NpmLockMetadataRepair' not in builder and 'Invoke-NpmSecurityLockRefresh' not in builder,'r4_release_builder_must_not_mutate_npm_locks')
    frontend_pkg=j('frontend/package.json')
    require(frontend_pkg.get('dependencies',{}).get('next')=='16.2.11','r23_next_security_pin_missing')
    for _pkg,_ver in {'nanoid':'3.3.17','postcss':'8.5.24','sharp':'0.35.3'}.items(): require(frontend_pkg.get('overrides',{}).get(_pkg)==_ver,f'r23_security_override_missing:{_pkg}:{_ver}')
    require('will not rewrite package-lock.json' in builder and "'ci'" in builder,'r4_npm_fail_closed_contract_missing')
    require((ROOT/'scripts/verify-npm-security-baseline.cjs').exists() and (ROOT/'scripts/verify-npm-security-delta.cjs').exists(),'r23_security_lock_helpers_missing')
    require("next:'16.2.11'" in npm_lock_validator and "nanoid:'3.3.17'" in npm_lock_validator and "postcss:'8.5.24'" in npm_lock_validator and "sharp:'0.35.3'" in npm_lock_validator,'r23_strict_security_lock_contract_missing')
    require(frontend_pkg.get('overrides',{}).get('@types/mapbox__point-geometry')=='0.1.4','deprecated_mapbox_point_geometry_stub_override_missing')
    require(frontend_pkg.get('allowScripts',{}).get('sharp@0.35.3') is True and 'sharp@0.34.5' not in frontend_pkg.get('allowScripts',{}),'sharp_allow_scripts_stale')
    require('moderate/high/critical package details' in audit and 'totals.moderate > 0' in audit,'moderate_audit_detail_or_gate_missing')
    require('test-npm-audit-policy.cjs' in builder and (ROOT/'scripts/test-npm-audit-policy.cjs').exists(),'npm_audit_policy_regression_gate_missing')
    require("$env:NPM_CONFIG_UPDATE_NOTIFIER = 'false'" in builder,'npm_update_notifier_not_disabled')
    require('install_playwright_runtime.py' in builder and (ROOT/'scripts/windows/install_playwright_runtime.py').exists(),'playwright_captured_installer_missing')
    contact_identity=read('frontend/src/mesh/meshIdentity.ts'); contact_test=read('frontend/src/__tests__/mesh/meshContactStorage.test.ts')
    require('export async function flushContactPersistence()' in contact_identity,'contact_persistence_flush_api_missing')
    require('await persistStoredContacts(hydrated);' in contact_identity,'legacy_contact_migration_not_awaited')
    require('await flushContactPersistence();' in contact_identity,'contact_hydrate_pending_write_barrier_missing')
    require('await mod.flushContactPersistence();' in contact_test and 'waitForEncryptedContacts' not in contact_test,'contact_storage_test_still_timer_polling')
    for test_rel in ['frontend/src/__tests__/mesh/gateCompatDecryptUx.test.tsx','frontend/src/__tests__/mesh/messagesViewFirstContact.test.tsx','frontend/src/__tests__/mesh/topRightControlsTerminalLauncher.test.tsx']:
        require('act' in read(test_rel),f'react_act_regression_fix_missing:{test_rel}')
    require((ROOT/'scripts/verify-npm-lock-stability.cjs').exists(),'npm_lock_stability_helper_missing'); require((ROOT/'scripts/refresh-npm-lock-integrities.cjs').exists(),'npm_registry_integrity_refresh_helper_missing')
    require('sha512-bLVMLPtstlZ4iMQHpFHTR7GAGj2jxi8Dg0s2h2MafAE4uSWF98FC/3MomU51iQAMf8/qDUbKWf5GxuvvVcXEhw==' in frontend_lock,'frontend_tr46_integrity_not_fixed')
    require('FHTR8GAG' not in frontend_lock,'frontend_tr46_corrupt_integrity_present')
    require('sha512-BR7VvDCVHO+q2xBEWskxS6DJE1qRnb7DxzUrogb71CWoSficBxYsiAGd+Kl0mmq/MprG9yArRkyrQxTO6XjMzA==' in frontend_lock,'frontend_semver_integrity_not_fixed')
    require('sha512-BR8VvDCVHO+q2xBEWskxS6DJE1qRnb7DxzUrogb71CWoSficBxYsiAGd+Kl0mmq/MprG9yArRkyrQxTO6XjMzA==' not in frontend_lock,'frontend_semver_corrupt_integrity_present')
    require(read('.node-version').strip()=='24.19.0','node_version_file_wrong'); require('channel = "1.97.1"' in read('rust-toolchain.toml'),'rust_toolchain_pin_wrong')
    require('version = "0.10.3"' in root_pyproject and 'version = "0.10.3"' in backend_pyproject,'python_project_version_not_r23')
    require('requires-python = ">=3.11"' in root_pyproject and 'requires-python = ">=3.11"' in backend_pyproject,'python_requires_contract_not_3_11_plus')
    require('requires-python = ">=3.11"' in uv_lock,'uv_lock_python_floor_not_3_11')
    require('name = "backend"\nversion = "0.10.3"' in uv_lock and 'name = "shadowbroker"\nversion = "0.10.3"' in uv_lock,'uv_lock_project_identity_stale_r23')
    core_dep_block = backend_pyproject.split('[project.optional-dependencies]',1)[0]
    require('meshtastic' not in core_dep_block.lower(),'meshtastic_still_core_dependency')
    require('mesh-hardware = [' in backend_pyproject and '"meshtastic==2.7.8"' in backend_pyproject,'mesh_hardware_optional_extra_missing')
    backend_lock_start = uv_lock.find('name = "backend"\nversion = "0.10.3"')
    backend_lock_end = uv_lock.find('[[package]]', backend_lock_start + 20) if backend_lock_start >= 0 else -1
    backend_lock = uv_lock[backend_lock_start:backend_lock_end] if backend_lock_start >= 0 and backend_lock_end > backend_lock_start else ''
    core_lock_deps = backend_lock.split('[package.optional-dependencies]',1)[0]
    require('{ name = "meshtastic" }' not in core_lock_deps,'meshtastic_still_core_locked_dependency')
    require('mesh-hardware = [' in backend_lock and '{ name = "meshtastic" }' in backend_lock,'mesh_hardware_lock_extra_missing')
    require('marker = "extra == \'mesh-hardware\'", specifier = "==2.7.8"' in backend_lock,'mesh_hardware_lock_metadata_missing')
    require("$IncludeMeshHardware = ($env:SB_INCLUDE_MESH_HARDWARE -eq '1')" in builder,'mesh_hardware_build_opt_in_missing')
    require("$runtimeExportArgs += @('--extra', 'mesh-hardware')" in builder,'mesh_hardware_export_switch_missing')
    require("Pattern '^meshtastic=='" in builder,'core_runtime_meshtastic_boundary_check_missing')
    require("$env:UV_HTTP_RETRIES = '8'" in builder and "$env:UV_HTTP_TIMEOUT = '120'" in builder and "$env:UV_HTTP_CONNECT_TIMEOUT = '30'" in builder,'uv_network_resilience_settings_missing')
    require('Invoke-UvNetworkResilient' in builder and 'Invoke-NativeWithRetry' in builder,'uv_retry_wrapper_missing')
    require((ROOT/'WINDOWS-DESKTOP-BUILD-WITH-MESH-HARDWARE.bat').exists() and (ROOT/'WINDOWS-DESKTOP-BUILD-WITH-MESH-HARDWARE.ps1').exists(),'mesh_hardware_optional_build_helpers_missing')
    for package_rel in ('frontend/package.json','desktop-shell/package.json','backend/package.json'):
        require((j(package_rel).get('engines') or {}).get('node')=='24.x',f'node_engine_pin_missing:{package_rel}')
    for cmd in ["$smokeArgs", "$regressionArgs", "'npm' @('--prefix', 'frontend', 'test')", "'cargo' @('test', '--locked'", 'validate_r24_release.py', 'validate_intelligence_core.py']:
        require(cmd in builder,f'full_release_gate_missing:{cmd}')
    require("'export', '--frozen', '--python', $portablePython" in builder and "'--require-hashes'" in builder,'python_frozen_requirements_install_missing')
    require("uv.lock is required for the frozen release build" in builder,'python_frozen_lock_presence_gate_missing')
    require('SB_ALLOW_HIGH_AUDIT' in audit and ('high > 0' in audit or 'high' in audit),'high_audit_gate_missing')
    require('SB_ALLOW_AUDIT_UNAVAILABLE' in audit,'audit_unavailable_override_missing')
    require('findingDetails' in audit and 'moderate/high/critical package details' in audit,'audit_package_diagnostics_missing')
    require('decodeAuditReport' in audit and 'utf16le' in audit and '0xfeff' in audit,'audit_encoding_tolerance_missing')
    require('System.Diagnostics.ProcessStartInfo' in builder and 'System.Text.UTF8Encoding($false)' in builder,'audit_utf8_native_capture_missing')
    require('ReadToEndAsync' in builder and 'ComSpec' in builder,'audit_capture_deadlock_or_cmd_wrapper_missing')
    require('test-npm-audit-encoding.cjs' in builder and (ROOT/'scripts/test-npm-audit-encoding.cjs').exists(),'audit_encoding_regression_gate_missing')
    require('PRIVATE_KEY' in secret_scan and 'KNOWN_TOKEN' in secret_scan and 'Source secret scan FAILED' in secret_scan,'source_secret_release_scan_missing')
    require('check_source_secrets.py' in builder,'source_secret_scan_not_in_windows_gate')
    perms=set(cap.get('permissions') or []); require(cap.get('windows')==['main'],'capability_window_scope_wrong'); require(perms=={'core:default','gokdogan-main-native'},f'default_capability_permission_set_wrong:{sorted(perms)}')
    native_permission=read('desktop-shell/tauri-skeleton/src-tauri/permissions/gokdogan-main-native.toml')
    require('identifier = "gokdogan-main-native"' in native_permission,'gokdogan_native_permission_identifier_missing')
    handler_match=re.search(r'\.invoke_handler\(tauri::generate_handler!\[(.*?)\]\)',main_rs,re.S)
    require(handler_match is not None,'tauri_invoke_handler_block_missing')
    if handler_match is not None:
        registered=set(re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*,?',handler_match.group(1)))
        allowed=set(re.findall(r'^\s*"([A-Za-z_][A-Za-z0-9_]*)",?\s*$',native_permission,re.M))
        require(registered==allowed,f'gokdogan_native_permission_command_mismatch:registered={sorted(registered)}:allowed={sorted(allowed)}')
    remote_urls=((cap.get('remote') or {}).get('urls') or [])
    require(remote_urls==['http://127.0.0.1:*/*'],f'capability_remote_origin_scope_wrong:{remote_urls}')
    updater=tauri.get('plugins',{}).get('updater',{}); require(updater.get('endpoints')==[],'default_updater_endpoint_present'); require((updater.get('pubkey') or '')=='','default_updater_pubkey_present'); require(tauri.get('bundle',{}).get('createUpdaterArtifacts') is False,'default_updater_artifacts_enabled')
    require('updater:default' in build and 'process:default' in build,'signed_updater_dynamic_permissions_missing'); require('$capability.permissions = @("core:default", "gokdogan-main-native")' in build and '$capability.permissions = @("core:default", "gokdogan-main-native", "updater:default", "process:default")' in build,'native_permission_stripped_by_packager'); require('SHADOWBROKER_ENABLE_SIGNED_UPDATER' in build,'signed_updater_gate_missing')
    csp=tauri.get('app',{}).get('security',{}).get('csp',''); require("object-src 'none'" in csp,'csp_object_none_missing'); require("frame-ancestors 'none'" in csp,'csp_frame_ancestors_missing'); require('connect-src' in csp and 'https://*' not in csp,'csp_connect_too_broad'); require("script-src 'self' 'unsafe-inline'" not in csp,'csp_script_unsafe_inline_present')
    require('SB_ENABLE_EXPERIMENTAL_PRIVACY' in runtime and 'preserve_non_default: false' in runtime,'managed_experimental_privacy_not_forced_off'); require('SB_ENABLE_EXPERIMENTAL_PRIVACY' in staged,'staged_privacy_safety_check_missing')
    require('PREVIOUS_INSTALL_DIR_NAME' in runtime and 'restore_previous_and_start_managed_backend' in runtime and 'snapshot_previous_runtime' in runtime,'managed_previous_runtime_rollback_missing')
    require('--self-test' in main_rs and 'desktop-self-test.json' in main_rs and 'database_integrity' in main_rs,'desktop_cli_self_test_missing')
    require('.runtime-integrity.json' in backend_stage and 'writeRuntimeIntegrityManifest' in backend_stage and 'sha256File' in backend_stage,'runtime_integrity_manifest_generation_missing')
    require('verify_runtime_integrity' in runtime and 'RUNTIME_INTEGRITY_MANIFEST_FILE' in runtime and 'Sha256' in runtime,'runtime_integrity_rust_verifier_missing')
    require('safe_manifest_relative_path' in runtime and 'managed_backend_integrity_invalid_path' in runtime,'runtime_integrity_path_guard_missing')
    require('verify_runtime_integrity(bundled_root)' in runtime and 'verify_runtime_integrity(&install_root)' in runtime and 'verify_runtime_integrity(&previous_root)' in runtime,'runtime_integrity_not_applied_to_bundle_install_and_rollback'); require('sync_manifest_owned_data(bundled_root, &install_root)?' in runtime and 'sync_manifest_owned_data(install_root, previous_root)?' in runtime,'runtime_seed_data_persistent_merge_missing')
    require('runtime_integrity_enforced' in main_rs and 'desktop-runtime-state.json' in main_rs and 'revision: "R24"' in main_rs,'desktop_runtime_state_or_integrity_status_missing')
    require('runtime_integrity_manifest_missing' in staged and 'runtime_integrity_hash_mismatch' in staged and 'R24 staged desktop runtime OK' in staged,'staged_runtime_integrity_gate_missing')
    require('prunePythonBytecodeCaches' in backend_stage and "lower.endsWith('.pyc')" in backend_stage and "part.toLowerCase() === '__pycache__'" in backend_stage,'python_bytecode_cache_pruning_or_manifest_exclusion_missing')
    require('PYTHONDONTWRITEBYTECODE' in runtime and '.arg("-B")' in runtime,'managed_python_bytecode_suppression_missing')
    require('validate_no_python_bytecode_caches' in staged and 'post_smoke_integrity' in staged and '[str(python), "-B", str(smoke)]' in staged,'staged_runtime_post_smoke_integrity_gate_missing')
    build_ps1=read('desktop-shell/tauri-skeleton/build.ps1')
    require('@($stagedPython, "-B", $stagedRuntimeValidator' in build_ps1 and '$env:PYTHONDONTWRITEBYTECODE = "1"' in build_ps1 and 'sys.flags.dont_write_bytecode' in staged,'staged_validator_self_mutation_guard_missing')
    require('sha2 = "0.10"' in cargo,'sha2_direct_dependency_missing')
    recovery=read('scripts/windows/recover_intelligence_database.py'); verify_install=read('WINDOWS-DESKTOP-VERIFY-INSTALL.ps1'); recovery_ps=read('WINDOWS-DESKTOP-DATA-RECOVERY.ps1')
    require('restore_snapshot' in recovery and 'quick_check' in recovery and 'snapshot_hash_mismatch' in recovery,'database_recovery_helper_missing')
    require('--self-test' in verify_install and 'desktop-self-test.json' in verify_install,'installed_runtime_verifier_missing')
    require('RestoreLatest' in recovery_ps and 'recover_intelligence_database.py' in recovery_ps,'database_recovery_wrapper_missing')
    require('hybrid-local-v1' in service and 'numpy-batched' in service,'hybrid_semantic_search_missing')
    update_runtime=read('frontend/src/lib/updateRuntime.ts')
    require('recovered_previous_runtime?: boolean' in update_runtime,'frontend_runtime_rollback_status_missing')
    for dist_tool in ('WINDOWS-DESKTOP-VERIFY-INSTALL.ps1','WINDOWS-DESKTOP-VERIFY-INSTALL.bat','WINDOWS-DESKTOP-DATA-RECOVERY.ps1','WINDOWS-DESKTOP-DATA-RECOVERY.bat','WINDOWS-DESKTOP-INSTALL-AND-VERIFY.ps1','WINDOWS-DESKTOP-INSTALL-AND-VERIFY.bat'):
        require(dist_tool in builder,f'dist_recovery_tool_missing:{dist_tool}')
    require('recover_intelligence_database.py' in builder,'dist_recovery_helper_missing')
    install_verify=read('WINDOWS-DESKTOP-INSTALL-AND-VERIFY.ps1')
    require('WINDOWS-DESKTOP-VERIFY-INSTALL.ps1' in install_verify and 'msiexec.exe' in install_verify and 'INSTALL + VERIFY PASSED' in install_verify,'install_and_verify_flow_missing')
    require('install-state.json' in install_verify and 'installer_sha256' in install_verify and "revision = 'R24'" in install_verify,'installer_state_journal_missing')
    require('runtime_integrity_enforced' in verify_install and 'desktop-runtime-state.json' in verify_install and "$runtime.revision -ne 'R24'" in verify_install,'installed_runtime_integrity_verification_missing')
    maintenance_ps=read('WINDOWS-DESKTOP-DATA-MAINTENANCE.ps1')
    require("'Health','AutoRepair'" in maintenance_ps and 'install-state.json' in maintenance_ps and 'WINDOWS-DESKTOP-INSTALL-AND-VERIFY.ps1' in maintenance_ps,'desktop_health_autorepair_missing')
    require((ROOT/'WINDOWS-DESKTOP-HEALTH-CHECK.bat').exists() and (ROOT/'WINDOWS-DESKTOP-AUTO-REPAIR.bat').exists(),'desktop_health_autorepair_wrappers_missing')
    require('WINDOWS-DESKTOP-HEALTH-CHECK.bat' in builder and 'WINDOWS-DESKTOP-AUTO-REPAIR.bat' in builder,'desktop_health_autorepair_not_distributed')
    require((ROOT/'backend/tests/test_desktop_runtime_manifest_contract.py').exists(),'runtime_integrity_contract_test_missing')
    require('MESH_INFONET_FLEET_JOIN: bool = False' in backend_config,'mesh_fleet_join_not_opt_in')
    require('FLEET_PEER_PUSH_SECRET' not in fleet_defaults,'source_controlled_fleet_secret_present')
    require('MESH_INFONET_FLEET_JOIN=${MESH_INFONET_FLEET_JOIN:-false}' in compose,'compose_mesh_fleet_join_not_opt_in')
    require('MESH_PEER_PUSH_SECRET: "${MESH_PEER_PUSH_SECRET:-}"' in compose_override,'compose_override_peer_secret_not_externalized')
    require('PRIVACY_CORE_DEV_OVERRIDE: "${PRIVACY_CORE_DEV_OVERRIDE:-false}"' in compose_override,'compose_override_privacy_dev_bypass_enabled')
    require('MESH_INFONET_FLEET_JOIN="${MESH_INFONET_FLEET_JOIN:-false}"' in meshnode_sh,'meshnode_sh_fleet_join_not_opt_in')
    require('set MESH_INFONET_FLEET_JOIN=false' in meshnode_bat,'meshnode_bat_fleet_join_not_opt_in')
    required=['/observations','/observations/bbox','/confidence/calibration','/snapshots/full','/search/semantic/reindex','/search/semantic','/diagnostics/bundle','/geofences','/workspaces','/local-ai/models/pull','/local-ai/models','/integrity','/snapshots/full/{snapshot_id}/validate','/sources/quarantine','/maintenance/report','/maintenance/run']
    for ep in required: require(ep in router,f'r23_endpoint_missing:{ep}')
    for token in ['SCHEMA_VERSION = 11','CREATE VIRTUAL TABLE IF NOT EXISTS search_fts','CREATE VIRTUAL TABLE IF NOT EXISTS observation_geo','source_lineage','semantic_vectors','hash_version','create_full_snapshot','restore_full_snapshot','CREATE TABLE IF NOT EXISTS geofences','CREATE TABLE IF NOT EXISTS entity_identifiers','def _migration_10','def _migration_11','CREATE VIRTUAL TABLE IF NOT EXISTS geofence_geo','def validate_full_snapshot','def integrity_report','def prune_history(']:
        require(token in storage,f'storage_feature_missing:{token}')
    require('runtime_offline_mode' in source_health and 'source_offline_mode' in source_health,'intelligence_source_offline_gate_missing')
    require('def _runtime_offline_mode' in data_fetcher and 'if _runtime_offline_mode()' in data_fetcher,'legacy_data_fetcher_offline_gate_missing')
    require('/storage/prune' in router and 'prune_history' in router,'retention_prune_endpoint_missing')
    require('dedup_key' in service and 'watchlist' in service.lower(),'target_dedup_or_watchlist_ingest_missing'); require('source_origin' in fusion or 'source_family' in fusion,'fusion_source_independence_missing')
    require('hashed_embedding' in localai and 'cosine_similarity' in localai,'local_vector_fallback_missing'); require('validate_model_name' in localai and 'pull_model' in localai and 'delete_model' in localai,'local_ai_model_manager_missing'); require('mark_source_failure' in retry+store and 'record_success' in store,'legacy_source_health_bridge_missing')
    require('ingest_legacy_layer' in legacy_bridge and '_legacy_intel_queue' in store and 'SB_LEGACY_INTEL_BRIDGE' in store,'legacy_observation_bridge_missing')
    require('tauri = { version = "=2.11.5"' in cargo,'tauri_core_secure_pin_missing')
    require('tauri-plugin-single-instance = "=2.4.3"' in cargo,'single_instance_pin_missing'); require('tauri-plugin-notification = "=2.3.3"' in cargo,'notification_plugin_pin_missing')
    require("$cargoManifestPath = Join-Path $TauriDir 'Cargo.toml'" in builder,'cargo_manifest_path_binding_missing')
    require("if ($cargoLockNeedsRefresh)" in builder and "generate-lockfile" in builder and "Cargo.lock onarildi" in builder,'cargo_lock_self_repair_contract_missing')
    require("@('metadata','--manifest-path',$cargoManifestPath,'--locked','--format-version','1','--no-deps')" in builder,'cargo_metadata_manifest_path_missing')
    require('cargo tree --manifest-path $cargoManifestPath --locked -p shadowbroker-tauri-shell' in builder,'cargo_tree_manifest_path_missing')
    require("(Join-Path $DesktopDir 'tauri-skeleton')" not in builder[builder.find("Write-Stage 5 'Tauri CLI"):builder.find("Write-Stage 6 'Static checks")], 'stage5_cargo_parent_workdir_regression')
    require('& cargo metadata --locked --format-version 1 --no-deps' not in builder,'unsafe_direct_cargo_metadata_probe_present')
    require('$requiredCargoPackages = @(' in builder and '$cargoLockNeedsRefresh' in builder,'cargo_lock_pin_precheck_missing')
    require('cargo tauri build --bundles nsis -- --locked' in read('desktop-shell/tauri-skeleton/build.ps1'),'tauri_release_not_locked_or_not_nsis')
    require('SHADOWBROKER_WINDOWS_CERT_THUMBPRINT' in build and 'certificateThumbprint' in build,'authenticode_build_integration_missing')
    require('Get-AuthenticodeSignature' in bundle_validator and 'SHADOWBROKER_REQUIRE_WINDOWS_SIGNATURE' in bundle_validator,'bundle_signature_validation_missing')
    require('Architecture budget OK' in arch_budget and 'backend/main.py' in arch_budget,'architecture_budget_gate_missing')
    require('updater_enabled' in main_rs and 'SHADOWBROKER_TAURI_UPDATER_ENABLED' in main_rs,'updater_runtime_context_missing'); require('desktop_notify' in main_rs and 'tauri_plugin_notification::init' in main_rs,'native_notification_bridge_missing')
    require(tauri.get('app',{}).get('withGlobalTauri') is True,'tauri_global_api_required_for_native_bridge')
    require('function _nativeInvoke(command, args)' in main_rs and 'native_tauri_api_unavailable' in main_rs,'native_tauri_bridge_invoke_guard_missing')
    require('window.__TAURI__.core.invoke' not in main_rs,'unsafe_direct_tauri_core_invoke_present')
    require('sanitize_notification_text' in main_rs and '#[test]' in main_rs,'native_notification_sanitizer_tests_missing')
    require('url::Url::parse' in companion_rs and 'matches!(parsed.scheme(), "http" | "https")' in companion_rs,'loopback_url_parser_hardening_missing')
    require('useIntelligenceAlertNotifications' in alert_hook and "'critical'" in alert_hook and "'flash'" in alert_hook and "'priority'" in alert_hook,'global_alert_notification_watcher_missing')
    require('useIntelligenceAlertNotifications();' in page_tsx,'global_alert_notification_watcher_not_mounted')
    require('openIntelligenceSearch' in keyboard_hook and "key.toLowerCase() === 'k'" in keyboard_hook,'ctrl_k_intelligence_search_missing')
    require('intelligenceInitialTab' in page_tsx and "setIntelligenceInitialTab('search')" in page_tsx,'ctrl_k_search_not_wired_to_panel')
    require("'workspaces'" in intel_panel and '/api/intelligence/workspaces' in intel_panel and 'saveWorkspace' in intel_panel and 'applyWorkspace' in intel_panel,'workspace_preset_ui_missing')
    require('set_max_concurrency' in task_queue and 'effective_max_background_jobs' in router,'runtime_task_concurrency_not_live')
    require('sb-runtime-prefs-updated' in intel_panel and 'map_marker_budget' in moving_budget and 'perLayerBudget' in moving_budget,'map_marker_budget_not_enforced')
    require("'tr'" in i18n and "label: 'Türkçe'" in i18n,'turkish_locale_registry_missing')
    require('"tr": "tr"' in telegram_translate,'telegram_turkish_target_missing')
    require('next/font/google' not in layout_tsx and 'JetBrains_Mono(' not in layout_tsx,'frontend_remote_google_font_build_dependency_present')
    require('Cascadia Mono' in globals_css and 'Consolas' in globals_css,'frontend_offline_monospace_stack_missing')
    require('fonts.googleapis.com' not in tauri_conf and 'fonts.gstatic.com' not in tauri_conf,'tauri_google_fonts_network_allowance_present')
    require((ROOT/'frontend/src/i18n/translations/tr.json').exists(),'turkish_translation_bundle_missing')
    require('CREATE TABLE IF NOT EXISTS source_quarantine' in storage,'source_quarantine_table_missing')
    require('CREATE TABLE IF NOT EXISTS maintenance_runs' in storage,'maintenance_runs_table_missing')
    require('def quarantine_source' in storage and 'def clear_source_quarantine' in storage,'source_quarantine_storage_api_missing')
    require('def run_database_maintenance' in storage,'database_maintenance_runner_missing')
    require('def maintenance_report' in service and 'health_score' in service,'maintenance_health_report_missing')
    require('source_quarantined:' in source_health and 'list_source_quarantine' in source_health,'source_quarantine_runtime_gate_missing')
    require('adapter_normalization_contract_failed' in router and 'schema-drift' in router,'adapter_schema_drift_quarantine_missing')
    require('/api/intelligence/maintenance/report' in intel_panel and 'ARAMAYI YENİDEN KUR + İYİLEŞTİR' in intel_panel,'maintenance_ui_missing')
    require((('QUARANTINE' in intel_panel and 'RELEASE' in intel_panel) or ('KARANTİNA' in intel_panel and 'SERBEST BIRAK' in intel_panel)),'source_quarantine_ui_missing')
    require((ROOT/'backend/tests/test_intelligence_core_r9.py').exists(),'r9_regression_tests_missing')
    routes,dups=route_scan(); py=compile_python(); NOTES.extend([f'routes={routes}',f'duplicate_routes={dups}',f'python_files_compiled={py}'])
    if FAILURES:
        print('R24 release validation FAILED'); [print(' - '+x) for x in FAILURES]; [print(' * '+x) for x in NOTES]; return 1
    print('R24 release validation OK'); [print(' - '+x) for x in NOTES]; return 0
if __name__=='__main__': raise SystemExit(main())
