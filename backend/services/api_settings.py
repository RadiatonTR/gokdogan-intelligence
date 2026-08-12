"""
API Settings management — serves the API key registry and allows updates.
Keys are stored in the backend .env file and loaded via python-dotenv.
"""

import os
import re
import tempfile
import threading
from pathlib import Path

# Path to the backend .env file
ENV_PATH = Path(__file__).parent.parent / ".env"
# Path to the example template that ships with the repo
ENV_EXAMPLE_PATH = Path(__file__).parent.parent.parent / ".env.example"
DATA_DIR = Path(os.environ.get("SB_DATA_DIR", str(Path(__file__).parent.parent / "data")))
if not DATA_DIR.is_absolute():
    DATA_DIR = Path(__file__).parent.parent / DATA_DIR
OPERATOR_KEYS_ENV_PATH = Path(
    os.environ.get("SHADOWBROKER_OPERATOR_KEYS_ENV", str(DATA_DIR / "operator_api_keys.env"))
)
OPENCLAW_ENV_PATH = Path(
    os.environ.get("SHADOWBROKER_OPENCLAW_ENV", str(DATA_DIR / "openclaw.env"))
)
OPENCLAW_PERSISTED_KEYS = frozenset({"OPENCLAW_HMAC_SECRET", "OPENCLAW_ACCESS_TIER"})
_ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

