"""Central FastAPI router loading for the ShadowBroker application.

R7 extracts optional-router discovery and registration from the legacy main.py
monolith. New product routers should be added here rather than growing main.py.
"""
from __future__ import annotations

import importlib
import logging
from collections.abc import Iterable

from fastapi import APIRouter, FastAPI

_ALWAYS = (
    "health",
    "mesh_peer_sync",
    "mesh_oracle",
    "mesh_dm",
    "mesh_public",
    "wormhole",
    "infonet",
)

_OSINT = (
    "cctv",
    "radio",
    "sigint",
    "tools",
    "admin",
    "data",
    "ai_intel",
    "sar",
    "road_corridors",
    "osint",
    "scm",
    "entity_graph",
    "intel_feeds",
    "analytics",
    "weather_traffic",
    "public_intel",
    "intelligence_core",
    "agent_shell",
)

# Stable registration order preserves existing middleware/test expectations.
_ORDER = (
    "health", "cctv", "radio", "sigint", "tools", "admin", "data",
    "mesh_peer_sync", "mesh_oracle", "mesh_dm", "mesh_public", "wormhole",
    "ai_intel", "sar", "infonet", "road_corridors", "osint", "scm",
    "entity_graph", "intel_feeds", "analytics", "weather_traffic", "public_intel", "intelligence_core", "agent_shell",
)


def _load_optional_router(name: str, logger: logging.Logger) -> APIRouter:
    module_name = f"routers.{name}"
    try:
        module = importlib.import_module(module_name)
        router = getattr(module, "router", None)
        if isinstance(router, APIRouter):
            return router
        logger.warning("Router module %s did not expose an APIRouter", module_name)
    except Exception as exc:  # optional dependencies are intentionally degradable
        logger.warning("Skipping router %s during startup: %s", module_name, type(exc).__name__)
    return APIRouter()


def build_router_registry(mesh_only: bool, logger: logging.Logger) -> dict[str, APIRouter]:
    routers = {name: _load_optional_router(name, logger) for name in _ALWAYS}
    for name in _OSINT:
        routers[name] = APIRouter() if mesh_only else _load_optional_router(name, logger)
    return routers


def register_routers(app: FastAPI, routers: dict[str, APIRouter], order: Iterable[str] = _ORDER) -> None:
    for name in order:
        app.include_router(routers[name])
