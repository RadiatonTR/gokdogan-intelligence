#!/usr/bin/env python3
from __future__ import annotations

import sys

# Refuse to run before importing any non-builtin modules unless the launcher
# has disabled bytecode writes. This prevents the validator itself from
# recreating __pycache__ inside the staged runtime it is validating.
if __name__ == "__main__" and not sys.flags.dont_write_bytecode:
    raise SystemExit("staged_runtime_validation_failed:validator_bytecode_write_not_disabled")

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"staged_runtime_validation_failed:{message}")



def validate_integrity_manifest(runtime: Path) -> dict:
    manifest_path = runtime / ".runtime-integrity.json"
    if not manifest_path.exists():
        fail("runtime_integrity_manifest_missing")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"runtime_integrity_manifest_invalid:{exc}")
    if manifest.get("manifest_version") != 1 or str(manifest.get("algorithm", "")).lower() != "sha256":
        fail("runtime_integrity_manifest_unsupported")
    files = manifest.get("files")
    if not isinstance(files, list) or manifest.get("file_count") != len(files):
        fail("runtime_integrity_file_count_mismatch")
    bundle_version = (runtime / ".bundle-version").read_text(encoding="utf-8").strip()
    if str(manifest.get("bundle_version", "")).strip() != bundle_version:
        fail("runtime_integrity_bundle_version_mismatch")
    for item in files:
        rel = str(item.get("path") or "")
        candidate_rel = Path(rel)
        if not rel or candidate_rel.is_absolute() or ".." in candidate_rel.parts or rel == ".runtime-integrity.json":
            fail(f"runtime_integrity_invalid_path:{rel}")
        full = (runtime / candidate_rel).resolve()
        try:
            full.relative_to(runtime)
        except ValueError:
            fail(f"runtime_integrity_path_escape:{rel}")
        if not full.is_file():
            fail(f"runtime_integrity_missing_file:{rel}")
        if full.stat().st_size != int(item.get("size", -1)):
            fail(f"runtime_integrity_size_mismatch:{rel}")
        digest = hashlib.sha256()
        with full.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest().lower() != str(item.get("sha256") or "").lower():
            fail(f"runtime_integrity_hash_mismatch:{rel}")
    return {"file_count": len(files), "bundle_version": bundle_version}


def validate_no_python_bytecode_caches(runtime: Path) -> None:
    python_root = runtime / "python-runtime"
    offenders: list[str] = []
    if not python_root.exists():
        return
    for candidate in python_root.rglob("*"):
        lower = candidate.name.lower()
        if (candidate.is_dir() and lower == "__pycache__") or (
            candidate.is_file() and (lower.endswith(".pyc") or lower.endswith(".pyo"))
        ):
            offenders.append(candidate.relative_to(runtime).as_posix())
            if len(offenders) >= 20:
                break
    if offenders:
        fail("python_bytecode_cache_present:" + ",".join(offenders))


