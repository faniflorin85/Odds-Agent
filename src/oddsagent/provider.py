"""Client pentru The Odds API (v4) cu cache pe disc, ca să economisim cota gratuită."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from .config import Settings
from .models import Event


class ProviderError(RuntimeError):
    """Eroare sanitizată: nu conține niciodată URL-ul cu cheia API."""


def parse_events(raw: list[dict], league_fallback: str = "") -> list[Event]:
    """Transformă răspunsul API în obiecte Event (piața h2h / 1X2)."""
    events: list[Event] = []
    for item in raw:
        try:
            commence = datetime.fromisoformat(item["commence_time"].replace("Z", "+00:00"))
            event = Event(
                id=str(item["id"]),
                league=item.get("sport_title") or league_fallback,
                home=item["home_team"],
                away=item["away_team"],
                commence=commence,
            )
        except (KeyError, ValueError, AttributeError):
            continue
        for book in item.get("bookmakers", []):
            for market in book.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                prices = {}
                for outcome in market.get("outcomes", []):
                    name, price = outcome.get("name"), outcome.get("price")
                    if isinstance(name, str) and isinstance(price, (int, float)) and price > 1.0:
                        prices[name] = float(price)
                if len(prices) >= 2:
                    event.books[book["key"]] = prices
                    event.book_titles[book["key"]] = book.get("title", book["key"])
        if event.books:
            events.append(event)
    return events


class OddsProvider:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self._client = client or httpx.Client(timeout=30)
        self.quota: dict[str, str] = {}

    # ---- cache -------------------------------------------------------
    def _cache_path(self, key: str) -> Path:
        digest = hashlib.sha1(key.encode()).hexdigest()
        return Path(self.settings.cache_dir) / f"{digest}.json"

    def _cache_get(self, key: str):
        path = self._cache_path(key)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if time.time() - payload.get("ts", 0) > self.settings.cache_ttl:
            return None
        self.quota = payload.get("quota", {})
        return payload.get("data")

    def _cache_put(self, key: str, data) -> None:
        path = self._cache_path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"ts": time.time(), "data": data, "quota": self.quota}),
                encoding="utf-8",
            )
        except OSError:
            pass  # cache-ul e opțional

    # ---- API ---------------------------------------------------------
    def _get(self, path: str, params: dict) -> list | dict:
        if not self.settings.odds_api_key:
            raise ProviderError("ODDS_API_KEY lipsește. Vezi .env.example.")
        try:
            response = self._client.get(
                f"{self.settings.odds_base_url}{path}",
                params={**params, "apiKey": self.settings.odds_api_key},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            code = error.response.status_code
            hint = {
                401: "cheia API nu este acceptată",
                422: "parametri invalizi (verifică cheia sportului)",
                429: "limită de cereri/credite atinsă",
            }.get(code, "eroare la furnizorul de cote")
            raise ProviderError(f"The Odds API a răspuns HTTP {code}: {hint}.") from None
        except httpx.HTTPError as error:
            raise ProviderError(f"Conexiune eșuată către The Odds API ({type(error).__name__}).") from None
        self.quota = {
            "remaining": response.headers.get("x-requests-remaining", ""),
            "used": response.headers.get("x-requests-used", ""),
        }
        return response.json()

    def list_sports(self) -> list[dict]:
        key = "sports"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        data = self._get("/sports", {})
        self._cache_put(key, data)
        return data

    def fetch_events(self, hours: int = 48) -> list[Event]:
        """Meciuri care încep în următoarele `hours` ore, din toate ligile configurate."""
        if not self.settings.odds_api_key:
            raise ProviderError("ODDS_API_KEY lipsește. Vezi .env.example.")
        now = datetime.now(timezone.utc).replace(microsecond=0)
        end =(now + timedelta(hours=hours)).replace(minute=0, second=0)
        events: list[Event] = []
        errors: list[str] = []
        for sport in self.settings.sports:
            params = {
                "regions": self.settings.regions,
                "markets": "h2h",
                "oddsFormat": "decimal",
                "dateFormat": "iso",
                "commenceTimeTo": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            # Filtrul ODDS_BOOKMAKERS se aplică selecțiilor, nu cererii: consensul
            # de probabilitate trebuie calculat din cât mai multe case.
            key =f"{sport}|{sorted(params.items())}"
            data = self._cache_get(key)
            if data is None:
                try:
                    data = self._get(f"/sports/{sport}/odds", params)
                except ProviderError as error:
                    errors.append(f"{sport}: {error}")
                    continue
                self._cache_put(key, data)
            events.extend(parse_events(data, league_fallback=sport))
        if not events and errors:
            raise ProviderError("; ".join(errors))
        return events
