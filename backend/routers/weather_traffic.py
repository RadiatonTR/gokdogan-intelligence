"""Live weather and road-traffic endpoints for the Gokdogan desktop profile.

All outbound sources are public/operator-configured services.  Secrets remain on
backend side.  No private camera discovery or live police-location tracking is
implemented here.
"""
from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Query, Request, Response

from limiter import limiter
from services.network_utils import fetch_with_curl, outbound_user_agent
from services.fetchers._store import _data_lock, latest_data

router = APIRouter()

_OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
_OPEN_METEO_AIR = "https://air-quality-api.open-meteo.com/v1/air-quality"
_OPEN_METEO_MARINE = "https://marine-api.open-meteo.com/v1/marine"
_TOMTOM = "https://api.tomtom.com"


def _bounded_coord(value: float, low: float, high: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"invalid_{name}")
    return value


def _as_list(obj: dict[str, Any], key: str) -> list[Any]:
    value = obj.get(key)
    return value if isinstance(value, list) else []


def _summary(values: list[Any]) -> dict[str, float | None]:
    nums: list[float] = []
    for value in values:
        try:
            f = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(f):
            nums.append(f)
    if not nums:
        return {"min": None, "max": None, "mean": None, "change": None}
    return {
        "min": round(min(nums), 1),
        "max": round(max(nums), 1),
        "mean": round(sum(nums) / len(nums), 1),
        "change": round(nums[-1] - nums[0], 1) if len(nums) > 1 else 0.0,
    }


