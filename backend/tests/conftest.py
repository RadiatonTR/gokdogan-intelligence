import os

import asyncio

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def _gt_analytics_standard_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests assume a standard (non-lean) runtime unless they override profile."""
    monkeypatch.setenv("GT_ANALYTICS_PROFILE", os.environ.get("GT_ANALYTICS_PROFILE", "standard"))
    try:
        from analytics.integration import reset_gt_engine

        reset_gt_engine()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _suppress_background_services():
    """Prevent real scheduler/stream/tracker from starting during tests."""
    # Pure Intelligence Core/storage tests should not be forced to import the
    # full scheduler stack just to reach their test body. On the full release
    # environment all backend dependencies are installed, so these imports
    # succeed and the real background entry points are always patched. In a
    # minimal source-validation environment, an unavailable *external* package
    # is allowed to defer the failure until a test actually imports that stack.
    try:
        from services import ais_stream, carrier_tracker, data_fetcher
        from services.mesh import mesh_private_transport_manager as mesh_transport
    except ModuleNotFoundError as exc:
        if exc.name and not exc.name.startswith("services"):
            yield
            return
        raise

    reset_private_transport_manager_for_tests = mesh_transport.reset_private_transport_manager_for_tests
    reset_private_transport_manager_for_tests()
    with (
        patch.object(data_fetcher, "start_scheduler"),
        patch.object(data_fetcher, "stop_scheduler"),
        patch.object(ais_stream, "start_ais_stream"),
        patch.object(ais_stream, "stop_ais_stream"),
        patch.object(carrier_tracker, "start_carrier_tracker"),
        patch.object(carrier_tracker, "stop_carrier_tracker"),
        patch.object(mesh_transport.private_transport_manager, "_kickoff_background_bootstrap", return_value=False),
    ):
        yield
    reset_private_transport_manager_for_tests()


@pytest.fixture()
def client(_suppress_background_services):
    """HTTPX test client against the FastAPI app (no real network)."""
    from httpx import ASGITransport, AsyncClient
    from main import app
    import asyncio

    # Return a sync-usable wrapper
    class SyncClient:
        def __init__(self):
            self._loop = asyncio.new_event_loop()
            self._transport = ASGITransport(app=app)

        def get(self, url, **kw):
            return self._loop.run_until_complete(self._get(url, **kw))

        async def _get(self, url, **kw):
            async with AsyncClient(transport=self._transport, base_url="http://test") as ac:
                return await ac.get(url, **kw)

        def post(self, url, **kw):
            return self._loop.run_until_complete(self._post(url, **kw))

        async def _post(self, url, **kw):
            async with AsyncClient(transport=self._transport, base_url="http://test") as ac:
                return await ac.post(url, **kw)

        def put(self, url, **kw):
            return self._loop.run_until_complete(self._put(url, **kw))

        async def _put(self, url, **kw):
            async with AsyncClient(transport=self._transport, base_url="http://test") as ac:
                return await ac.put(url, **kw)

        def delete(self, url, **kw):
            return self._loop.run_until_complete(self._delete(url, **kw))

        async def _delete(self, url, **kw):
            async with AsyncClient(transport=self._transport, base_url="http://test") as ac:
                return await ac.delete(url, **kw)

    return SyncClient()


@pytest.fixture()
def remote_client(_suppress_background_services):
    """HTTPX test client that simulates a remote (non-loopback) IP address.

    Unlike the default ``client`` fixture (127.0.0.1 — bypasses auth via
    loopback), this client originates from 1.2.3.4 and must present valid
    authentication to access protected routes.
    """
    from httpx import ASGITransport, AsyncClient
    from main import app

    class RemoteSyncClient:
        def __init__(self):
            self._loop = asyncio.new_event_loop()
            self._transport = ASGITransport(app=app, client=("1.2.3.4", 12345))
            self._base = "http://1.2.3.4:8000"

        def get(self, url, **kw):
            return self._loop.run_until_complete(self._req("GET", url, **kw))

        def post(self, url, **kw):
            return self._loop.run_until_complete(self._req("POST", url, **kw))

        def put(self, url, **kw):
            return self._loop.run_until_complete(self._req("PUT", url, **kw))

        def delete(self, url, **kw):
            return self._loop.run_until_complete(self._req("DELETE", url, **kw))

        async def _req(self, method, url, **kw):
            async with AsyncClient(transport=self._transport, base_url=self._base) as ac:
                return await ac.request(method, url, **kw)

    return RemoteSyncClient()
