def test_node_settings_roundtrip(tmp_path, monkeypatch):
    from services import node_settings

    settings_path = tmp_path / "node.json"
    monkeypatch.setattr(node_settings, "NODE_FILE", settings_path)
    monkeypatch.setattr(node_settings, "_cache", None)
    monkeypatch.setattr(node_settings, "_cache_ts", 0.0)

    initial = node_settings.read_node_settings()
    disabled = node_settings.write_node_settings(enabled=False)
    updated = node_settings.write_node_settings(enabled=True)
    reread = node_settings.read_node_settings()

    assert initial["enabled"] is True
    assert initial["operator_disabled"] is False
    assert disabled["enabled"] is False
    assert disabled["operator_disabled"] is True
    assert updated["enabled"] is True
    assert updated["operator_disabled"] is False
    assert reread["enabled"] is True


def test_legacy_disabled_node_settings_auto_enable(tmp_path, monkeypatch):
    from services import node_settings

    settings_path = tmp_path / "node.json"
    settings_path.write_text('{"enabled": false, "updated_at": 123}', encoding="utf-8")
    monkeypatch.setattr(node_settings, "NODE_FILE", settings_path)
    monkeypatch.setattr(node_settings, "_cache", None)
    monkeypatch.setattr(node_settings, "_cache_ts", 0.0)

    reread = node_settings.read_node_settings()

    assert reread["enabled"] is True
    assert reread["operator_disabled"] is False


def test_explicit_operator_disabled_stays_disabled(tmp_path, monkeypatch):
    from services import node_settings

    settings_path = tmp_path / "node.json"
    settings_path.write_text('{"enabled": false, "operator_disabled": true, "updated_at": 123}', encoding="utf-8")
    monkeypatch.setattr(node_settings, "NODE_FILE", settings_path)
    monkeypatch.setattr(node_settings, "_cache", None)
    monkeypatch.setattr(node_settings, "_cache_ts", 0.0)

    reread = node_settings.read_node_settings()

    assert reread["enabled"] is False
    assert reread["operator_disabled"] is True
