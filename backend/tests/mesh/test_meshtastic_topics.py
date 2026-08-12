from services.mesh.meshtastic_topics import build_subscription_topics, known_roots, parse_topic_metadata


def test_default_subscription_is_longfast_only():
    assert build_subscription_topics() == [
        "msh/US/2/e/LongFast/#",
        "msh/US/2/json/LongFast/#",
    ]
    assert known_roots() == ["US"]


def test_extra_roots_are_longfast_only():
    assert build_subscription_topics(extra_roots="EU_868,ANZ") == [
        "msh/US/2/e/LongFast/#",
        "msh/US/2/json/LongFast/#",
        "msh/EU_868/2/e/LongFast/#",
        "msh/EU_868/2/json/LongFast/#",
        "msh/ANZ/2/e/LongFast/#",
        "msh/ANZ/2/json/LongFast/#",
    ]


def test_parse_longfast_topic_root():
    meta = parse_topic_metadata("msh/US/2/e/LongFast/!12345678")
    assert meta["region"] == "US"
    assert meta["root"] == "US"
    assert meta["channel"] == "LongFast"
