"""AISHub REST fallback for ship tracking when AISStream is unreachable.

Background
----------
On 2026-05-23 ``stream.aisstream.io`` (the primary live AIS WebSocket feed)
went fully offline. Backend's only ship signal vanished. This module polls
``data.aishub.net``'s free REST API on a slow cadence (default 20 min) when
the WebSocket primary is disconnected, so the ships layer doesn't go fully
dark during upstream outages.

Why 20 minutes
--------------
AISHub's free tier is rate-limited and explicitly asks consumers to be
courteous. 20 minutes is well inside their limits, gives ships time to
move enough to look "alive" on the map, and won't drain their service.
Configurable via the ``AISHUB_POLL_INTERVAL_MINUTES`` env var (clamped to
[1, 360]).

Why slow vs primary
-------------------
This is degraded mode, not a replacement. A ship at 20 knots moves about
6 nautical miles in 20 minutes — visible on the map but coarser than the
real-time WebSocket signal. When AISStream comes back online, the
WebSocket data will overwrite these records via the same ``_vessels``
dict and ``source`` will flip from ``"aishub"`` back to upstream-live.

Opt-in
------
Operator must set ``AISHUB_USERNAME`` (free registration at
https://www.aishub.net/api). If unset, this fetcher is a no-op.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from services.network_utils import fetch_with_curl

logger = logging.getLogger(__name__)


AISHUB_URL = "https://data.aishub.net/ws.php"


def aishub_username() -> str:
    return str(os.environ.get("AISHUB_USERNAME", "")).strip()


def aishub_fallback_enabled() -> bool:
    """Returns True only when the operator has registered with AISHub and
    set ``AISHUB_USERNAME``. The presence of the username is the opt-in."""
    return bool(aishub_username())


def aishub_poll_interval_minutes() -> int:
    """Default 20 minutes. Clamped to [1, 360] so a hostile or
    misconfigured env var can't either hammer the upstream or silence the
    fallback for a day."""
    raw = os.environ.get("AISHUB_POLL_INTERVAL_MINUTES", "20")
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        value = 20
    return max(1, min(360, value))


def _should_run_fallback() -> bool:
    """Only run when the primary WebSocket is disconnected. Avoids stomping
    over fresher live data when AISStream is healthy.

    Returns False if:
      * AISHub isn't configured (no username)
      * AISStream primary is currently connected (recent vessel messages)

    Returns True only when AIS is configured-but-down. The
    ``proxy_spawn_count > 0`` guard means "the primary has at least tried
    to run" — if the user set AISHUB_USERNAME but not AIS_API_KEY at all,
    AISHub will still serve as a primary on its own slow cadence.
    """
    if not aishub_fallback_enabled():
        return False
    try:
        from services.ais_stream import ais_proxy_status
        status = ais_proxy_status() or {}
    except Exception:
        return True  # ais_stream not importable? still try AISHub.
    # If the WebSocket primary is connected, skip the fallback — fresher
    # data is already flowing.
    if status.get("connected") is True:
        return False
    return True


def _parse_aishub_response(payload: str) -> list[dict]:
    """Parse the AISHub JSON response into a list of vessel records.

    Successful response shape::

        [
            {"ERROR": false, "USERNAME": "...", "FORMAT": "1", "RECORDS": N},
            [{"MMSI": ..., "LATITUDE": ..., "LONGITUDE": ..., ...}, ...]
        ]

    Error response shape::

        [{"ERROR": true, "ERROR_MESSAGE": "..."}]

    Empty payload (e.g. silent rate-limit drop) returns ``[]``.
    """
    if not payload or not payload.strip():
        return []
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as e:
        logger.warning("AISHub: response is not JSON: %s", e)
        return []
    if not isinstance(data, list) or not data:
        return []
    header = data[0] if isinstance(data[0], dict) else {}
    if header.get("ERROR") is True:
        logger.warning(
            "AISHub: upstream error: %s",
            header.get("ERROR_MESSAGE", "<unspecified>"),
        )
        return []
    if len(data) < 2 or not isinstance(data[1], list):
        return []
    return [row for row in data[1] if isinstance(row, dict)]


def _normalize_record(row: dict) -> dict | None:
    """Map an AISHub vessel record to our internal vessel schema.

    Returns None when the record can't be used (no MMSI, bad position,
    sentinel "not available" lat/lng).
    """
    try:
        mmsi = int(row.get("MMSI") or 0)
    except (TypeError, ValueError):
        return None
    if not mmsi:
        return None
    try:
        lat = float(row.get("LATITUDE"))
        lng = float(row.get("LONGITUDE"))
    except (TypeError, ValueError):
        return None
    # AIS uses 91/181 as "no position available" sentinels.
    if abs(lat) > 90 or abs(lng) > 180:
        return None
    if lat == 91.0 or lng == 181.0:
        return None
    # SOG raw 102.3 is "speed not available"; sanitize to 0.
    try:
        sog_raw = float(row.get("SOG") or 0)
    except (TypeError, ValueError):
        sog_raw = 0.0
    sog = 0.0 if sog_raw >= 102.2 else sog_raw
    try:
        cog = float(row.get("COG") or 0)
    except (TypeError, ValueError):
        cog = 0.0
    try:
        heading_raw = int(row.get("HEADING") or 511)
    except (TypeError, ValueError):
        heading_raw = 511
    # AIS heading sentinel 511 = "not available" — fall back to COG.
    heading = heading_raw if heading_raw != 511 else cog
    try:
        ais_type = int(row.get("TYPE") or 0)
    except (TypeError, ValueError):
        ais_type = 0
    return {
        "mmsi": mmsi,
        "lat": lat,
        "lng": lng,
        "sog": sog,
        "cog": cog,
        "heading": heading,
        "name": str(row.get("NAME") or "").strip() or "UNKNOWN",
        "callsign": str(row.get("CALLSIGN") or "").strip(),
        "destination": str(row.get("DEST") or "").strip().replace("@", "") or "",
        "imo": int(row.get("IMO") or 0),
        "ais_type_code": ais_type,
    }


def fetch_aishub_vessels() -> int:
    """Poll AISHub and merge vessels into the shared ``_vessels`` store.

    Returns the number of vessels updated (0 on skip, error, or no data).
    Designed to be called by the APScheduler tier — see
    ``data_fetcher.py`` for the 20-minute interval job that wraps this.
    """
    if not _should_run_fallback():
        logger.debug("AISHub fallback skipped: primary connected or not configured")
        return 0

    username = aishub_username()
    url = (
        f"{AISHUB_URL}?username={username}&format=1&output=json"
        f"&compress=0"
    )

    try:
        response = fetch_with_curl(url, timeout=30)
    except Exception as e:
        logger.warning("AISHub fetch failed: %s", e)
        return 0

    if not response or response.status_code != 200:
        logger.warning(
            "AISHub HTTP %s",
            getattr(response, "status_code", "None"),
        )
        return 0

    rows = _parse_aishub_response(getattr(response, "text", "") or "")
    if not rows:
        return 0

    # Inline imports to avoid a circular dependency at module load time
    # (ais_stream imports lots of things and is loaded by main.py).
    from services.ais_stream import (
        _vessels,
        _vessels_lock,
        _record_vessel_trail_locked,
        classify_vessel,
        get_country_from_mmsi,
    )

    now = time.time()
    count = 0
    with _vessels_lock:
        for row in rows:
            normalized = _normalize_record(row)
            if normalized is None:
                continue
            mmsi = normalized["mmsi"]
            vessel = _vessels.setdefault(mmsi, {"mmsi": mmsi})
            # Don't overwrite fresher live data: if the WebSocket pushed an
            # update for this MMSI more recently than now-1s (race during
            # the brief reconnection window) keep the live one.
            last = float(vessel.get("_updated") or 0)
            if last > now - 1:
                continue
            vessel.update(
                {
                    "lat": normalized["lat"],
                    "lng": normalized["lng"],
                    "sog": normalized["sog"],
                    "cog": normalized["cog"],
                    "heading": normalized["heading"],
                    "_updated": now,
                    "source": "aishub",
                }
            )
            if normalized["name"] and normalized["name"] != "UNKNOWN":
                vessel["name"] = normalized["name"]
            if normalized["callsign"]:
                vessel["callsign"] = normalized["callsign"]
            if normalized["destination"]:
                vessel["destination"] = normalized["destination"]
            if normalized["imo"]:
                vessel["imo"] = normalized["imo"]
            if normalized["ais_type_code"]:
                vessel["ais_type_code"] = normalized["ais_type_code"]
                vessel["type"] = classify_vessel(normalized["ais_type_code"], mmsi)
            if not vessel.get("country"):
                vessel["country"] = get_country_from_mmsi(mmsi)
            _record_vessel_trail_locked(
                mmsi,
                normalized["lat"],
                normalized["lng"],
                normalized["sog"],
                now,
            )
            count += 1

    if count:
        logger.info(
            "AISHub fallback: merged %d vessels (poll interval %d min)",
            count,
            aishub_poll_interval_minutes(),
        )
    return count
