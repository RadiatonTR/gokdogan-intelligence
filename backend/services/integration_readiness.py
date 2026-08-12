"""Operator-visible integration readiness and safe refresh orchestration.

This module never exposes secret values.  It turns the API registry plus the
live data store into an honest feature-readiness matrix so the desktop can tell
an operator whether a feature is active, waiting for a key, warming up, or
manual/external by design.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from services.api_settings import API_REGISTRY, load_persisted_api_keys_into_environ


@dataclass(frozen=True)
class IntegrationSpec:
    data_keys: tuple[str, ...] = ()
    refresh: str | None = None
    mode: str = "scheduled"
    note: str = ""
    stale_after_seconds: int | None = 1800


_SPECS: dict[str, IntegrationSpec] = {
    "opensky_client_id": IntegrationSpec(("commercial_flights", "tracked_flights"), "flights", note="OpenSky Client Secret ile eşleşir; adsb.lol anahtarsız yedek kaynak olarak kalır.", stale_after_seconds=180),
    "opensky_client_secret": IntegrationSpec(("commercial_flights", "tracked_flights"), "flights", note="OpenSky OAuth2 kimlik bilgisi çifti.", stale_after_seconds=180),
    "adsb_lol": IntegrationSpec(("commercial_flights", "tracked_flights"), "flights", note="Anahtarsız uçuş yedek kaynağı.", stale_after_seconds=180),
    "ais_api_key": IntegrationSpec(("ships",), "ships", note="Canlı AIS WebSocket; dış servis erişilebilirliğine bağlıdır.", stale_after_seconds=600),
    "aishub_username": IntegrationSpec(("ships",), "ships", note="İsteğe bağlı AIS yedek kaynağı.", stale_after_seconds=600),
    "gfw_api_token": IntegrationSpec(("fishing_activity",), "fishing", note="Balıkçılık etkinliği katmanı; canlı AIS gemilerinden ayrıdır.", stale_after_seconds=3600),
    "usgs_earthquakes": IntegrationSpec(("earthquakes",), "earthquakes", stale_after_seconds=1800),
    "firms_map_key": IntegrationSpec(("firms_fires",), "firms", note="Küresel yangın katmanı anahtarsız çalışır; anahtar ülke bazlı zenginleştirme ekler.", stale_after_seconds=1800),
    "airframes_api_key": IntegrationSpec((), "airframes", mode="enrichment", note="ACARS/VDL dosya zenginleştirmesi; harita konum kaynağı değildir.", stale_after_seconds=None),
    "celestrak": IntegrationSpec(("satellites",), "satellites", stale_after_seconds=7200),
    "gdelt": IntegrationSpec(("gdelt",), "gdelt", stale_after_seconds=1200),
    "rss_feeds": IntegrationSpec(("news",), "news", stale_after_seconds=1200),
    "yfinance": IntegrationSpec(("financial", "stocks", "crypto", "fx", "metals", "indices", "oil"), "financial", stale_after_seconds=1200),
    "finnhub_api_key": IntegrationSpec(("stocks", "unusual_whales"), "financial", note="İsteğe bağlı piyasa zenginleştirmesi; yfinance anahtarsız temel kaynak olarak kalır.", stale_after_seconds=1200),
    "openaq_api_key": IntegrationSpec(("air_quality",), "air_quality", stale_after_seconds=3600),
    "lta_account_key": IntegrationSpec(("cctv",), "cctv", note="Singapur kamu trafik kameralarını ekler.", stale_after_seconds=3600),
    "windy_api_key": IntegrationSpec(("cctv",), "cctv", note="Yapılandırılmış sağlayıcı üzerinden erişilebilen kamu webcamlerini ekler.", stale_after_seconds=3600),
    "public_camera_catalog_urls": IntegrationSpec(("cctv",), "cctv", note="Operatörün tanımladığı resmî kamu kamera katalogları; her kayıt kamu erişimini açıkça doğrulamalıdır.", stale_after_seconds=3600),
    "public_camera_catalog_hosts": IntegrationSpec(("cctv",), "cctv", mode="configuration", note="Resmî kamu kamera katalog sunucuları için izin listesi; yerel/özel ağlar reddedilir.", stale_after_seconds=None),
    "public_camera_media_hosts": IntegrationSpec(("cctv",), "cctv", mode="configuration", note="Ek resmî kamu kamera medya sunucuları için izin listesi; yalnız küresel yönlendirilebilir sunucular proxy edilir.", stale_after_seconds=None),
    "alerts_in_ua_token": IntegrationSpec(("ukraine_alerts",), "ukraine_alerts", stale_after_seconds=600),
    "nominatim": IntegrationSpec((), None, mode="on_demand", note="Operatör coğrafi kodlama istediğinde kullanılır.", stale_after_seconds=None),
    "rainviewer": IntegrationSpec((), None, mode="tiles", note="Harita radar karo katmanı; dış tile servisinin erişilebilirliğine bağlıdır.", stale_after_seconds=None),
    "open_meteo": IntegrationSpec((), None, mode="on_demand", note="Anahtarsız küresel hava tahmini ve sıcaklık geçmişi özetleri.", stale_after_seconds=None),
    "nasa_eonet": IntegrationSpec(("global_disasters",), "global_disasters", note="NASA EONET v3 kamu doğal olay akışı.", stale_after_seconds=3600),
    "gdacs": IntegrationSpec(("global_disasters",), "global_disasters", note="GDACS kamu afet uyarı/olay akışı.", stale_after_seconds=3600),
    "cbp_border_wait": IntegrationSpec(("border_status",), "border_status", note="Resmî ABD CBP kamu sınır bekleme tablosu ve Gökdoğan kamu koridor bağlamı.", stale_after_seconds=3600),
    "tomtom_api_key": IntegrationSpec((), None, mode="tiles", note="İsteğe bağlı gerçek zamanlı yol trafik akışı/olayları; anahtar yalnız backend tarafında tutulur.", stale_after_seconds=None),
    "openmhz": IntegrationSpec(("scanners",), "scanners", mode="on_demand", note="Kamu tarayıcı dizini/bağlantıları; ses erişimi dış servise bağlıdır.", stale_after_seconds=None),
    "shodan_api_key": IntegrationSpec((), None, mode="manual_only", note="Bilinçli olarak arka planda sorgulanmaz; sorgular operatör tarafından tetiklenir.", stale_after_seconds=None),
    "abuseipdb_api_key": IntegrationSpec((), None, mode="on_demand", note="Pasif IP itibar zenginleştirmesi; yalnız operatör IP sorguladığında çalışır.", stale_after_seconds=None),
    "sentinel_client_id": IntegrationSpec(("road_corridor_trends",), None, mode="on_demand", note="Sentinel Client Secret ile eşleşir; görüntü istekleri operatör/katman tarafından tetiklenir.", stale_after_seconds=None),
    "sentinel_client_secret": IntegrationSpec(("road_corridor_trends",), None, mode="on_demand", note="Sentinel Client ID ile eşleşir.", stale_after_seconds=None),
    "fred_api_key": IntegrationSpec((), None, mode="intelligence_core", note="Pasif makroekonomik bağdaştırıcı.", stale_after_seconds=None),
    "bls_api_key": IntegrationSpec((), None, mode="intelligence_core", note="Pasif işgücü/ekonomi bağdaştırıcısı.", stale_after_seconds=None),
    "eia_api_key": IntegrationSpec((), None, mode="intelligence_core", note="Pasif enerji/ekonomi bağdaştırıcısı.", stale_after_seconds=None),
    "reliefweb_appname": IntegrationSpec((), None, mode="intelligence_core", note="İnsani yardım/afet pasif bağdaştırıcısı.", stale_after_seconds=None),
    "opencti_url": IntegrationSpec((), None, mode="external", note="Operatöre ait OpenCTI sunucusu ve token gerekir.", stale_after_seconds=None),
    "opencti_token": IntegrationSpec((), None, mode="external", note="Operatöre ait OpenCTI sunucu URL'si gerekir.", stale_after_seconds=None),
    "opencti_connector_id": IntegrationSpec((), None, mode="external_optional", note="Yalnız push iş akışları için gereklidir.", stale_after_seconds=None),
    "nuforc_mapbox_token": IntegrationSpec(("uap_sightings",), None, mode="enrichment", note="İsteğe bağlı coğrafi zenginleştirme; gözlemler onsuz da yüklenebilir.", stale_after_seconds=None),
}

_PAIR_GROUPS: dict[str, tuple[str, ...]] = {
    "opensky_client_id": ("OPENSKY_CLIENT_ID", "OPENSKY_CLIENT_SECRET"),
    "opensky_client_secret": ("OPENSKY_CLIENT_ID", "OPENSKY_CLIENT_SECRET"),
    "sentinel_client_id": ("SENTINEL_CLIENT_ID", "SENTINEL_CLIENT_SECRET"),
    "sentinel_client_secret": ("SENTINEL_CLIENT_ID", "SENTINEL_CLIENT_SECRET"),
    "opencti_url": ("OPENCTI_URL", "OPENCTI_TOKEN"),
    "opencti_token": ("OPENCTI_URL", "OPENCTI_TOKEN"),
}


def _row_count(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, dict):
        # Market dictionaries and structured result envelopes count as populated
        # when they contain any non-empty payload.
        total = 0
        for item in value.values():
            if isinstance(item, (dict, list, tuple, set)):
                total += len(item)
            elif item not in (None, "", False):
                total += 1
        return total
    try:
        return len(value)
    except TypeError:
        return 1 if value else 0


def _timestamp_age_seconds(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return max(0.0, time.time() - float(value))
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, time.time() - dt.timestamp())
    except ValueError:
        return None


def _feature_state(api: dict[str, Any], spec: IntegrationSpec, values: dict[str, Any], timestamps: dict[str, Any]) -> tuple[str, int, str | None]:
    env_key = api.get("env_key")
    configured = True if not env_key else bool(os.environ.get(str(env_key), "").strip())
    group = _PAIR_GROUPS.get(str(api.get("id")))
    if group:
        present = [bool(os.environ.get(key, "").strip()) for key in group]
        if any(present) and not all(present):
            return "partial_config", 0, None
        configured = all(present)
    if env_key and not configured:
        # Only required credentials are an error-like readiness state. Optional
        # provider credentials are displayed separately and keyless fallbacks
        # remain usable where the integration supports them.
        return ("needs_key" if bool(api.get("required")) else "optional_key"), 0, None

    count = sum(_row_count(values.get(key)) for key in spec.data_keys)
    latest: str | None = None
    for key in spec.data_keys:
        ts = timestamps.get(key)
        if ts and (latest is None or str(ts) > latest):
            latest = str(ts)
    if count > 0:
        age = _timestamp_age_seconds(latest)
        if spec.stale_after_seconds and age is not None and age > spec.stale_after_seconds:
            return "stale", count, latest
        return "live", count, latest
    if spec.mode in {"manual_only", "on_demand", "tiles", "external", "external_optional", "intelligence_core", "enrichment"}:
        return "ready", 0, latest
    return "warming", 0, latest


def integration_readiness_snapshot() -> dict[str, Any]:
    load_persisted_api_keys_into_environ()
    from services.fetchers._store import get_latest_data_refs_snapshot, get_source_timestamps_snapshot

    values = get_latest_data_refs_snapshot()
    timestamps = get_source_timestamps_snapshot()
    integrations: list[dict[str, Any]] = []
    counts: dict[str, int] = {"live": 0, "stale": 0, "ready": 0, "warming": 0, "needs_key": 0, "optional_key": 0, "partial_config": 0}
    for api in API_REGISTRY:
        spec = _SPECS.get(str(api.get("id")), IntegrationSpec())
        state, records, last_success = _feature_state(api, spec, values, timestamps)
        counts[state] = counts.get(state, 0) + 1
        integrations.append({
            "id": api.get("id"),
            "name": api.get("name"),
            "category": api.get("category"),
            "url": api.get("url"),
            "required": bool(api.get("required")),
            "has_key": api.get("env_key") is not None,
            "env_key": api.get("env_key"),
            "configured": True if not api.get("env_key") else bool(os.environ.get(str(api.get("env_key")), "").strip()),
            "state": state,
            "records": records,
            "last_success_at": last_success,
            "mode": spec.mode,
            "refreshable": bool(spec.refresh),
            "stale_after_seconds": spec.stale_after_seconds,
            "note": spec.note,
        })

    # Honest capability flags for pieces that cannot become functional merely
    # by pasting an API key.
    try:
        from services.runtime_profile import get_runtime_profile
        profile = get_runtime_profile()
    except Exception:
        profile = {}
    capabilities = [
        {"id": "core_osint", "name": "Kamuya Açık OSINT Veri Motoru", "state": "ready", "detail": "Scheduler + API fallback veri yolu etkin."},
        {"id": "infonet_core", "name": "InfoNet temel düğüm/olay katmanı", "state": "ready", "detail": "Temel düğüm ve olay akışları mevcut; deneysel gizlilik kriptografisi production garantisi değildir."},
        {"id": "infonet_privacy", "name": "InfoNet deneysel gizlilik katmanı", "state": "experimental", "detail": "RingCT/stealth/ileri privacy scaffolding production özelliği olarak sunulmuyor."},
        {"id": "meshtastic_public", "name": "Meshtastic kamu harita verisi", "state": "ready", "detail": "Kamu harita kaynağı/cache ile çalışır; upstream hizmet bağımlıdır."},
        {"id": "meshtastic_hardware", "name": "Meshtastic USB/Bluetooth cihazı", "state": "hardware_required", "detail": "Fiziksel cihaz + mesh-hardware build profili gerektirir."},
        {"id": "host_shell", "name": "Host shell", "state": "disabled_by_design", "detail": "Güvenlik nedeniyle masaüstü runtime'da varsayılan kapalı tutulur."},
        {"id": "active_recon", "name": "Aktif ağ keşfi", "state": "disabled_by_design", "detail": "Varsayılan olarak kapalı; Shodan yalnızca operatör tetiklemeli sorgu katmanıdır."},
        {"id": "public_cameras", "name": "Kamuya açık / yetkili kameralar", "state": "ready", "detail": "Resmî trafik/sokak/kamu webcam katalogları desteklenir; özel veya kapalı ağ kameraları reddedilir."},
        {"id": "live_police_tracking", "name": "Canlı kolluk ekibi konumu", "state": "disabled_by_design", "detail": "Canlı polis/ekip takibi ve kaçınmayı kolaylaştıran operasyonel konum akışı sunulmaz."},
        {"id": "sensitive_military_telemetry", "name": "Gizli askerî telemetri", "state": "disabled_by_design", "detail": "Yalnız kamuya açık OSINT/ADS-B/AIS ve yayımlanmış stratejik kaynaklar kullanılır; gizli telemetri toplanmaz."},
        {"id": "submarine_live_positions", "name": "Canlı denizaltı konumları", "state": "source_limited", "detail": "Kamuya açık, doğrulanabilir yayın yoksa denizaltı konumu üretilmez veya tahmin edilmiş gerçek konum gibi gösterilmez."},
        {"id": "offline_mode", "name": "Çevrimdışı mod", "state": "enabled" if profile.get("offline_mode") else "disabled", "detail": "Açıksa uzak veri fetcher'ları bilinçli olarak durdurulur."},
    ]
    return {"ok": True, "counts": counts, "integrations": integrations, "capabilities": capabilities, "generated_at": time.time()}


_REFRESH_LOCK = threading.Lock()
_REFRESH_RUNNING: set[str] = set()


def _refresh_callable(group: str) -> Callable[[], Any]:
    if group == "flights":
        from services.fetchers.flights import fetch_flights
        return fetch_flights
    if group == "ships":
        from services.fetchers.geo import fetch_ships
        return fetch_ships
    if group == "fishing":
        from services.fetchers.geo import fetch_fishing_activity
        return fetch_fishing_activity
    if group == "earthquakes":
        from services.fetchers.earth_observation import fetch_earthquakes
        return fetch_earthquakes
    if group == "firms":
        from services.fetchers.earth_observation import fetch_firms_fires
        return fetch_firms_fires
    if group == "airframes":
        from services.fetchers.airframes import sync_airframes_messages
        return lambda: sync_airframes_messages(force=True)
    if group == "satellites":
        from services.fetchers.satellites import fetch_satellites
        return fetch_satellites
    if group == "gdelt":
        from services.fetchers.geo import fetch_gdelt
        return fetch_gdelt
    if group == "news":
        from services.fetchers.news import fetch_news
        return fetch_news
    if group == "financial":
        from services.fetchers.financial import fetch_financial_markets
        return fetch_financial_markets
    if group == "air_quality":
        from services.fetchers.earth_observation import fetch_air_quality
        return fetch_air_quality
    if group == "cctv":
        from services.fetchers.infrastructure import fetch_cctv
        return fetch_cctv
    if group == "ukraine_alerts":
        from services.fetchers.ukraine_alerts import fetch_ukraine_air_raid_alerts
        return fetch_ukraine_air_raid_alerts
    if group == "scanners":
        from services.fetchers.infrastructure import fetch_scanners
        return fetch_scanners
    if group == "global_disasters":
        from services.fetchers.public_events import fetch_global_disasters
        return fetch_global_disasters
    if group == "border_status":
        from services.fetchers.public_events import fetch_border_status
        return fetch_border_status
    raise KeyError(group)


def request_integration_refresh(integration_id: str) -> dict[str, Any]:
    spec = _SPECS.get(str(integration_id))
    if not spec or not spec.refresh:
        return {"ok": False, "detail": "integration_not_refreshable"}
    snapshot = integration_readiness_snapshot()
    item = next((row for row in snapshot["integrations"] if row["id"] == integration_id), None)
    if item and item.get("state") in {"needs_key", "optional_key", "partial_config"}:
        return {"ok": False, "detail": item.get("state"), "integration": item}
    group = spec.refresh
    with _REFRESH_LOCK:
        if group in _REFRESH_RUNNING:
            return {"ok": True, "started": False, "already_running": True, "group": group}
        _REFRESH_RUNNING.add(group)

    def worker() -> None:
        try:
            func = _refresh_callable(group)
            func()
            try:
                from services.fetchers._store import bump_data_version
                bump_data_version()
            except Exception:
                pass
        finally:
            with _REFRESH_LOCK:
                _REFRESH_RUNNING.discard(group)

    threading.Thread(target=worker, daemon=True, name=f"integration-refresh-{group}").start()
    return {"ok": True, "started": True, "group": group}
