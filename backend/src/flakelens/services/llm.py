"""LLM client factory for every FlakeLens agent.

Default: the Anthropic API (ANTHROPIC_API_KEY). Alternative: any self-hosted
server that speaks the Anthropic Messages dialect — Ollama's /v1 Anthropic
compatibility, a LiteLLM proxy in front of vLLM/llama.cpp/LM Studio, etc. —
selected with two env vars and no code changes:

    FLAKELENS_LLM_BASE_URL=http://localhost:11434   # your local server
    FLAKELENS_LLM_MODEL=qwen3-coder:30b             # its model name

With a base_url set, no Anthropic key is needed and nothing leaves the box.
"""
import os

from flakelens.config import settings


def llm_available() -> bool:
    """Agents are usable if a hosted key OR a local endpoint is configured."""
    return bool(os.environ.get("ANTHROPIC_API_KEY") or settings.llm_base_url)


def unavailable_detail(feature: str) -> str:
    return (
        f"{feature} unavailable: set ANTHROPIC_API_KEY (hosted) or "
        "FLAKELENS_LLM_BASE_URL (local LLM) on the server"
    )


def make_client():
    """Anthropic SDK client, pointed at the configured endpoint."""
    import anthropic

    kwargs: dict = {}
    if settings.llm_base_url:
        kwargs["base_url"] = settings.llm_base_url
        # Local servers don't check the key, but the SDK requires one.
        kwargs["api_key"] = os.environ.get("ANTHROPIC_API_KEY") or "local"
    return anthropic.Anthropic(**kwargs)


def model_kwargs(max_tokens: int) -> dict:
    """model + token budget, plus adaptive thinking for Claude models only —
    local/OSS models served through compatibility layers reject the param."""
    kwargs: dict = {"model": settings.llm_model, "max_tokens": max_tokens}
    if settings.llm_model.startswith("claude"):
        kwargs["thinking"] = {"type": "adaptive"}
    return kwargs
