"""ニュースRSSフェッチャー + 記事本文スクレイパー (NHK / Yahoo Japan / BBC)。

Usage: python src/main.py [limit]   # limit = ソースあたり件数 (デフォルト 5)
JSON配列を標準出力。Actions等で `> data/news-YYYY-MM-DD.json` にリダイレクトする想定。

各アイテムに 'body' フィールドを追加 (記事本文 / スクレイプ失敗時は空文字)。
"""

from __future__ import annotations

import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

NEWS_FEEDS: dict[str, str] = {
    "NHK主要":      "https://news.web.nhk/n-data/conf/na/rss/cat0.xml",
    "NHK政治":      "https://news.web.nhk/n-data/conf/na/rss/cat4.xml",
    "NHK経済":      "https://news.web.nhk/n-data/conf/na/rss/cat5.xml",
    "NHK国際":      "https://news.web.nhk/n-data/conf/na/rss/cat6.xml",
    "Yahoo主要":    "https://news.yahoo.co.jp/rss/topics/top-picks.xml",
    "Yahoo国際":    "https://news.yahoo.co.jp/rss/topics/world.xml",
    "Yahoo経済":    "https://news.yahoo.co.jp/rss/topics/business.xml",
    "BBC World":    "http://feeds.bbci.co.uk/news/world/rss.xml",
    "BBC Business": "http://feeds.bbci.co.uk/news/business/rss.xml",
    "BBC Politics": "http://feeds.bbci.co.uk/news/politics/rss.xml",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.9",
}
SCRAPE_TIMEOUT = 15
MAX_BODY_CHARS = 3000
MAX_WORKERS = 8


def _xml_text(el, tag: str) -> str:
    child = el.find(tag)
    return (child.text or "").strip() if child is not None else ""


def _extract_body(soup: BeautifulSoup, url: str) -> str:
    """ソース別の抽出戦略でプレーンテキストを返す。"""
    paragraphs: list[str] = []

    if "bbc." in url or "bbc.co" in url:
        # BBC: data-component="text-block" の <p> を収集
        for block in soup.find_all("div", attrs={"data-component": "text-block"}):
            for p in block.find_all("p"):
                paragraphs.append(p.get_text(strip=True))
        # 上記が空なら <article> 内 <p> にフォールバック
        if not paragraphs:
            article = soup.find("article")
            if article:
                paragraphs = [p.get_text(strip=True) for p in article.find_all("p")]

    elif "nhk" in url:
        # NHK: <article> の <p> を収集
        article = soup.find("article")
        if article:
            paragraphs = [p.get_text(strip=True) for p in article.find_all("p")]
        if not paragraphs:
            # 本文 div (クラス名が変動するため data-* や role で試みる)
            for attr in ("main", "article"):
                tag = soup.find(role=attr) or soup.find("main")
                if tag:
                    paragraphs = [p.get_text(strip=True) for p in tag.find_all("p")]
                    break

    elif "yahoo" in url:
        # Yahoo Japan: <article> または .article_body
        article = (
            soup.find("article")
            or soup.find(class_=lambda c: c and "article" in c.lower())
        )
        if article:
            paragraphs = [p.get_text(strip=True) for p in article.find_all("p")]

    # 汎用フォールバック
    if not paragraphs:
        article = soup.find("article") or soup.find("main")
        if article:
            paragraphs = [p.get_text(strip=True) for p in article.find_all("p")]
        else:
            # <p> タグを上から最大20個
            paragraphs = [p.get_text(strip=True) for p in soup.find_all("p")[:20]]

    text = "\n".join(p for p in paragraphs if len(p) > 20)
    return text[:MAX_BODY_CHARS]


def scrape_body(url: str) -> str:
    """URL から記事本文を取得。失敗時は空文字。"""
    if not url:
        return ""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=SCRAPE_TIMEOUT,
                            allow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")
        # スクリプト・スタイル・ナビを除去
        for tag in soup(["script", "style", "nav", "header", "footer",
                          "aside", "noscript", "iframe"]):
            tag.decompose()
        return _extract_body(soup, url)
    except Exception as exc:
        print(f"WARN scrape {url}: {exc}", file=sys.stderr)
        return ""


def fetch(limit: int = 5) -> list[dict]:
    # ① RSS フィードから記事リストを収集
    items: list[dict] = []
    for category, feed_url in NEWS_FEEDS.items():
        try:
            req = urllib.request.Request(feed_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                root = ET.fromstring(resp.read())
        except Exception as exc:
            print(f"WARN: {category} ({feed_url}): {exc}", file=sys.stderr)
            continue
        for entry in root.findall(".//item")[:limit]:
            items.append({
                "category":  category,
                "title":     _xml_text(entry, "title"),
                "summary":   _xml_text(entry, "description"),
                "link":      _xml_text(entry, "link"),
                "published": _xml_text(entry, "pubDate"),
                "body":      "",
            })

    # ② 記事本文を並列スクレイプ
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(scrape_body, item["link"]): i
                   for i, item in enumerate(items)}
        for future in as_completed(futures):
            idx = futures[future]
            items[idx]["body"] = future.result()

    return items


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    json.dump(fetch(limit), sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
