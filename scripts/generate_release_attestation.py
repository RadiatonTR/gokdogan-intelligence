#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "backend" / "data" / "release_attestation.json"


def sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def _git_commit() -> str | None:
    explicit = (os.environ.get("GOKDOGAN_SOURCE_COMMIT") or os.environ.get("SB_GIT_COMMIT") or "").strip()
    if explicit:
        return explicit
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False, timeout=5)
        value = result.stdout.strip()
        if result.returncode == 0 and value:
            return value
    except Exception:
        pass
    return None


_TREE_EXCLUDED_DIRS = {
    ".git", ".pytest_cache", "__pycache__", "node_modules", "target", "dist",
    ".venv", "venv", ".next", "coverage",
}
_TREE_EXCLUDED_FILES = {
    "backend/data/release_attestation.json",
    "windows-desktop-build.log",
    "GOKDOGAN-DIAGNOSTIC.zip",
}


def _source_tree_fingerprint() -> tuple[str, int]:
    """Hash the immutable release tree without transient/runtime artifacts.

    The digest covers path + per-file SHA-256 for every release file, not only
    lockfiles. The attestation itself is excluded to avoid a circular digest.
    """
    h = hashlib.sha256()
    count = 0
    paths = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        parts = set(path.relative_to(ROOT).parts)
        if parts & _TREE_EXCLUDED_DIRS:
            continue
        if rel in _TREE_EXCLUDED_FILES or rel.endswith((".pyc", ".pyo")):
            continue
        paths.append((rel, path))
    for rel, path in sorted(paths, key=lambda item: item[0]):
        digest = sha256(path)
        if not digest:
            continue
        h.update(f"{rel}={digest}\n".encode("utf-8"))
        count += 1
    return h.hexdigest(), count


def main() -> int:
    tauri = read_json(ROOT / "desktop-shell" / "tauri-skeleton" / "src-tauri" / "tauri.conf.json")
    impl = read_json(ROOT / "R24-IMPLEMENTATION-MANIFEST.json")
    release = read_json(ROOT / "release-version.json")
    revision = (ROOT / "WINDOWS-DESKTOP-BUILD-REVISION.txt").read_text(encoding="utf-8").strip()
    inputs = []
    for rel in [
        "uv.lock",
        "frontend/package-lock.json",
        "desktop-shell/package-lock.json",
        "desktop-shell/tauri-skeleton/src-tauri/Cargo.lock",
        "R24-IMPLEMENTATION-MANIFEST.json",
        "SBOM-R24.cdx.json",
        "release-version.json",
        ".node-version",
    ]:
        digest = sha256(ROOT / rel)
        if digest:
            inputs.append({"path": rel, "sha256": digest})
    git_commit = _git_commit()
    tree_fingerprint, source_file_count = _source_tree_fingerprint()
    payload = {
        "schema": "gokdogan.release-attestation.v2",
        "product": release.get("product") or tauri.get("productName", "Gökdoğan Intelligence Desktop"),
        "distribution": release.get("distribution", "Gökdoğan Intelligence 1.0.0"),
        "version": tauri.get("version", "0.0.0"),
        "revision": revision,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "git_commit": git_commit,
        "git_commit_status": "available" if git_commit else "unavailable-source-archive",
        "source_tree_fingerprint": tree_fingerprint,
        "source_file_count": source_file_count,
        "default_language": release.get("default_language", "tr"),
        "release_profile": release.get("release_profile", "public-authorized-osint"),
        "safety_defaults": impl.get("safety_defaults", {}),
        "safety_boundaries": release.get("safety_boundaries", {}),
        "source_inputs": inputs,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Release attestation: {OUT.relative_to(ROOT)} ({source_file_count} source files; {len(inputs)} pinned inputs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
