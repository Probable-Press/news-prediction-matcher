"""Polymarket 出来高上位の市場一括取得。

キーワード検索ではなく、現在アクティブな市場を出来高順にまるごと取得する。
ニュースとのマッチングは Claude 側で行う。

Usage: python src/fetch_markets.py [limit]   # default 50
JSON配列を標準出力。
"""

from __future__ import annotations

import json
import sys

import requests

GAMMA_BASE = "https://gamma-api.polymarket.com"
TIMEOUT = 20


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


SPORTS_TAGS = {"sports", "nba", "nfl", "mlb", "nhl", "soccer", "tennis", "golf",
               "esports", "dota", "lol", "valorant", "csgo"}


def _is_sports(event: dict) -> bool:
    cat = (event.get("category") or "").lower()
    if cat in SPORTS_TAGS:
        return True
    tags = [str(t.get("slug", t)).lower() if isinstance(t, dict) else str(t).lower()
            for t in (event.get("tags") or [])]
    return any(t in SPORTS_TAGS for t in tags)


def _fetch_events(order: str) -> list[dict]:
    resp = requests.get(
        f"{GAMMA_BASE}/events",
        params={"active": "true", "closed": "false", "archived": "false",
                "order": order, "ascending": "false", "limit": 100},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json() or []


def _flatten(event: dict) -> list[dict]:
    out = []
    for m in event.get("markets", []) or []:
        if m.get("closed") or not m.get("active", True):
            continue
        vol = _coerce_float(m.get("volumeNum")) or _coerce_float(m.get("volume"))
        out.append({
            "question":    (m.get("question") or event.get("title") or "").strip(),
            "event_title": (event.get("title") or "").strip(),
            "event_slug":  (event.get("slug") or "").strip(),
            "category":    event.get("category") or "",
            "is_sports":   _is_sports(event),
            "yes_price":   _yes_price(m),
            "volume":      vol,
            "volume_24h":  _coerce_float(m.get("volume24hr")) or _coerce_float(event.get("volume24hr")),
            "end_date":    m.get("endDate") or event.get("endDate"),
            "url":         f"https://polymarket.com/event/{event.get('slug', '')}",
        })
    return out


def fetch_top(limit: int = 50) -> list[dict]:
    """カテゴリ多様性を確保した市場リストを返す。

    24h volume と 全期間 volume の両方から候補を集め、上位 80% を非スポーツ、
    残り 20% でスポーツを含む全体を補完する。
    """
    seen: set[str] = set()
    pool: list[dict] = []
    for order in ("volume24hr", "volume"):
        for ev in _fetch_events(order):
            for m in _flatten(ev):
                key = f"{m['event_slug']}::{m['question']}"
                if key in seen:
                    continue
                seen.add(key)
                pool.append(m)

    def vol(m): return m["volume_24h"] or m["volume"] or 0.0
    pool.sort(key=vol, reverse=True)

    quota_non_sports = max(1, int(limit * 0.8))
    non_sports = [m for m in pool if not m["is_sports"]][:quota_non_sports]
    chosen_keys = {f"{m['event_slug']}::{m['question']}" for m in non_sports}
    rest = [m for m in pool
            if f"{m['event_slug']}::{m['question']}" not in chosen_keys][:limit - len(non_sports)]
    return non_sports + rest


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    json.dump(fetch_top(limit), sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
