import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN_RS = ROOT / "desktop-shell" / "tauri-skeleton" / "src-tauri" / "src" / "main.rs"
WINDOWS_BUILDER = ROOT / "WINDOWS-DESKTOP-ONE-CLICK.ps1"


def test_async_tauri_state_commands_return_result():
    source = MAIN_RS.read_text(encoding="utf-8")
    # Tauri 2.x async commands borrowing tauri::State must return Result<...>.
    blocks = re.findall(
        r"#\[tauri::command\]\s*async\s+fn\s+(\w+)\s*\((.*?)\)\s*->\s*([^\{]+)\{",
        source,
        flags=re.S,
    )
    state_commands = [(name, ret.strip()) for name, args, ret in blocks if "tauri::State<'_" in args]
    assert state_commands, "No async Tauri State command found; contract test is stale."
    offenders = [(name, ret) for name, ret in state_commands if not ret.startswith("Result<")]
    assert not offenders, f"Async Tauri State commands must return Result: {offenders}"
    assert ("desktop_backend_status", "Result<DesktopBackendStatus, String>") in state_commands
    assert ("desktop_self_test", "Result<DesktopSelfTestResult, String>") in state_commands


def test_hf15_contract_is_part_of_windows_release_gate():
    source = WINDOWS_BUILDER.read_text(encoding="utf-8-sig")
    assert "backend\\tests\\test_gokdogan_hf15_tauri_async_command_contract.py" in source