@router.get("/api/weather/forecast")
@limiter.limit("60/minute")
async def weather_forecast(
    request: Request,
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
):
    """Return current + hourly + daily weather around a selected map point.

    Uses Open-Meteo's keyless forecast endpoint with 30 past days and 7 forecast
    days so the desktop can render day/week/month temperature-change summaries
    without a second provider credential.
    """
    lat = _bounded_coord(lat, -90, 90, "lat")
    lng = _bounded_coord(lng, -180, 180, "lng")
    params = {
        "latitude": f"{lat:.5f}",
        "longitude": f"{lng:.5f}",
        "timezone": "auto",
        "past_days": "30",
        "forecast_days": "16",
        "current": ",".join(
            [
                "temperature_2m",
                "relative_humidity_2m",
                "apparent_temperature",
                "precipitation",
                "rain",
                "showers",
                "snowfall",
                "weather_code",
                "cloud_cover",
                "pressure_msl",
                "wind_speed_10m",
                "wind_direction_10m",
                "wind_gusts_10m",
            ]
        ),
        "hourly": ",".join(
            [
                "temperature_2m",
                "apparent_temperature",
                "precipitation_probability",
                "precipitation",
                "rain",
                "showers",
                "snowfall",
                "weather_code",
                "cloud_cover",
                "visibility",
                "surface_pressure",
                "cloud_cover_low",
                "cloud_cover_mid",
                "cloud_cover_high",
                "wind_speed_10m",
                "wind_gusts_10m",
            ]
        ),
        "daily": ",".join(
            [
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "temperature_2m_mean",
                "precipitation_sum",
                "rain_sum",
                "showers_sum",
                "snowfall_sum",
                "precipitation_probability_max",
                "wind_speed_10m_max",
                "wind_gusts_10m_max",
                "uv_index_max",
                "daylight_duration",
                "sunshine_duration",
                "sunrise",
                "sunset",
            ]
        ),
    }
    url = f"{_OPEN_METEO}?{urlencode(params)}"
    try:
        upstream = fetch_with_curl(
            url,
            timeout=15,
            headers={"Accept": "application/json", "Accept-Encoding": "identity"},
        )
        if upstream.status_code != 200:
            return Response(
                content='{"ok":false,"detail":"weather_upstream_unavailable"}',
                status_code=502,
                media_type="application/json",
            )
        data = upstream.json()
    except Exception:
        return Response(
            content='{"ok":false,"detail":"weather_upstream_unavailable"}',
            status_code=502,
            media_type="application/json",
        )

    hourly = data.get("hourly") if isinstance(data.get("hourly"), dict) else {}
    daily = data.get("daily") if isinstance(data.get("daily"), dict) else {}
    temperatures = _as_list(hourly, "temperature_2m")
    times = _as_list(hourly, "time")

    # The response contains 30 past days + today + forecast.  Derive exact
    # local-history slices by timestamp rather than relying on a hard-coded
    # offset so DST/local timezone transitions remain harmless.
    now_local = str((data.get("current") or {}).get("time") or "")[:10]
    past_temps: list[tuple[str, float]] = []
    for idx, raw_time in enumerate(times):
        if idx >= len(temperatures):
            break
        stamp = str(raw_time)
        if now_local and stamp[:10] >= now_local:
            continue
        try:
            value = float(temperatures[idx])
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            past_temps.append((stamp, value))
    temp_values = [item[1] for item in past_temps]
    history = {
        "day": _summary(temp_values[-24:]),
        "week": _summary(temp_values[-24 * 7 :]),
        "month": _summary(temp_values[-24 * 30 :]),
    }

    # Next 12h cloud/precipitation trajectory for an "approaching weather"
    # readout.  We intentionally return source values rather than invented
    # tactical labels.
    current_time = str((data.get("current") or {}).get("time") or "")
    start_idx = 0
    if current_time and current_time in times:
        start_idx = times.index(current_time)
    next_hours = []
    cloud = _as_list(hourly, "cloud_cover")
    pop = _as_list(hourly, "precipitation_probability")
    precip = _as_list(hourly, "precipitation")
    wcode = _as_list(hourly, "weather_code")
    for idx in range(start_idx, min(start_idx + 12, len(times))):
        next_hours.append(
            {
                "time": times[idx],
                "temperature": temperatures[idx] if idx < len(temperatures) else None,
                "cloud_cover": cloud[idx] if idx < len(cloud) else None,
                "precip_probability": pop[idx] if idx < len(pop) else None,
                "precipitation": precip[idx] if idx < len(precip) else None,
                "weather_code": wcode[idx] if idx < len(wcode) else None,
            }
        )

    current = data.get("current") if isinstance(data.get("current"), dict) else {}
    risk_flags: list[dict[str, Any]] = []
    try:
        temp = float(current.get("temperature_2m"))
        if temp >= 38:
            risk_flags.append({"kind": "heat", "level": "high", "label": "Aşırı sıcak"})
        elif temp <= -10:
            risk_flags.append({"kind": "cold", "level": "high", "label": "Aşırı soğuk"})
    except (TypeError, ValueError):
        pass
    try:
        gust = float(current.get("wind_gusts_10m"))
        if gust >= 70:
            risk_flags.append({"kind": "wind", "level": "high", "label": "Kuvvetli rüzgâr hamlesi"})
        elif gust >= 50:
            risk_flags.append({"kind": "wind", "level": "medium", "label": "Kuvvetli rüzgâr"})
    except (TypeError, ValueError):
        pass
    try:
        precip_now = float(current.get("precipitation"))
        if precip_now >= 8:
            risk_flags.append({"kind": "precipitation", "level": "high", "label": "Şiddetli yağış"})
    except (TypeError, ValueError):
        pass

    return {
        "ok": True,
        "source": "Open-Meteo",
        "source_url": "https://open-meteo.com/",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "latitude": data.get("latitude", lat),
        "longitude": data.get("longitude", lng),
        "timezone": data.get("timezone"),
        "current": data.get("current") or {},
        "hourly": hourly,
        "daily": daily,
        "next_12h": next_hours,
        "temperature_change": history,
        "risk_flags": risk_flags,
        "forecast_days": 16,
    }


