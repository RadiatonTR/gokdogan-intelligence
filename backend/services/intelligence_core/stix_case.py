from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _id(kind: str, seed: str | None = None) -> str:
    if seed:
        namespace = uuid.UUID("d8aa911f-8e1e-4cb0-8fb0-03eddb8abf71")
        return f"{kind}--{uuid.uuid5(namespace, seed)}"
    return f"{kind}--{uuid.uuid4()}"


def case_to_stix(case: dict[str, Any]) -> dict[str, Any]:
    """Represent a local investigation case as portable STIX 2.1 objects.

    This intentionally uses standard Identity/Note/Report objects so bundles can
    be imported by OpenCTI and other STIX-aware tooling without custom schema.
    """
    created = str(case.get("created_at") or _now()).replace("+00:00", "Z")
    modified = str(case.get("updated_at") or created).replace("+00:00", "Z")
    producer_id = _id("identity", "shadowbroker-intelligence-desktop")
    objects: list[dict[str, Any]] = [
        {
            "type": "identity",
            "spec_version": "2.1",
            "id": producer_id,
            "created": created,
            "modified": modified,
            "name": "Gokdogan Intelligence Desktop",
            "identity_class": "system",
            "description": "Local analyst workstation export identity.",
        }
    ]
    note_refs: list[str] = []
    for ev in list(case.get("evidence") or []):
        ev_id = _id("note", f"{case.get('id')}:{ev.get('id')}:{ev.get('sha256')}")
        note_refs.append(ev_id)
        refs = []
        if ev.get("source_uri"):
            refs.append({"source_name": "source", "url": str(ev.get("source_uri"))[:2000]})
        refs.append({"source_name": "sha256", "external_id": str(ev.get("sha256") or "")})
        objects.append(
            {
                "type": "note",
                "spec_version": "2.1",
                "id": ev_id,
                "created": str(ev.get("captured_at") or created).replace("+00:00", "Z"),
                "modified": str(ev.get("captured_at") or created).replace("+00:00", "Z"),
                "created_by_ref": producer_id,
                "abstract": str(ev.get("title") or "Evidence")[:200],
                "content": str(ev.get("content_text") or ev.get("title") or "Captured evidence"),
                "object_refs": [producer_id],
                "external_references": refs,
            }
        )

    report_id = _id("report", str(case.get("id") or case.get("title")))
    report_refs = [producer_id, *note_refs]
    objects.append(
        {
            "type": "report",
            "spec_version": "2.1",
            "id": report_id,
            "created": created,
            "modified": modified,
            "created_by_ref": producer_id,
            "name": str(case.get("title") or "Intelligence Case")[:300],
            "description": str(case.get("description") or ""),
            "published": modified,
            "report_types": ["threat-report"],
            "labels": ["shadowbroker-case", str(case.get("case_type") or "investigation"), str(case.get("priority") or "normal")],
            "object_refs": report_refs,
            "external_references": [{"source_name": "shadowbroker-case", "external_id": str(case.get("id") or "")}],
        }
    )
    digest = hashlib.sha256(str(case).encode("utf-8", errors="ignore")).hexdigest()
    return {
        "type": "bundle",
        "id": _id("bundle"),
        "objects": objects,
        "x_shadowbroker_export": {"case_id": case.get("id"), "generated_at": _now(), "content_sha256": digest},
    }