def validate_no_packaged_python_test_trees(runtime: Path) -> None:
    python_root = runtime / "python-runtime"
    offenders: list[str] = []
    for site_packages in python_root.rglob("site-packages"):
        if not site_packages.is_dir():
            continue
        for candidate in site_packages.rglob("*"):
            if candidate.is_dir() and candidate.name.lower() in {"test", "tests"}:
                offenders.append(candidate.relative_to(runtime).as_posix())
                if len(offenders) >= 20:
                    break
        if len(offenders) >= 20:
            break
    if offenders:
        fail("python_test_only_tree_present:" + ",".join(offenders))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True)
    args = parser.parse_args()
    runtime = Path(args.runtime).resolve()
    if not (runtime / "main.py").exists():
        fail("main_py_missing")
    integrity = validate_integrity_manifest(runtime)
    validate_no_packaged_python_test_trees(runtime)
    validate_no_python_bytecode_caches(runtime)

    python = runtime / "python-runtime" / ("python.exe" if os.name == "nt" else "bin/python3")
    node = runtime / "node-runtime" / ("node.exe" if os.name == "nt" else "node")
    if not python.exists():
        fail(f"python_missing:{python}")
    if not node.exists():
        fail(f"node_missing:{node}")

    smoke_source = f'''\nimport json, os, sys\nfrom pathlib import Path\nruntime = Path({str(runtime)!r}).resolve()\nsys.path.insert(0, str(runtime))\nos.environ.setdefault("ADMIN_KEY", "r21-smoke-admin-key-0123456789abcdef0123456789abcdef")\nos.environ.setdefault("MESH_PEER_PUSH_SECRET", "r21-smoke-peer-secret-0123456789abcdef")\nos.environ.setdefault("MESH_DM_TOKEN_PEPPER", "r21-smoke-dm-secret-0123456789abcdef")\nos.environ["SB_DESKTOP_MANAGED_RUNTIME"] = "true"\nos.environ["SB_DESKTOP_SAFE_MODE"] = "true"\nos.environ["SB_ALLOW_ACTIVE_RECON"] = "false"\nos.environ["SB_ALLOW_AGENT_SHELL"] = "false"\nos.environ["SB_ENABLE_EXPERIMENTAL_PRIVACY"] = "false"\nimport fastapi, uvicorn, cryptography, numpy, orjson, playwright, pandas, scipy, yfinance, reverse_geocoder\nimport main\nfrom services.intelligence_core.storage import IntelligenceStore\nimport tempfile\nroutes = {{getattr(route, "path", "") for route in main.app.routes}}\nrequired = {{"/api/health", "/api/intelligence/status"}}\nmissing = sorted(required - routes)\nif missing:\n    raise SystemExit("missing_routes:" + ",".join(missing))\nsite_root = (runtime / "python-runtime").resolve()\nmodule_paths = {{}}\nfor module in (fastapi, uvicorn, cryptography, numpy, orjson, playwright, pandas, scipy, yfinance, reverse_geocoder):\n    module_path = Path(module.__file__).resolve()\n    module_paths[module.__name__] = str(module_path)\n    if site_root not in module_path.parents:\n        raise SystemExit(f"module_outside_bundled_runtime:{{module.__name__}}:{{module_path}}")\nprobe = numpy.array([1, 2, 3], dtype=numpy.int64).astype(numpy.float64)\nif probe.tolist() != [1.0, 2.0, 3.0]:\n    raise SystemExit("numpy_runtime_probe_failed")\nframe = pandas.DataFrame({{"value": [1, 2]}})\nif int(frame["value"].sum()) != 3:\n    raise SystemExit("pandas_runtime_probe_failed")\nif not getattr(scipy, "__version__", ""):\n    raise SystemExit("scipy_runtime_probe_failed")\nif not callable(getattr(yfinance, "Ticker", None)):\n    raise SystemExit("yfinance_runtime_probe_failed")\nwith tempfile.TemporaryDirectory(prefix="gokdogan-intel-smoke-") as td:\n    store = IntelligenceStore(Path(td) / "intelligence-core.db")\n    integrity_report = store.integrity_report()\n    if not integrity_report.get("ok"):\n        raise SystemExit("intelligence_store_integrity_failed:" + json.dumps(integrity_report, sort_keys=True))\nprint(json.dumps({{"ok": True, "route_count": len(routes), "module_paths": module_paths, "intelligence_store": integrity_report}}, sort_keys=True))\n'''
    with tempfile.TemporaryDirectory(prefix="sb-r21-smoke-") as td:
        smoke = Path(td) / "smoke.py"
        smoke.write_text(smoke_source, encoding="utf-8")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(runtime)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run(
            [str(python), "-B", str(smoke)],
            cwd=runtime,
            env=env,
            text=True,
            capture_output=True,
            timeout=90,
        )
        if result.returncode != 0:
            fail(f"python_smoke:{result.stderr.strip() or result.stdout.strip()}")
        try:
            payload = json.loads(result.stdout.strip().splitlines()[-1])
        except Exception as exc:
            fail(f"python_smoke_output:{exc}:{result.stdout[-1000:]}")

    # The smoke probe must not mutate any integrity-managed file. Re-validate
    # after importing the full production runtime so packaging cannot silently
    # ship a tree different from the manifest that was checked above.
    post_smoke_integrity = validate_integrity_manifest(runtime)
    validate_no_python_bytecode_caches(runtime)

    node_result = subprocess.run([str(node), "--version"], text=True, capture_output=True, timeout=20)
    if node_result.returncode != 0:
        fail(f"node_smoke:{node_result.stderr.strip()}")

    print("R24 staged desktop runtime OK")
    print(f" - integrity_files={integrity.get('file_count')}")
    print(f" - bundle_version={integrity.get('bundle_version')}")
    print(f" - routes={payload.get('route_count')}")
    print(f" - node={node_result.stdout.strip()}")
    print(f" - safe_mode=true")
    print(" - python_test_only_trees=0")
    print(" - python_bytecode_caches=0")
    print(f" - post_smoke_integrity={post_smoke_integrity.get('file_count') == integrity.get('file_count')}")
    print(f" - intelligence_store_ok={bool(payload.get('intelligence_store', {}).get('ok'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
