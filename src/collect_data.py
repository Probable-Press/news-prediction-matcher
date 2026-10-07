"""Publish only validated collector output; keep failures visible after committing.

The manifest lives outside data/ and contains only fixed status messages and
approved output paths, never raw collector stderr (which may include API keys).
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
# The workflow starts this budget before checkout/setup, leaving roughly three
# minutes of its unchanged ten-minute job for validation, commit/push and report.
COLLECTION_BUDGET_SECONDS = 420
# script, arguments, required configuration, timeout, existing retention days
SOURCES = {
    "news": ("main.py", ["5"], (), 240, 7),
    "markets": ("fetch_markets.py", ["50"], (), 90, None),
    "dune": ("fetch_dune.py", [], ("DUNE_API_KEY", "DUNE_QUERY_ID"), 120, 14),
    "metaculus": ("fetch_metaculus.py", ["30"], ("METACULUS_API_KEY",), 45, 30),
    "guardian": ("fetch_guardian.py", ["15"], ("GUARDIAN_API_KEY",), 45, 7),
}
# Minimum identity fields in the existing collectors' list-of-object contract.
IDENTITY = {"news": ("title", "link"), "markets": ("question", "url"),
            "dune": ("tx_hash",), "metaculus": ("title", "url"),
            "guardian": ("title", "url")}


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        temp_path = Path(tmp.name)
        try:
            tmp.write(content)
            tmp.close()
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)


def validate(source: str, content: bytes) -> list[dict]:
    def reject_constant(value):
        raise ValueError("Non-finite JSON number")
    rows = json.loads(content, parse_constant=reject_constant)
    if not isinstance(rows, list):
        raise ValueError("Expected a JSON array")
    if any(not isinstance(row, dict) or any(
            not isinstance(row.get(key), str) or not row[key].strip()
            for key in IDENTITY[source]) for row in rows):
        raise ValueError("Missing record identity")
    json.dumps(rows, allow_nan=False)  # Reject overflow such as 1e999 as well.
    # main.py catches individual feed failures and can otherwise emit [] with
    # exit 0. Empty news/markets/Guardian is not a useful replacement snapshot.
    if not rows and source in {"news", "markets", "guardian"}:
        raise ValueError("Empty primary source")
    return rows


def collect_source(source: str, today: str, root: Path, *, config=None,
                   deadline: float | None = None) -> dict:
    script, args, required, timeout, retention = config or SOURCES[source]
    result = {"status": "failed", "reason": "collector failed", "changed": []}
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        return {**result, "status": "skipped", "reason": "configuration missing"}
    path = root / "data" / f"{source}-{today}.json"
    # Neither stdout nor stderr can create/truncate a published file.
    # Preserve each collector's original credential scope even though the
    # orchestrator receives the configuration for all sources.
    keys = {key for config in SOURCES.values() for key in config[2]}
    env = {key: value for key, value in os.environ.items()
           if key not in keys or key in required}
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        remaining = deadline - time.monotonic() if deadline is not None else timeout
        if remaining <= 0:
            return {**result, "status": "skipped", "reason": "collection budget exhausted"}
        effective_timeout = min(timeout, remaining)
        try:
            process = subprocess.run([sys.executable, str(root / "src" / script), *args],
                                     stdout=output, stderr=errors, timeout=effective_timeout,
                                     cwd=root, env=env, check=False)
        except subprocess.TimeoutExpired:
            reason = ("collection budget exhausted" if effective_timeout < timeout
                      else "collector timed out")
            return {**result, "reason": reason}
        except OSError:
            return {**result, "reason": "collector could not start"}
        errors.seek(0)
        # Extract only a numeric HTTP status; never copy exception text/URLs.
        diagnostics = errors.read().decode("utf-8", errors="replace")
        if process.returncode:
            match = re.search(r"\b([45]\d\d) (?:Client|Server) Error\b", diagnostics)
            reason = f"HTTP {match[1]}" if match else "collector exited nonzero"
            return {**result, "reason": reason}
        output.seek(0)
        content = output.read()
    try:
        rows = validate(source, content)
    except (ValueError, UnicodeError, RecursionError):
        return {**result, "reason": "invalid or empty collector output"}
    changed = []
    if not path.exists() or path.read_bytes() != content:
        atomic_write(path, content)
        changed.append({"path": str(path.relative_to(root)),
                        "sha256": hashlib.sha256(content).hexdigest()})
    # Retain existing mtime policy, but purge only after this source produced a
    # valid replacement. Failed/skipped sources' last-known snapshots survive.
    retention_failed = False
    if retention is not None:
        cutoff = time.time() - (retention + 1) * 86400  # find -mtime +N
        try:
            for old in (root / "data").glob(f"{source}-????-??-??.json"):
                try:
                    date.fromisoformat(old.stem.removeprefix(source + "-"))
                except ValueError:
                    continue
                if old != path and old.stat().st_mtime < cutoff:
                    old.unlink()
                    changed.append({"path": str(old.relative_to(root)), "sha256": None})
        except OSError:
            # Data is valid and already published. Preserve its commit path,
            # report cleanup degradation, and still attempt later collectors.
            retention_failed = True
    reason = ("retention incomplete" if retention_failed else
              "collector reported warnings" if diagnostics.strip() else "validated")
    return {"status": "success" if reason == "validated" else "partial",
            "reason": reason, "count": len(rows), "changed": changed}


def collect(today: str, manifest: Path, root: Path = ROOT, *,
            deadline: float | None = None) -> dict:
    if deadline is not None and not math.isfinite(deadline):
        raise ValueError("Invalid collection deadline")
    local_deadline = time.monotonic() + COLLECTION_BUDGET_SECONDS
    deadline = min(deadline, local_deadline) if deadline is not None else local_deadline
    today = date.fromisoformat(today).isoformat()
    report = {"date": today, "sources": {
        source: {"status": "pending", "reason": "not completed", "changed": []}
        for source in SOURCES}}
    def save():
        atomic_write(manifest, (json.dumps(report, indent=2) + "\n").encode())
    save()  # Replace any stale manifest before starting.
    for source in SOURCES:
        try:
            if time.monotonic() >= deadline:
                report["sources"][source] = {
                    "status": "skipped", "reason": "collection budget exhausted", "changed": []}
            else:
                report["sources"][source] = collect_source(source, today, root, deadline=deadline)
        except Exception:
            # This is the source failure boundary, not a success fallback.
            # Include no exception text, and do not stage that source's files.
            report["sources"][source] = {
                "status": "failed", "reason": "collector processing failed", "changed": []}
        save()
    return report


def stage(report: dict, root: Path = ROOT) -> None:
    """Stage only this run's validated changes, including its scoped retention."""
    today = date.fromisoformat(report["date"]).isoformat()
    paths = []
    for source, result in report["sources"].items():
        if source not in SOURCES or result["status"] not in {"success", "partial"}:
            continue
        for change in result["changed"]:
            name = change["path"]
            if not re.fullmatch(rf"data/{source}-\d{{4}}-\d{{2}}-\d{{2}}\.json", name):
                raise ValueError("Unexpected changed path")
            path = root / name
            if change["sha256"] is None:
                if path.exists():
                    raise ValueError("Expected a removed retention file")
            else:
                if name != f"data/{source}-{today}.json":
                    raise ValueError("Unexpected snapshot date")
                content = path.read_bytes()
                validate(source, content)
                if hashlib.sha256(content).hexdigest() != change["sha256"]:
                    raise ValueError("Snapshot changed after collection")
            paths.append(name)
    if paths:
        subprocess.run(["git", "add", "--", *paths], cwd=root, check=True)


