# Running the AI agents on a local LLM (no API key)

Every FlakeLens agent — SelfHeal, the author agent, the API-test agent, failure
analysis, crew classification — talks to one configurable LLM endpoint. By
default that's the Anthropic API (`ANTHROPIC_API_KEY`). Point it at any server
that speaks the **Anthropic Messages API dialect** instead and everything runs
fully local: no key, no cost per call, no test data leaving your machine.

```bash
FLAKELENS_LLM_BASE_URL=http://localhost:11434   # your local server
FLAKELENS_LLM_MODEL=qwen3-coder:30b             # its model name
```

That's the whole configuration. With a base URL set, `ANTHROPIC_API_KEY` is not
required; the agent buttons light up in the dashboard.

## Option A — Ollama (simplest)

Ollama exposes Anthropic-compatible Messages endpoints natively:

```bash
ollama pull qwen3-coder:30b
# .env / container env:
FLAKELENS_LLM_BASE_URL=http://localhost:11434
FLAKELENS_LLM_MODEL=qwen3-coder:30b
```

In docker-compose, use `http://host.docker.internal:11434` so the container can
reach Ollama on the host.

## Option B — LiteLLM proxy (fronts anything)

If your model is served by vLLM, llama.cpp, LM Studio, or a cloud provider that
isn't Anthropic, put a [LiteLLM](https://docs.litellm.ai/) proxy in front — it
translates the Anthropic Messages dialect to whatever the backend speaks:

```bash
pip install 'litellm[proxy]'
litellm --model ollama/qwen3-coder:30b --port 4000
# then:
FLAKELENS_LLM_BASE_URL=http://localhost:4000
FLAKELENS_LLM_MODEL=ollama/qwen3-coder:30b
```

## Honest expectations

The agents are **tool-use loops**: the model must reliably emit structured tool
calls (read file, edit file, run tests, click, fill) over many turns. That's
the capability that separates models here.

- **Failure analysis and crew classification** work well on mid-size local
  models — they're single-shot prompts.
- **SelfHeal / author / API agents** need a strong tool-calling coder model.
  Realistic minimum: ~30B-class coder models (qwen3-coder, deepseek-coder-v2).
  Small 7B models will wander, mis-call tools, and burn iterations.
- Every agent has a hard iteration cap and verifies its work by actually
  running the tests, so a weaker model fails *safe* — a job ends as "failed"
  or "gave up", never as an unverified change. PRs remain human-reviewed.

## What stays true regardless of provider

- Evidence is scrubbed of secrets (`services/redact.py`) before it is sent to
  **any** LLM, local or hosted.
- No LLM configured at all? Every observability feature still works — the
  agent buttons show how to enable them.