@router.get("/api/weather/radar/tile/{z}/{x}/{y}.png")
@limiter.limit("600/minute")
async def weather_radar_tile(request: Request, z: int, x: int, y: int):
    """Proxy the latest public RainViewer precipitation-radar tile.

    The frontend only talks to loopback, keeping the desktop CSP deterministic.
    """
    if z < 0 or z > 12 or x < 0 or y < 0 or x >= 2**z or y >= 2**z:
        return Response(status_code=400)
    with _data_lock:
        weather = dict(latest_data.get("weather") or {})
    stamp = weather.get("time")
    host = str(weather.get("host") or "https://tilecache.rainviewer.com").rstrip("/")
    if not stamp or not host.startswith("https://"):
        return Response(status_code=204, headers={"X-Gokdogan-Weather": "warming-up"})
    url = f"{host}/v2/radar/{int(stamp)}/256/{z}/{x}/{y}/2/1_1.png"
    try:
        res = requests.get(
            url,
            headers={"User-Agent": outbound_user_agent("rainviewer-radar"), "Accept": "image/png", "Accept-Encoding": "identity"},
            timeout=(3, 10),
        )
        if res.status_code != 200:
            return Response(status_code=502, headers={"X-Gokdogan-Upstream": str(res.status_code)})
        return Response(
            content=res.content,
            media_type=res.headers.get("Content-Type", "image/png"),
            headers={"Cache-Control": "public, max-age=120", "X-Gokdogan-Source": "RainViewer"},
        )
    except requests.RequestException:
        return Response(status_code=502)


@router.get("/api/weather/air-quality")
@limiter.limit("60/minute")
async def weather_air_quality(
    request: Request,
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
):
    params = {
        "latitude": f"{lat:.5f}",
        "longitude": f"{lng:.5f}",
        "timezone": "auto",
        "forecast_days": "7",
        "current": ",".join(["european_aqi", "us_aqi", "pm10", "pm2_5", "nitrogen_dioxide", "ozone", "dust", "uv_index"]),
        "hourly": ",".join(["european_aqi", "us_aqi", "pm10", "pm2_5", "dust", "uv_index"]),
    }
    try:
        res = fetch_with_curl(
            f"{_OPEN_METEO_AIR}?{urlencode(params)}",
            timeout=15,
            headers={"Accept": "application/json", "Accept-Encoding": "identity"},
        )
        if res.status_code != 200:
            return Response(content='{"ok":false,"detail":"air_quality_upstream_unavailable"}', status_code=502, media_type="application/json")
        payload = res.json()
        return {"ok": True, "source": "Open-Meteo / CAMS", "fetched_at": datetime.now(timezone.utc).isoformat(), **payload}
    except Exception:
        return Response(content='{"ok":false,"detail":"air_quality_upstream_unavailable"}', status_code=502, media_type="application/json")


@router.get("/api/weather/marine")
@limiter.limit("60/minute")
async def marine_weather(
    request: Request,
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
):
    params = {
        "latitude": f"{lat:.5f}",
        "longitude": f"{lng:.5f}",
        "timezone": "auto",
        "forecast_days": "8",
        "current": ",".join(["wave_height", "wave_direction", "wave_period", "sea_surface_temperature", "ocean_current_velocity", "ocean_current_direction"]),
        "hourly": ",".join(["wave_height", "wave_direction", "wave_period", "sea_surface_temperature", "ocean_current_velocity", "ocean_current_direction"]),
        "daily": ",".join(["wave_height_max", "wave_direction_dominant", "wave_period_max"]),
    }
    try:
        res = fetch_with_curl(
            f"{_OPEN_METEO_MARINE}?{urlencode(params)}",
            timeout=15,
            headers={"Accept": "application/json", "Accept-Encoding": "identity"},
        )
        if res.status_code != 200:
            return Response(content='{"ok":false,"detail":"marine_upstream_unavailable"}', status_code=502, media_type="application/json")
        payload = res.json()
        return {"ok": True, "source": "Open-Meteo Marine", "fetched_at": datetime.now(timezone.utc).isoformat(), **payload}
    except Exception:
        return Response(content='{"ok":false,"detail":"marine_upstream_unavailable"}', status_code=502, media_type="application/json")


@router.get("/api/traffic/status")
@limiter.limit("60/minute")
async def traffic_status(request: Request):
    key = os.environ.get("TOMTOM_API_KEY", "").strip()
    return {
        "ok": True,
        "provider": "TomTom Traffic",
        "configured": bool(key),
        "flow_tiles": bool(key),
        "incident_tiles": bool(key),
        "detail": "ready" if key else "tomtom_api_key_required",
    }


