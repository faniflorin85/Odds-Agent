"""Matematica cotelor: eliminarea marjei, consens între case, căutare de combinații.

Totul este determinist. Modelul de limbaj NU alege cote sau meciuri.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from .models import Combo, Event, Leg

MAX_DFS_NODES = 2_000_000


def margin(prices: dict[str, float]) -> float:
    """Marja casei pe o piață: suma probabilităților implicite minus 1."""
    return sum(1.0 / p for p in prices.values()) - 1.0


def devig(prices: dict[str, float]) -> dict[str, float]:
    """Probabilități fără marjă (metoda proporțională). Suma = 1."""
    inverse = {name: 1.0 / price for name, price in prices.items()}
    total = sum(inverse.values())
    return {name: value / total for name, value in inverse.items()}


def consensus(event: Event, min_books: int = 3) -> dict[str, float] | None:
    """Probabilitatea 'corectă' per rezultat: media probabilităților fără marjă.

    Se folosesc doar casele cu piața completă (același set de rezultate).
    Dacă sunt mai puține de `min_books`, meciul este ignorat.
    """
    if not event.books:
        return None
    shapes = Counter(frozenset(prices) for prices in event.books.values())
    outcome_set, _ = shapes.most_common(1)[0]
    complete = [prices for prices in event.books.values() if frozenset(prices) == outcome_set]
    if len(complete) < min_books or len(outcome_set) < 2:
        return None
    sums = {name: 0.0 for name in outcome_set}
    for prices in complete:
        for name, prob in devig(prices).items():
            sums[name] += prob
    total = sum(sums.values())
    return {name: value / total for name, value in sums.items()}


def build_legs(
    events: list[Event],
    *,
    min_books: int = 3,
    min_prob: float = 0.5,
    min_leg_odds: float = 1.10,
    allowed_books: set[str] | None = None,
    now: datetime | None = None,
    max_legs_per_book: int = 40,
) -> dict[str, list[Leg]]:
    """Selecții candidate, grupate pe casă de pariuri.

    Probabilitatea vine din consensul tuturor caselor; cota vine de la casa respectivă.
    """
    now = now or datetime.now(timezone.utc)
    by_book: dict[str, list[Leg]] = {}
    for event in events:
        if event.commence <= now:
            continue
        fair = consensus(event, min_books=min_books)
        if fair is None:
            continue
        for book, prices in event.books.items():
            if allowed_books and book not in allowed_books:
                continue
            for pick, odds in prices.items():
                prob = fair.get(pick)
                if prob is None or odds < min_leg_odds or prob < min_prob:
                    continue
                by_book.setdefault(book, []).append(
                    Leg(
                        event_id=event.id,
                        match=event.label,
                        league=event.league,
                        commence=event.commence,
                        pick=pick,
                        odds=odds,
                        fair_prob=prob,
                        book=book,
                    )
                )
    for book, legs in by_book.items():
        legs.sort(key=lambda leg: leg.fair_prob, reverse=True)
        by_book[book] = legs[:max_legs_per_book]
    return by_book


def find_combos(
    legs_by_book: dict[str, list[Leg]],
    *,
    target: float = 2.0,
    tol_low: float = 0.05,
    tol_high: float = 0.20,
    min_legs: int = 2,
    max_legs: int = 5,
    top_n: int = 5,
    rank_by: str = "ev",
) -> list[Combo]:
    """Bilete cu cota totală în [target - tol_low, target + tol_high].

    Toate selecțiile unui bilet sunt la aceeași casă și la meciuri diferite.
    """
    low, high = target - tol_low, target + tol_high
    found: list[Combo] = []

    for book, legs in legs_by_book.items():
        ordered = sorted(legs, key=lambda leg: leg.odds)
        nodes = 0

        def dfs(start: int, chosen: list[Leg], product: float, events: set[str]) -> None:
            nonlocal nodes
            if len(chosen) >= min_legs and low <= product <= high:
                found.append(Combo(book=book, legs=tuple(chosen)))
            if len(chosen) == max_legs:
                return
            for index in range(start, len(ordered)):
                nodes += 1
                if nodes > MAX_DFS_NODES:
                    return
                leg = ordered[index]
                new_product = product * leg.odds
                if new_product > high:
                    break  # lista e sortată crescător după cotă
                if leg.event_id in events:
                    continue
                chosen.append(leg)
                events.add(leg.event_id)
                dfs(index + 1, chosen, new_product, events)
                events.discard(leg.event_id)
                chosen.pop()

        dfs(0, [], 1.0, set())

    if rank_by == "prob":
        found.sort(key=lambda c: (-c.prob, len(c.legs)))
    else:
        found.sort(key=lambda c: (-c.ev, len(c.legs)))

    unique: list[Combo] = []
    seen: set[tuple] = set()
    for combo in found:
        key = (combo.book, tuple(sorted((l.event_id, l.pick) for l in combo.legs)))
        if key in seen:
            continue
        seen.add(key)
        unique.append(combo)
        if len(unique) >= top_n:
            break
    return unique
