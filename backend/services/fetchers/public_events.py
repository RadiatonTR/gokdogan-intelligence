"""Public, non-sensitive global event feeds used by Gokdogan.

Sources are official/public endpoints only.  The module intentionally excludes
private CCTV discovery, live police-unit tracking, and non-public sensitive
military telemetry.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from services.fetchers._store import _data_lock, _mark_fresh, latest_data
from services.network_utils import fetch_with_curl

logger = logging.getLogger("services.data_fetcher")

_EONET_EVENTS = "https://eonet.gsfc.nasa.gov/api/v3/events?status=open&limit=250"
_GDACS_GEOJSON = "https://www.gdacs.org/contentdata/xml/gdacs.geojson"


def _float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _latest_geometry(event: dict[str, Any]) -> tuple[float | None, float | None, str | None]:
    geoms = event.get("geometry")
    if not isinstance(geoms, list) or not geoms:
        return None, None, None
    for geom in reversed(geoms):
        if not isinstance(geom, dict):
            continue
        coords = geom.get("coordinates")
        if isinstance(coords, list) and len(coords) >= 2 and not isinstance(coords[0], list):
            lng = _float(coords[0])
            lat = _float(coords[1])
            if lat is not None and lng is not None:
                return lat, lng, str(geom.get("date") or "") or None
    return None, None, None


def _normalize_eonet(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    out: list[dict[str, Any]] = []
    for event in payload.get("events") or []:
        if not isinstance(event, dict):
            continue
        lat, lng, event_time = _latest_geometry(event)
        categories = [
            str(item.get("title") or item.get("id") or "")
            for item in (event.get("categories") or [])
            if isinstance(item, dict)
        ]
        sources = [
            str(item.get("url") or "")
            for item in (event.get("sources") or [])
            if isinstance(item, dict) and item.get("url")
        ]
        out.append(
            {
                "id": f"eonet:{event.get('id')}",
                "provider": "NASA EONET",
                "provider_id": event.get("id"),
                "title": str(event.get("title") or "Doğal olay"),
                "description": str(event.get("description") or "")[:800],
                "categories": categories,
                "lat": lat,
                "lng": lng,
                "event_time": event_time,
                "severity": None,
                "alert_level": None,
                "url": sources[0] if sources else str(event.get("link") or ""),
                "source_urls": sources,
                "active": event.get("closed") in (None, ""),
            }
        )
    return out


def _coords_from_geometry(geometry: Any) -> tuple[float | None, float | None]:
    if not isinstance(geometry, dict):
        return None, None
    coords = geometry.get("coordinates")
    kind = str(geometry.get("type") or "")
    if kind == "Point" and isinstance(coords, list) and len(coords) >= 2:
        return _float(coords[1]), _float(coords[0])
    # GDACS may publish polygons; use a cheap bbox-like average of the outer ring
    # only for display centering.  The raw geometry is preserved separately.
    ring = None
    if kind == "Polygon" and isinstance(coords, list) and coords:
        ring = coords[0]
    elif kind == "MultiPolygon" and isinstance(coords, list) and coords and coords[0]:
        ring = coords[0][0]
    if isinstance(ring, list):
        pts = [(p[1], p[0]) for p in ring if isinstance(p, list) and len(p) >= 2]
        if pts:
            return sum(float(p[0]) for p in pts) / len(pts), sum(float(p[1]) for p in pts) / len(pts)
    return None, None


def _normalize_gdacs(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    out: list[dict[str, Any]] = []
    for feature in payload.get("features") or []:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
        lat, lng = _coords_from_geometry(feature.get("geometry"))
        event_type = str(props.get("eventtype") or props.get("eventType") or props.get("type") or "")
        event_id = props.get("eventid") or props.get("eventId") or props.get("id")
        title = str(props.get("name") or props.get("eventname") or props.get("title") or event_type or "GDACS olayı")
        alert = str(props.get("alertlevel") or props.get("alertLevel") or "").upper() or None
        severity = props.get("severity") or props.get("severitydata")
        url = str(props.get("url") or props.get("link") or props.get("web") or "")
        if not url and event_type and event_id:
            url = f"https://www.gdacs.org/report.aspx?eventtype={event_type}&eventid={event_id}"
        event_time = props.get("fromdate") or props.get("fromDate") or props.get("date") or props.get("todate")
        out.append(
            {
                "id": f"gdacs:{event_type}:{event_id}",
                "provider": "GDACS",
                "provider_id": event_id,
                "title": title,
                "description": str(props.get("description") or props.get("episodealertscore") or "")[:800],
                "categories": [event_type] if event_type else [],
                "lat": lat,
                "lng": lng,
                "event_time": str(event_time or "") or None,
                "severity": severity,
                "alert_level": alert,
                "url": url,
                "geometry": feature.get("geometry"),
                "active": True,
            }
        )
    return out


def _dedupe(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in events:
        key = str(item.get("id") or "").strip()
        if not key:
            key = f"{item.get('provider')}|{item.get('title')}|{item.get('event_time')}"
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def fetch_global_disasters() -> list[dict[str, Any]]:
    """Fetch public global natural-disaster events from NASA EONET + GDACS."""
    events: list[dict[str, Any]] = []
    source_status: dict[str, Any] = {}
    for name, url, normalizer in (
        ("NASA EONET", _EONET_EVENTS, _normalize_eonet),
        ("GDACS", _GDACS_GEOJSON, _normalize_gdacs),
    ):
        started = time.perf_counter()
        try:
            response = fetch_with_curl(
                url,
                timeout=18,
                headers={"Accept": "application/json", "Accept-Encoding": "identity"},
            )
            if response.status_code != 200:
                raise RuntimeError(f"http_{response.status_code}")
            rows = normalizer(response.json())
            events.extend(rows)
            source_status[name] = {
                "ok": True,
                "records": len(rows),
                "latency_ms": round((time.perf_counter() - started) * 1000),
            }
        except Exception as exc:
            source_status[name] = {
                "ok": False,
                "records": 0,
                "error": type(exc).__name__,
                "latency_ms": round((time.perf_counter() - started) * 1000),
            }
            logger.warning("Global disaster source %s failed: %s", name, exc)

    events = _dedupe(events)
    snapshot = {
        "events": events,
        "sources": source_status,
        "updated_at": _iso_now(),
        "total": len(events),
    }
    with _data_lock:
        latest_data["global_disasters"] = snapshot
    _mark_fresh("global_disasters")
    logger.info("Global disasters: %d events", len(events))
    return events

_CBP_ALL_PORTS = "https://bwt.cbp.gov/ViewAllPorts"


def _parse_minutes(text: str) -> int | None:
    import re
    values = [int(x) for x in re.findall(r"\b(\d{1,3})\s*min(?:ute)?s?\b", text, flags=re.I)]
    if values:
        return max(values)
    if "no delay" in text.lower():
        return 0
    return None


def _parse_cbp_rows(html: str) -> list[dict[str, Any]]:
    """Best-effort parser for CBP's public ViewAllPorts table.

    We keep the raw human-readable row because the public site's columns can
    change; this prevents silently inventing lane semantics when markup shifts.
    """
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return []
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, Any]] = []
    for tr in soup.find_all("tr"):
        cells = [" ".join(cell.get_text(" ", strip=True).split()) for cell in tr.find_all(["th", "td"])]
        if len(cells) < 2:
            continue
        joined = " | ".join(cells)
        low = joined.lower()
        if not any(token in low for token in ("delay", "lanes closed", "update pending", "lane open", "lanes open")):
            continue
        name = cells[0].strip()
        if not name or name.lower() in {"port", "port of entry"}:
            continue
        wait = _parse_minutes(joined)
        rows.append(
            {
                "id": f"cbp:{len(rows)+1}",
                "name": name,
                "country_pair": "ABD / Kanada veya Meksika",
                "provider": "U.S. CBP Border Wait Times",
                "mode": "official_live_table",
                "wait_minutes": wait,
                "status_text": joined[:1400],
                "url": _CBP_ALL_PORTS,
            }
        )
        if len(rows) >= 120:
            break
    return rows


def _corridor_crossings() -> list[dict[str, Any]]:
    from services.road_corridor_sat.presets import CORRIDOR_PRESETS

    with _data_lock:
        trends = dict(latest_data.get("road_corridor_trends") or {})
        cameras = list(latest_data.get("cctv") or [])
    trend_rows = trends.get("corridors") if isinstance(trends.get("corridors"), list) else []
    by_id = {str(row.get("id") or row.get("corridor_id") or ""): row for row in trend_rows if isinstance(row, dict)}
    out: list[dict[str, Any]] = []
    for preset in CORRIDOR_PRESETS:
        if preset.get("category") != "border_crossing":
            continue
        pid = str(preset["id"])
        trend = by_id.get(pid) or {}
        label = str(preset["label"])
        camera_hits = 0
        low_label = label.lower()
        for cam in cameras:
            if not isinstance(cam, dict):
                continue
            blob = " ".join(str(cam.get(k) or "") for k in ("name", "location", "source", "region", "country")).lower()
            if any(token in blob for token in (pid.split("_")[0], "kapıkule" if "kapikule" in pid else "", "ipsala" if "ipsala" in pid else "", "habur" if "habur" in pid else "", "gürbulak" if "gurbulak" in pid else "" ) if token):
                camera_hits += 1
        bbox = preset.get("bbox")
        center_lat = center_lng = None
        if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            try:
                center_lng = (float(bbox[0]) + float(bbox[2])) / 2.0
                center_lat = (float(bbox[1]) + float(bbox[3])) / 2.0
            except (TypeError, ValueError):
                center_lat = center_lng = None
        out.append(
            {
                "id": f"corridor:{pid}",
                "name": label,
                "lat": center_lat,
                "lng": center_lng,
                "country_pair": preset.get("country"),
                "provider": "Gökdoğan kamu koridor analizi",
                "mode": "satellite_trend_and_public_camera_metadata",
                "bbox": preset.get("bbox"),
                "trend": trend,
                "public_camera_count": camera_hits,
                "status_text": "Uydu eğilimi ve kamu kamera metadatası; resmî bekleme süresi feed'i yoksa dakika uydurulmaz.",
            }
        )
    return out


def fetch_border_status() -> list[dict[str, Any]]:
    """Aggregate public border-crossing status without private checkpoint data."""
    crossings = _corridor_crossings()
    sources: dict[str, Any] = {
        "Gökdoğan koridorları": {"ok": True, "records": len(crossings)},
    }
    started = time.perf_counter()
    try:
        response = fetch_with_curl(
            _CBP_ALL_PORTS,
            timeout=18,
            headers={"Accept": "text/html", "Accept-Encoding": "identity"},
        )
        if response.status_code != 200:
            raise RuntimeError(f"http_{response.status_code}")
        cbp_rows = _parse_cbp_rows(response.text)
        crossings.extend(cbp_rows)
        sources["U.S. CBP"] = {
            "ok": True,
            "records": len(cbp_rows),
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "url": _CBP_ALL_PORTS,
        }
    except Exception as exc:
        sources["U.S. CBP"] = {
            "ok": False,
            "records": 0,
            "error": type(exc).__name__,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "url": _CBP_ALL_PORTS,
        }
        logger.warning("CBP border wait feed failed: %s", exc)

    snapshot = {
        "crossings": crossings,
        "sources": sources,
        "updated_at": _iso_now(),
        "total": len(crossings),
    }
    with _data_lock:
        latest_data["border_status"] = snapshot
    _mark_fresh("border_status")
    logger.info("Border status: %d crossings/status rows", len(crossings))
    return crossings
