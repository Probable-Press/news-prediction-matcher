"""Guardian Open Platform API からニュース記事を取得。

NHK/Yahoo/BBC RSS の補強として、構造化された英語ニュース全文を取得する。

セットアップ:
  1. https://open-platform.theguardian.com/access/ で Developer key を申請（即時発行）
  2. GitHub Secrets に GUARDIAN_API_KEY を登録

Usage: python src/fetch_guardian.py [limit]   # default 15
JSON配列を標準出力。
"""
from __future__ import annotations

import json
import os
import sys

import requests

API_BASE = "https://content.guardianapis.com"
TIMEOUT = 30
SECTIONS = "world|business|politics|environment|us-news"
BODY_LIMIT = 3000


def fetch_recent(limit: int = 15) -> list[dict]:
    api_key = os.getenv("GUARDIAN_API_KEY", "")
    if not api_key:
        return []

    resp = requests.get(
        f"{API_BASE}/search",
        params={
            "api-key":     api_key,
            "section":     SECTIONS,
            "page-size":   limit,
            "order-by":    "newest",
            "show-fields": "bodyText,trailText,headline",
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()

    out = []
    for r in resp.json().get("response", {}).get("results", []):
        fields = r.get("fields") or {}
        body = (fields.get("bodyText") or "").strip()
        if len(body) > BODY_LIMIT:
            body = body[:BODY_LIMIT].rstrip() + "…"
        out.append({
            "title":     (fields.get("headline") or r.get("webTitle") or "").strip(),
            "summary":   (fields.get("trailText") or "").strip(),
            "body":      body,
            "url":       r.get("webUrl") or "",
            "section":   r.get("sectionName") or "",
            "published": r.get("webPublicationDate") or "",
            "source":    "Guardian",
        })
    return out


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    json.dump(fetch_recent(limit), sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
