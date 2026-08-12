from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_r47_removes_experimental_visual_console_everywhere():
    assert not list(ROOT.glob('GOKDOGAN-*-KONSOLU.bat'))
    assert not list(ROOT.glob('GOKDOGAN-*-KONSOLU.ps1'))
    main = (ROOT / 'desktop-shell/tauri-skeleton/src-tauri/src/main.rs').read_text(encoding='utf-8')
    install = (ROOT / 'WINDOWS-DESKTOP-INSTALL-AND-VERIFY.ps1').read_text(encoding='utf-8-sig')
    usb = (ROOT / 'GOKDOGAN-USB-KUR.ps1').read_text(encoding='utf-8-sig')
    assert 'CREATE_NEW_CONSOLE' not in main


def test_r47_frontend_has_no_custom_hud_color_switcher():
    theme = (ROOT / 'frontend/src/lib/ThemeContext.tsx').read_text(encoding='utf-8')
    panel = (ROOT / 'frontend/src/components/WorldviewLeftPanel.tsx').read_text(encoding='utf-8')
    assert 'cycleHudColor' not in theme
    assert 'hudColor' not in theme
    assert 'cycleHudColor' not in panel


def test_r47_stops_only_gokdogan_owned_stale_runtime_processes_before_verify():
    verify = (ROOT / 'WINDOWS-DESKTOP-VERIFY-INSTALL.ps1').read_text(encoding='utf-8-sig')
    assert 'function Stop-StaleGokdoganProcesses' in verify
    assert "Join-Path $stateDir 'managed-backend'" in verify
    assert 'Get-CimInstance Win32_Process' in verify
    assert 'Stop-Process -Id $pidValue -Force' in verify
    assert 'Stop-StaleGokdoganProcesses' in verify


def test_r47_runtime_clear_is_lock_tolerant_and_preserves_user_state():
    source = (ROOT / 'desktop-shell/tauri-skeleton/src-tauri/src/backend_runtime.rs').read_text(encoding='utf-8')
    assert 'best_effort_stop_stale_managed_backend_processes' in source
    assert 'remove_dir_all_with_retry' in source
    assert 'remove_file_with_retry' in source
    assert 'clear_readonly_attributes' in source
    assert 'PERSISTENT_NAMES: &[&str] = &[".env", "data"]' in source
    assert 'managed_backend_clear_dir_failed:{}' in source


def test_r47_backend_logs_are_fresh_for_each_runtime_start():
    source = (ROOT / 'desktop-shell/tauri-skeleton/src-tauri/src/backend_runtime.rs').read_text(encoding='utf-8')
    runtime_log_block = source[source.index('let stdout_log'):source.index('let mut command')]
    assert runtime_log_block.count('.truncate(true)') == 2
    assert '.append(true)' not in runtime_log_block


def test_r47_release_identity_is_current():
    release = (ROOT / 'release-version.json').read_text(encoding='utf-8')
    start = (ROOT / 'START-HERE.bat').read_text(encoding='utf-8-sig')
    one_click = (ROOT / 'WINDOWS-DESKTOP-ONE-CLICK.ps1').read_text(encoding='utf-8-sig')
    assert '"package_revision": "1.0.0"' in release
    assert 'GOKDOGAN INTELLIGENCE v1.0.0' in start
    assert 'Gokdogan-Intelligence-v1.0.0-OFFLINE-USB.zip' in one_click
