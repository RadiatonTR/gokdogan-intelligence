from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MetricRule:
    path: str
    threshold: float = 0.0
    percent: bool = False
    risk_direction: str = "up"


def _get_path(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def compare_snapshots(current: dict[str, Any], previous: dict[str, Any] | None, rules: list[MetricRule] | None = None) -> dict[str, Any]:
    if previous is None:
        return {"baseline": True, "signals": {"new": [], "escalated": [], "deescalated": [], "unchanged": []}, "summary": {"total_changes": 0, "critical_changes": 0, "direction": "baseline"}}
    rules = rules or []
    signals = {"new": [], "escalated": [], "deescalated": [], "unchanged": []}
    critical = risk_up = risk_down = 0
    for rule in rules:
        curr, prev = _get_path(current, rule.path), _get_path(previous, rule.path)
        if not isinstance(curr, (int, float)) or not isinstance(prev, (int, float)):
            continue
        diff = curr - prev
        change = ((diff / abs(prev)) * 100) if rule.percent and prev else diff
        if abs(change) < rule.threshold:
            signals["unchanged"].append(rule.path)
            continue
        severity = "critical" if abs(change) >= max(rule.threshold * 3, rule.threshold + 1) else "high" if abs(change) >= max(rule.threshold * 2, rule.threshold + 0.5) else "moderate"
        entry = {"key": rule.path, "from": prev, "to": curr, "change": diff, "metric_change": round(change, 3), "severity": severity}
        signals["escalated" if change > 0 else "deescalated"].append(entry)
        if severity == "critical":
            critical += 1
        adverse = (change > 0 and rule.risk_direction == "up") or (change < 0 and rule.risk_direction == "down")
        if adverse:
            risk_up += 1
        else:
            risk_down += 1

    for key, value in current.items():
        if not isinstance(value, list) or not isinstance(previous.get(key), list):
            continue
        def identity(item: Any) -> str | None:
            if not isinstance(item, dict):
                return None
            for candidate in ("id", "event_id", "icao24", "mmsi", "callsign", "url", "name", "title"):
                raw = item.get(candidate)
                if raw not in (None, ""):
                    return f"{candidate}:{str(raw).strip().casefold()}"
            return None
        old = {identity(x) for x in previous[key]}
        old.discard(None)
        for item in value:
            ident = identity(item)
            if ident and ident not in old:
                signals["new"].append({"key": key, "identity": ident, "item": item})
    total = sum(len(signals[k]) for k in ("new", "escalated", "deescalated"))
    direction = "risk_up" if risk_up > risk_down else "risk_down" if risk_down > risk_up else "mixed"
    return {"baseline": False, "signals": signals, "summary": {"total_changes": total, "critical_changes": critical, "direction": direction}}