# ---------------------------------------------------------------------------
# API Registry — every external service the dashboard depends on
# ---------------------------------------------------------------------------
API_REGISTRY = [
    {
        "id": "opensky_client_id",
        "env_key": "OPENSKY_CLIENT_ID",
        "name": "OpenSky Network — İstemci Kimliği",
        "description": "OpenSky Network OAuth2 istemci kimliği. İsteğe bağlıdır; girildiğinde sivil uçuş verisini zenginleştirir, girilmezse anahtarsız ADS-B yedek kaynağı kullanılmaya devam eder.",
        "category": "Havacılık",
        "url": "https://opensky-network.org/",
        "required": False,
    },
    {
        "id": "opensky_client_secret",
        "env_key": "OPENSKY_CLIENT_SECRET",
        "name": "OpenSky Network — İstemci Gizli Anahtarı",
        "description": "OpenSky istemci kimliğiyle eşleşen isteğe bağlı OAuth2 gizli anahtarı. Kimlik bilgili uçuş akışını etkinleştirir; anahtarsız yedek akışlar çalışmaya devam eder.",
        "category": "Havacılık",
        "url": "https://opensky-network.org/",
        "required": False,
    },
    {
        "id": "ais_api_key",
        "env_key": "AIS_API_KEY",
        "name": "AIS Stream",
        "description": "Kamuya açık AIS Stream canlı gemi yayınları için isteğe bağlı API anahtarı. Girilmezse önbellek ve yapılandırılmış kamu/yedek denizcilik kaynakları kullanılabilir.",
        "category": "Denizcilik",
        "url": "https://aisstream.io/",
        "required": False,
    },
    {
        "id": "gfw_api_token",
        "env_key": "GFW_API_TOKEN",
        "name": "Global Fishing Watch",
        "description": "Global Fishing Watch balıkçılık etkinliği olaylarını almak için isteğe bağlı erişim belirteci.",
        "category": "Denizcilik",
        "url": "https://globalfishingwatch.org/our-apis/",
        "required": False,
    },
    {
        "id": "adsb_lol",
        "env_key": None,
        "name": "ADS-B Exchange (adsb.lol)",
        "description": "Anahtar gerektirmeyen topluluk ADS-B uçuş kaynağı. OpenSky kullanılamadığında yedek kaynak olarak çalışabilir.",
        "category": "Havacılık",
        "url": "https://api.adsb.lol/",
        "required": False,
    },
    {
        "id": "usgs_earthquakes",
        "env_key": None,
        "name": "USGS Deprem Tehlikeleri",
        "description": "USGS tarafından yayımlanan güncel küresel deprem akışı. API anahtarı gerektirmez.",
        "category": "Jeofizik",
        "url": "https://earthquake.usgs.gov/",
        "required": False,
    },
    {
        "id": "firms_map_key",
        "env_key": "FIRMS_MAP_KEY",
        "name": "NASA FIRMS — MAP Anahtarı (isteğe bağlı)",
        "description": "Ülke bazlı VIIRS yangın zenginleştirmesi için isteğe bağlı NASA Earthdata MAP anahtarı; temel küresel yangın verisi anahtarsız çalışır.",
        "category": "Jeofizik",
        "url": "https://firms.modaps.eosdis.nasa.gov/api/area/",
        "required": False,
    },
    {
        "id": "airframes_api_key",
        "env_key": "AIRFRAMES_API_KEY",
        "name": "Airframes.io — API Anahtarı",
        "description": "ACARS/VDL uçak dosyası zenginleştirmesi için Airframes.io API anahtarı.",
        "category": "Havacılık",
        "url": "https://app.airframes.io/user/dashboard",
        "required": False,
    },
    {
        "id": "celestrak",
        "env_key": None,
        "name": "CelesTrak (NORAD TLEs)",
        "description": "Aktif uyduların NORAD/TLE yörünge verilerini sağlayan anahtarsız açık kaynak.",
        "category": "Uzay",
        "url": "https://celestrak.org/",
        "required": False,
    },
    {
        "id": "gdelt",
        "env_key": None,
        "name": "GDELT Projesi",
        "description": "Küresel haber ve jeopolitik olay verilerini sağlayan açık GDELT kaynağı; anahtar gerektirmez.",
        "category": "İstihbarat",
        "url": "https://www.gdeltproject.org/",
        "required": False,
    },
    {
        "id": "nominatim",
        "env_key": None,
        "name": "Nominatim (OpenStreetMap)",
        "description": "Koordinatları okunabilir yer adlarına dönüştüren OpenStreetMap ters coğrafi kodlama hizmeti.",
        "category": "Coğrafi Konum",
        "url": "https://nominatim.openstreetmap.org/",
        "required": False,
    },
    {
        "id": "rainviewer",
        "env_key": None,
        "name": "RainViewer",
        "description": "Küresel yağış/radar harita katmanı; anahtar gerektirmez.",
        "category": "Hava Durumu",
        "url": "https://www.rainviewer.com/",
        "required": False,
    },
    {
        "id": "open_meteo",
        "env_key": None,
        "name": "Open-Meteo",
        "description": "Küresel hava durumu, saatlik tahmin, bulut ve sıcaklık eğilimi; genel kullanımda anahtar gerektirmez.",
        "category": "Hava Durumu",
        "url": "https://open-meteo.com/",
        "required": False,
    },
    {
        "id": "nasa_eonet",
        "env_key": None,
        "name": "NASA EONET",
        "description": "NASA EONET üzerinden yangın, sel, fırtına, volkan ve diğer doğal olayların açık küresel akışı.",
        "category": "Afet / Yer Gözlemi",
        "url": "https://eonet.gsfc.nasa.gov/",
        "required": False,
    },
    {
        "id": "gdacs",
        "env_key": None,
        "name": "GDACS",
        "description": "GDACS üzerinden küresel afet uyarıları ve insani yardım olayları; anahtar gerektirmez.",
        "category": "Afet / İnsani Yardım",
        "url": "https://www.gdacs.org/",
        "required": False,
    },
    {
        "id": "cbp_border_wait",
        "env_key": None,
        "name": "ABD CBP Sınır Bekleme Süreleri",
        "description": "ABD CBP tarafından yayımlanan resmî sınır kapısı bekleme süreleri.",
        "category": "Sınırlar / Trafik",
        "url": "https://bwt.cbp.gov/",
        "required": False,
    },
    {
        "id": "tomtom_api_key",
        "env_key": "TOMTOM_API_KEY",
        "name": "TomTom Traffic — API Anahtarı",
        "description": "Gerçek zamanlı yol trafik akışı ve trafik olayı zenginleştirmesi için isteğe bağlı TomTom anahtarı.",
        "category": "Trafik / Kamu Kameraları",
        "url": "https://developer.tomtom.com/",
        "required": False,
    },
    {
        "id": "rss_feeds",
        "env_key": None,
        "name": "RSS Haber Akışları",
        "description": "Küresel ve yerel haber sağlayıcılarının yapılandırılabilir RSS/Atom akışları.",
        "category": "İstihbarat",
        "url": None,
        "required": False,
    },
    {
        "id": "yfinance",
        "env_key": None,
        "name": "Yahoo Finance (yfinance)",
        "description": "Hisse, endeks, döviz, kripto, petrol ve değerli maden temel piyasa verileri için anahtarsız kaynak.",
        "category": "Piyasalar",
        "url": "https://finance.yahoo.com/",
        "required": False,
    },
    {
        "id": "openmhz",
        "env_key": None,
        "name": "OpenMHz",
        "description": "Kamuya açık radyo/telsiz dizini ve yayın bağlantıları; erişim upstream servise bağlıdır.",
        "category": "Açık Radyo Kaynakları",
        "url": "https://openmhz.com/",
        "required": False,
    },
    {
        "id": "shodan_api_key",
        "env_key": "SHODAN_API_KEY",
        "name": "Shodan — Operatör API Anahtarı",
        "description": "Yalnız operatörün bilinçli olarak başlattığı pasif Shodan sorguları için API anahtarı; arka planda otomatik tarama yapılmaz.",
        "category": "Pasif Keşif",
        "url": "https://account.shodan.io/billing",
        "required": False,
    },
    {
        "id": "abuseipdb_api_key",
        "env_key": "ABUSEIPDB_API_KEY",
        "name": "AbuseIPDB — API Anahtarı",
        "description": "Operatör tarafından sorgulanan IP adresleri için pasif itibar zenginleştirmesi.",
        "category": "Siber İstihbarat",
        "url": "https://www.abuseipdb.com/account/api",
        "required": False,
    },
    {
        "id": "finnhub_api_key",
        "env_key": "FINNHUB_API_KEY",
        "name": "Finnhub — API Anahtarı",
        "description": "Piyasa verilerini zenginleştirmek için isteğe bağlı Finnhub anahtarı; anahtarsız temel piyasa kaynağı korunur.",
        "category": "Finans",
        "url": "https://finnhub.io/register",
        "required": False,
    },
    # Issue #298 (tg12): Sentinel Hub / Copernicus Data Space Ecosystem
    # credentials were previously held in browser localStorage / sessionStorage
    # by the Settings panel. Moved server-side to the same .env-backed
    # store every other third-party API key lives in. The Sentinel proxy
    # routes (POST /api/sentinel/token, /tile) now fall back to these
    # env values when the request body omits credentials — see
    # backend/routers/tools.py for the resolution order.
    {
        "id": "sentinel_client_id",
        "env_key": "SENTINEL_CLIENT_ID",
        "name": "Sentinel Hub / Copernicus — İstemci Kimliği",
        "description": "Copernicus/Sentinel görüntü istekleri için OAuth istemci kimliği.",
        "category": "Uydu Görüntüleme",
        "url": "https://dataspace.copernicus.eu/",
        "required": False,
    },
    {
        "id": "sentinel_client_secret",
        "env_key": "SENTINEL_CLIENT_SECRET",
        "name": "Sentinel Hub / Copernicus — İstemci Gizli Anahtarı",
        "description": "Sentinel istemci kimliğiyle eşleşen OAuth gizli anahtarı.",
        "category": "Uydu Görüntüleme",
        "url": "https://dataspace.copernicus.eu/",
        "required": False,
    },
    {
        "id": "aishub_username",
        "env_key": "AISHUB_USERNAME",
        "name": "AISHub — Kullanıcı Adı",
        "description": "AIS Stream kullanılamadığında yapılandırılabilen isteğe bağlı AISHub yedek kullanıcı adı.",
        "category": "Denizcilik",
        "url": "https://www.aishub.net/",
        "required": False,
    },
    {
        "id": "lta_account_key",
        "env_key": "LTA_ACCOUNT_KEY",
        "name": "Singapur LTA DataMall — Hesap Anahtarı",
        "description": "Singapur LTA DataMall kamu trafik kameralarını eklemek için hesap anahtarı.",
        "category": "Trafik / Kamu Kameraları",
        "url": "https://datamall.lta.gov.sg/",
        "required": False,
    },
    {
        "id": "windy_api_key",
        "env_key": "WINDY_API_KEY",
        "name": "Windy Webcams — API Anahtarı",
        "description": "Yapılandırılmış sağlayıcı üzerinden kamuya açık webcam kaynaklarını eklemek için Windy API anahtarı.",
        "category": "Trafik / Kamu Kameraları",
        "url": "https://api.windy.com/",
        "required": False,
    },
    {
        "id": "public_camera_catalog_urls",
        "env_key": "GOKDOGAN_PUBLIC_CAMERA_CATALOG_URLS",
        "name": "Yetkili Kamu Kamera Katalogları — HTTPS URL listesi",
        "description": "Operatörün tanımladığı resmî ve kamuya açık HTTPS kamera kataloglarının listesi.",
        "category": "Trafik / Kamu Kameraları",
        "url": None,
        "required": False,
    },
    {
        "id": "public_camera_catalog_hosts",
        "env_key": "GOKDOGAN_PUBLIC_CAMERA_CATALOG_HOSTS",
        "name": "Yetkili Kamu Kamera Katalogları — İzinli katalog hostları",
        "description": "Kamu kamera katalogları için izin verilen resmî sunucu adları. Özel/yerel ağ adresleri reddedilir.",
        "category": "Trafik / Kamu Kameraları",
        "url": None,
        "required": False,
    },
    {
        "id": "public_camera_media_hosts",
        "env_key": "GOKDOGAN_PUBLIC_CAMERA_MEDIA_HOSTS",
        "name": "Yetkili Kamu Kamera Medyası — İzinli hostlar",
        "description": "Kamu kamera medya akışları için izin verilen resmî sunucu adları.",
        "category": "Trafik / Kamu Kameraları",
        "url": None,
        "required": False,
    },
    {
        "id": "openaq_api_key",
        "env_key": "OPENAQ_API_KEY",
        "name": "OpenAQ — API Anahtarı",
        "description": "Hava kalitesi verilerini zenginleştirmek için OpenAQ API anahtarı.",
        "category": "Çevre",
        "url": "https://openaq.org/developers/",
        "required": False,
    },
    {
        "id": "fred_api_key",
        "env_key": "FRED_API_KEY",
        "name": "FRED — API Anahtarı",
        "description": "FRED makroekonomik veri bağdaştırıcısı için API anahtarı.",
        "category": "Ekonomi",
        "url": "https://fred.stlouisfed.org/docs/api/api_key.html",
        "required": False,
    },
    {
        "id": "bls_api_key",
        "env_key": "BLS_API_KEY",
        "name": "ABD BLS — Kayıt Anahtarı",
        "description": "ABD Çalışma İstatistikleri Bürosu veri bağdaştırıcısı için kayıt anahtarı.",
        "category": "Ekonomi",
        "url": "https://data.bls.gov/registrationEngine/",
        "required": False,
    },
    {
        "id": "eia_api_key",
        "env_key": "EIA_API_KEY",
        "name": "ABD EIA — API Anahtarı",
        "description": "ABD Enerji Bilgi İdaresi enerji/ekonomi veri bağdaştırıcısı için API anahtarı.",
        "category": "Ekonomi",
        "url": "https://www.eia.gov/opendata/register.php",
        "required": False,
    },
    {
        "id": "reliefweb_appname",
        "env_key": "RELIEFWEB_APPNAME",
        "name": "ReliefWeb — Uygulama Adı",
        "description": "ReliefWeb insani yardım veri erişimi için uygulama adı/kimliği.",
        "category": "İnsani Yardım",
        "url": "https://apidoc.reliefweb.int/",
        "required": False,
    },
    {
        "id": "alerts_in_ua_token",
        "env_key": "ALERTS_IN_UA_TOKEN",
        "name": "alerts.in.ua — API Belirteci",
        "description": "alerts.in.ua tarafından yayımlanan uyarı akışı için API belirteci.",
        "category": "İnsani Yardım",
        "url": "https://alerts.in.ua/",
        "required": False,
    },
    {
        "id": "opencti_url",
        "env_key": "OPENCTI_URL",
        "name": "OpenCTI — Sunucu Adresi",
        "description": "Operatöre ait OpenCTI sunucusunun HTTPS adresi.",
        "category": "Siber İstihbarat",
        "url": "https://docs.opencti.io/",
        "required": False,
    },
    {
        "id": "opencti_token",
        "env_key": "OPENCTI_TOKEN",
        "name": "OpenCTI — API Belirteci",
        "description": "Operatöre ait OpenCTI sunucusuna erişim için API belirteci.",
        "category": "Siber İstihbarat",
        "url": "https://docs.opencti.io/",
        "required": False,
    },
    {
        "id": "opencti_connector_id",
        "env_key": "OPENCTI_CONNECTOR_ID",
        "name": "OpenCTI — Bağlayıcı Kimliği",
        "description": "OpenCTI push/bağlayıcı iş akışları için isteğe bağlı bağlayıcı kimliği.",
        "category": "Siber İstihbarat",
        "url": "https://docs.opencti.io/",
        "required": False,
    },
    {
        "id": "nuforc_mapbox_token",
        "env_key": "NUFORC_MAPBOX_TOKEN",
        "name": "NUFORC Mapbox — Belirteç",
        "description": "NUFORC coğrafi zenginleştirmesinde isteğe bağlı Mapbox belirteci.",
        "category": "Coğrafi Konum",
        "url": "https://www.mapbox.com/",
        "required": False,
    },
]

