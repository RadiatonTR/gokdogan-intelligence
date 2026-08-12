"""Safety policy for operator-configured public CCTV media hosts.

Only explicitly configured hostnames that resolve exclusively to globally
routable IP addresses are accepted. This keeps the CCTV proxy from becoming
an internal-network/private-camera proxy.
"""
from __future__ import annotations

import ipaddress
import os
import socket
from functools import lru_cache


def configured_public_camera_media_hosts() -> tuple[str, ...]:
    raw = str(os.getenv("GOKDOGAN_PUBLIC_CAMERA_MEDIA_HOSTS", "") or "")
    values: list[str] = []
    for token in raw.replace(";", ",").replace("\n", ",").split(","):
        host = token.strip().lower().rstrip(".")
        if host and host not in values:
            values.append(host)
        if len(values) >= 64:
            break
    return tuple(values)


@lru_cache(maxsize=256)
def host_resolves_only_public_addresses(hostname: str) -> bool:
    host = str(hostname or "").strip().lower().rstrip(".")
    if not host or host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return False
    try:
        direct = ipaddress.ip_address(host)
    except ValueError:
        direct = None
    if direct is not None:
        return bool(direct.is_global)
    try:
        addresses = {
            info[4][0]
            for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            if info and len(info) >= 5 and info[4]
        }
    except OSError:
        return False
    if not addresses:
        return False
    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            return False
        if not parsed.is_global:
            return False
    return True


def configured_public_camera_media_host_allowed(hostname: str) -> bool:
    host = str(hostname or "").strip().lower().rstrip(".")
    if not host:
        return False
    for allowed in configured_public_camera_media_hosts():
        if host == allowed or host.endswith(f".{allowed}"):
            return host_resolves_only_public_addresses(host)
    return False
