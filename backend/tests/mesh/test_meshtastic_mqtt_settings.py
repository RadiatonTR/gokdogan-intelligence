import importlib


def test_meshtastic_mqtt_settings_redacts_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("SB_DATA_DIR", str(tmp_path))

    from services import meshtastic_mqtt_settings

    settings = importlib.reload(meshtastic_mqtt_settings)
    saved = settings.write_meshtastic_mqtt_settings(
        enabled=True,
        broker="mqtt.example.test",
        port=1884,
        username="mesh-user",
        password="mesh-pass",
        psk="001122",
        include_default_roots=False,
        extra_roots="EU,US",
    )
    redacted = settings.redacted_meshtastic_mqtt_settings(saved)

    assert saved["password"] == "mesh-pass"
    assert saved["psk"] == "001122"
    assert redacted["enabled"] is True
    assert redacted["broker"] == "mqtt.example.test"
    assert redacted["port"] == 1884
    assert redacted["username"] == "mesh-user"
    assert redacted["has_password"] is True
    assert redacted["has_psk"] is True
    assert "password" not in redacted
    assert "psk" not in redacted
    assert settings.mqtt_connection_config() == ("mqtt.example.test", 1884, "mesh-user", "mesh-pass")
    assert settings.mqtt_bridge_enabled() is True
    assert settings.mqtt_psk_hex() == "001122"
    assert settings.mqtt_subscription_settings() == ("EU,US", "", False)


def test_meshtastic_mqtt_settings_hide_public_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("SB_DATA_DIR", str(tmp_path))

    from services import meshtastic_mqtt_settings

    settings = importlib.reload(meshtastic_mqtt_settings)
    saved = settings.write_meshtastic_mqtt_settings(
        enabled=True,
        broker="mqtt.meshtastic.org",
        username="",
        password="",
    )
    redacted = settings.redacted_meshtastic_mqtt_settings(saved)

    assert redacted["username"] == ""
    assert redacted["uses_default_credentials"] is True
    assert settings.mqtt_connection_config() == ("mqtt.meshtastic.org", 1883, "meshdev", "large4cats")
