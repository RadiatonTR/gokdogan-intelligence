"""Kamuya açık/yetkili OSINT operasyon uçları — Gökdoğan Intelligence v1.0.0.

This router intentionally exposes only public/authorized data.  It does not
implement private CCTV discovery, hidden services, live police-unit tracking,
or non-public sensitive military telemetry.
"""
from __future__ import annotations

import os
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Query, Request

from limiter import limiter
from services.fetch_health import get_health_snapshot
from services.fetchers._store import _data_lock, latest_data, source_timestamps
from services.integration_readiness import integration_readiness_snapshot, request_integration_refresh
from services.network_utils import fetch_with_curl, outbound_user_agent

router = APIRouter()


_PROBE_LOCK = threading.Lock()
_PROBE_RESULTS: dict[str, dict[str, Any]] = {}
_TESTABLE_PROVIDER_IDS: tuple[str, ...] = (
    "open_meteo", "rainviewer", "usgs_earthquakes", "nasa_eonet", "gdacs",
    "cbp_border_wait", "celestrak", "gdelt", "yfinance",
    "finnhub_api_key", "tomtom_api_key", "opensky_client_id", "shodan_api_key",
)
_CATEGORY_TR = {
    "Aviation": "HAVACILIK", "Maritime": "DENİZCİLİK", "Geophysical": "JEOFİZİK",
    "Space": "UZAY", "Intelligence": "İSTİHBARAT", "Geolocation": "COĞRAFİ KONUM",
    "Weather": "HAVA", "Financial": "FİNANS", "Markets": "PİYASALAR",
    "SIGINT": "SİNYAL İSTİHBARATI", "Reconnaissance": "KEŞİF",
    "Cyber Intelligence": "SİBER İSTİHBARAT", "Imagery": "GÖRÜNTÜLEME",
    "Traffic / CCTV": "TRAFİK / KAMERALAR", "Borders / Traffic": "SINIR / TRAFİK",
    "Disaster / Earth Observation": "AFET / YER GÖZLEMİ",
    "Disaster / Humanitarian": "AFET / İNSANİ YARDIM",
}
_MODE_TR = {
    "scheduled": "ZAMANLANMIŞ", "on_demand": "İSTEK ÜZERİNE", "tiles": "HARİTA KATMANI",
    "manual_only": "YALNIZ MANUEL", "external": "HARİCÎ SERVİS",
    "external_optional": "İSTEĞE BAĞLI HARİCÎ", "intelligence_core": "İSTİHBARAT MERKEZİ",
    "enrichment": "ZENGİNLEŞTİRME", "configuration": "YAPILANDIRMA",
}
_STATE_TR = {
    "live": "CANLI", "stale": "BAYAT", "ready": "HAZIR", "warming": "ISINIYOR",
    "needs_key": "ANAHTAR EKSİK", "partial_config": "EKSİK ÇİFT",
}


def _remember_probe(integration_id: str, result: dict[str, Any]) -> dict[str, Any]:
    clean = {
        "ok": bool(result.get("ok")),
        "status": result.get("status"),
        "latency_ms": result.get("latency_ms"),
        "detail": result.get("detail"),
        "tested_at": result.get("tested_at") or _iso_now(),
    }
    with _PROBE_LOCK:
        _PROBE_RESULTS[integration_id] = clean
    return clean


def _probe_snapshot() -> dict[str, dict[str, Any]]:
    with _PROBE_LOCK:
        return {key: dict(value) for key, value in _PROBE_RESULTS.items()}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return 0.0
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return 0.0


def _news_ts(item: dict[str, Any]) -> float:
    for key in ("published_at", "published", "timestamp", "date", "datetime", "seendate", "created_at"):
        ts = _parse_dt(item.get(key))
        if ts:
            return ts
    return 0.0


def _news_title(item: dict[str, Any]) -> str:
    return str(
        item.get("title_translated")
        or item.get("headline_translated")
        or item.get("title")
        or item.get("headline")
        or item.get("name")
        or ""
    ).strip()


def _news_summary(item: dict[str, Any]) -> str:
    return str(
        item.get("description_translated")
        or item.get("summary_translated")
        or item.get("summary")
        or item.get("description")
        or item.get("text")
        or ""
    ).strip()


def _news_url(item: dict[str, Any]) -> str:
    value = str(item.get("url") or item.get("link") or item.get("source_url") or "").strip()
    return value if value.startswith(("https://", "http://")) else ""


