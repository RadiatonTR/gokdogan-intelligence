"""Runtime safety gates for local desktop-only high-privilege features.

The Windows desktop package is intended to be useful as an intelligence/OSINT
workstation without silently enabling host-shell or active discovery features.
Those capabilities remain available to an operator who deliberately opts in,
but the managed desktop backend seeds them to disabled.
"""
from __future__ import annotations

import os

_TRUE = {"1", "true", "yes", "on", "enabled"}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in _TRUE


def desktop_managed_runtime() -> bool:
    return _env_bool("SB_DESKTOP_MANAGED_RUNTIME", False)


def active_recon_allowed() -> bool:
    """Whether active subnet discovery may be invoked.

    Passive IP/DNS/WHOIS/CVE/Shodan metadata lookups are not affected by this
    gate. Only the subnet sweep execution path is gated.
    """
    return _env_bool("SB_ALLOW_ACTIVE_RECON", False)


def agent_shell_allowed() -> bool:
    """Whether the local host-shell WebSocket/API is enabled."""
    return _env_bool("SB_ALLOW_AGENT_SHELL", False)


def desktop_safety_status() -> dict[str, bool]:
    return {
        "managed_runtime": desktop_managed_runtime(),
        "active_recon_enabled": active_recon_allowed(),
        "agent_shell_enabled": agent_shell_allowed(),
    }