def _tile_upstream(kind: str, z: int, x: int, y: int) -> str:
    if kind == "flow":
        return f"{_TOMTOM}/maps/orbis/traffic/flow/raster/tile/{z}/{x}/{y}?apiVersion=2&style=dark&tileSize=256"
    return f"{_TOMTOM}/maps/orbis/traffic/incidents/raster/tile/{z}/{x}/{y}?apiVersion=2&style=dark&tileSize=256"


@router.get("/api/traffic/tile/{kind}/{z}/{x}/{y}.png")
@limiter.limit("600/minute")
async def traffic_tile(request: Request, kind: str, z: int, x: int, y: int):
    """Backend-only TomTom traffic raster proxy; never exposes the key to JS."""
    if kind not in {"flow", "incidents"}:
        return Response(status_code=404)
    if z < 0 or z > 22 or x < 0 or y < 0 or x >= 2**z or y >= 2**z:
        return Response(status_code=400)
    key = os.environ.get("TOMTOM_API_KEY", "").strip()
    if not key:
        return Response(status_code=204, headers={"X-Gokdogan-Traffic": "key-required"})
    try:
        res = requests.get(
            _tile_upstream(kind, z, x, y),
            headers={
                "TomTom-Api-Key": key,
                "User-Agent": outbound_user_agent("tomtom-traffic"),
                "Accept": "image/png",
                "Accept-Encoding": "identity",
            },
            timeout=(3, 10),
        )
        if res.status_code != 200:
            return Response(status_code=502, headers={"X-Gokdogan-Upstream": str(res.status_code)})
        return Response(
            content=res.content,
            media_type=res.headers.get("Content-Type", "image/png"),
            headers={"Cache-Control": "public, max-age=45", "X-Gokdogan-Source": "TomTom Traffic"},
        )
    except requests.RequestException:
        return Response(status_code=502)


@router.get("/api/traffic/incidents")
@limiter.limit("30/minute")
async def traffic_incidents(
    request: Request,
    south: float = Query(..., ge=-90, le=90),
    west: float = Query(..., ge=-180, le=180),
    north: float = Query(..., ge=-90, le=90),
    east: float = Query(..., ge=-180, le=180),
):
    """Return real-time TomTom road incidents for a bounded viewport.

    The endpoint is intentionally about road conditions/incidents.  It does not
    provide or infer live police-unit locations.
    """
    key = os.environ.get("TOMTOM_API_KEY", "").strip()
    if not key:
        return {"ok": False, "configured": False, "detail": "tomtom_api_key_required", "incidents": []}
    if south >= north or west >= east:
        return Response(status_code=400)
    # Limit requests to a reasonably regional viewport; TomTom also applies an
    # upstream area limit.  This prevents accidental world-scale incident pulls.
    if (north - south) * (east - west) > 25:
        return {"ok": False, "configured": True, "detail": "zoom_in_for_incidents", "incidents": []}
    params = {
        "apiVersion": "2",
        "bbox": f"{west:.6f},{south:.6f},{east:.6f},{north:.6f}",
        "timeValidity": "present",
    }
    url = f"{_TOMTOM}/maps/orbis/traffic/incidents/details?{urlencode(params)}"
    attributes = (
        "incidents(type,geometry(type,coordinates),properties("
        "id,iconCategory,magnitudeOfDelay,events(description,code,iconCategory),"
        "startTime,endTime,from,to,lengthInMeters,delayInSeconds,roadNumbers,timeValidity,"
        "probabilityOfOccurrence,numberOfReports,lastReportTime))"
    )
    try:
        res = requests.get(
            url,
            headers={
                "TomTom-Api-Key": key,
                "TomTom-Api-Version": "2",
                "Attributes": attributes,
                "Accept-Language": "tr-TR",
                "User-Agent": outbound_user_agent("tomtom-incidents"),
                "Accept": "application/json",
                "Accept-Encoding": "identity",
            },
            timeout=(3, 12),
        )
        if res.status_code != 200:
            return Response(status_code=502)
        payload = res.json()
        incidents = payload.get("incidents") if isinstance(payload, dict) else []
        return {
            "ok": True,
            "configured": True,
            "source": "TomTom Traffic",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "incidents": incidents if isinstance(incidents, list) else [],
        }
    except (requests.RequestException, ValueError):
        return Response(status_code=502)