def _dedupe_news(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in sorted(rows, key=_news_ts, reverse=True):
        title = _news_title(item)
        if not title:
            continue
        key = re.sub(r"[^a-z0-9çğıöşü]+", " ", title.lower()).strip()[:180]
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _collect_news_rows() -> list[dict[str, Any]]:
    with _data_lock:
        rss = list(latest_data.get("news") or [])
        gdelt = list(latest_data.get("gdelt") or [])
        crowd = list(latest_data.get("crowdthreat") or [])
        telegram = dict(latest_data.get("telegram_osint") or {})
    rows: list[dict[str, Any]] = []
    for provider, values in (("RSS", rss), ("GDELT", gdelt), ("CrowdThreat", crowd)):
        for raw in values:
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            item.setdefault("provider", provider)
            item.setdefault("source", provider)
            rows.append(item)
    for raw in telegram.get("posts") or []:
        if isinstance(raw, dict):
            item = dict(raw)
            item.setdefault("provider", "Telegram OSINT")
            rows.append(item)
    return rows


def _filter_news_scope(rows: list[dict[str, Any]], scope: str) -> list[dict[str, Any]]:
    if scope == "local":
        local_tokens = (
            "turkey", "türkiye", "istanbul", "ankara", "izmir", "edirne", "gaziantep",
            "diyarbakır", "adana", "antalya", "bursa", "konya", "samsun", "trabzon", "turkish",
        )
        local_providers = {"trt haber", "anadolu ajansı", "anadolu ajansi"}
        return [
            row for row in rows
            if str(row.get("provider") or row.get("source") or "").lower() in local_providers
            or any(tok in (" " + _news_title(row).lower() + " " + str(row.get("country") or "").lower()) for tok in local_tokens)
        ]
    if scope == "global":
        local_tokens = ("turkey", "türkiye", "istanbul", "ankara", "izmir")
        return [row for row in rows if not any(tok in (" " + _news_title(row).lower() + " ") for tok in local_tokens)]
    return rows


def _normalize_news(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": _news_title(row),
        "summary": _news_summary(row)[:700],
        "url": _news_url(row),
        "provider": str(row.get("provider") or row.get("source") or "Açık kaynak"),
        "published_at": row.get("published_at") or row.get("published") or row.get("timestamp") or row.get("date"),
        "lat": row.get("lat"),
        "lng": row.get("lng") or row.get("lon"),
        "country": row.get("country"),
        "risk": row.get("risk") or row.get("severity") or row.get("threat_level"),
        "source_lang": row.get("source_lang"),
        "source_lang_label": row.get("source_lang_label"),
    }


def _translate_news_to_turkish(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if str(os.environ.get("GOKDOGAN_NEWS_AUTO_TRANSLATE", "true")).strip().lower() in {"0", "false", "no", "off"}:
        return items
    try:
        translation_limit = max(0, min(40, int(os.environ.get("GOKDOGAN_NEWS_TRANSLATION_LIMIT", "24"))))
    except ValueError:
        translation_limit = 24
    if translation_limit <= 0:
        return items

    def translate_one(item: dict[str, Any]) -> dict[str, Any]:
        from services.telegram_translate import source_lang_label, translate_text
        updated = dict(item)
        original_title = str(updated.get("title") or "").strip()
        original_summary = str(updated.get("summary") or "").strip()
        if not original_title:
            return updated
        translated_title, source_lang = translate_text(original_title, "tr")
        updated["title_original"] = original_title
        updated["title"] = translated_title or original_title
        if original_summary:
            translated_summary, _ = translate_text(original_summary[:900], "tr")
            updated["summary_original"] = original_summary
            updated["summary"] = translated_summary or original_summary
        updated["source_lang"] = source_lang
        updated["source_lang_label"] = source_lang_label(source_lang)
        updated["translation_target"] = "tr"
        return updated

    head = items[:translation_limit]
    if not head:
        return items
    translated: list[dict[str, Any] | None] = [None] * len(head)
    with ThreadPoolExecutor(max_workers=min(6, len(head)), thread_name_prefix="news-tr") as pool:
        futures = {pool.submit(translate_one, item): idx for idx, item in enumerate(head)}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                translated[idx] = future.result()
            except Exception:
                translated[idx] = head[idx]
    return [row if row is not None else head[idx] for idx, row in enumerate(translated)] + items[len(head):]


@router.get("/api/public-intel/breaking-news")
@limiter.limit("60/minute")
async def breaking_news(
    request: Request,
    scope: str = Query("all", pattern="^(all|global|local)$"),
    limit: int = Query(40, ge=10, le=120),
    turkish: bool = Query(True),
):
    """Kamuya açık beslemelerden tekilleştirilmiş yerel/küresel son dakika akışı."""
    rows = _filter_news_scope(_collect_news_rows(), scope)
    normalized = [_normalize_news(row) for row in _dedupe_news(rows, limit)]
    if turkish:
        normalized = _translate_news_to_turkish(normalized)
    return {
        "ok": True,
        "scope": scope,
        "language": "tr" if turkish else "source",
        "items": normalized,
        "total": len(normalized),
        "generated_at": _iso_now(),
    }


_DIPLOMACY_RE = re.compile(
    r"\b(agreement|treaty|accord|memorandum|mou|summit|bilateral|diplomatic|talks|meeting|signed|ceasefire|"
    r"anlaşma|antlaşma|mutabakat|protokol|zirve|diplomatik|görüşme|toplantı|imzalandı|ateşkes|iş\s*birliği)\b",
    re.IGNORECASE,
)


@router.get("/api/public-intel/diplomacy")
@limiter.limit("60/minute")
async def diplomacy(request: Request, limit: int = Query(40, ge=10, le=100)):
    """Açık haber kaynaklarından diplomasi/anlaşma/toplantı sinyallerini çıkarır."""
    candidates: list[dict[str, Any]] = []
    for row in _collect_news_rows():
        blob = f"{_news_title(row)} {_news_summary(row)}"
        if _DIPLOMACY_RE.search(blob):
            candidates.append(row)
    items = [_normalize_news(row) for row in _dedupe_news(candidates, limit)]
    items = _translate_news_to_turkish(items)
    return {
        "ok": True,
        "items": items,
        "total": len(items),
        "generated_at": _iso_now(),
        "scope_note": "Bu akış resmî antlaşma sicili değildir; kamuya açık haber/OSINT kaynaklarındaki diplomasi ve anlaşma sinyallerini bir araya getirir.",
    }


def _as_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _http_url(value: Any) -> str:
    text = str(value or "").strip()
    return text if text.startswith(("https://", "http://")) else ""


@router.get("/api/public-intel/public-cameras")
@limiter.limit("60/minute")
async def public_cameras(request: Request, limit: int = Query(300, ge=10, le=1000)):
    """Yalnız CCTV pipeline tarafından kamuya açık/yetkili olarak alınmış kamera kayıtları."""
    with _data_lock:
        rows = list(latest_data.get("cctv") or [])
    out: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        lat = _as_float(raw.get("lat", raw.get("latitude")))
        lng = _as_float(raw.get("lng", raw.get("lon", raw.get("longitude"))))
        media = _http_url(raw.get("media_url") or raw.get("stream_url") or raw.get("snapshot_url"))
        if lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180):
            continue
        out.append({
            "id": str(raw.get("id") or raw.get("camera_id") or f"cam-{len(out)+1}"),
            "name": str(raw.get("name") or raw.get("direction_facing") or raw.get("location") or "Kamu kamerası")[:160],
            "source_agency": str(raw.get("source_agency") or raw.get("source") or "Kamu kamera kaynağı")[:120],
            "lat": lat,
            "lng": lng,
            "media_url": media,
            "media_type": str(raw.get("media_type") or "image"),
            "refresh_rate_seconds": raw.get("refresh_rate_seconds"),
            "public_access": True,
        })
        if len(out) >= limit:
            break
    return {
        "ok": True,
        "items": out,
        "total": len(out),
        "updated_at": source_timestamps.get("cctv"),
        "generated_at": _iso_now(),
        "scope_note": "Yalnız kamuya açık/yetkili kataloglardan gelen kameralar gösterilir; özel/kapalı kamera keşfi yapılmaz.",
    }


def _aircraft_is_sensitive_or_targeted(row: dict[str, Any]) -> bool:
    blob = " ".join(
        str(row.get(key) or "")
        for key in ("type", "category", "source", "operator", "airline", "airline_name", "name", "tags", "alert_category")
    ).lower()
    return any(token in blob for token in (
        "military", "air force", "army", "navy", "coast guard", "presidential", "government vip",
        "private jet", "private / ga", "tracked", "potus", "asker", "özel jet",
    )) or bool(row.get("alert_category") or row.get("vip") or row.get("tracked"))


def _ship_is_sensitive_or_targeted(row: dict[str, Any]) -> bool:
    blob = " ".join(
        str(row.get(key) or "")
        for key in ("type", "ship_type", "vessel_type", "category", "source", "operator", "name", "alert_category", "alert_operator")
    ).lower()
    return any(token in blob for token in (
        "military", "navy", "warship", "coast guard", "carrier", "donanma", "savaş gem", "asker",
        "tracked yacht", "yacht alert", "plan navy", "people's liberation army navy", "ccg", "law enforcement",
    )) or bool(row.get("alert_category") or row.get("yacht_alert") or row.get("plan_vessel"))


def _civilian_aircraft(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("icao24") or row.get("id") or row.get("callsign") or ""),
        "callsign": str(row.get("callsign") or "").strip(),
        "registration": str(row.get("registration") or "").strip(),
        "airline": str(row.get("airline_name") or row.get("airline") or row.get("operator") or "").strip(),
        "model": str(row.get("model") or row.get("aircraft_type") or "").strip(),
        "origin": row.get("origin") or row.get("origin_iata") or row.get("departure_airport"),
        "destination": row.get("destination") or row.get("destination_iata") or row.get("arrival_airport"),
        "lat": _as_float(row.get("lat")),
        "lng": _as_float(row.get("lng", row.get("lon"))),
        "altitude": row.get("altitude") or row.get("altitude_ft"),
        "speed": row.get("speed") or row.get("ground_speed") or row.get("velocity"),
        "heading": row.get("heading") or row.get("track"),
        "first_seen": row.get("first_seen") or row.get("departure_time"),
        "last_seen": row.get("last_seen") or row.get("_seen_at"),
        "flight_number": row.get("flight_number") or row.get("flight") or row.get("callsign"),
        "scheduled_departure": row.get("scheduled_departure") or row.get("departure_time"),
        "scheduled_arrival": row.get("scheduled_arrival") or row.get("arrival_time"),
    }


