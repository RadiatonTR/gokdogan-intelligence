from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlparse

import httpx


class OpenCTIConnector:
    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        self.base_url = (base_url or os.environ.get("OPENCTI_URL") or "").rstrip("/")
        self.token = token or os.environ.get("OPENCTI_TOKEN") or ""
        self.connector_id = os.environ.get("OPENCTI_CONNECTOR_ID") or ""


    def _graphql_url(self) -> str:
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("invalid_opencti_url")
        return f"{self.base_url}/graphql"

    async def _graphql(self, query: str, variables: dict[str, Any] | None = None, timeout: float = 15.0) -> tuple[httpx.Response, dict[str, Any]]:
        if not self.configured:
            raise ValueError("opencti_not_configured")
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.post(
                self._graphql_url(),
                json={"query": query, "variables": variables or {}},
                headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            )
        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        return response, data

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.token)

    async def test(self) -> dict[str, Any]:
        if not self.configured:
            return {"ok": False, "configured": False, "detail": "OPENCTI_URL / OPENCTI_TOKEN not configured"}
        query = "query ShadowBrokerProbe { about { version } }"
        try:
            response, data = await self._graphql(query, timeout=8.0)
            return {
                "ok": response.is_success and not data.get("errors"),
                "configured": True,
                "status_code": response.status_code,
                "version": ((data.get("data") or {}).get("about") or {}).get("version"),
                "errors": data.get("errors", [])[:3],
            }
        except Exception as exc:
            return {"ok": False, "configured": True, "detail": type(exc).__name__}


    async def push_stix_bundle(self, bundle: dict[str, Any], *, work_id: str | None = None) -> dict[str, Any]:
        """Explicitly push a STIX bundle to an operator-configured OpenCTI connector."""
        if not self.connector_id:
            return {"ok": False, "configured": self.configured, "detail": "OPENCTI_CONNECTOR_ID not configured"}
        query = """mutation ShadowBrokerStixPush($connectorId: String!, $bundle: String!, $workId: String) { stixBundlePush(connectorId: $connectorId, bundle: $bundle, work_id: $workId) }"""
        try:
            response, data = await self._graphql(
                query,
                {"connectorId": self.connector_id, "bundle": json.dumps(bundle, ensure_ascii=False, separators=(",", ":")), "workId": work_id},
                timeout=30.0,
            )
            return {
                "ok": response.is_success and not data.get("errors") and bool((data.get("data") or {}).get("stixBundlePush")),
                "configured": True,
                "status_code": response.status_code,
                "errors": data.get("errors", [])[:3],
            }
        except Exception as exc:
            return {"ok": False, "configured": self.configured, "detail": type(exc).__name__}
