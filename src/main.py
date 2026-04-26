"""NHK RSS フェッチャー。

JSON で標準出力に書き出す。Claude Code がこれを読んでキーワード抽出・ギャップ分析を行う。

Usage:
    python src/main.py [limit]   # limit = カテゴリあたり件数 (デフォルト 5)
"""

from __future__ import annotations

import json
import sys

import feedparser

NHK_FEEDS: dict[str, str] = {
    "主要": "https://www3.nhk.or.jp/rss/news/cat0.xml",
    "国際": "https://www3.nhk.or.jp/rss/news/cat6.xml",
    "経済": "https://www3.nhk.or.jp/rss/news/cat5.xml",
}


def fetch(limit: int = 5) -> list[dict]:
    items: list[dict] = []
    for category, url in NHK_FEEDS.items():
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            print(f"WARN: {category} ({url}) failed", file=sys.stderr)
            continue
        for entry in feed.entries[:limit]:
            items.append({
                "category": category,
                "title": (entry.get("title") or "").strip(),
                "summary": (entry.get("summary") or "").strip(),
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
            })
    return items


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    json.dump(fetch(limit), sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
