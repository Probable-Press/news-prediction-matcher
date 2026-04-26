"""News-tone vs market-probability gap analysis.

For a (news item, Polymarket market) pair, asks Claude to estimate the YES
probability implied by the news, then compares it against the current market
price. A large gap is the signal: the market may be under- or over-pricing
the event relative to what the news suggests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from polymarket import Market

MODEL = "claude-opus-4-7"

GAP_SYSTEM_PROMPT = """You are a calibrated forecaster comparing a news headline against a prediction-market price.

Given:
- A Japanese news headline + summary
- A Polymarket market (its YES question and current YES probability)

Estimate the YES probability that the news *alone* implies, treating the news as the only new information. Then judge whether the current market price is too high, too low, or about right relative to that estimate.

Rules:
- Output `implied_yes_probability` ∈ [0.0, 1.0] — your best estimate of YES given the news
- `direction`:
  - "yes_underpriced" if news suggests YES is more likely than the market price
  - "yes_overpriced"  if news suggests YES is less likely than the market price
  - "no_clear_signal" if the news is unrelated, ambiguous, or barely moves the estimate
- `confidence`: "high" only if the news is directly and unambiguously about the market's question; "low" if loosely related
- `reasoning`: 1-2 short sentences in English explaining the call. Be concrete (cite the news fact and the price).
- If the news doesn't actually relate to the market, set direction="no_clear_signal" and explain why.
"""


class GapJudgement(BaseModel):
    """Claude's structured assessment of a (news, market) pair."""

    direction: Literal["yes_underpriced", "yes_overpriced", "no_clear_signal"]
    implied_yes_probability: float = Field(..., ge=0.0, le=1.0)
    confidence: Literal["low", "medium", "high"]
    reasoning: str = Field(..., max_length=400)


@dataclass
class GapResult:
    """A gap-analysis result for one (news, market) pair."""

    market: Market
    judgement: GapJudgement
    market_yes_price: float
    gap: float  # implied - market_yes_price; positive = market underpriced

    @property
    def abs_gap(self) -> float:
        return abs(self.gap)


def analyze_gap(
    client: anthropic.Anthropic,
    *,
    category: str,
    title: str,
    summary: str,
    market: Market,
) -> GapResult | None:
    """Run gap analysis. Returns None if the market has no current YES price."""
    if market.yes_price is None:
        return None

    user_prompt = (
        f"# News\n"
        f"カテゴリ: {category}\n"
        f"見出し: {title}\n"
        f"概要: {summary or '(概要なし)'}\n\n"
        f"# Polymarket market\n"
        f"Question: {market.question}\n"
        f"Current YES probability: {market.yes_price:.2%}\n"
        f"Volume: {f'${market.volume:,.0f}' if market.volume is not None else 'unknown'}\n"
    )

    response = client.messages.parse(
        model=MODEL,
        max_tokens=512,
        system=GAP_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
        output_format=GapJudgement,
    )
    parsed = response.parsed_output
    if parsed is None:
        raise RuntimeError(f"Claude refused or returned unparseable output: stop_reason={response.stop_reason}")

    return GapResult(
        market=market,
        judgement=parsed,
        market_yes_price=market.yes_price,
        gap=parsed.implied_yes_probability - market.yes_price,
    )
