from datetime import datetime, timedelta, timezone

import pytest

from oddsagent.models import Event, Leg
from oddsagent.oddsmath import build_legs, consensus, devig, find_combos, margin

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
LATER = NOW + timedelta(hours=5)


def make_event(event_id, books, commence=LATER):
    return Event(
        id=event_id,
        league="Test League",
        home=f"H{event_id}",
        away=f"A{event_id}",
        commence=commence,
        books=books,
    )


def three_books(home, draw, away):
    return {
        "b1": {"home": home, "draw": draw, "away": away},
        "b2": {"home": home * 1.02, "draw": draw, "away": away * 0.98},
        "b3": {"home": home * 0.99, "draw": draw * 1.01, "away": away * 1.01},
    }


def test_margin_and_devig():
    prices = {"home": 1.80, "draw": 3.60, "away": 4.50}
    assert margin(prices) > 0
    assert sum(devig(prices).values()) == pytest.approx(1.0)


def test_devig_fair_market_unchanged():
    prices = {"a": 2.0, "b": 2.0}
    assert devig(prices) == {"a": pytest.approx(0.5), "b": pytest.approx(0.5)}


def test_consensus_needs_enough_books():
    event = make_event("1", {"b1": {"home": 1.5, "draw": 4.0, "away": 6.0}})
    assert consensus(event, min_books=3) is None
    assert consensus(event, min_books=1) is not None


def test_consensus_ignores_incomplete_markets():
    books = three_books(1.5, 4.0, 6.0)
    books["b4"] = {"home": 1.4, "away": 7.0}  # fără egal: exclusă
    fair = consensus(make_event("1", books), min_books=3)
    assert fair is not None
    assert set(fair) == {"home", "draw", "away"}
    assert sum(fair.values()) == pytest.approx(1.0)


def test_build_legs_filters_past_and_low_prob():
    past = make_event("1", three_books(1.5, 4.0, 6.0), commence=NOW - timedelta(hours=1))
    future = make_event("2", three_books(1.5, 4.0, 6.0))
    legs = build_legs([past, future], min_prob=0.5, now=NOW)
    assert legs
    for book_legs in legs.values():
        for leg in book_legs:
            assert leg.event_id == "2"
            assert leg.fair_prob >= 0.5
            assert leg.odds >= 1.10


def test_find_combos_respects_constraints():
    events = [make_event(str(i), three_books(1.25 + i * 0.03, 5.0, 9.0)) for i in range(8)]
    legs = build_legs(events, min_prob=0.5, now=NOW)
    combos = find_combos(legs, target=2.0, tol_low=0.05, tol_high=0.20, max_legs=5, top_n=5)
    assert combos
    for combo in combos:
        assert 1.95 <= combo.odds <= 2.20 + 1e-9
        assert 2 <= len(combo.legs) <= 5
        assert len({leg.event_id for leg in combo.legs}) == len(combo.legs)
        assert len({leg.book for leg in combo.legs}) == 1
    evs = [c.ev for c in combos]
    assert evs == sorted(evs, reverse=True)


def test_combo_math():
    legs = (
        Leg("1", "A - B", "L", LATER, "home", 1.40, 0.70, "b1"),
        Leg("2", "C - D", "L", LATER, "home", 1.50, 0.65, "b1"),
    )
    from oddsagent.models import Combo

    combo = Combo(book="b1", legs=legs)
    assert combo.odds == pytest.approx(2.10)
    assert combo.prob == pytest.approx(0.455)
    assert combo.ev == pytest.approx(0.455 * 2.10 - 1)


def test_no_combo_when_impossible():
    events = [make_event("1", three_books(1.05, 8.0, 20.0))]
    legs = build_legs(events, min_prob=0.5, min_leg_odds=1.0, now=NOW)
    assert find_combos(legs, target=2.0) == []


def test_rank_by_prob_orders_by_probability():
    events = [make_event(str(i), three_books(1.20 + i * 0.04, 5.0, 9.0)) for i in range(8)]
    legs = build_legs(events, min_prob=0.5, now=NOW)
    combos = find_combos(legs, rank_by="prob", top_n=5)
    probs = [c.prob for c in combos]
    assert probs == sorted(probs, reverse=True)
