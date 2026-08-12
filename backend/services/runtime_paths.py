"""Per-user runtime storage paths for Gökdoğan.

Release/source trees are treated as immutable. Runtime databases, generated
operator identity and local secrets must live in a writable user-data directory
unless an operator explicitly sets ``SB_DATA_DIR``.
"""
from __future__ import annotations

import os
from pathlib import Path


def runtime_data_dir() -> Path:
    """Return the writable runtime data directory without touching source data."""
    override = os.environ.get("SB_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return (Path(base) / "GokdoganIntelligence" / "data").resolve()

    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg:
        return (Path(xdg).expanduser() / "gokdogan-intelligence").resolve()

    return (Path.home() / ".local" / "share" / "gokdogan-intelligence").resolve()