def _civilian_vessel(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("mmsi") or row.get("imo") or row.get("id") or ""),
        "name": str(row.get("name") or row.get("ship_name") or "").strip(),
        "mmsi": str(row.get("mmsi") or "").strip(),
        "imo": str(row.get("imo") or "").strip(),
        "vessel_type": str(row.get("ship_type") or row.get("vessel_type") or row.get("type") or "").strip(),
        "flag": row.get("flag") or row.get("flag_state") or row.get("country"),
        "destination": row.get("destination"),
        "origin": row.get("origin") or row.get("departure_port"),
        "lat": _as_float(row.get("lat")),
        "lng": _as_float(row.get("lng", row.get("lon"))),
        "speed": row.get("speed") or row.get("sog"),
        "course": row.get("course") or row.get("cog") or row.get("heading"),
        "eta": row.get("eta"),
        "last_seen": row.get("last_seen") or row.get("timestamp") or row.get("_seen_at"),
    }


@router.get("/api/public-intel/civilian-movement")
@limiter.limit("60/minute")
async def civilian_movement(request: Request, limit: int = Query(120, ge=10, le=300)):
    """Sivil/ticari hava ve deniz hareketlerinin kamuya açık/yetkili birleşik görünümü."""
    with _data_lock:
        aircraft_raw = list(latest_data.get("commercial_flights") or [])
        ships_raw = list(latest_data.get("ships") or [])
    aircraft = [_civilian_aircraft(row) for row in aircraft_raw if isinstance(row, dict) and not _aircraft_is_sensitive_or_targeted(row)][:limit]
    vessels = [_civilian_vessel(row) for row in ships_raw if isinstance(row, dict) and not _ship_is_sensitive_or_targeted(row)][:limit]
    return {
        "ok": True,
        "aircraft": aircraft,
        "vessels": vessels,
        "counts": {"aircraft": len(aircraft), "vessels": len(vessels)},
        "updated_at": {
            "aircraft": source_timestamps.get("commercial_flights"),
            "vessels": source_timestamps.get("ships"),
        },
        "generated_at": _iso_now(),
        "scope_note": "Bu toplu görünüm ticari/sivil hareketlerle sınırlıdır; özel kişi hedefli ve hassas askerî canlı takip kayıtlarını içermez.",
    }


