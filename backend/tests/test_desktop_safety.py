from services import desktop_safety


def test_high_privilege_desktop_features_default_off(monkeypatch):
    monkeypatch.delenv("SB_ALLOW_ACTIVE_RECON", raising=False)
    monkeypatch.delenv("SB_ALLOW_AGENT_SHELL", raising=False)
    assert desktop_safety.active_recon_allowed() is False
    assert desktop_safety.agent_shell_allowed() is False


def test_high_privilege_desktop_features_require_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("SB_ALLOW_ACTIVE_RECON", "true")
    monkeypatch.setenv("SB_ALLOW_AGENT_SHELL", "1")
    assert desktop_safety.active_recon_allowed() is True
    assert desktop_safety.agent_shell_allowed() is True


def test_desktop_managed_runtime_marker(monkeypatch):
    monkeypatch.setenv("SB_DESKTOP_MANAGED_RUNTIME", "yes")
    status = desktop_safety.desktop_safety_status()
    assert status["managed_runtime"] is True
