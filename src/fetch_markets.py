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


def fetch_top(limit: int = 50) -> list[dict]:
    """出来高降順でアクティブな events を取得し、配下の market を平坦化して返す。"""
    resp = requests.get(
        f"{GAMMA_BASE}/events",
        params={
            "active": "true",
            "closed": "false",
            "archived": "false",
            "order": "volume24hr",
            "ascending": "false",
            "limit": min(limit, 100),
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    events = resp.json() or []
    out: list[dict] = []
    for event in events:
        for m in event.get("markets", []) or []:
            if m.get("closed") or not m.get("active", True):
                continue
            vol = _coerce_float(m.get("volumeNum")) or _coerce_float(m.get("volume"))
            out.append({
                "question":    (m.get("question") or event.get("title") or "").strip(),
                "event_title": (event.get("title") or "").strip(),
                "event_slug":  (event.get("slug") or "").strip(),
                "category":    event.get("category") or "",
                "yes_price":   _yes_price(m),
                "volume":      vol,
                "volume_24h":  _coerce_float(m.get("volume24hr")) or _coerce_float(event.get("volume24hr")),
                "end_date":    m.get("endDate") or event.get("endDate"),
                "url":         f"https://polymarket.com/event/{event.get('slug', '')}",
            })
    out.sort(key=lambda x: x["volume_24h"] or x["volume"] or 0.0, reverse=True)
    return out[:limit]


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    json.dump(fetch_top(limit), sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