def _trail_metrics(points: list[Any]) -> dict[str, Any]:
    cleaned: list[list[Any]] = []
    timestamps: list[float] = []
    for raw in points[-200:]:
        if not isinstance(raw, (list, tuple)) or len(raw) < 2:
            continue
        lat = _as_float(raw[0])
        lng = _as_float(raw[1])
        if lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180):
            continue
        point = list(raw[:4])
        cleaned.append(point)
        if len(raw) >= 4:
            ts = _as_float(raw[3])
            if ts and ts > 0:
                timestamps.append(ts)
    duration = max(timestamps) - min(timestamps) if len(timestamps) >= 2 else None
    return {
        "points": cleaned,
        "point_count": len(cleaned),
        "observed_duration_seconds": round(duration) if duration is not None else None,
        "first_observed_at": datetime.fromtimestamp(min(timestamps), timezone.utc).isoformat() if timestamps else None,
        "last_observed_at": datetime.fromtimestamp(max(timestamps), timezone.utc).isoformat() if timestamps else None,
    }


def _find_commercial_aircraft(identifier: str) -> dict[str, Any] | None:
    needle = str(identifier or "").strip().lower()
    if not needle:
        return None
    with _data_lock:
        rows = list(latest_data.get("commercial_flights") or [])
    for raw in rows:
        if not isinstance(raw, dict) or _aircraft_is_sensitive_or_targeted(raw):
            continue
        ids = {
            str(raw.get("icao24") or "").strip().lower(),
            str(raw.get("id") or "").strip().lower(),
            str(raw.get("callsign") or "").strip().lower(),
            str(raw.get("registration") or "").strip().lower(),
        }
        if needle in ids:
            return raw
    return None


