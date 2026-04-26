"""NHK RSS → Polymarket keyword extraction + market search (prototype).

Fetches recent NHK headlines from the 主要 / 国際 / 経済 feeds, asks Claude
to translate each headline into 3 short English keywords, and then searches
Polymarket for prediction markets matching those keywords.

Run: python src/main.py
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import anthropic
import feedparser
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from polymarket import search_markets

NHK_FEEDS: dict[str, str] = {
    "主要": "https://www3.nhk.or.jp/rss/news/cat0.xml",
    "国際": "https://www3.nhk.or.jp/rss/news/cat6.xml",
    "経済": "https://www3.nhk.or.jp/rss/news/cat5.xml",
}

MODEL = "claude-opus-4-7"

KEYWORD_SYSTEM_PROMPT = """You translate Japanese news topics into short English search queries for Polymarket, a prediction market.

Given a Japanese news headline and summary, output exactly 3 English keyword phrases that would surface the most relevant Polymarket markets.

Rules:
- Each phrase: 1-4 words, lowercase English
- Focus on the entities and outcomes a market would bet on (people, countries, companies, elections, prices, conflicts, deals)
- Prefer concrete, searchable terms — e.g. "trump election", "japan interest rate", "boj rate hike", "russia ukraine ceasefire"
- Avoid generic words like "news", "report", "statement", "announcement"
- If the story is purely domestic Japanese with no obvious market angle, still produce 3 plausible English search phrases (translate proper nouns, name the policy area)
"""


class Keywords(BaseModel):
    """Three English Polymarket search phrases for a news item."""

    keywords: list[str] = Field(..., min_length=3, max_length=3)


@dataclass
class NewsItem:
    category: str
    title: str
    summary: str
    link: str
    published: str


def fetch_nhk_news(limit_per_category: int = 5) -> list[NewsItem]:
    items: list[NewsItem] = []
    for category, url in NHK_FEEDS.items():
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            print(f"WARN: failed to parse feed for {category} ({url})", file=sys.stderr)
            continue
        for entry in feed.entries[:limit_per_category]:
            items.append(
                NewsItem(
                    category=category,
                    title=(entry.get("title") or "").strip(),
                    summary=(entry.get("summary") or "").strip(),
                    link=entry.get("link", ""),
                    published=entry.get("published", ""),
                )
            )
    return items


def extract_keywords(client: anthropic.Anthropic, item: NewsItem) -> list[str]:
    user_prompt = (
        f"カテゴリ: {item.category}\n"
        f"見出し: {item.title}\n"
        f"概要: {item.summary or '(概要なし)'}"
    )
    response = client.messages.parse(
        model=MODEL,
        max_tokens=512,
        system=KEYWORD_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
        output_format=Keywords,
    )
    parsed = response.parsed_output
    if parsed is None:
        raise RuntimeError(f"Claude refused or returned unparseable output: stop_reason={response.stop_reason}")
    return parsed.keywords


def main() -> int:
    load_dotenv()
    if not os.getenv("ANTHROPIC_API_KEY"):
        print(
            "ERROR: ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in.",
            file=sys.stderr,
        )
        return 1

    client = anthropic.Anthropic()

    print("Fetching NHK RSS feeds...")
    items = fetch_nhk_news(limit_per_category=3)
    print(f"Fetched {len(items)} items across {len(NHK_FEEDS)} categories.\n")

    for item in items:
        print(f"[{item.category}] {item.title}")
        if item.link:
            print(f"  link: {item.link}")
        try:
            keywords = extract_keywords(client, item)
            print(f"  keywords: {', '.join(keywords)}")
        except Exception as exc:  # noqa: BLE001 — prototype: print and keep going
            print(f"  ERROR (keywords): {exc}")
            print()
            continue

        seen_slugs: set[str] = set()
        for kw in keywords:
            try:
                markets = search_markets(kw, limit=3)
            except Exception as exc:  # noqa: BLE001
                print(f"  [{kw}] ERROR: {exc}")
                continue
            if not markets:
                print(f"  [{kw}] no active markets")
                continue
            for m in markets:
                if m.event_slug in seen_slugs:
                    continue
                seen_slugs.add(m.event_slug)
                price_str = f"{m.yes_price * 100:.0f}%" if m.yes_price is not None else "—"
                vol_str = f"${m.volume:,.0f}" if m.volume is not None else "—"
                print(f"  [{kw}] {price_str} vol={vol_str} — {m.question}")
                print(f"          {m.url}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
