import pytest

from llm_client.pricing import cost_usd


def test_cost_counts_every_token_kind() -> None:
    cost = cost_usd(
        "claude-sonnet-5",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_write_tokens=1_000_000,
        cache_read_tokens=1_000_000,
    )
    assert cost == pytest.approx(2 + 10 + 2.5 + 0.2)


def test_unknown_model_has_no_cost() -> None:
    zero = {"input_tokens": 1, "output_tokens": 1, "cache_write_tokens": 0, "cache_read_tokens": 0}
    assert cost_usd("some-other-model", **zero) is None
