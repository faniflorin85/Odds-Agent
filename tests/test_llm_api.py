import json
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from oddsagent.api import create_app
from oddsagent.llm import LLM, LLMError
from oddsagent.provider import OddsProvider

from conftest import raw_event

PAYLOAD = {"params": {"target": 2.0}, "combos": []}


def llm_with(settings, handler, **changes):
    return LLM(
        replace(settings, **changes),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_llm_none_returns_nothing(settings):
    llm = llm_with(settings, lambda r: httpx.Response(500))
    assert llm.enabled is False
    assert llm.explain(PAYLOAD) is None


def test_llm_ollama(settings):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"content": " Explicație. "}})

    llm = llm_with(settings, handler, llm_backend="ollama")
    assert llm.explain(PAYLOAD) == "Explicație."
    assert seen["url"].endswith("/api/chat")
    assert seen["body"]["model"] == "test-model" and seen["body"]["stream"] is False


def test_llm_openai_compatible(settings):
    seen = {}

    def handler(request):
        seen["auth"] = request.headers["authorization"]
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    llm = llm_with(settings, handler, llm_backend="openai")
    assert llm.explain(PAYLOAD) == "ok"
    assert seen["auth"] == "Bearer LLM-SECRET"
    assert seen["url"] == "https://llm.example/v1/chat/completions"


def test_llm_errors_are_sanitized(settings):
    llm = llm_with(settings, lambda r: httpx.Response(401), llm_backend="openai")
    with pytest.raises(LLMError) as info:
        llm.explain(PAYLOAD)
    assert "LLM-SECRET" not in str(info.value)


def test_llm_openai_requires_key(settings):
    llm = llm_with(settings, lambda r: httpx.Response(200), llm_backend="openai", llm_api_key="")
    with pytest.raises(LLMError, match="LLM_API_KEY"):
        llm.explain(PAYLOAD)


def make_client(settings, events_json, llm=None):
    provider = OddsProvider(
        settings,
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=events_json))),
    )
    return TestClient(create_app(settings, provider, llm or LLM(settings)))


def test_health_and_index(settings):
    client = make_client(settings, [])
    assert client.get("/health").json()["status"] == "ok"
    assert "Odds Agent" in client.get("/").text


def test_suggest_endpoint_end_to_end(settings):
    events = [raw_event(i, home_odds=1.22 + i * 0.03) for i in range(8)]
    client = make_client(settings, events)
    response = client.get("/suggest", params={"target": 2.0, "max_legs": 5, "hours": 48})
    assert response.status_code == 200
    data = response.json()
    assert data["events_analyzed"] == 8
    assert data["combos"], data["notes"]
    for combo in data["combos"]:
        assert 1.95 <= combo["odds"] <= 2.20
        assert 2 <= len(combo["legs"]) <= 5
    assert "garantat" in data["disclaimer"]
    assert "SECRET-KEY-123" not in response.text


def test_suggest_with_llm_explanation(settings):
    events = [raw_event(i, home_odds=1.22 + i * 0.03) for i in range(8)]
    llm = llm_with(
        settings,
        lambda r: httpx.Response(200, json={"message": {"content": "Rezumat."}}),
        llm_backend="ollama",
    )
    data = make_client(settings, events, llm).get("/suggest").json()
    assert data["explanation"] == "Rezumat."


def test_llm_failure_does_not_break_suggestions(settings):
    events = [raw_event(i, home_odds=1.22 + i * 0.03) for i in range(8)]
    llm = llm_with(settings, lambda r: httpx.Response(500), llm_backend="ollama")
    data = make_client(settings, events, llm).get("/suggest").json()
    assert data["combos"]
    assert data["explanation"] is None
    assert any("LLM" in note for note in data["notes"])


def test_provider_failure_returns_502(settings):
    provider = OddsProvider(
        settings,
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429))),
    )
    client = TestClient(create_app(settings, provider, LLM(settings)))
    response = client.get("/suggest")
    assert response.status_code == 502
    assert "SECRET-KEY-123" not in response.text


def test_parameter_validation(settings):
    client = make_client(settings, [])
    assert client.get("/suggest", params={"max_legs": 9}).status_code == 422
    assert client.get("/suggest", params={"target": 0.5}).status_code == 422
