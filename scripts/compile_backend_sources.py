#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
EXCLUDED_DIRS = {
    ".desktop-python", ".desktop-browsers", "node_modules", ".next", "target",
    "dist", "build", "build-reports", "__pycache__", ".pytest_cache", ".git",
    ".venv", "venv", "backend-runtime", "python-runtime", "site-packages",
}


def is_generated_path(path: Path) -> bool:
    """Return true for build/runtime trees that are not repository sources."""
    return any(part.casefold() in EXCLUDED_DIRS for part in path.parts)

def main() -> int:
    compiled = 0
    failures: list[str] = []
    for path in sorted(BACKEND.rglob("*.py")):
        rel = path.relative_to(BACKEND)
        if is_generated_path(rel):
            continue
        try:
            source = path.read_text(encoding="utf-8-sig")
            compile(source, str(path), "exec", dont_inherit=True)
            compiled += 1
        except Exception as exc:
            failures.append(f"{path.relative_to(ROOT)}: {exc}")
    if failures:
        print("Backend source compile FAILED")
        for item in failures:
            print(f" - {item}")
        return 1
    print(f"Backend source compile OK; files={compiled}; generated_runtime_excluded=true")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