@router.get("/api/public-intel/civilian-aircraft/{identifier}")
@limiter.limit("60/minute")
async def civilian_aircraft_detail(request: Request, identifier: str):
    """Ayrıntılı kamuya açık sivil/ticari uçuş özeti ve bu oturumda gözlenen rota izi."""
    raw = _find_commercial_aircraft(identifier)
    if raw is None:
        return {"ok": False, "detail": "Sivil/ticari hava aracı bulunamadı veya güvenli kapsam dışında."}
    item = _civilian_aircraft(raw)
    try:
        from services.fetchers.flights import get_flight_trail
        trail = get_flight_trail(str(raw.get("icao24") or raw.get("id") or identifier))
    except Exception:
        trail = []
    return {
        "ok": True,
        "aircraft": item,
        "trail": _trail_metrics(list(trail or [])),
        "updated_at": source_timestamps.get("commercial_flights"),
        "generated_at": _iso_now(),
        "scope_note": "Yalnız sivil/ticari açık kaynak gözlemleri; hassas askerî veya özel kişi hedefli kayıt yoktur.",
    }


def _find_civilian_vessel(identifier: str) -> dict[str, Any] | None:
    needle = str(identifier or "").strip().lower()
    if not needle:
        return None
    with _data_lock:
        rows = list(latest_data.get("ships") or [])
    for raw in rows:
        if not isinstance(raw, dict) or _ship_is_sensitive_or_targeted(raw):
            continue
        ids = {
            str(raw.get("mmsi") or "").strip().lower(),
            str(raw.get("imo") or "").strip().lower(),
            str(raw.get("id") or "").strip().lower(),
            str(raw.get("name") or raw.get("ship_name") or "").strip().lower(),
        }
        if needle in ids:
            return raw
    return None


@router.get("/api/public-intel/civilian-vessel/{identifier}")
@limiter.limit("60/minute")
async def civilian_vessel_detail(request: Request, identifier: str):
    """Ayrıntılı kamuya açık sivil/ticari gemi özeti ve bu oturumda gözlenen rota izi."""
    raw = _find_civilian_vessel(identifier)
    if raw is None:
        return {"ok": False, "detail": "Sivil/ticari deniz aracı bulunamadı veya güvenli kapsam dışında."}
    item = _civilian_vessel(raw)
    try:
        from services.ais_stream import get_vessel_trail
        mmsi = int(str(raw.get("mmsi") or identifier))
        trail = get_vessel_trail(mmsi)
    except Exception:
        trail = []
    return {
        "ok": True,
        "vessel": item,
        "trail": _trail_metrics(list(trail or [])),
        "updated_at": source_timestamps.get("ships"),
        "generated_at": _iso_now(),
        "scope_note": "Yalnız sivil/ticari açık kaynak gözlemleri; hassas askerî veya özel kişi hedefli kayıt yoktur.",
    }


