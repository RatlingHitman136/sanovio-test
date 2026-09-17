"""Chooses the LLM client from settings; tests pass a FakeLLM instead."""

from hospital_node.core.settings import NodeSettings
from llm_client import AnthropicClient, LLMClient


def make_llm(settings: NodeSettings) -> LLMClient | None:
    """None when no call can be made: rules mode, or llm mode without the hospital's key."""
    if settings.normalize_mode == "rules" or settings.anthropic_api_key is None:
        return None
    return AnthropicClient(settings.anthropic_api_key)
