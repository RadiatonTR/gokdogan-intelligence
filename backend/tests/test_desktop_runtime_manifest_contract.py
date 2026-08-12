from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "validate_staged_desktop_runtime.py"
spec = importlib.util.spec_from_file_location("validate_staged_desktop_runtime", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_manifest(root: Path, *, override_path: str | None = None) -> None:
    main = root / "main.py"
    bundle = root / ".bundle-version"
    files = [
        {"path": override_path or "main.py", "size": main.stat().st_size, "sha256": _sha(main)},
        {"path": ".bundle-version", "size": bundle.stat().st_size, "sha256": _sha(bundle)},
    ]
    manifest = {
        "manifest_version": 1,
        "algorithm": "sha256",
        "bundle_version": bundle.read_text(encoding="utf-8").strip(),
        "file_count": len(files),
        "files": files,
    }
    (root / ".runtime-integrity.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_staged_runtime_integrity_manifest_accepts_valid_tree(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / ".bundle-version").write_text("0.9.97\n", encoding="utf-8")
    _write_manifest(tmp_path)
    result = module.validate_integrity_manifest(tmp_path.resolve())
    assert result["bundle_version"] == "0.9.97"
    assert result["file_count"] == 2


def test_staged_runtime_integrity_manifest_detects_tampering(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / ".bundle-version").write_text("0.9.97\n", encoding="utf-8")
    _write_manifest(tmp_path)
    (tmp_path / "main.py").write_text("print('tampered')\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="runtime_integrity_(size|hash)_mismatch"):
        module.validate_integrity_manifest(tmp_path.resolve())


def test_staged_runtime_integrity_manifest_rejects_path_traversal(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / ".bundle-version").write_text("0.9.97\n", encoding="utf-8")
    _write_manifest(tmp_path, override_path="../main.py")
    with pytest.raises(SystemExit, match="runtime_integrity_invalid_path"):
        module.validate_integrity_manifest(tmp_path.resolve())


def test_staged_runtime_rejects_python_bytecode_caches(tmp_path: Path) -> None:
    cache = tmp_path / "python-runtime" / "Lib" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "tarfile.cpython-312.pyc").write_bytes(b"mutable-bytecode")
    with pytest.raises(SystemExit, match="python_bytecode_cache_present"):
        module.validate_no_python_bytecode_caches(tmp_path.resolve())


def test_staged_runtime_accepts_python_tree_without_bytecode_caches(tmp_path: Path) -> None:
    lib = tmp_path / "python-runtime" / "Lib"
    lib.mkdir(parents=True)
    (lib / "tarfile.py").write_text("# source remains integrity-managed\n", encoding="utf-8")
    module.validate_no_python_bytecode_caches(tmp_path.resolve())
