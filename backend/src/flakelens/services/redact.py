"""Evidence sanitization — strip secrets from any text before it reaches an LLM.

Applied to failure context (analysis), the SelfHeal task, and the OpenAPI spec.
Targeted patterns only: we redact things that are almost certainly secrets
(bearer tokens, API keys, passwords in URLs, JWTs, cookies), not arbitrary
long strings — over-redaction would hide the very evidence the model needs.
"""
import re

_PLACEHOLDER = "«redacted»"

# Each rule: (compiled pattern, replacement). Order matters — most specific first.
_RULES: list[tuple[re.Pattern, str]] = [
    # Authorization: Bearer <token>  /  Authorization: Basic <b64>
    (re.compile(r"(?i)(authorization\s*[:=]\s*)(bearer|basic|token)\s+\S+"),
     rf"\1\2 {_PLACEHOLDER}"),
    # Cookie / Set-Cookie header values
    (re.compile(r"(?i)(set-)?cookie\s*[:=]\s*[^\r\n]+"),
     rf"cookie: {_PLACEHOLDER}"),
    # user:password@host  (credentials embedded in a URL)
    (re.compile(r"(?i)([a-z][a-z0-9+.\-]*://[^\s:/@]+:)[^\s:/@]+(@)"),
     rf"\1{_PLACEHOLDER}\2"),
    # JWTs: header.payload.signature (three base64url segments)
    (re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),
     _PLACEHOLDER),
    # Provider API keys with recognizable prefixes (Anthropic, OpenAI, GitHub,
    # AWS, Slack, Google, Stripe, and FlakeLens' own flk_).
    (re.compile(
        r"\b("
        r"sk-ant-[A-Za-z0-9_\-]{6,}"
        r"|sk-[A-Za-z0-9][A-Za-z0-9_\-]{18,}"
        r"|gh[pousr]_[A-Za-z0-9]{20,}"
        r"|github_pat_[A-Za-z0-9_]{20,}"
        r"|flk_[A-Za-z0-9]{20,}"
        r"|AKIA[0-9A-Z]{16}"
        r"|xox[baprs]-[A-Za-z0-9\-]{10,}"
        r"|AIza[A-Za-z0-9_\-]{20,}"
        r"|(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{10,}"
        r")\b"),
     _PLACEHOLDER),
    # KEY=value / "key": "value" where the key name looks sensitive. Group 1
    # keeps the key + separator + any opening quote; the value is redacted.
    (re.compile(
        r"(?i)([\"']?[a-z0-9_]*(?:password|passwd|secret|token|api[_-]?key|access[_-]?key"
        r"|private[_-]?key|client[_-]?secret|auth)[a-z0-9_]*[\"']?\s*[:=]\s*[\"']?)"
        r"([^\s\"'&]{4,})"),
     rf"\1{_PLACEHOLDER}"),
]


def scrub(text: str | None) -> str:
    if not text:
        return text or ""
    for pattern, replacement in _RULES:
        text = pattern.sub(replacement, text)
    return text
