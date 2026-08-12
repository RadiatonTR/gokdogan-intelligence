#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def quick_check(db_path: Path) -> dict:
    if not db_path.exists():
        return {"ok": False, "error": "database_missing", "path": str(db_path)}
    try:
        con = sqlite3.connect(db_path, timeout=10)
        try:
            quick = [str(r[0]) for r in con.execute("PRAGMA quick_check").fetchall()]
            row = con.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
            schema = int(row[0]) if row else 0
        finally:
            con.close()
        return {
            "ok": quick == ["ok"],
            "path": str(db_path),
            "schema_version": schema,
            "quick_check": quick[:20],
            "size_bytes": db_path.stat().st_size,
        }
    except Exception as exc:
        return {"ok": False, "path": str(db_path), "error": f"sqlite_check_failed:{type(exc).__name__}"}


def valid_snapshot(manifest: Path) -> dict:
    try:
        meta = json.loads(manifest.read_text(encoding="utf-8"))
        db_path = manifest.parent / str(meta.get("database_file") or "")
        if not db_path.exists():
            return {"ok": False, "manifest": str(manifest), "error": "snapshot_database_missing"}
        actual = sha256_file(db_path)
        if actual != meta.get("database_sha256"):
            return {"ok": False, "manifest": str(manifest), "error": "snapshot_hash_mismatch"}
        check = quick_check(db_path)
        return {"ok": bool(check.get("ok")), "manifest": str(manifest), "database": str(db_path), "meta": meta, "check": check}
    except Exception as exc:
        return {"ok": False, "manifest": str(manifest), "error": f"snapshot_validation_failed:{type(exc).__name__}"}


def list_valid_snapshots(data_dir: Path) -> list[dict]:
    snap_dir = data_dir / "intelligence-snapshots"
    if not snap_dir.exists():
        return []
    results = []
    for manifest in sorted(snap_dir.glob("snapshot-*.json"), reverse=True):
        result = valid_snapshot(manifest)
        if result.get("ok"):
            results.append(result)
    return results


def safety_backup(db_path: Path, data_dir: Path) -> Path:
    recovery = data_dir / "recovery-backups"
    recovery.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = recovery / f"intelligence-core-pre-recovery-{stamp}.sqlite"
    if db_path.exists():
        src = sqlite3.connect(db_path, timeout=10)
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
    return target


def restore_snapshot(db_path: Path, snapshot_db: Path, data_dir: Path) -> dict:
    backup = safety_backup(db_path, data_dir)
    tmp = db_path.with_suffix(".restore.tmp")
    if tmp.exists():
        tmp.unlink()
    src = sqlite3.connect(snapshot_db, timeout=10)
    dst = sqlite3.connect(tmp)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    restored_check = quick_check(tmp)
    if not restored_check.get("ok"):
        tmp.unlink(missing_ok=True)
        raise RuntimeError("restored_snapshot_quick_check_failed")
    # Remove stale WAL/SHM before atomic database-file replacement.
    for suffix in ("-wal", "-shm"):
        Path(str(db_path) + suffix).unlink(missing_ok=True)
    tmp.replace(db_path)
    return {"ok": True, "restored_from": str(snapshot_db), "safety_backup": str(backup), "check": quick_check(db_path)}


def main() -> int:
    ap = argparse.ArgumentParser(description="ShadowBroker Intelligence Core database recovery helper")
    ap.add_argument("--data-dir", required=True, type=Path)
    ap.add_argument("--action", choices=["check", "restore-latest"], default="check")
    ap.add_argument("--json-output", type=Path)
    args = ap.parse_args()
    data_dir = args.data_dir.resolve()
    db_path = data_dir / "intelligence-core.db"
    report = {"action": args.action, "data_dir": str(data_dir), "database": quick_check(db_path)}
    snapshots = list_valid_snapshots(data_dir)
    report["valid_snapshots"] = [
        {"id": x.get("meta", {}).get("id"), "created_at": x.get("meta", {}).get("created_at"), "database": x.get("database")}
        for x in snapshots[:20]
    ]
    if args.action == "restore-latest":
        if not snapshots:
            report["ok"] = False
            report["error"] = "no_valid_snapshots"
        else:
            try:
                report["restore"] = restore_snapshot(db_path, Path(snapshots[0]["database"]), data_dir)
                report["ok"] = True
            except Exception as exc:
                report["ok"] = False
                report["error"] = f"restore_failed:{type(exc).__name__}"
    else:
        report["ok"] = bool(report["database"].get("ok"))
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
