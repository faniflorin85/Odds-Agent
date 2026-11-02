"""Structuri de date comune."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Event:
    """Un meci cu cotele 1X2 de la mai multe case.

    books: cheie casă -> {nume rezultat -> cotă zecimală}
    """

    id: str
    league: str
    home: str
    away: str
    commence: datetime
    books: dict[str, dict[str, float]] = field(default_factory=dict)
    book_titles: dict[str, str] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return f"{self.home} - {self.away}"


@dataclass(frozen=True)
class Leg:
    """O selecție (un rezultat la un meci) la cota unei anumite case."""

    event_id: str
    match: str
    league: str
    commence: datetime
    pick: str
    odds: float
    fair_prob: float
    book: str


@dataclass(frozen=True)
class Combo:
    """Un bilet: mai multe selecții la ACEEAȘI casă de pariuri."""

    book: str
    legs: tuple[Leg, ...]

    @property
    def odds(self) -> float:
        total = 1.0
        for leg in self.legs:
            total *= leg.odds
        return total

    @property
    def prob(self) -> float:
        """Probabilitate comună estimată (meciuri independente)."""
        total = 1.0
        for leg in self.legs:
            total *= leg.fair_prob
        return total

    @property
    def ev(self) -> float:
        """Valoare așteptată per 1 unitate mizată: prob * cotă - 1."""
        return self.prob * self.odds - 1.0
