"""LLM access for both services: a typed request/result interface, Anthropic adapter, fake."""

from llm_client.anthropic_client import AnthropicClient
from llm_client.client import CallRecord, Effort, LLMClient, LLMResult, StructuredRequest
from llm_client.fake_client import FakeLLM
from llm_client.prompts import render
from llm_client.usage import ModelUsage, RecordingLLM, summarize

__all__ = [
    "AnthropicClient",
    "CallRecord",
    "Effort",
    "FakeLLM",
    "LLMClient",
    "LLMResult",
    "ModelUsage",
    "RecordingLLM",
    "StructuredRequest",
    "render",
    "summarize",
]
