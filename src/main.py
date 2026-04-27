"""ニュースRSSフェッチャー (NHK / Yahoo Japan / BBC)。標準ライブラリのみ使用。

Usage: python src/main.py [limit]   # limit = ソースあたり件数 (デフォルト 5)
JSON配列を標準出力。Actions等で `> data/news-YYYY-MM-DD.json` にリダイレクトする想定。
"""

from __future__ import annotations

import json
import sys
import urllib.request
import xml.etree.ElementTree as ET

NEWS_FEEDS: dict[str, str] = {
    # NHK
    "NHK主要":   "https://news.web.nhk/n-data/conf/na/rss/cat0.xml",
    "NHK政治":   "https://news.web.nhk/n-data/conf/na/rss/cat4.xml",
    "NHK経済":   "https://news.web.nhk/n-data/conf/na/rss/cat5.xml",
    "NHK国際":   "https://news.web.nhk/n-data/conf/na/rss/cat6.xml",
    # Yahoo Japan
    "Yahoo主要": "https://news.yahoo.co.jp/rss/topics/top-picks.xml",
    "Yahoo国際": "https://news.yahoo.co.jp/rss/topics/world.xml",
    "Yahoo経済": "https://news.yahoo.co.jp/rss/topics/business.xml",
    # BBC
    "BBC World":    "http://feeds.bbci.co.uk/news/world/rss.xml",
    "BBC Business": "http://feeds.bbci.co.uk/news/business/rss.xml",
    "BBC Politics": "http://feeds.bbci.co.uk/news/politics/rss.xml",
}


def _text(el, tag: str) -> str:
    child = el.find(tag)
    return (child.text or "").strip() if child is not None else ""


def fetch(limit: int = 5) -> list[dict]:
    items: list[dict] = []
    for category, url in NEWS_FEEDS.items():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                root = ET.fromstring(resp.read())
        except Exception as exc:
            print(f"WARN: {category} ({url}): {exc}", file=sys.stderr)
            continue
        for entry in root.findall(".//item")[:limit]:
            items.append({
                "category": category,
                "title": _text(entry, "title"),
                "summary": _text(entry, "description"),
                "link": _text(entry, "link"),
                "published": _text(entry, "pubDate"),
            })
    return items


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    json.dump(fetch(limit), sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