ALLOWED_ENV_KEYS = {
    str(api["env_key"])
    for api in API_REGISTRY
    if api.get("env_key")
}


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not _ENV_KEY_RE.match(key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def _quote_env_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _write_env_values(path: Path, updates: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    next_lines: list[str] = []
    for raw_line in lines:
        stripped = raw_line.strip()
        if "=" not in stripped or stripped.startswith("#"):
            next_lines.append(raw_line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            next_lines.append(f"{key}={_quote_env_value(updates[key])}")
            seen.add(key)
        else:
            next_lines.append(raw_line)
    for key, value in updates.items():
        if key not in seen:
            next_lines.append(f"{key}={_quote_env_value(value)}")

    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f"{path.name}.tmp.", text=True)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(next_lines).rstrip() + "\n")
        if os.name != "nt":
            os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
        if os.name != "nt":
            os.chmod(path, 0o600)
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass


def load_persisted_api_keys_into_environ() -> None:
    """Load persisted operator API keys if no process env value exists."""
    for key, value in _parse_env_file(OPERATOR_KEYS_ENV_PATH).items():
        if key in ALLOWED_ENV_KEYS and value and not os.environ.get(key):
            os.environ[key] = value


def load_persisted_openclaw_into_environ() -> None:
    """Load OpenClaw secrets from the data volume when env is unset/empty.

    Docker Compose often injects ``OPENCLAW_HMAC_SECRET=`` as an empty string,
    which blocks pydantic from reading backend/.env. Persisting bootstrap output
    under ``data/openclaw.env`` (on the backend_data volume) keeps remote HMAC
    working across container restarts (#424).
    """
    persisted = _parse_env_file(OPENCLAW_ENV_PATH)
    if not persisted.get("OPENCLAW_HMAC_SECRET"):
        # One-time migration from legacy backend/.env writes inside the image.
        persisted = {**_parse_env_file(ENV_PATH), **persisted}

    for key, value in persisted.items():
        if key not in OPENCLAW_PERSISTED_KEYS:
            continue
        cleaned = str(value or "").strip()
        if cleaned and not str(os.environ.get(key, "")).strip():
            os.environ[key] = cleaned


def persist_openclaw_env_value(key: str, value: str) -> None:
    """Persist OpenClaw runtime settings to the data volume."""
    if key not in OPENCLAW_PERSISTED_KEYS:
        return
    _write_env_values(OPENCLAW_ENV_PATH, {key: value})


def get_env_path_info() -> dict:
    """Return absolute paths for the backend .env and .env.example template.

    Surfaced to the frontend so the API Keys settings panel can tell users
    exactly where to put their keys when in-app editing fails (admin-not-set,
    file permissions, read-only filesystem, etc.).
    """
    env_path = ENV_PATH.resolve()
    example_path = ENV_EXAMPLE_PATH.resolve()
    return {
        "env_path": str(env_path),
        "env_path_exists": env_path.exists(),
        "env_path_writable": os.access(env_path.parent, os.W_OK)
            and (not env_path.exists() or os.access(env_path, os.W_OK)),
        "env_example_path": str(example_path),
        "env_example_path_exists": example_path.exists(),
        "operator_keys_env_path": str(OPERATOR_KEYS_ENV_PATH.resolve()),
        "operator_keys_env_path_exists": OPERATOR_KEYS_ENV_PATH.exists(),
        "operator_keys_env_path_writable": os.access(OPERATOR_KEYS_ENV_PATH.parent, os.W_OK)
            and (not OPERATOR_KEYS_ENV_PATH.exists() or os.access(OPERATOR_KEYS_ENV_PATH, os.W_OK)),
        "openclaw_env_path": str(OPENCLAW_ENV_PATH.resolve()),
        "openclaw_env_path_exists": OPENCLAW_ENV_PATH.exists(),
        "openclaw_env_path_writable": os.access(OPENCLAW_ENV_PATH.parent, os.W_OK)
            and (not OPENCLAW_ENV_PATH.exists() or os.access(OPENCLAW_ENV_PATH, os.W_OK)),
    }


def get_api_keys():
    """Return the API registry with a binary set/unset flag per key.

    Key values themselves are NEVER returned to the client — not even an
    obfuscated prefix. Users edit the .env file directly; the panel uses
    `is_set` to render a CONFIGURED / NOT CONFIGURED badge and the path
    info from `get_env_path_info()` to tell them where to put each key.
    """
    load_persisted_api_keys_into_environ()
    result = []
    for api in API_REGISTRY:
        entry = {
            "id": api["id"],
            "name": api["name"],
            "description": api["description"],
            "category": api["category"],
            "url": api["url"],
            "required": api["required"],
            "has_key": api["env_key"] is not None,
            "env_key": api["env_key"],
            "is_set": False,
        }
        if api["env_key"]:
            raw = os.environ.get(api["env_key"], "")
            entry["is_set"] = bool(raw)
        result.append(entry)
    return result


def get_api_key_diagnostics() -> dict:
    """Return a secret-free health snapshot for the API credential subsystem.

    This deliberately validates storage/runtime wiring without making third-party
    network requests or returning credential values. It is safe to expose to the
    local operator UI and useful for distinguishing a bad provider key from a
    broken desktop/backend persistence path.
    """
    load_persisted_api_keys_into_environ()
    rows = get_api_keys()
    configured = sorted(
        str(row.get("env_key"))
        for row in rows
        if row.get("env_key") and row.get("is_set")
    )
    required_missing = sorted(
        str(row.get("env_key") or row.get("id"))
        for row in rows
        if row.get("required") and row.get("has_key") and not row.get("is_set")
    )
    optional_missing = sorted(
        str(row.get("env_key") or row.get("id"))
        for row in rows
        if not row.get("required") and row.get("has_key") and not row.get("is_set")
    )

    pair_specs = {
        "opensky": ("OPENSKY_CLIENT_ID", "OPENSKY_CLIENT_SECRET"),
        "sentinel": ("SENTINEL_CLIENT_ID", "SENTINEL_CLIENT_SECRET"),
        "opencti": ("OPENCTI_URL", "OPENCTI_TOKEN"),
    }
    pairs = []
    for pair_id, keys in pair_specs.items():
        present = [bool(str(os.environ.get(key, "")).strip()) for key in keys]
        pairs.append({
            "id": pair_id,
            "keys": list(keys),
            "configured": all(present),
            "partial": any(present) and not all(present),
        })

    path_info = get_env_path_info()
    parent = OPERATOR_KEYS_ENV_PATH.parent
    store_parent_writable = os.access(parent, os.W_OK) if parent.exists() else os.access(parent.parent, os.W_OK)
    return {
        "ok": not required_missing and bool(store_parent_writable),
        "registry_count": len(rows),
        "configured_count": len(configured),
        "configured_env_keys": configured,
        "required_missing": required_missing,
        "optional_missing_count": len(optional_missing),
        "pairs": pairs,
        "runtime_environment_active": bool(configured),
        "persistent_store": {
            "path": str(OPERATOR_KEYS_ENV_PATH.resolve()),
            "exists": OPERATOR_KEYS_ENV_PATH.exists(),
            "writable": bool(path_info.get("operator_keys_env_path_writable")),
            "parent_writable": bool(store_parent_writable),
        },
        "note": "Bu test üçüncü taraf API'lere gizli değer göndermez; yalnız yerel kayıt ve çalışma zamanı zincirini doğrular.",
    }


def _normalize_api_key_updates(updates: dict[str, str]) -> dict[str, str]:
    clean: dict[str, str] = {}
    for key, value in updates.items():
        env_key = str(key or "").strip().upper()
        if env_key not in ALLOWED_ENV_KEYS:
            continue
        clean_value = str(value or "").strip()
        if clean_value:
            clean[env_key] = clean_value
    return clean


def _activate_api_keys(clean: dict[str, str]) -> list[str]:
    """Apply already-validated credentials to the current backend process.

    This is shared by persistent local-operator saves and the packaged desktop's
    native-vault hot-apply path.  It never returns secret values.
    """
    for key, value in clean.items():
        os.environ[key] = value
    if "AIS_API_KEY" in clean:
        try:
            from services import ais_stream
            ais_stream.API_KEY = clean["AIS_API_KEY"]
            # Anahtar uygulama çalışırken eklendiyse başlangıçta devre dışı kalan
            # AIS proxy zincirini yeniden başlat. Bu işlem arka planda yapılır.
            def _restart_ais_after_key_update() -> None:
                try:
                    ais_stream.stop_ais_stream()
                except Exception:
                    pass
                try:
                    ais_stream.start_ais_stream()
                except Exception:
                    pass
            threading.Thread(
                target=_restart_ais_after_key_update,
                daemon=True,
                name="ais-key-hot-restart",
            ).start()
        except Exception:
            pass
    if "OPENSKY_CLIENT_ID" in clean or "OPENSKY_CLIENT_SECRET" in clean:
        try:
            from services.fetchers import flights
            flights.opensky_client.client_id = os.environ.get("OPENSKY_CLIENT_ID", "")
            flights.opensky_client.client_secret = os.environ.get("OPENSKY_CLIENT_SECRET", "")
            flights.opensky_client.token = None
            flights.opensky_client.expires_at = 0
        except Exception:
            pass
    if "AIRFRAMES_API_KEY" in clean:
        try:
            from services.fetchers.airframes import sync_airframes_messages
            threading.Thread(
                target=lambda: sync_airframes_messages(force=True),
                daemon=True,
                name="airframes-initial-sync",
            ).start()
        except Exception:
            pass
    try:
        from services.config import get_settings
        get_settings.cache_clear()
    except Exception:
        pass

    refresh_ids_by_env = {
        "OPENSKY_CLIENT_ID": "opensky_client_id",
        "OPENSKY_CLIENT_SECRET": "opensky_client_secret",
        "AIS_API_KEY": "ais_api_key",
        "AISHUB_USERNAME": "aishub_username",
        "GFW_API_TOKEN": "gfw_api_token",
        "FIRMS_MAP_KEY": "firms_map_key",
        "AIRFRAMES_API_KEY": "airframes_api_key",
        "FINNHUB_API_KEY": "finnhub_api_key",
        "OPENAQ_API_KEY": "openaq_api_key",
        "LTA_ACCOUNT_KEY": "lta_account_key",
        "WINDY_API_KEY": "windy_api_key",
        "GOKDOGAN_PUBLIC_CAMERA_CATALOG_URLS": "public_camera_catalog_urls",
        "GOKDOGAN_PUBLIC_CAMERA_CATALOG_HOSTS": "public_camera_catalog_hosts",
        "GOKDOGAN_PUBLIC_CAMERA_MEDIA_HOSTS": "public_camera_media_hosts",
        "ALERTS_IN_UA_TOKEN": "alerts_in_ua_token",
    }
    refresh_started: list[str] = []
    try:
        from services.integration_readiness import request_integration_refresh
        seen_ids: set[str] = set()
        for env_key in clean:
            integration_id = refresh_ids_by_env.get(env_key)
            if not integration_id or integration_id in seen_ids:
                continue
            seen_ids.add(integration_id)
            result = request_integration_refresh(integration_id)
            if result.get("ok") and (result.get("started") or result.get("already_running")):
                refresh_started.append(integration_id)
    except Exception:
        pass
    return sorted(refresh_started)


def apply_api_keys_runtime(updates: dict[str, str]) -> dict:
    """Hot-apply credentials already persisted in the native desktop vault.

    Unlike :func:`save_api_keys`, this does not write plaintext credentials to
    disk.  It exists so packaged Windows builds can use newly saved DPAPI-backed
    secrets immediately without requiring an application restart.
    """
    clean = _normalize_api_key_updates(updates)
    if not clean:
        return {"ok": False, "detail": "Desteklenen bir API anahtarı sağlanmadı."}
    refresh_started = _activate_api_keys(clean)
    return {
        "ok": True,
        "updated": sorted(clean.keys()),
        "keys": get_api_keys(),
        "refresh_started": refresh_started,
        "persistence": "runtime-only",
    }


def save_api_keys(updates: dict[str, str]) -> dict:
    """Persist allowed API keys from a local operator request.

    Values are accepted write-only: the response includes only configured flags.
    """
    clean = _normalize_api_key_updates(updates)
    if not clean:
        return {"ok": False, "detail": "Desteklenen bir API anahtarı sağlanmadı."}

    _write_env_values(OPERATOR_KEYS_ENV_PATH, clean)
    try:
        _write_env_values(ENV_PATH, clean)
    except OSError:
        pass
    refresh_started = _activate_api_keys(clean)
    return {
        "ok": True,
        "updated": sorted(clean.keys()),
        "keys": get_api_keys(),
        "env": get_env_path_info(),
        "refresh_started": refresh_started,
        "persistence": "operator-env",
    }