@router.get("/api/public-intel/conflict-regions")
@limiter.limit("60/minute")
async def conflict_regions(request: Request, limit: int = Query(120, ge=10, le=300)):
    """Kamuya açık olay beslemelerinden bölgesel çatışma sinyali; taktik hassasiyet bilinçli olarak azaltılır."""
    with _data_lock:
        gdelt = list(latest_data.get("gdelt") or [])
        crowd = list(latest_data.get("crowdthreat") or [])
        frontlines = list(latest_data.get("frontlines") or [])
    rows: list[dict[str, Any]] = []
    for provider, values in (("GDELT", gdelt), ("CrowdThreat", crowd)):
        for raw in values:
            if not isinstance(raw, dict):
                continue
            lat = _as_float(raw.get("lat", raw.get("latitude")))
            lng = _as_float(raw.get("lng", raw.get("lon", raw.get("longitude"))))
            rows.append({
                "title": _news_title(raw) or str(raw.get("event") or raw.get("description") or "Çatışma/gerilim olayı")[:220],
                "provider": str(raw.get("provider") or raw.get("source") or provider),
                "country": raw.get("country") or raw.get("region"),
                "category": raw.get("category") or raw.get("type") or raw.get("event_type"),
                "severity": raw.get("severity") or raw.get("risk") or raw.get("threat_level"),
                # Coarse regional position (~11 km at equator); not a tactical live target coordinate.
                "lat": round(lat, 1) if lat is not None else None,
                "lng": round(lng, 1) if lng is not None else None,
                "published_at": raw.get("published_at") or raw.get("timestamp") or raw.get("date"),
                "url": _news_url(raw),
            })
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break
    return {
        "ok": True,
        "items": rows[:limit],
        "total": len(rows[:limit]),
        "frontline_feature_count": len(frontlines),
        "generated_at": _iso_now(),
        "scope_note": "Bölgesel açık kaynak durum farkındalığıdır. Canlı taktik birlik konumu, gizli tesis veya hedeflenebilir hassas askerî telemetri sunulmaz.",
    }


@router.get("/api/public-intel/disasters")
@limiter.limit("60/minute")
async def disasters(request: Request, limit: int = Query(300, ge=10, le=1000)):
    with _data_lock:
        snapshot = dict(latest_data.get("global_disasters") or {})
        earthquakes = list(latest_data.get("earthquakes") or [])
        fires = list(latest_data.get("firms_fires") or [])
        volcanoes = list(latest_data.get("volcanoes") or [])
        weather_alerts = list(latest_data.get("weather_alerts") or [])
    return {
        "ok": True,
        "global": (snapshot.get("events") or [])[:limit],
        "sources": snapshot.get("sources") or {},
        "updated_at": snapshot.get("updated_at"),
        "layer_counts": {
            "earthquakes": len(earthquakes),
            "fires": len(fires),
            "volcanoes": len(volcanoes),
            "weather_alerts": len(weather_alerts),
        },
    }


@router.get("/api/public-intel/borders")
@limiter.limit("60/minute")
async def borders(request: Request, limit: int = Query(200, ge=10, le=500)):
    with _data_lock:
        snapshot = dict(latest_data.get("border_status") or {})
    return {
        "ok": True,
        "crossings": (snapshot.get("crossings") or [])[:limit],
        "sources": snapshot.get("sources") or {},
        "updated_at": snapshot.get("updated_at"),
        "scope_note": "Resmî/açık bekleme süreleri, kamu kamera metadatası ve koridor eğilimleri; kapalı kontrol noktaları veya canlı kolluk konumları yoktur.",
    }


def _age_seconds(iso_value: Any) -> float | None:
    ts = _parse_dt(iso_value)
    if not ts:
        return None
    return max(0.0, time.time() - ts)


