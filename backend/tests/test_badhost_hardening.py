from starlette.requests import Request

import auth


async def _empty_receive():
    return {"type": "http.request", "body": b"", "more_body": False}


def _request(path: str, *, host: str = "example.com/health?x=", client_host: str = "203.0.113.10") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "server": ("127.0.0.1", 8000),
            "client": (client_host, 12345),
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": [(b"host", host.encode("ascii"))],
        },
        receive=_empty_receive,
    )


def test_scope_auth_uses_asgi_path_not_host_derived_url_path():
    request = _request("/api/mesh/gate/alpha/message")

    assert auth._request_scope_path(request) == "/api/mesh/gate/alpha/message"
    assert auth._required_scope_for_request(request) == "mesh"


def test_debug_test_request_does_not_trust_host_header(monkeypatch):
    monkeypatch.setattr(auth, "_debug_mode_enabled", lambda: True)

    request = _request("/api/admin", host="test/api/public?x=")

    assert auth._is_debug_test_request(request) is False


def test_peer_hmac_identity_requires_explicit_peer_url_header():
    request = _request("/api/mesh/infonet/push", host="https://peer.example/api/public?x=")

    assert auth._peer_hmac_url_from_request(request) == ""

    request = _request("/api/mesh/infonet/push")
    request.scope["headers"].append((b"x-peer-url", b"https://peer.example/"))

    assert auth._peer_hmac_url_from_request(request) == "https://peer.example"
