from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any


def _path(data: dict[str, Any], dotted: str) -> Any:
    current: Any = data
    for part in dotted.split('.'):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))


def _point_in_polygon(lat: float, lng: float, polygon: list[list[float]]) -> bool:
    # Polygon coordinate order is [lng, lat], matching GeoJSON.
    inside = False
    j = len(polygon) - 1
    for i, point in enumerate(polygon):
        if len(point) < 2 or len(polygon[j]) < 2:
            j = i
            continue
        xi, yi = float(point[0]), float(point[1])
        xj, yj = float(polygon[j][0]), float(polygon[j][1])
        intersects = ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi)
        if intersects:
            inside = not inside
        j = i
    return inside


def condition_matches(condition: dict[str, Any], event: dict[str, Any]) -> bool:
    kind = str(condition.get('kind') or 'field').lower()
    if kind == 'field':
        value = _path(event, str(condition.get('path') or ''))
        op = str(condition.get('op') or 'eq').lower()
        target = condition.get('value')
        try:
            if op == 'eq': return value == target
            if op == 'ne': return value != target
            if op == 'gt': return float(value) > float(target)
            if op == 'gte': return float(value) >= float(target)
            if op == 'lt': return float(value) < float(target)
            if op == 'lte': return float(value) <= float(target)
            if op == 'contains': return str(target).casefold() in str(value).casefold()
            if op == 'in': return value in (target if isinstance(target, list) else [target])
        except (TypeError, ValueError):
            return False
        return False
    if kind == 'circle':
        loc = event.get('location') or event
        if not isinstance(loc, dict): return False
        lat, lng = loc.get('lat'), loc.get('lng', loc.get('lon'))
        if lat is None or lng is None: return False
        center = condition.get('center') or {}
        try:
            return _haversine_km(float(lat), float(lng), float(center['lat']), float(center['lng'])) <= float(condition.get('radius_km', 0))
        except (KeyError, TypeError, ValueError):
            return False
    if kind == 'polygon':
        loc = event.get('location') or event
        if not isinstance(loc, dict): return False
        lat, lng = loc.get('lat'), loc.get('lng', loc.get('lon'))
        polygon = condition.get('coordinates') or []
        if lat is None or lng is None or not isinstance(polygon, list) or len(polygon) < 3: return False
        try: return _point_in_polygon(float(lat), float(lng), polygon)
        except (TypeError, ValueError): return False
    return False


def rule_matches(rule: dict[str, Any], event: dict[str, Any]) -> bool:
    conditions = rule.get('conditions') or {}
    mode = str(conditions.get('mode') or 'all').lower()
    items = conditions.get('items') or []
    if not items:
        return False
    results = [condition_matches(item, event) for item in items if isinstance(item, dict)]
    return any(results) if mode == 'any' else bool(results) and all(results)


def cooldown_elapsed(last_triggered_at: str | None, cooldown_seconds: int) -> bool:
    if not last_triggered_at:
        return True
    try:
        last = datetime.fromisoformat(last_triggered_at)
        if last.tzinfo is None: last = last.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - last).total_seconds() >= max(0, cooldown_seconds)
    except Exception:
        return True