@router.get("/api/public-intel/provider-health")
@limiter.limit("60/minute")
async def provider_health(request: Request):
    readiness = integration_readiness_snapshot()
    health = get_health_snapshot()
    with _data_lock:
        timestamps = dict(source_timestamps)
    rows = []
    probes = _probe_snapshot()
    for row in readiness.get("integrations") or []:
        item = dict(row)
        last = item.get("last_success_at")
        item["age_seconds"] = _age_seconds(last)
        state = str(item.get("state") or "")
        item["turkish_state"] = _STATE_TR.get(state, state.upper() or "BİLİNMİYOR")
        item["turkish_category"] = _CATEGORY_TR.get(str(item.get("category") or ""), str(item.get("category") or ""))
        item["turkish_mode"] = _MODE_TR.get(str(item.get("mode") or ""), str(item.get("mode") or ""))
        item["last_probe"] = probes.get(str(item.get("id") or ""))
        rows.append(item)
    return {
        "ok": True,
        "counts": readiness.get("counts") or {},
        "integrations": rows,
        "capabilities": readiness.get("capabilities") or [],
        "task_health": health,
        "source_timestamps": timestamps,
        "generated_at": _iso_now(),
    }


def _probe_json(url: str, *, headers: dict[str, str] | None = None, timeout: int = 12) -> dict[str, Any]:
    started = time.perf_counter()
    response = fetch_with_curl(url, timeout=timeout, headers={"Accept-Encoding": "identity", **(headers or {})})
    elapsed = round((time.perf_counter() - started) * 1000)
    if response.status_code < 200 or response.status_code >= 300:
        return {"ok": False, "status": response.status_code, "latency_ms": elapsed}
    try:
        payload = response.json()
    except Exception:
        payload = None
    return {"ok": True, "status": response.status_code, "latency_ms": elapsed, "json": isinstance(payload, (dict, list))}


def _test_provider(integration_id: str) -> dict[str, Any]:
    integration_id = str(integration_id or "").strip()
    if integration_id == "open_meteo":
        return _probe_json("https://api.open-meteo.com/v1/forecast?latitude=41.015&longitude=28.979&current=temperature_2m")
    if integration_id == "rainviewer":
        return _probe_json("https://api.rainviewer.com/public/weather-maps.json")
    if integration_id == "nasa_eonet":
        return _probe_json("https://eonet.gsfc.nasa.gov/api/v3/events?status=open&limit=1")
    if integration_id == "gdacs":
        return _probe_json("https://www.gdacs.org/contentdata/xml/gdacs.geojson")
    if integration_id == "cbp_border_wait":
        started = time.perf_counter()
        res = fetch_with_curl("https://bwt.cbp.gov/ViewAllPorts", timeout=12, headers={"Accept": "text/html", "Accept-Encoding": "identity"})
        return {"ok": res.status_code == 200, "status": res.status_code, "latency_ms": round((time.perf_counter() - started) * 1000)}
    if integration_id == "finnhub_api_key":
        key = os.environ.get("FINNHUB_API_KEY", "").strip()
        if not key:
            return {"ok": False, "detail": "api_key_required"}
        return _probe_json(f"https://finnhub.io/api/v1/quote?symbol=AAPL&token={key}")
    if integration_id == "tomtom_api_key":
        key = os.environ.get("TOMTOM_API_KEY", "").strip()
        if not key:
            return {"ok": False, "detail": "api_key_required"}
        started = time.perf_counter()
        url = "https://api.tomtom.com/maps/orbis/traffic/flow/raster/tile/0/0/0?apiVersion=2&style=dark&tileSize=256"
        res = requests.get(url, headers={"TomTom-Api-Key": key, "User-Agent": outbound_user_agent("provider-test"), "Accept-Encoding": "identity"}, timeout=(3, 10))
        return {"ok": res.status_code == 200, "status": res.status_code, "latency_ms": round((time.perf_counter() - started) * 1000)}
    if integration_id in {"opensky_client_id", "opensky_client_secret"}:
        client_id = os.environ.get("OPENSKY_CLIENT_ID", "").strip()
        secret = os.environ.get("OPENSKY_CLIENT_SECRET", "").strip()
        if not client_id or not secret:
            return {"ok": False, "detail": "client_id_and_secret_required"}
        started = time.perf_counter()
        res = requests.post(
            "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token",
            data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": secret},
            headers={"Accept": "application/json", "Accept-Encoding": "identity", "User-Agent": outbound_user_agent("opensky-auth-test")},
            timeout=(3, 12),
        )
        ok = res.status_code == 200 and bool((res.json() if res.headers.get("content-type", "").startswith("application/json") else {}).get("access_token"))
        return {"ok": ok, "status": res.status_code, "latency_ms": round((time.perf_counter() - started) * 1000)}
    if integration_id == "shodan_api_key":
        key = os.environ.get("SHODAN_API_KEY", "").strip()
        if not key:
            return {"ok": False, "detail": "api_key_required"}
        return _probe_json(f"https://api.shodan.io/api-info?key={key}")
    if integration_id == "usgs_earthquakes":
        return _probe_json("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson")
    if integration_id == "celestrak":
        return _probe_json("https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=json")
    if integration_id == "gdelt":
        return _probe_json("https://api.gdeltproject.org/api/v2/doc/doc?query=Turkey&mode=ArtList&maxrecords=1&format=json")
    if integration_id == "yfinance":
        return _probe_json("https://query1.finance.yahoo.com/v8/finance/chart/AAPL?range=1d&interval=5m")

    readiness = integration_readiness_snapshot()
    row = next((x for x in readiness.get("integrations") or [] if x.get("id") == integration_id), None)
    if row:
        return {"ok": row.get("state") in {"live", "ready"}, "detail": "readiness_only", "state": row.get("state"), "records": row.get("records")}
    return {"ok": False, "detail": "unknown_integration"}


