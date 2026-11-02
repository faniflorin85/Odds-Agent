import httpx
import pytest

from oddsagent.provider import OddsProvider, ProviderError, parse_events

from conftest import raw_event


def make_provider(settings, handler):
    return OddsProvider(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_parse_events_extracts_h2h():
    events = parse_events([raw_event(1)])
    assert len(events) == 1
    event = events[0]
    assert event.home == "Home1" and event.away == "Away1"
    assert set(event.books) == {"alpha", "beta", "gamma", "delta"}
    assert set(event.books["alpha"]) == {"Home1", "Draw", "Away1"}
    assert event.book_titles["alpha"] == "Alpha"


def test_parse_events_skips_malformed_and_bad_prices():
    bad = {"id": "x"}  # lipsesc câmpuri
    weird = raw_event(2)
    weird["bookmakers"][0]["markets"][0]["outcomes"][0]["price"] = 0.9  # cotă invalidă
    events = parse_events([bad, weird])
    assert len(events) == 1
    assert "Home2" not in events[0].books["alpha"]


def test_fetch_events_uses_cache(settings):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=[raw_event(1)], headers={"x-requests-remaining": "490"})

    provider = make_provider(settings, handler)
    assert len(provider.fetch_events(hours=24)) == 1
    assert len(provider.fetch_events(hours=24)) == 1
    assert len(calls) == 1  # a doua oară din cache
    assert provider.quota.get("remaining") == "490"


def test_http_error_is_sanitized(settings):
    provider = make_provider(settings, lambda request: httpx.Response(401, json={"message": "bad key"}))
    with pytest.raises(ProviderError) as info:
        provider.fetch_events(hours=24)
    message = str(info.value)
    assert "401" in message
    assert "SECRET-KEY-123" not in message


def test_connection_error_is_sanitized(settings):
    def handler(request):
        raise httpx.ConnectError("boom", request=request)

    provider = make_provider(settings, handler)
    with pytest.raises(ProviderError) as info:
        provider.fetch_events(hours=24)
    assert "SECRET-KEY-123" not in str(info.value)


def test_missing_key_message(settings):
    from dataclasses import replace

    provider = make_provider(replace(settings, odds_api_key=""), lambda r: httpx.Response(200, json=[]))
    with pytest.raises(ProviderError, match="ODDS_API_KEY"):
        provider.fetch_events(hours=24)


def test_partial_failure_still_returns_other_leagues(settings):
    from dataclasses import replace

    both = replace(settings, sports=("soccer_a", "soccer_b"))

    def handler(request):
        if "soccer_a" in str(request.url):
            return httpx.Response(422, json={})
        return httpx.Response(200, json=[raw_event(1)])

    events = make_provider(both, handler).fetch_events(hours=24)
    assert len(events) == 1
