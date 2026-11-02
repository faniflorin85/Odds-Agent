"""Orchestrare: cote -> candidați -> bilete -> explicație (opțională)."""
from __future__ import annotations

from datetime import datetime, timezone

from .config import Settings
from .llm import LLM, LLMError
from .models import Combo
from .oddsmath import build_legs, find_combos
from .provider import OddsProvider

DISCLAIMER = (
    "Estimările folosesc probabilități derivate din cotele caselor, nu o prognoză proprie. "
    "Casele au marjă, deci pe termen lung valoarea așteptată este de obicei negativă. "
    "Nimic nu este garantat. Doar 18+, joacă responsabil și doar sume pe care ți le permiți."
)


def combo_to_dict(combo: Combo, titles: dict[str, str]) -> dict:
    return {
        "book": combo.book,
        "book_title": titles.get(combo.book, combo.book),
        "odds": round(combo.odds, 2),
        "probability": round(combo.prob, 3),
        "ev": round(combo.ev, 3),
        "legs": [
            {
                "match": leg.match,
                "league": leg.league,
                "start": leg.commence.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                "pick": leg.pick,
                "odds": round(leg.odds, 2),
                "fair_probability": round(leg.fair_prob, 3),
            }
            for leg in combo.legs
        ],
    }


def suggest(
    settings: Settings,
    provider: OddsProvider,
    llm: LLM,
    *,
    target: float = 2.0,
    max_legs: int = 5,
    hours: int = 48,
    min_prob: float = 0.5,
    rank_by: str = "ev",
    explain: bool = True,
    top_n: int = 5,
) -> dict:
    events = provider.fetch_events(hours=hours)
    titles: dict[str, str] = {}
    for event in events:
        titles.update(event.book_titles)

    allowed = set(settings.bookmakers) or None
    legs_by_book = build_legs(
        events,
        min_books=settings.min_books,
        min_prob=min_prob,
        allowed_books=allowed,
    )
    combos = find_combos(
        legs_by_book,
        target=target,
        max_legs=max_legs,
        top_n=top_n,
        rank_by=rank_by,
    )

    notes: list[str] = []
    if not events:
        notes.append("Nu am găsit meciuri în intervalul cerut.")
    elif not combos:
        notes.append(
            "Nu există un bilet care să respecte cota țintă cu filtrele curente. "
            "Încearcă mai multe ore, mai multe ligi sau un prag de probabilitate mai mic."
        )

    result = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "params": {
            "target": target,
            "max_legs": max_legs,
            "hours": hours,
            "min_prob": min_prob,
            "rank_by": rank_by,
        },
        "events_analyzed": len(events),
        "quota": provider.quota,
        "combos": [combo_to_dict(c, titles) for c in combos],
        "explanation": None,
        "notes": notes,
        "disclaimer": DISCLAIMER,
    }

    if explain and combos and llm.enabled:
        try:
            result["explanation"] = llm.explain({"params": result["params"], "combos": result["combos"]})
        except LLMError as error:
            notes.append(f"Explicația LLM nu a fost generată: {error}")
    return result
