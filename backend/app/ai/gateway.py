"""AI provider gateway — walks the configured priority chain
(Ollama → OpenRouter → Gemini → Claude → OpenAI), returning the first
provider that is available. Every provider speaks one interface; callers
never learn which one answered.

Zero providers available is a first-class state, not an error: callers fall
back to deterministic logic so the platform never hard-fails on AI.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from app.core.settings import get_settings

log = structlog.get_logger("ai.gateway")

_JSON_BLOCK = re.compile(r"\{.*\}", re.S)


@dataclass
class ChatResult:
    text: str
    provider: str
    model: str


class ProviderUnavailable(Exception):
    """Raised inside a provider when it cannot serve; the gateway moves on."""


class AiUnavailable(Exception):
    """No provider in the chain could serve. Callers must degrade gracefully."""


# --------------------------------------------------------------------------
# Individual providers. Each is a thin function: (messages, json_mode, max_tokens)
# → text, or raises ProviderUnavailable.
# --------------------------------------------------------------------------
def _ollama(messages: list[dict], json_mode: bool, max_tokens: int) -> ChatResult:
    s = get_settings()
    base = s.ollama_base_url.rstrip("/")
    try:
        tags = httpx.get(f"{base}/api/tags", timeout=2).json()
        models = tags.get("models") or []
        if not models:
            raise ProviderUnavailable("ollama: no models pulled")
        model = models[0]["name"]
        body: dict[str, Any] = {"model": model, "messages": messages, "stream": False,
                                "options": {"num_predict": max_tokens}}
        if json_mode:
            body["format"] = "json"
        r = httpx.post(f"{base}/api/chat", json=body, timeout=120)
        r.raise_for_status()
        return ChatResult(r.json()["message"]["content"], "OLLAMA", model)
    except ProviderUnavailable:
        raise
    except Exception as e:  # noqa: BLE001
        raise ProviderUnavailable(f"ollama: {e}") from e


def _openai_compatible(provider: str, base_url: str, api_key: str, model: str,
                       messages: list[dict], json_mode: bool,
                       max_tokens: int) -> ChatResult:
    if not api_key:
        raise ProviderUnavailable(f"{provider}: no api key")
    body: dict[str, Any] = {"model": model, "messages": messages,
                            "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    try:
        r = httpx.post(f"{base_url}/chat/completions", json=body, timeout=120,
                       headers={"Authorization": f"Bearer {api_key}"})
        r.raise_for_status()
        return ChatResult(r.json()["choices"][0]["message"]["content"], provider, model)
    except Exception as e:  # noqa: BLE001
        raise ProviderUnavailable(f"{provider}: {e}") from e


def _openrouter(messages, json_mode, max_tokens) -> ChatResult:
    s = get_settings()
    return _openai_compatible(
        "OPENROUTER", "https://openrouter.ai/api/v1", s.openrouter_api_key,
        "meta-llama/llama-3.1-8b-instruct:free", messages, json_mode, max_tokens)


def _openai(messages, json_mode, max_tokens) -> ChatResult:
    s = get_settings()
    return _openai_compatible(
        "OPENAI", "https://api.openai.com/v1", s.openai_api_key,
        "gpt-4o-mini", messages, json_mode, max_tokens)


def _gemini(messages, json_mode, max_tokens) -> ChatResult:
    s = get_settings()
    if not s.gemini_api_key:
        raise ProviderUnavailable("gemini: no api key")
    # Gemini uses an OpenAI-compatible endpoint.
    return _openai_compatible(
        "GEMINI", "https://generativelanguage.googleapis.com/v1beta/openai",
        s.gemini_api_key, "gemini-1.5-flash", messages, json_mode, max_tokens)


def _anthropic(messages, json_mode, max_tokens) -> ChatResult:
    s = get_settings()
    if not s.anthropic_api_key:
        raise ProviderUnavailable("anthropic: no api key")
    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    turns = [m for m in messages if m["role"] != "system"]
    if json_mode:
        system += "\nRespond with a single valid JSON object and nothing else."
    try:
        r = httpx.post("https://api.anthropic.com/v1/messages", timeout=120,
                       headers={"x-api-key": s.anthropic_api_key,
                                "anthropic-version": "2023-06-01"},
                       json={"model": "claude-haiku-4-5-20251001",
                             "max_tokens": max_tokens,
                             "system": system, "messages": turns})
        r.raise_for_status()
        return ChatResult(r.json()["content"][0]["text"], "ANTHROPIC",
                          "claude-haiku-4-5-20251001")
    except Exception as e:  # noqa: BLE001
        raise ProviderUnavailable(f"anthropic: {e}") from e


_PROVIDERS = {
    "OLLAMA": _ollama, "OPENROUTER": _openrouter, "GEMINI": _gemini,
    "ANTHROPIC": _anthropic, "OPENAI": _openai,
}


class AiGateway:
    """Instantiate per call-site; walks the settings.ai_provider_chain."""

    def __init__(self, chain: list[str] | None = None):
        self.chain = chain or get_settings().ai_provider_chain

    def available(self) -> bool:
        try:
            self.chat([{"role": "user", "content": "ping"}], max_tokens=1)
            return True
        except AiUnavailable:
            return False

    def chat(self, messages: list[dict], *, json_mode: bool = False,
             max_tokens: int = 800) -> ChatResult:
        errors = []
        for provider_id in self.chain:
            fn = _PROVIDERS.get(provider_id)
            if fn is None:
                continue
            try:
                result = fn(messages, json_mode, max_tokens)
                log.info("ai_chat", provider=result.provider, model=result.model)
                return result
            except ProviderUnavailable as e:
                errors.append(str(e))
                continue
        raise AiUnavailable("; ".join(errors) or "no providers configured")

    def chat_json(self, messages: list[dict], *, max_tokens: int = 800) -> dict:
        """Chat expecting a JSON object; tolerant of prose-wrapped output."""
        result = self.chat(messages, json_mode=True, max_tokens=max_tokens)
        try:
            return json.loads(result.text)
        except json.JSONDecodeError:
            match = _JSON_BLOCK.search(result.text)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
        raise AiUnavailable("provider returned non-JSON output")
