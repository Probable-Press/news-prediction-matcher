"""Dune Analytics からポリマーケットのオンチェーン大口取引を取得。

reports/ の背景情報として使用。articles/ には反映させない。

セットアップ:
  1. https://dune.com でアカウント作成 → Settings → API Keys → New Key
  2. GitHub Secrets に DUNE_API_KEY を登録
  3. 以下のSQLでDuneクエリを作成し、DUNE_QUERY_ID に設定:

     -- Polymarket 大口取引 (過去24時間, Polygon)
     -- CTF Exchange: 0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E
     SELECT
       block_time,
       tx_hash,
       "from" AS wallet,
       value / 1e6 AS usdc_amount
     FROM polygon.transactions
     WHERE to = lower('0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E')
       AND block_time >= now() - interval '24' hour
       AND value / 1e6 >= 10000
     ORDER BY usdc_amount DESC
     LIMIT 50

Usage:
  DUNE_API_KEY=xxx python src/fetch_dune.py [query_id]
  JSON配列を標準出力。
"""
from __future__ import annotations

import json
import os
import sys
import time

import requests

DUNE_API = "https://api.dune.com/api/v1"
TIMEOUT = 30
# クエリ作成後にここを書き換えるか、環境変数 DUNE_QUERY_ID で上書き
DEFAULT_QUERY_ID = os.getenv("DUNE_QUERY_ID", "")
LARGE_BET_THRESHOLD = 10_000  # USD


def _headers(api_key: str) -> dict:
    return {"X-DUNE-API-KEY": api_key}


def get_latest_results(query_id: str, api_key: str) -> list[dict]:
    """クエリの最新キャッシュ結果を取得。なければ実行してポーリング。"""
    url = f"{DUNE_API}/query/{query_id}/results"
    resp = requests.get(url, headers=_headers(api_key), timeout=TIMEOUT)

    if resp.status_code == 200:
        data = resp.json()
        rows = data.get("result", {}).get("rows", [])
        if rows:
            return rows

    # キャッシュなし → 実行リクエスト
    exec_resp = requests.post(
        f"{DUNE_API}/query/{query_id}/execute",
        headers=_headers(api_key),
        timeout=TIMEOUT,
    )
    exec_resp.raise_for_status()
    execution_id = exec_resp.json()["execution_id"]

    # 完了まで待機（最大60秒）
    for _ in range(12):
        time.sleep(5)
        status_resp = requests.get(
            f"{DUNE_API}/execution/{execution_id}/status",
            headers=_headers(api_key),
            timeout=TIMEOUT,
        )
        state = status_resp.json().get("state", "")
        if state == "QUERY_STATE_COMPLETED":
            result_resp = requests.get(
                f"{DUNE_API}/execution/{execution_id}/results",
                headers=_headers(api_key),
                timeout=TIMEOUT,
            )
            return result_resp.json().get("result", {}).get("rows", [])
        if state in ("QUERY_STATE_FAILED", "QUERY_STATE_CANCELLED"):
            raise RuntimeError(f"Dune query {state}")

    raise TimeoutError("Dune query did not complete in 60s")


def summarize(rows: list[dict]) -> list[dict]:
    """大口取引のみフィルタして整形。"""
    out = []
    for r in rows:
        amount = float(r.get("usdc_amount") or 0)
        if amount < LARGE_BET_THRESHOLD:
            continue
        out.append({
            "block_time":  r.get("block_time"),
            "wallet":      (r.get("wallet") or "")[:10] + "...",  # 部分匿名化
            "usdc_amount": round(amount, 2),
            "tx_hash":     r.get("tx_hash", ""),
            "dune_url":    f"https://dune.com/queries/{DEFAULT_QUERY_ID}",
        })
    return sorted(out, key=lambda x: x["usdc_amount"], reverse=True)


def main() -> None:
    api_key = os.getenv("DUNE_API_KEY", "")
    if not api_key:
        print("[]")  # キーなしは空配列で終了（CI を止めない）
        return

    query_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUERY_ID
    if not query_id:
        print("ERROR: DUNE_QUERY_ID が未設定です。コメントのSQLでクエリを作成してください。",
              file=sys.stderr)
        print("[]")
        return

    rows = get_latest_results(query_id, api_key)
    result = summarize(rows)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
