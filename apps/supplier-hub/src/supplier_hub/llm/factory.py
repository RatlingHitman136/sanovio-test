"""Chooses the LLM client from settings; tests inject their own FakeLLM."""

from llm_client import AnthropicClient, LLMClient
from supplier_hub.core.settings import HubSettings
from supplier_hub.llm.fake_readings import fake_normalizer


def make_llm(settings: HubSettings) -> LLMClient | None:
    """`fake` answers from the scripted readings, so an offline seed is still a full seed."""
    if settings.llm_mode == "fake":
        return fake_normalizer()
    if settings.anthropic_api_key is None:
        return None
    return AnthropicClient(settings.anthropic_api_key)
