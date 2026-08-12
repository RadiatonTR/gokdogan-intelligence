"""Low-overhead bridge from legacy dashboard layers into Intelligence Core.

The legacy fetchers remain the owner of their public-data adapters and in-memory
map state.  This bridge creates canonical observations *only when an analyst has
configured a watchlist, rule, or geofence*.  It intentionally avoids turning
all high-frequency map telemetry into an unbounded SQLite history stream.
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

from .entity_resolution import normalize_text

if TYPE_CHECKING:  # pragma: no cover
    from .service import IntelligenceCore

_LAYER_ENTITY_TYPE: dict[str, str] = {
    "ships": "vessel",
    "commercial_flights": "aircraft",
    "private_flights": "aircraft",
    "private_jets": "aircraft",
    "military_flights": "aircraft",
    "tracked_flights": "aircraft",
    "supplemental_flights": "aircraft",
    "satellites": "satellite",
    "cctv": "camera",
    "earthquakes": "event",
    "firms_fires": "event",
    "weather_alerts": "event",
    "ukraine_alerts": "event",
    "gdelt": "report",
    "liveuamap": "report",
    "news": "report",
    "telegram_osint": "report",
    "cyber_threats": "cyber-indicator",
    "malware_threats": "cyber-indicator",
    "internet_outages": "infrastructure",
    "datacenters": "infrastructure",
    "military_bases": "infrastructure",
    "power_plants": "infrastructure",
    "trains": "train",
    "fishing_activity": "vessel",
    "uap_sightings": "event",
    "volcanoes": "event",
    "air_quality": "sensor",
    "wastewater": "sensor",
}

_ID_KEYS = ("icao24", "icao", "hex", "mmsi", "imo", "id", "uuid", "callsign", "registration", "name")
_NAME_KEYS = ("title", "name", "callsign", "registration", "ship_name", "description", "summary", "type")
_TIME_KEYS = ("observed_at", "timestamp", "updated_at", "last_seen", "time", "date")


def _first(item: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _location(item: dict[str, Any]) -> dict[str, float] | None:
    lat = item.get("lat", item.get("latitude"))
    lng = item.get("lng", item.get("lon", item.get("longitude")))
    try:
        if lat is None or lng is None:
            return None
        lat_f, lng_f = float(lat), float(lng)
        if not (-90 <= lat_f <= 90 and -180 <= lng_f <= 180):
            return None
        return {"lat": lat_f, "lng": lng_f}
    except (TypeError, ValueError):
        return None


def _compact_attributes(item: dict[str, Any], limit: int = 48) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in item.items():
        if len(out) >= limit:
            break
        if isinstance(value, (str, int, float, bool)) or value is None:
            text = value
            if isinstance(value, str) and len(value) > 2000:
                text = value[:2000]
            out[str(key)[:120]] = text
    return out


def ingest_legacy_layer(core: "IntelligenceCore", layer: str, items: list[Any], *, max_rule_items: int = 250) -> dict[str, int]:
    """Evaluate an updated legacy layer against analyst monitoring state.

    Watchlists and geofences are scanned across the supplied snapshot. Generic
    rules are capped because some layers contain many thousands of positions.
    The caller supplies a bounded shallow snapshot, so this function never owns
    or mutates the live dashboard store.
    """
    watches = [w for w in core.store.list_watch() if w.get("enabled")]
    fences = [f for f in core.store.list_geofences() if f.get("enabled")]
    rules = [r for r in core.store.list_rules() if r.get("enabled")]
    if not watches and not fences and not rules:
        return {"scanned": 0, "ingested": 0}

    entity_type = _LAYER_ENTITY_TYPE.get(layer, layer.rstrip("s").replace("_", "-"))[:64]
    watch_values = {
        (str(w.get("entity_type") or "").casefold(), normalize_text(str(w.get("value") or "")))
        for w in watches
    }
    ingested = 0
    scanned = 0
    rule_budget = max(0, int(max_rule_items))

    for raw in items:
        if not isinstance(raw, dict):
            continue
        scanned += 1
        entity_value = _first(raw, _ID_KEYS)
        normalized = normalize_text(entity_value)
        loc = _location(raw)
        watch_interest = bool(normalized and ((entity_type.casefold(), normalized) in watch_values))
        fence_interest = False
        if loc and fences:
            lat, lng = loc["lat"], loc["lng"]
            fence_interest = any(
                float(f.get("min_lat", -91)) <= lat <= float(f.get("max_lat", 91))
                and float(f.get("min_lng", -181)) <= lng <= float(f.get("max_lng", 181))
                for f in fences
            )
        rule_interest = bool(rules and rule_budget > 0)
        if not (watch_interest or fence_interest or rule_interest):
            continue
        if rule_interest:
            rule_budget -= 1

        label = _first(raw, _NAME_KEYS) or entity_value or f"{layer} observation"
        observed_at = _first(raw, _TIME_KEYS) or None
        core.ingest_observation({
            "kind": "observed",
            "entity_id": entity_value or None,
            "entity_type": entity_type,
            "entity_value": entity_value,
            "entity_name": label,
            "event_type": f"legacy.{layer}",
            "summary": label[:2000],
            "location": loc,
            "source": {
                "source_id": f"legacy:{layer}",
                "provider": f"Legacy fetcher / {layer}",
                "family": f"legacy:{layer}",
                "origin_id": f"legacy:{layer}",
                "reliability": 0.65,
            },
            "observed_at": observed_at,
            "confidence": 0.65,
            "attributes": _compact_attributes(raw),
            "provenance": [{"stage": "legacy-normalize", "actor": "intelligence-core-r7"}],
        })
        ingested += 1
    return {"scanned": scanned, "ingested": ingested}
