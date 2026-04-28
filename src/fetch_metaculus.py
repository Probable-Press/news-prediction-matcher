"""Metaculus からアクティブな予測を取得。

Polymarket の「お金の集合知」と Metaculus の「専門家コミュニティ予測」を
比較する素材を提供する。

セットアップ:
  1. https://www.metaculus.com にアカウント作成
  2. Profile → API Tokens → Generate
  3. GitHub Secrets に METACULUS_API_KEY を登録

Usage: python src/fetch_metaculus.py [limit]   # default 30
JSON配列を標準出力。
"""
from __future__ import annotations

import json
import os
import sys

import requests

API_BASE = "https://www.metaculus.com/api"
TIMEOUT = 30


def fetch_active(limit: int = 30) -> list[dict]:
    api_key = os.getenv("METACULUS_API_KEY", "")
    if not api_key:
        return []

    resp = requests.get(
        f"{API_BASE}/posts/",
        params={
            "limit": limit,
            "order_by": "-hotness",
            "statuses": "open",
            "forecast_type": "binary",
        },
        headers={"Authorization": f"Token {api_key}"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()

    out = []
    for post in data.get("results", []):
        question = post.get("question") or {}
        aggregations = question.get("aggregations") or {}
        latest = (aggregations.get("recency_weighted") or {}).get("latest") or {}
        centers = latest.get("centers") or []
        community = centers[0] if centers else None

        post_id = post.get("id")
        out.append({
            "id":         post_id,
            "title":      (post.get("title") or "").strip(),
            "url":        post.get("url") or f"https://www.metaculus.com/questions/{post_id}",
            "community_prediction": round(community, 4) if isinstance(community, (int, float)) else None,
            "num_forecasters": question.get("num_forecasters"),
            "close_time": question.get("scheduled_close_time"),
        })
    return out


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    json.dump(fetch_active(limit), sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
