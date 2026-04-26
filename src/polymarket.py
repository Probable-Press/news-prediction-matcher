"""Polymarket Gamma API 検索。

JSON で標準出力に書き出す。Claude Code が各キーワードごとに呼び出す。

Usage:
    python src/polymarket.py "trump ukraine" ["japan rate"] ...
"""

from __future__ import annotations

import json
import sys

import requests

GAMMA_API_BASE = "https://gamma-api.polymarket.com"
SEARCH_PATH = "/public-search"
DEFAULT_LIMIT = 5
TIMEOUT = 15


def _coerce_float(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _parse_list(raw) -> list:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return []
    return []


def _yes_price(market: dict) -> float | None:
    last = _coerce_float(market.get("lastTradePrice"))
    if last is not None:
        return last
    outcomes = [str(o).strip().lower() for o in _parse_list(market.get("outcomes"))]
    prices = [_coerce_float(p) for p in _parse_list(market.get("outcomePrices"))]
    if not prices:
        return None
    for label, price in zip(outcomes, prices):
        if label == "yes" and price is not None:
            return price
    return prices[0] if prices[0] is not None else None


def search(query: str, limit: int = DEFAULT_LIMIT, only_active: bool = True) -> list[dict]:
    resp = requests.get(
        f"{GAMMA_API_BASE}{SEARCH_PATH}",
        params={"q": query, "limit_per_type": limit},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    markets: list[dict] = []
    for event in resp.json().get("events", []) or []:
        for m in event.get("markets", []) or []:
            active = bool(m.get("active", event.get("active", False)))
            closed = bool(m.get("closed", event.get("closed", False)))
            if only_active and (closed or not active):
                continue
            vol = _coerce_float(m.get("volumeNum")) or _coerce_float(m.get("volume"))
            markets.append({
                "question": (m.get("question") or event.get("title") or "").strip(),
                "event_title": (event.get("title") or "").strip(),
                "event_slug": (event.get("slug") or "").strip(),
                "yes_price": _yes_price(m),
                "volume": vol,
                "end_date": m.get("endDate") or event.get("endDate"),
                "url": f"https://polymarket.com/event/{event.get('slug', '')}",
            })
    markets.sort(key=lambda x: x["volume"] or 0.0, reverse=True)
    return markets[:limit]


def main() -> None:
    queries = sys.argv[1:]
    if not queries:
        print("Usage: python src/polymarket.py <query> [query2 ...]", file=sys.stderr)
        sys.exit(1)

    results: dict[str, list[dict]] = {}
    for q in queries:
        try:
            results[q] = search(q)
        except Exception as exc:
            results[q] = [{"error": str(exc)}]

    json.dump(results, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
