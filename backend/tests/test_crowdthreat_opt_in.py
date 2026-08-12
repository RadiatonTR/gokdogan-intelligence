"""CrowdThreat ingestion is operator opt-in only."""


class _CrowdThreatResponse:
    status_code = 200

    def json(self):
        return {
            "data": {
                "threats": [
                    {
                        "id": "ct-1",
                        "title": "Example report",
                        "location": {
                            "lng_lat": [12.5, 41.9],
                            "name": "Example place",
                            "country": {"name": "Italy"},
                        },
                        "category": {"id": 1, "name": "Security"},
                    }
                ]
            }
        }


def test_crowdthreat_disabled_by_default_does_not_call_upstream(monkeypatch):
    from services.fetchers import _store, crowdthreat

    monkeypatch.delenv("CROWDTHREAT_ENABLED", raising=False)
    monkeypatch.setitem(_store.latest_data, "crowdthreat", [{"id": "old"}])
    monkeypatch.setattr(
        crowdthreat,
        "fetch_with_curl",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("upstream called")),
    )

    crowdthreat.fetch_crowdthreat()

    assert _store.latest_data["crowdthreat"] == []


def test_crowdthreat_opt_in_fetches_when_layer_is_enabled(monkeypatch):
    from services.fetchers import _store, crowdthreat

    monkeypatch.setenv("CROWDTHREAT_ENABLED", "true")
    monkeypatch.setitem(_store.active_layers, "crowdthreat", True)
    monkeypatch.setattr(crowdthreat, "fetch_with_curl", lambda *args, **kwargs: _CrowdThreatResponse())

    crowdthreat.fetch_crowdthreat()

    assert _store.latest_data["crowdthreat"][0]["id"] == "ct-1"
    assert _store.latest_data["crowdthreat"][0]["source"] == "CrowdThreat"
