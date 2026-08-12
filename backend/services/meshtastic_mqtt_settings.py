from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from services.config import get_settings


PUBLIC_DEFAULT_USER = "meshdev"
PUBLIC_DEFAULT_PASS = "large4cats"
DATA_DIR = Path(os.environ.get("SB_DATA_DIR", str(Path(__file__).parent.parent / "data")))
if not DATA_DIR.is_absolute():
    DATA_DIR = Path(__file__).parent.parent / DATA_DIR

SETTINGS_FILE = DATA_DIR / "meshtastic_mqtt.json"
_cache: dict[str, Any] | None = None
_cache_ts: float = 0.0
_CACHE_TTL = 2.0


def _settings_defaults() -> dict[str, Any]:
    try:
        s = get_settings()
        return {
            "enabled": bool(getattr(s, "MESH_MQTT_ENABLED", False)),
            "broker": str(getattr(s, "MESH_MQTT_BROKER", "") or "mqtt.meshtastic.org"),
            "port": int(getattr(s, "MESH_MQTT_PORT", 1883) or 1883),
            "username": str(getattr(s, "MESH_MQTT_USER", "") or PUBLIC_DEFAULT_USER),
            "password": str(getattr(s, "MESH_MQTT_PASS", "") or PUBLIC_DEFAULT_PASS),
            "psk": str(getattr(s, "MESH_MQTT_PSK", "") or ""),
            "include_default_roots": bool(getattr(s, "MESH_MQTT_INCLUDE_DEFAULT_ROOTS", True)),
            "extra_roots": str(getattr(s, "MESH_MQTT_EXTRA_ROOTS", "") or ""),
            "extra_topics": str(getattr(s, "MESH_MQTT_EXTRA_TOPICS", "") or ""),
        }
    except Exception:
        return {
            "enabled": False,
            "broker": "mqtt.meshtastic.org",
            "port": 1883,
            "username": PUBLIC_DEFAULT_USER,
            "password": PUBLIC_DEFAULT_PASS,
            "psk": "",
            "include_default_roots": True,
            "extra_roots": "",
            "extra_topics": "",
        }


def _safe_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < 1 or parsed > 65535:
        return default
    return parsed


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    defaults = _settings_defaults()
    return {
        "enabled": bool(data.get("enabled", defaults["enabled"])),
        "broker": str(data.get("broker", defaults["broker"]) or defaults["broker"]).strip(),
        "port": _safe_int(data.get("port", defaults["port"]), defaults["port"]),
        "username": str(data.get("username", defaults["username"]) or "").strip(),
        "password": str(data.get("password", defaults["password"]) or ""),
        "psk": str(data.get("psk", defaults["psk"]) or "").strip(),
        "include_default_roots": bool(data.get("include_default_roots", defaults["include_default_roots"])),
        "extra_roots": str(data.get("extra_roots", defaults["extra_roots"]) or "").strip(),
        "extra_topics": str(data.get("extra_topics", defaults["extra_topics"]) or "").strip(),
        "updated_at": _safe_int(data.get("updated_at", 0), 0),
    }


def read_meshtastic_mqtt_settings() -> dict[str, Any]:
    global _cache, _cache_ts
    now = time.monotonic()
    if _cache is not None and (now - _cache_ts) < _CACHE_TTL:
        return dict(_cache)
    if not SETTINGS_FILE.exists():
        result = {**_settings_defaults(), "updated_at": 0}
    else:
        try:
            loaded = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            loaded = {}
        result = _normalize(loaded if isinstance(loaded, dict) else {})
    _cache = result
    _cache_ts = now
    return dict(result)


def write_meshtastic_mqtt_settings(**updates: Any) -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    existing = read_meshtastic_mqtt_settings()
    next_data = dict(existing)
    for key in (
        "enabled",
        "broker",
        "port",
        "username",
        "password",
        "psk",
        "include_default_roots",
        "extra_roots",
        "extra_topics",
    ):
        if key in updates and updates[key] is not None:
            next_data[key] = updates[key]
    if "username" in updates and not str(updates.get("username") or "").strip() and "password" not in updates:
        next_data["password"] = PUBLIC_DEFAULT_PASS
    next_data["updated_at"] = int(time.time())
    normalized = _normalize(next_data)
    SETTINGS_FILE.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    if os.name != "nt":
        os.chmod(SETTINGS_FILE, 0o600)
    global _cache, _cache_ts
    _cache = normalized
    _cache_ts = time.monotonic()
    return dict(normalized)


def redacted_meshtastic_mqtt_settings(data: dict[str, Any] | None = None) -> dict[str, Any]:
    source = read_meshtastic_mqtt_settings() if data is None else dict(data)
    username = str(source.get("username", "") or "")
    uses_default_credentials = username in ("", PUBLIC_DEFAULT_USER) and str(source.get("password", "") or "") in (
        "",
        PUBLIC_DEFAULT_PASS,
    )
    return {
        "enabled": bool(source.get("enabled")),
        "broker": str(source.get("broker", "")),
        "port": int(source.get("port", 1883) or 1883),
        "username": "" if uses_default_credentials else username,
        "uses_default_credentials": uses_default_credentials,
        "has_password": bool(str(source.get("password", "") or "")),
        "has_psk": bool(str(source.get("psk", "") or "")),
        "include_default_roots": bool(source.get("include_default_roots", True)),
        "extra_roots": str(source.get("extra_roots", "") or ""),
        "extra_topics": str(source.get("extra_topics", "") or ""),
        "updated_at": int(source.get("updated_at", 0) or 0),
    }


def mqtt_connection_config() -> tuple[str, int, str, str]:
    data = read_meshtastic_mqtt_settings()
    return (
        str(data.get("broker") or "mqtt.meshtastic.org"),
        int(data.get("port") or 1883),
        str(data.get("username") or PUBLIC_DEFAULT_USER),
        str(data.get("password") or PUBLIC_DEFAULT_PASS),
    )


def mqtt_bridge_enabled() -> bool:
    return bool(read_meshtastic_mqtt_settings().get("enabled"))


def mqtt_psk_hex() -> str:
    return str(read_meshtastic_mqtt_settings().get("psk", "") or "").strip()


def mqtt_subscription_settings() -> tuple[str, str, bool]:
    data = read_meshtastic_mqtt_settings()
    return (
        str(data.get("extra_roots", "") or ""),
        str(data.get("extra_topics", "") or ""),
        bool(data.get("include_default_roots", True)),
    )
