from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from .confidence import score_confidence


def _time(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _loc(item: dict[str, Any]) -> tuple[float, float] | None:
    location = item.get("location") if isinstance(item.get("location"), dict) else item
    lat = location.get("lat", location.get("latitude"))
    lon = location.get("lon", location.get("lng", location.get("longitude")))
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180):
        return None
    return lat_f, lon_f


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.atan2(math.sqrt(h), math.sqrt(max(0.0, 1 - h)))


def _severity_rank(value: str) -> int:
    return {"info": 0, "watch": 1, "priority": 2, "flash": 3, "critical": 4}.get(str(value).lower(), 1)


def fuse_observations(
    observations: list[dict[str, Any]],
    *,
    radius_km: float = 75.0,
    window_minutes: int = 90,
    min_observations: int = 2,
) -> list[dict[str, Any]]:
    """Cluster passive observations into candidate incidents.

    A cluster is built when records are close in time and, when both have
    coordinates, close in space. Records without coordinates can still cluster
    via shared entity IDs. No predictive or active collection is performed.
    """
    clean: list[dict[str, Any]] = []
    for idx, raw in enumerate(observations[:10_000]):
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        item.setdefault("id", f"obs-{idx}")
        item["_ts"] = _time(item.get("observed_at") or item.get("timestamp") or item.get("time"))
        item["_loc"] = _loc(item)
        clean.append(item)
    clean.sort(key=lambda x: x.get("_ts") or 0)

    clusters: list[list[dict[str, Any]]] = []
    max_dt = max(1, int(window_minutes)) * 60
    max_km = max(0.1, float(radius_km))

    for item in clean:
        placed = False
        for cluster in reversed(clusters[-200:]):
            anchor = cluster[-1]
            t1, t2 = item.get("_ts"), anchor.get("_ts")
            if t1 is not None and t2 is not None and abs(t1 - t2) > max_dt:
                continue
            loc1, loc2 = item.get("_loc"), anchor.get("_loc")
            same_entity = bool(item.get("entity_id") and item.get("entity_id") == anchor.get("entity_id"))
            if loc1 and loc2 and _km(loc1, loc2) > max_km and not same_entity:
                continue
            if not loc1 and not loc2 and not same_entity:
                # Non-geospatial records need a shared entity or explicit correlation key.
                key1, key2 = item.get("correlation_key"), anchor.get("correlation_key")
                if not key1 or key1 != key2:
                    continue
            cluster.append(item)
            placed = True
            break
        if not placed:
            clusters.append([item])

    incidents: list[dict[str, Any]] = []
    for cluster in clusters:
        if len(cluster) < max(1, min_observations):
            continue
        sources = sorted({str(x.get("source_id") or x.get("source") or "unknown") for x in cluster})
        # Independence is based on the canonical origin/family when supplied, not
        # merely on the number of republishing endpoints. This prevents a Reuters
        # story mirrored by several sites from counting as several confirmations.
        origins = sorted({
            str(x.get("source_origin") or x.get("source_family") or x.get("source_id") or x.get("source") or "unknown")
            for x in cluster
        })
        entities = sorted({str(x.get("entity_id")) for x in cluster if x.get("entity_id")})
        kinds = sorted({str(x.get("kind") or x.get("type") or "observation") for x in cluster})
        locs = [x["_loc"] for x in cluster if x.get("_loc")]
        center = None
        if locs:
            center = {"lat": sum(x[0] for x in locs) / len(locs), "lon": sum(x[1] for x in locs) / len(locs), "uncertainty_km": max_km}
        timestamps = [x["_ts"] for x in cluster if x.get("_ts") is not None]
        first_seen = datetime.fromtimestamp(min(timestamps), UTC).isoformat() if timestamps else datetime.now(UTC).isoformat()
        last_seen = datetime.fromtimestamp(max(timestamps), UTC).isoformat() if timestamps else first_seen
        sev = max((str(x.get("severity") or "watch") for x in cluster), key=_severity_rank)
        rel = sum(float(x.get("source_reliability", 0.7)) for x in cluster) / len(cluster)
        freshness = sum(float(x.get("freshness", 0.8)) for x in cluster) / len(cluster)
        independent_count = len(origins)
        agreement = min(1.0, 0.45 + 0.10 * len(cluster) + 0.10 * max(0, independent_count - 1))
        conf = score_confidence({
            "source_reliability": rel,
            "freshness": freshness,
            "location_certainty": 0.9 if locs else 0.55,
            "timestamp_certainty": 0.9 if timestamps else 0.5,
            "independent_confirmation": min(1.0, independent_count / 4),
            "source_independence": min(1.0, independent_count / max(1, len(sources))),
            "cross_source_agreement": agreement,
        })
        incidents.append({
            "title": f"Correlated {', '.join(kinds[:3])} activity",
            "summary": f"{len(cluster)} observations from {len(sources)} source endpoint(s) / {independent_count} independent origin(s) were correlated within {window_minutes} minutes / {radius_km:g} km.",
            "severity": sev,
            "confidence": conf["score"],
            "confidence_detail": conf,
            "status": "open",
            "location": center,
            "observation_ids": [str(x.get("id")) for x in cluster],
            "entity_ids": entities,
            "source_ids": sources,
            "tags": ["fusion", *kinds[:8]],
            "assessment": {"observation_count": len(cluster), "source_count": len(sources), "independent_source_count": independent_count, "source_origins": origins, "kinds": kinds},
            "first_seen": first_seen,
            "last_seen": last_seen,
        })
    incidents.sort(key=lambda x: (_severity_rank(x["severity"]), x["confidence"], len(x["observation_ids"])), reverse=True)
    return incidents
