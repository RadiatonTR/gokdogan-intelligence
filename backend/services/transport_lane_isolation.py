from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def disable_public_mesh_lane(*, reason: str = "private_lane_enabled") -> dict[str, Any]:
    """Disable public Meshtastic MQTT before private Wormhole/Infonet starts."""
    result: dict[str, Any] = {
        "ok": True,
        "reason": reason,
        "settings_disabled": False,
        "runtime_stopped": False,
    }

    # Scheduled Wormhole prewarm must not mutate the user's explicit public
    # MeshChat session. Only a deliberate private-lane activation should sever
    # the public MQTT lane.
    normalized_reason = str(reason or "").strip().lower()
    if normalized_reason == "wormhole_scheduled_prewarm" or normalized_reason.endswith(":scheduled_prewarm"):
        try:
            from services.meshtastic_mqtt_settings import mqtt_bridge_enabled

            if mqtt_bridge_enabled():
                logger.info("Keeping public Mesh lane active during Wormhole prewarm: %s", reason)
                result["skipped"] = True
                result["skip_reason"] = "public_mesh_user_enabled"
                return result
        except Exception as exc:
            logger.debug("Could not inspect public Mesh state during %s: %s", reason, exc)

    logger.info("Disabling public Mesh lane: %s", reason)

    try:
        from services.meshtastic_mqtt_settings import write_meshtastic_mqtt_settings

        settings = write_meshtastic_mqtt_settings(enabled=False)
        result["settings_disabled"] = not bool(settings.get("enabled"))
    except Exception as exc:
        logger.warning("Failed to disable public Mesh settings during %s: %s", reason, exc)
        result["ok"] = False
        result["settings_error"] = str(exc)

    try:
        from services.sigint_bridge import sigint_grid

        if sigint_grid.mesh.is_running():
            sigint_grid.mesh.stop()
        result["runtime_stopped"] = not sigint_grid.mesh.is_running()
    except Exception as exc:
        logger.warning("Failed to stop public Mesh runtime during %s: %s", reason, exc)
        result["ok"] = False
        result["runtime_error"] = str(exc)

    return result
