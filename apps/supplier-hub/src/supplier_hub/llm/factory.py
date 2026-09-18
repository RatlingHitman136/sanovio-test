"""Chooses the LLM client from settings; tests inject their own FakeLLM."""

from llm_client import AnthropicClient, LLMClient
from supplier_hub.core.settings import HubSettings
from supplier_hub.llm.fakes import fake_llm


def make_llm(settings: HubSettings) -> LLMClient | None:
    """`fake` answers every pipeline deterministically, so offline runs are complete runs."""
    if settings.llm_mode == "fake":
        return fake_llm()
    if settings.anthropic_api_key is None:
        return None
    return AnthropicClient(settings.anthropic_api_key)
