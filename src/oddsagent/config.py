"""Configurare din variabile de mediu (vezi .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_SPORTS = (
    "soccer_epl,soccer_spain_la_liga,soccer_italy_serie_a,soccer_germany_bundesliga,"
    "soccer_france_ligue_one,soccer_uefa_champs_league,soccer_uefa_europa_league"
)


def _csv(name: str, default: str = "") -> tuple[str, ...]:
    raw = os.environ.get(name, default)
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    odds_api_key: str
    odds_base_url: str
    sports: tuple[str, ...]
    regions: str
    bookmakers: tuple[str, ...]  # gol = toate casele returnate
    cache_dir: str
    cache_ttl: int
    min_books: int
    llm_backend: str  # none | ollama | openai
    ollama_url: str
    ollama_model: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_timeout: int


def load_settings() -> Settings:
    return Settings(
        odds_api_key=os.environ.get("ODDS_API_KEY", "").strip(),
        odds_base_url=os.environ.get("ODDS_BASE_URL", "https://api.the-odds-api.com/v4").rstrip("/"),
        sports=_csv("ODDS_SPORTS", DEFAULT_SPORTS),
        regions=os.environ.get("ODDS_REGIONS", "eu").strip(),
        bookmakers=_csv("ODDS_BOOKMAKERS"),
        cache_dir=os.environ.get("CACHE_DIR", "/data/cache"),
        cache_ttl=_int("CACHE_TTL_SECONDS", 3600),
        min_books=_int("MIN_BOOKS", 3),
        llm_backend=os.environ.get("LLM_BACKEND", "none").strip().lower(),
        ollama_url=os.environ.get("OLLAMA_URL", "http://ollama:11434").rstrip("/"),
        ollama_model=os.environ.get("OLLAMA_MODEL", "llama3.2:3b"),
        llm_base_url=os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        llm_api_key=os.environ.get("LLM_API_KEY", "").strip(),
        llm_model=os.environ.get("LLM_MODEL", "gpt-5-mini"),
        llm_timeout=_int("LLM_TIMEOUT_SECONDS", 120),
    )
