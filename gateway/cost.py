"""Token cost math. Prices come from policy.yaml, never from code."""

from __future__ import annotations

from gateway.config import Price


def cost_usd(prices: dict[str, Price], model: str, input_tokens: int, output_tokens: int) -> float:
    price = prices.get(model)
    if price is None:
        return 0.0
    return (input_tokens * price.input + output_tokens * price.output) / 1_000_000


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars per token) used only by the mock upstream."""
    return max(1, round(len(text) / 4)) if text else 0