@router.post("/api/public-intel/provider-test/{integration_id}")
@limiter.limit("20/minute")
async def provider_test(request: Request, integration_id: str):
    result = _test_provider(integration_id)
    result["integration_id"] = integration_id
    result["tested_at"] = _iso_now()
    _remember_probe(integration_id, result)
    return result


@router.post("/api/public-intel/provider-test-all")
@limiter.limit("4/minute")
async def provider_test_all(request: Request):
    """Safely probe public/configured providers without exposing credentials."""
    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="provider-probe") as pool:
        futures = {pool.submit(_test_provider, provider_id): provider_id for provider_id in _TESTABLE_PROVIDER_IDS}
        for future in as_completed(futures):
            provider_id = futures[future]
            try:
                result = dict(future.result())
            except Exception as exc:
                result = {"ok": False, "detail": f"probe_error:{type(exc).__name__}"}
            result["integration_id"] = provider_id
            result["tested_at"] = _iso_now()
            _remember_probe(provider_id, result)
            results[provider_id] = result
    return {
        "ok": True,
        "tested": len(results),
        "passed": sum(1 for row in results.values() if row.get("ok")),
        "results": results,
        "tested_at": _iso_now(),
    }


@router.post("/api/public-intel/provider-refresh/{integration_id}")
@limiter.limit("20/minute")
async def provider_refresh(request: Request, integration_id: str):
    return request_integration_refresh(integration_id)


@router.get("/api/public-intel/entity-movement")
@limiter.limit("60/minute")
async def entity_movement(
    request: Request,
    entity_type: str = Query(""),
    icao24: str = Query(""),
    callsign: str = Query(""),
    registration: str = Query(""),
    mmsi: str = Query(""),
    imo: str = Query(""),
    name: str = Query(""),
):
    from services.entity_trail import get_entity_trail

    result = get_entity_trail(
        entity_type=entity_type,
        icao24=icao24,
        callsign=callsign,
        registration=registration,
        mmsi=mmsi,
        imo=imo,
        name=name,
        max_points=160,
        include_datalink=True,
    )
    # Translate only product-authored notes; source fields remain untouched.
    result["notes"] = [
        str(note)
        .replace("No matching aircraft or vessel in live layers.", "Canlı katmanlarda eşleşen hava veya deniz aracı bulunamadı.")
        .replace("Trails accumulate while ShadowBroker is running; they are not pre-flight history.", "Rota izi Gökdoğan çalışırken birikir; uçuş öncesi geçmiş değildir.")
        .replace("Trail points are observed positions since this ShadowBroker instance started tracking the entity.", "Rota noktaları bu Gökdoğan oturumu aracı izlemeye başladığından beri gözlenen konumlardır.")
        .replace("Use Time Machine snapshots for longer historical playback when enabled.", "Daha uzun geçmiş için etkinse Zaman Makinesi kayıtlarını kullanın.")
        .replace("No trail points yet — the entity may have just appeared or trail retention expired.", "Henüz rota noktası yok; araç yeni görünmüş veya rota saklama süresi dolmuş olabilir.")
        .replace("Route origin/destination unknown; infer direction from trail bearing only.", "Kalkış/varış bilinmiyor; yalnız gözlenen rota yönü kullanılabilir.")
        for note in (result.get("notes") or [])
    ]
    return result