def summarize(report: dict) -> bool:
    lines = [f"## Data collection: {report['date']}", ""]
    complete = True
    for source in SOURCES:
        result = report["sources"][source]
        status, reason = result["status"], result["reason"]
        lines.append(f"- {source}: {status} ({reason})")
        if status != "success":
            complete = False
            print(f"::warning::{source}: {status} ({reason}); inspect collection summary")
    if not complete:
        lines.extend(["", "Degraded collection. Only validated source outputs are eligible "
                      "for commit; failed/skipped sources keep their prior data. "
                      "Check the Commit data step for publication success."])
    summary = "\n".join(lines) + "\n"
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as out:
            out.write(summary)
    return complete


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("collect", "stage", "report"))
    parser.add_argument("--date")
    parser.add_argument("--deadline", type=float,
                        help="Absolute monotonic collection deadline from the workflow")
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "collect":
        if not args.date:
            parser.error("collect requires --date")
        report = collect(args.date, args.manifest, deadline=args.deadline)
        # The workflow explicitly continues to stage/commit even on degradation.
        sys.exit(0 if all(r["status"] == "success" for r in report["sources"].values()) else 1)
    report = json.loads(args.manifest.read_text(encoding="utf-8"))
    if args.action == "stage":
        stage(report)
    else:
        sys.exit(0 if summarize(report) else 1)


if __name__ == "__main__":
    main()
