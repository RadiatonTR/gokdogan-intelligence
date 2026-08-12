import os


def test_save_api_keys_persists_write_only(tmp_path, monkeypatch):
    from services import api_settings

    key_store = tmp_path / "operator_api_keys.env"
    backend_env = tmp_path / ".env"
    monkeypatch.setattr(api_settings, "OPERATOR_KEYS_ENV_PATH", key_store)
    monkeypatch.setattr(api_settings, "ENV_PATH", backend_env)
    monkeypatch.delenv("OPENSKY_CLIENT_ID", raising=False)

    result = api_settings.save_api_keys(
        {
            "OPENSKY_CLIENT_ID": "client-id-value",
            "NOT_ALLOWED": "ignore-me",
        }
    )

    assert result["ok"] is True
    assert result["updated"] == ["OPENSKY_CLIENT_ID"]
    assert "client-id-value" not in str(result)
    assert os.environ["OPENSKY_CLIENT_ID"] == "client-id-value"
    assert 'OPENSKY_CLIENT_ID="client-id-value"' in key_store.read_text(encoding="utf-8")
    assert "NOT_ALLOWED" not in key_store.read_text(encoding="utf-8")


def test_persisted_api_keys_load_when_process_env_blank(tmp_path, monkeypatch):
    from services import api_settings

    key_store = tmp_path / "operator_api_keys.env"
    key_store.write_text('AIS_API_KEY="saved-ais-key"\n', encoding="utf-8")
    monkeypatch.setattr(api_settings, "OPERATOR_KEYS_ENV_PATH", key_store)
    monkeypatch.setenv("AIS_API_KEY", "")

    api_settings.load_persisted_api_keys_into_environ()

    assert os.environ["AIS_API_KEY"] == "saved-ais-key"
