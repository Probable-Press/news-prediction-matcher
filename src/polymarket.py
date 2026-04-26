"""Polymarket Gamma API client.

Looks up active markets on Polymarket using the public search endpoint.
Used to find prediction markets relevant to a news headline's keywords.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests

GAMMA_API_BASE = "https://gamma-api.polymarket.com"
SEARCH_PATH = "/public-search"
DEFAULT_TIMEOUT = 15
POLYMARKET_EVENT_URL = "https://polymarket.com/event/{slug}"


@dataclass
class Market:
    """A Polymarket market with its current YES probability."""

    question: str
    event_title: str
    event_slug: str
    yes_price: float | None
    volume: float | None
    end_date: str | None
    active: bool
    closed: bool

    @property
    def url(self) -> str:
        return POLYMARKET_EVENT_URL.format(slug=self.event_slug)


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_outcome_prices(raw: Any) -> list[float]:
    """outcomePrices is sometimes a JSON-encoded string, sometimes a list."""
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if isinstance(raw, list):
        out: list[float] = []
        for v in raw:
            f = _coerce_float(v)
            if f is not None:
                out.append(f)
        return out
    return []


def _parse_outcomes(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if isinstance(raw, list):
        return [str(v) for v in raw]
    return []


def _yes_price(market: dict[str, Any]) -> float | None:
    """Extract the YES-side probability (0..1) from a market dict."""
    last = _coerce_float(market.get("lastTradePrice"))
    if last is not None:
        return last
    outcomes = _parse_outcomes(market.get("outcomes"))
    prices = _parse_outcome_prices(market.get("outcomePrices"))
    if not prices:
        return None
    for label, price in zip(outcomes, prices):
        if label.strip().lower() == "yes":
            return price
    return prices[0]


def _build_market(event: dict[str, Any], market: dict[str, Any]) -> Market:
    volume = _coerce_float(market.get("volumeNum")) or _coerce_float(market.get("volume"))
    return Market(
        question=str(market.get("question") or event.get("title") or "").strip(),
        event_title=str(event.get("title") or "").strip(),
        event_slug=str(event.get("slug") or "").strip(),
        yes_price=_yes_price(market),
        volume=volume,
        end_date=market.get("endDate") or event.get("endDate"),
        active=bool(market.get("active", event.get("active", False))),
        closed=bool(market.get("closed", event.get("closed", False))),
    )


def search_markets(query: str, limit: int = 5, *, only_active: bool = True) -> list[Market]:
    """Search Polymarket for markets matching a keyword.

    Returns up to `limit` markets, sorted by descending volume.
    """
    response = requests.get(
        f"{GAMMA_API_BASE}{SEARCH_PATH}",
        params={"q": query, "limit_per_type": limit},
        timeout=DEFAULT_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()

    markets: list[Market] = []
    for event in data.get("events", []) or []:
        for raw_market in event.get("markets", []) or []:
            m = _build_market(event, raw_market)
            if only_active and (m.closed or not m.active):
                continue
            markets.append(m)

    markets.sort(key=lambda m: m.volume or 0.0, reverse=True)
    return markets[:limit]
