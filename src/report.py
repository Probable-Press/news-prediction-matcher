"""Markdown report generation for the gap analysis pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from gap_analysis import GapResult


@dataclass
class NewsAnalysis:
    """All analysis output for a single news item."""

    category: str
    title: str
    link: str
    keywords: list[str]
    results: list[GapResult]


def render_report(analyses: list[NewsAnalysis], *, generated_at: datetime, flag_threshold: float) -> str:
    """Render a Markdown report. `flag_threshold` is in [0,1] (e.g. 0.10 = 10pp)."""
    flagged = sorted(
        (
            (a, r)
            for a in analyses
            for r in a.results
            if r.abs_gap >= flag_threshold and r.judgement.direction != "no_clear_signal"
        ),
        key=lambda pair: pair[1].abs_gap,
        reverse=True,
    )

    lines: list[str] = []
    date_str = generated_at.strftime("%Y-%m-%d")
    lines.append(f"# News × Polymarket Gap Analysis — {date_str}")
    lines.append("")
    lines.append(f"_Generated: {generated_at.strftime('%Y-%m-%d %H:%M:%S %Z')}_")
    lines.append("")
    lines.append(
        f"- News items analyzed: **{len(analyses)}**"
    )
    lines.append(
        f"- Markets analyzed: **{sum(len(a.results) for a in analyses)}**"
    )
    lines.append(
        f"- Flagged gaps (|gap| ≥ {flag_threshold * 100:.0f}pp): **{len(flagged)}**"
    )
    lines.append("")

    lines.append(f"## 🚩 Flagged Gaps")
    lines.append("")
    if not flagged:
        lines.append("_No gaps above threshold today._")
        lines.append("")
    else:
        for analysis, result in flagged:
            _append_flagged_block(lines, analysis, result)

    lines.append("## All Items")
    lines.append("")
    for analysis in analyses:
        _append_news_block(lines, analysis, flag_threshold)

    return "\n".join(lines).rstrip() + "\n"


def _append_flagged_block(lines: list[str], analysis: NewsAnalysis, result: GapResult) -> None:
    j = result.judgement
    market_pct = result.market_yes_price * 100
    implied_pct = j.implied_yes_probability * 100
    gap_pp = result.gap * 100
    vol_str = f"${result.market.volume:,.0f}" if result.market.volume is not None else "—"

    lines.append(f"### [{analysis.category}] {analysis.title}")
    lines.append("")
    lines.append(f"- **Market**: {result.market.question}")
    lines.append(
        f"- **Market**: {market_pct:.0f}% | "
        f"**News-implied**: {implied_pct:.0f}% | "
        f"**Gap**: {gap_pp:+.0f}pp"
    )
    lines.append(f"- **Direction**: `{j.direction}` (confidence: {j.confidence})")
    lines.append(f"- **Volume**: {vol_str}")
    lines.append(f"- **Reasoning**: {j.reasoning}")
    parts = [f"[Polymarket]({result.market.url})"]
    if analysis.link:
        parts.append(f"[News source]({analysis.link})")
    lines.append(f"- {' · '.join(parts)}")
    lines.append("")


def _append_news_block(lines: list[str], analysis: NewsAnalysis, flag_threshold: float) -> None:
    title_line = f"### [{analysis.category}] {analysis.title}"
    if analysis.link:
        title_line += f" ([source]({analysis.link}))"
    lines.append(title_line)
    lines.append("")

    if analysis.keywords:
        kw_str = ", ".join(f"`{k}`" for k in analysis.keywords)
        lines.append(f"Keywords: {kw_str}")
        lines.append("")

    if not analysis.results:
        lines.append("_No matching markets._")
        lines.append("")
        return

    lines.append("| Market | Market | Implied | Gap | Direction | Conf | Volume |")
    lines.append("|---|---:|---:|---:|---|---|---:|")
    for r in analysis.results:
        j = r.judgement
        market_pct = r.market_yes_price * 100
        implied_pct = j.implied_yes_probability * 100
        gap_pp = r.gap * 100
        flag = " 🚩" if r.abs_gap >= flag_threshold and j.direction != "no_clear_signal" else ""
        vol_str = f"${r.market.volume:,.0f}" if r.market.volume is not None else "—"
        question = _md_escape(r.market.question)
        lines.append(
            f"| [{question}]({r.market.url}) "
            f"| {market_pct:.0f}% | {implied_pct:.0f}% | {gap_pp:+.0f}pp{flag} "
            f"| {j.direction} | {j.confidence} | {vol_str} |"
        )
    lines.append("")
    for r in analysis.results:
        lines.append(f"- _{r.market.question}_: {r.judgement.reasoning}")
    lines.append("")


def _md_escape(text: str) -> str:
    """Escape characters that would break a Markdown table cell."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def write_report(report_md: str, *, reports_dir: Path, generated_at: datetime) -> Path:
    """Write the report to `reports/YYYY-MM-DD.md` and return the path."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{generated_at.strftime('%Y-%m-%d')}.md"
    path.write_text(report_md, encoding="utf-8")
    return path


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)
