"""エンドツーエンドパイプライン。

1. GitHub Actions の fetch-data ワークフローを起動
2. 完了まで待機
3. git pull でデータを取得
4. ギャップ分析スクリプトを呼び出し（reports/DATE.md を生成）
5. commit & push

Usage:
    GITHUB_PAT=<token> python src/pipeline.py [--date YYYY-MM-DD] [--skip-trigger]

環境変数:
    GITHUB_PAT   - GitHub Personal Access Token (repo + workflow スコープ)
    GITHUB_REPO  - オーナー/リポジトリ名 (デフォルト: probable-press/news-prediction-matcher)
    GITHUB_REF   - ワークフロー起動ブランチ (デフォルト: main)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import date, timezone


REPO = os.getenv("GITHUB_REPO", "probable-press/news-prediction-matcher")
GITHUB_API = "https://api.github.com"
WORKFLOW_FILE = "fetch-data.yml"
POLL_INTERVAL = 15   # seconds between status checks
MAX_WAIT = 600       # 10 minutes


def _api(method: str, path: str, body: dict | None = None, token: str = "") -> dict | list:
    url = f"{GITHUB_API}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read()) if resp.status not in (204,) else {}


def trigger_workflow(token: str, ref: str = "main") -> None:
    print(f"→ ワークフロー起動: {WORKFLOW_FILE} (ref={ref})")
    _api(
        "POST",
        f"/repos/{REPO}/actions/workflows/{WORKFLOW_FILE}/dispatches",
        body={"ref": ref},
        token=token,
    )
    time.sleep(3)  # give GitHub time to create the run


def get_latest_run(token: str) -> dict | None:
    runs = _api(
        "GET",
        f"/repos/{REPO}/actions/workflows/{WORKFLOW_FILE}/runs?per_page=1",
        token=token,
    )
    items = runs.get("workflow_runs", []) if isinstance(runs, dict) else []
    return items[0] if items else None


def wait_for_run(token: str) -> bool:
    """最新のワークフロー実行が完了するまで待機。成功なら True。"""
    deadline = time.time() + MAX_WAIT
    run_id = None
    while time.time() < deadline:
        run = get_latest_run(token)
        if run is None:
            time.sleep(POLL_INTERVAL)
            continue
        if run_id is None:
            run_id = run["id"]
            print(f"  Run #{run_id} 検出: {run['html_url']}")
        status = run["status"]
        conclusion = run.get("conclusion")
        print(f"  ステータス: {status} / {conclusion or '—'}")
        if status == "completed":
            return conclusion == "success"
        time.sleep(POLL_INTERVAL)
    print("ERROR: タイムアウト (10分)")
    return False


def git_pull() -> None:
    print("→ git pull でデータ取得")
    subprocess.run(["git", "pull", "--rebase"], check=True)


def run_analysis(today: str) -> None:
    """src/analyze.py が存在すればそれを使う。なければ終了して Claude に委ねる。"""
    script = os.path.join(os.path.dirname(__file__), "analyze.py")
    if os.path.exists(script):
        print(f"→ 分析スクリプト実行: {script}")
        subprocess.run([sys.executable, script, today], check=True)
    else:
        news_file = f"data/news-{today}.json"
        markets_file = f"data/markets-{today}.json"
        print(f"\n✓ データ取得完了: {news_file}, {markets_file}")
        print("  分析は Claude Code が reports/ に直接書き込みます。")


def git_commit_push(today: str, branch: str) -> None:
    report = f"reports/{today}.md"
    if not os.path.exists(report):
        print(f"WARN: {report} が存在しません。コミットをスキップ。")
        return
    print(f"→ コミット & プッシュ: {report}")
    subprocess.run(["git", "add", report], check=True)
    subprocess.run(
        ["git", "commit", "-m", f"report: {today} gap analysis"],
        check=True,
    )
    subprocess.run(["git", "push", "-u", "origin", branch], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="End-to-end pipeline")
    parser.add_argument("--date", default=date.today(tz=timezone.utc).isoformat(),
                        help="対象日 (YYYY-MM-DD)")
    parser.add_argument("--skip-trigger", action="store_true",
                        help="GitHub Actions 起動をスキップ（データ取得済みの場合）")
    parser.add_argument("--branch", default=os.getenv("GITHUB_REF", "main"),
                        help="起動するブランチ / コミット先ブランチ")
    args = parser.parse_args()

    token = os.getenv("GITHUB_PAT", "")

    # データが既にある場合はトリガーをスキップ
    news_file = f"data/news-{args.date}.json"
    markets_file = f"data/markets-{args.date}.json"
    data_ready = os.path.exists(news_file) and os.path.exists(markets_file)

    if data_ready:
        print(f"✓ データ既存: {news_file}, {markets_file}")
    elif args.skip_trigger:
        print(f"WARN: --skip-trigger 指定だがデータが見つかりません: {news_file}")
    elif not token:
        print("ERROR: GITHUB_PAT 環境変数が未設定です。")
        print("  export GITHUB_PAT=<token>  # repo + workflow スコープ必須")
        sys.exit(1)
    else:
        trigger_workflow(token, ref=args.branch)
        ok = wait_for_run(token)
        if not ok:
            print("ERROR: ワークフロー失敗。ログを確認してください。")
            sys.exit(1)
        git_pull()

    run_analysis(args.date)


if __name__ == "__main__":
    main()
