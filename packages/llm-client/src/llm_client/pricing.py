"""Per-call cost from token usage.

Prices in USD per million tokens, from platform.claude.com/docs/en/about-claude/pricing
(checked 2026-09-17). Cache writes use the 5-minute rate, the only duration the adapter requests.
"""

from dataclasses import dataclass

_PER_TOKEN = 1 / 1_000_000


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_write: float
    cache_read: float


PRICES: dict[str, Price] = {
    "claude-opus-5": Price(input=5, output=25, cache_write=6.25, cache_read=0.50),
    "claude-sonnet-5": Price(input=2, output=10, cache_write=2.50, cache_read=0.20),
    "claude-haiku-4-5": Price(input=1, output=5, cache_write=1.25, cache_read=0.10),
}


def cost_usd(
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_write_tokens: int,
    cache_read_tokens: int,
) -> float | None:
    """None for a model without a known price, rather than a wrong number."""
    price = PRICES.get(model)
    if price is None:
        return None
    total = (
        input_tokens * price.input
        + output_tokens * price.output
        + cache_write_tokens * price.cache_write
        + cache_read_tokens * price.cache_read
    )
    return round(total * _PER_TOKEN, 6)
