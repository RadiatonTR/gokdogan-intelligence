#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "backend" / "data"

FORBIDDEN_RELATIVE = {
    "secure_storage_secret.key",
    "operator_handle.json",
    "gates/gates.json",
    "_domain_keys/gates.key",
    "cctv.db",
    "intelligence-core.db",
}
FORBIDDEN_SUFFIXES = {".key", ".pem", ".p12", ".pfx"}
FORBIDDEN_WATCHLISTS = {
    "plane_alert_db.json",
    "tracked_names.json",
    "yacht_alert_db.json",
    "plan_ccg_vessels.json",
}


def main() -> int:
    findings: list[str] = []
    if DATA.exists():
        for path in DATA.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(DATA).as_posix()
            if rel in FORBIDDEN_RELATIVE or path.suffix.lower() in FORBIDDEN_SUFFIXES:
                findings.append(f"runtime-state/secret: backend/data/{rel}")
            if rel in FORBIDDEN_WATCHLISTS:
                findings.append(f"targeted-default-watchlist: backend/data/{rel}")
    version_path = ROOT / "release-version.json"
    if not version_path.exists():
        findings.append("missing: release-version.json")
    else:
        try:
            payload = json.loads(version_path.read_text(encoding="utf-8-sig"))
            if payload.get("default_language") != "tr":
                findings.append("release-version.json: default_language must be tr")
        except Exception as exc:
            findings.append(f"release-version.json invalid: {type(exc).__name__}")
    if findings:
        print("Gökdoğan release-cleanliness FAILED")
        for item in findings:
            print(f" - {item}")
        return 1
    print("Gökdoğan release-cleanliness OK: sır/günlük durum/hedefli varsayılan izleme listesi yok.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
