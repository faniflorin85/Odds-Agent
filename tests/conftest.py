import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from oddsagent.config import Settings  # noqa: E402


@pytest.fixture
def settings(tmp_path):
    return Settings(
        odds_api_key="SECRET-KEY-123",
        odds_base_url="https://odds.example/v4",
        sports=("soccer_test",),
        regions="eu",
        bookmakers=(),
        cache_dir=str(tmp_path / "cache"),
        cache_ttl=3600,
        min_books=3,
        llm_backend="none",
        ollama_url="http://ollama:11434",
        ollama_model="test-model",
        llm_base_url="https://llm.example/v1",
        llm_api_key="LLM-SECRET",
        llm_model="test-llm",
        llm_timeout=5,
    )


def raw_event(event_id, hours_ahead=6, home_odds=1.30):
    start = (datetime.now(timezone.utc) + timedelta(hours=hours_ahead)).strftime("%Y-%m-%dT%H:%M:%SZ")
    books = []
    for key, factor in (("alpha", 1.00), ("beta", 1.02), ("gamma", 0.99), ("delta", 1.01)):
        books.append(
            {
                "key": key,
                "title": key.title(),
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": f"Home{event_id}", "price": round(home_odds * factor, 2)},
                            {"name": "Draw", "price": 5.5},
                            {"name": f"Away{event_id}", "price": 9.0},
                        ],
                    }
                ],
            }
        )
    return {
        "id": f"ev{event_id}",
        "sport_key": "soccer_test",
        "sport_title": "Test League",
        "commence_time": start,
        "home_team": f"Home{event_id}",
        "away_team": f"Away{event_id}",
        "bookmakers": books,
    }
