from __future__ import annotations

import os
import platform
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any


def diagnostics_snapshot(store) -> dict[str, Any]:
    data_dir = Path(os.environ.get("SB_DATA_DIR") or store.db_path.parent)
    disk = shutil.disk_usage(data_dir if data_dir.exists() else Path.cwd())
    return {
        "runtime": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "desktop_managed": os.environ.get("SB_DESKTOP_MANAGED_RUNTIME", "").lower() in {"1", "true", "yes"},
            "safe_mode": os.environ.get("SB_DESKTOP_SAFE_MODE", "").lower() in {"1", "true", "yes", "on"},
            "node_bin": bool(os.environ.get("SB_NODE_BIN")),
            "playwright_browsers": bool(os.environ.get("PLAYWRIGHT_BROWSERS_PATH")),
        },
        "database": {
            **store.schema_info(),
            "exists": store.db_path.exists(),
            "size_bytes": store.db_path.stat().st_size if store.db_path.exists() else 0,
            "sqlite_version": sqlite3.sqlite_version,
        },
        "storage": {"data_dir": str(data_dir), "free_bytes": disk.free, "total_bytes": disk.total},
        "safety": {
            "active_recon_enabled": os.environ.get("SB_ALLOW_ACTIVE_RECON", "").lower() in {"1", "true", "yes"},
            "host_shell_enabled": os.environ.get("SB_ALLOW_AGENT_SHELL", "").lower() in {"1", "true", "yes"},
        },
    }
