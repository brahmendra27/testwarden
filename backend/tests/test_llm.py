"""LLM provider layer: hosted key vs local base_url selection."""
from flakelens.config import settings
from flakelens.services.llm import llm_available, make_client, model_kwargs


def test_available_with_key_only(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr(settings, "llm_base_url", "")
    assert llm_available()


def test_available_with_local_base_url_and_no_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(settings, "llm_base_url", "http://localhost:11434")
    assert llm_available()


def test_unavailable_with_neither(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(settings, "llm_base_url", "")
    assert not llm_available()


def test_make_client_points_at_local_server_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(settings, "llm_base_url", "http://localhost:11434")
    client = make_client()
    assert "localhost:11434" in str(client.base_url)
    assert client.api_key == "local"  # SDK requires one; local servers ignore it


def test_model_kwargs_claude_gets_adaptive_thinking(monkeypatch):
    monkeypatch.setattr(settings, "llm_model", "claude-opus-4-8")
    kw = model_kwargs(max_tokens=2000)
    assert kw == {"model": "claude-opus-4-8", "max_tokens": 2000,
                  "thinking": {"type": "adaptive"}}


def test_model_kwargs_local_model_omits_thinking(monkeypatch):
    monkeypatch.setattr(settings, "llm_model", "qwen3-coder:30b")
    kw = model_kwargs(max_tokens=2000)
    assert kw == {"model": "qwen3-coder:30b", "max_tokens": 2000}
