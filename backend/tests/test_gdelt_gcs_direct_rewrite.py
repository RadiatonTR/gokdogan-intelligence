"""GDELT's ``data.gdeltproject.org`` is a CNAME to a Google Cloud Storage
bucket. GCS responds with the wildcard ``*.storage.googleapis.com``
certificate, which legitimately does NOT cover the GDELT custom
domain, so Python's TLS verification refuses the connection. Some
networks happen to route through a path where this works; many
(notably Docker Desktop's outbound NAT on local installs) do not.

The fix in ``services.geopolitics._gcs_direct_gdelt_url`` rewrites any
URL pointing at ``data.gdeltproject.org`` to its GCS-direct equivalent
(``storage.googleapis.com/data.gdeltproject.org/...``), where the
standard GCS certificate is genuinely valid. ``api.gdeltproject.org``
and every other host are left untouched.

These tests pin that behavior so a future refactor that drops the
helper or accidentally rewrites the wrong host gets a loud failure.
"""
from __future__ import annotations

import pytest


def test_rewrites_data_gdeltproject_https():
    from services.geopolitics import _gcs_direct_gdelt_url

    assert _gcs_direct_gdelt_url(
        "https://data.gdeltproject.org/gdeltv2/lastupdate.txt"
    ) == "https://storage.googleapis.com/data.gdeltproject.org/gdeltv2/lastupdate.txt"


def test_rewrites_data_gdeltproject_http():
    """GDELT's lastupdate.txt sometimes lists URLs with http:// — we
    rewrite those too (the downstream call upgrades them to https)."""
    from services.geopolitics import _gcs_direct_gdelt_url

    assert _gcs_direct_gdelt_url(
        "http://data.gdeltproject.org/gdeltv2/20260301120000.export.CSV.zip"
    ) == "http://storage.googleapis.com/data.gdeltproject.org/gdeltv2/20260301120000.export.CSV.zip"


def test_rewrites_preserve_query_string_and_path():
    from services.geopolitics import _gcs_direct_gdelt_url

    url = "https://data.gdeltproject.org/some/deep/path?a=1&b=2&c=hello%20world"
    rewritten = _gcs_direct_gdelt_url(url)
    assert rewritten == (
        "https://storage.googleapis.com/data.gdeltproject.org"
        "/some/deep/path?a=1&b=2&c=hello%20world"
    )


def test_does_not_touch_api_gdeltproject_org():
    """The API host is NOT a CNAME to GCS; rewriting it would break the
    actual GDELT API endpoint."""
    from services.geopolitics import _gcs_direct_gdelt_url

    url = "https://api.gdeltproject.org/api/v2/doc/doc?query=carrier"
    assert _gcs_direct_gdelt_url(url) == url


def test_does_not_touch_other_hosts():
    from services.geopolitics import _gcs_direct_gdelt_url

    for url in (
        "https://en.wikipedia.org/wiki/Boeing_747",
        "https://query.wikidata.org/sparql",
        "https://storage.googleapis.com/already-correct/path",
        "https://nominatim.openstreetmap.org/search",
    ):
        assert _gcs_direct_gdelt_url(url) == url


def test_does_not_partially_match_strings():
    """``data.gdeltproject.org`` is matched exactly; URLs that merely
    contain that substring elsewhere (in a query parameter, for example)
    are left alone. Otherwise we'd rewrite something like
    ``https://example.com/?ref=data.gdeltproject.org/x`` which is wrong."""
    from services.geopolitics import _gcs_direct_gdelt_url

    # The match requires ``://`` immediately before the host, so a host
    # like ``example-data.gdeltproject.org`` would also be left alone
    # (treated as a different host, which is correct).
    url = "https://example-data.gdeltproject.org/path"
    assert _gcs_direct_gdelt_url(url) == url
