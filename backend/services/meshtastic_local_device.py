"""Local Meshtastic radio bridge for Gokdogan desktop.

Uses the official Meshtastic Python SDK when it is packaged.  The bridge only
controls a radio physically/locally attached to the operator's workstation
(or an explicitly configured local TCP radio).  It does not scan arbitrary
remote hosts.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Any


class LocalMeshtasticDevice:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._interface: Any = None
        self._mode = ""
        self._target = ""
        self._connected_at = 0.0
        self._last_error = ""
        self._subscriptions_ready = False

    @staticmethod
    def _sdk_available() -> bool:
        try:
            import meshtastic  # noqa: F401
            return True
        except Exception:
            return False

    @property
    def connected(self) -> bool:
        return self._interface is not None

    def _subscribe_once(self) -> None:
        if self._subscriptions_ready:
            return
        from pubsub import pub

        pub.subscribe(self._on_receive, "meshtastic.receive")
        pub.subscribe(self._on_connection_lost, "meshtastic.connection.lost")
        self._subscriptions_ready = True

    def _on_connection_lost(self, interface=None, topic=None, **_kwargs) -> None:  # noqa: ARG002
        with self._lock:
            if interface is None or interface is self._interface:
                self._last_error = "Meshtastic cihaz bağlantısı kesildi"

    def _on_receive(self, packet=None, interface=None, **_kwargs) -> None:  # noqa: ARG002
        if not isinstance(packet, dict):
            return
        try:
            decoded = packet.get("decoded") or {}
            text = str(decoded.get("text") or "").strip()
            if not text:
                return
            sender_num = packet.get("from")
            recipient_num = packet.get("to")
            sender = f"!{int(sender_num) & 0xFFFFFFFF:08x}" if isinstance(sender_num, int) else str(sender_num or "???")
            recipient = (
                f"!{int(recipient_num) & 0xFFFFFFFF:08x}"
                if isinstance(recipient_num, int) and recipient_num != 0xFFFFFFFF
                else "broadcast"
            )
            from services.sigint_bridge import sigint_grid

            sigint_grid.mesh.append_text_message(
                {
                    "from": sender,
                    "to": recipient,
                    "text": text,
                    "channel": str(decoded.get("channel") or "LongFast"),
                    "root": "LOCAL",
                    "region": "LOCAL",
                    "source": "meshtastic-local",
                    "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "rxSnr": packet.get("rxSnr"),
                    "hopLimit": packet.get("hopLimit"),
                }
            )
        except Exception:
            # A malformed radio packet must never terminate the SDK callback thread.
            return

    def connect(self, *, mode: str = "serial", target: str = "") -> dict[str, Any]:
        with self._lock:
            if self._interface is not None:
                return self.status()
            if not self._sdk_available():
                self._last_error = "Meshtastic Python SDK kurulu değil"
                return self.status()
            try:
                self._subscribe_once()
                normalized_mode = str(mode or "serial").strip().lower()
                normalized_target = str(target or "").strip()
                if normalized_mode == "tcp":
                    from meshtastic.tcp_interface import TCPInterface

                    host = normalized_target or os.environ.get("MESHTASTIC_TCP_HOST", "").strip()
                    if not host:
                        raise ValueError("TCP bağlantısı için cihaz adresi gerekli")
                    # The SDK owns the TCP transport; only an operator-supplied host is used.
                    interface = TCPInterface(hostname=host)
                    self._target = host
                elif normalized_mode == "serial":
                    from meshtastic.serial_interface import SerialInterface

                    device = normalized_target or os.environ.get("MESHTASTIC_SERIAL_DEVICE", "").strip()
                    interface = SerialInterface(devPath=device) if device else SerialInterface()
                    self._target = device or "otomatik"
                else:
                    raise ValueError("Desteklenmeyen Meshtastic bağlantı türü")
                self._interface = interface
                self._mode = normalized_mode
                self._connected_at = time.time()
                self._last_error = ""
            except Exception as exc:
                self._interface = None
                self._last_error = f"Meshtastic cihaz bağlantısı kurulamadı: {exc}"
            return self.status()

    def disconnect(self) -> dict[str, Any]:
        with self._lock:
            interface = self._interface
            self._interface = None
            if interface is not None:
                try:
                    interface.close()
                except Exception:
                    pass
            self._mode = ""
            self._target = ""
            return self.status()

    def send_text(self, text: str, destination: str = "") -> dict[str, Any]:
        message = str(text or "").strip()
        if not message:
            return {"ok": False, "detail": "Mesaj boş olamaz"}
        with self._lock:
            if self._interface is None:
                # A user action may auto-detect a locally attached serial radio.
                self.connect(mode="serial", target="")
            if self._interface is None:
                return {"ok": False, "detail": self._last_error or "Meshtastic cihazı bağlı değil"}
            try:
                kwargs: dict[str, Any] = {}
                dest = str(destination or "").strip()
                if dest and dest.lower() not in {"broadcast", "^all"}:
                    kwargs["destinationId"] = dest
                self._interface.sendText(message, **kwargs)
                return {"ok": True, "transport": "local-radio", "destination": dest or "broadcast"}
            except Exception as exc:
                self._last_error = f"Meshtastic gönderim hatası: {exc}"
                return {"ok": False, "detail": self._last_error}

    def status(self) -> dict[str, Any]:
        with self._lock:
            interface = self._interface
            nodes = getattr(interface, "nodes", {}) if interface is not None else {}
            own = getattr(interface, "myInfo", None) if interface is not None else None
            return {
                "ok": True,
                "sdk_available": self._sdk_available(),
                "connected": interface is not None,
                "mode": self._mode or None,
                "target": self._target or None,
                "connected_at": self._connected_at or None,
                "node_count": len(nodes) if isinstance(nodes, dict) else 0,
                "own_node": str(own) if own is not None else None,
                "last_error": self._last_error or None,
            }


local_meshtastic_device = LocalMeshtasticDevice()
