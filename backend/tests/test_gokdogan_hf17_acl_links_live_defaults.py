from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_tauri_main_capability_allows_only_app_owned_loopback_remote_origin():
    path = ROOT / 'desktop-shell' / 'tauri-skeleton' / 'src-tauri' / 'capabilities' / 'main.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    urls = (data.get('remote') or {}).get('urls') or []
    assert 'http://127.0.0.1:*/*' in urls
    assert all('127.0.0.1' in url for url in urls)
    assert 'main' in data.get('windows', [])


def test_native_commands_needed_by_loopback_webview_are_registered():
    source = (ROOT / 'desktop-shell' / 'tauri-skeleton' / 'src-tauri' / 'src' / 'main.rs').read_text(encoding='utf-8')
    for command in (
        'desktop_secret_set_many',
        'desktop_open_external',
        'desktop_backend_status',
        'invoke_local_control',
    ):
        assert command in source
    assert "http://127.0.0.1:" in source
    assert "parsed.scheme()" in source
    assert '"http" | "https"' in source


def test_participant_node_activation_does_not_require_tor():
    source = (ROOT / 'frontend' / 'src' / 'components' / 'TopRightControls.tsx').read_text(encoding='utf-8')
    assert "void startTorHiddenService().catch(() => null);" in source
    assert "throw new Error(torStatus?.detail || 'Tor onion service did not start')" not in source
    assert 'katılımcı düğüm eşitlemesi Wormhole gerektirmez' in source


def test_public_live_layers_are_on_by_default_in_backend_and_frontend():
    backend = (ROOT / 'backend' / 'services' / 'fetchers' / '_store.py').read_text(encoding='utf-8')
    frontend = (ROOT / 'frontend' / 'src' / 'lib' / 'layerPreferences.ts').read_text(encoding='utf-8')
    for token in ('"cctv": True', '"firms": True', '"crowdthreat": True'):
        assert token in backend
    for token in ('cctv: true', 'firms: true', 'crowdthreat: true'):
        assert token in frontend


def test_startup_preloads_realtime_context_and_cctv_ingest_is_not_three_minutes_late():
    source = (ROOT / 'backend' / 'services' / 'data_fetcher.py').read_text(encoding='utf-8')
    for func in ('fetch_weather,', 'fetch_earthquakes,', 'fetch_frontlines,', 'fetch_space_weather,'):
        assert func in source
    assert 'SHADOWBROKER_STARTUP_CCTV_INGEST_DELAY_S", "10"' in source


def test_crowdthreat_uses_gokdogan_live_profile_without_forcing_generic_upstream_builds():
    from services.fetchers.crowdthreat import crowdthreat_fetch_enabled

    old_explicit = os.environ.pop('CROWDTHREAT_ENABLED', None)
    old_live = os.environ.get('GOKDOGAN_LIVE_DATA')
    try:
        os.environ['GOKDOGAN_LIVE_DATA'] = 'true'
        assert crowdthreat_fetch_enabled() is True
        os.environ['CROWDTHREAT_ENABLED'] = 'false'
        assert crowdthreat_fetch_enabled() is False
    finally:
        if old_explicit is None:
            os.environ.pop('CROWDTHREAT_ENABLED', None)
        else:
            os.environ['CROWDTHREAT_ENABLED'] = old_explicit
        if old_live is None:
            os.environ.pop('GOKDOGAN_LIVE_DATA', None)
        else:
            os.environ['GOKDOGAN_LIVE_DATA'] = old_live
