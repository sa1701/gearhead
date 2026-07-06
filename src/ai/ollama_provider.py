"""Local Ollama implementation of the AIProvider interface (Phase 2 brain).

Free and fully offline: talks to the Ollama server on this machine over HTTP.
Text-only — image blocks in the content are dropped, so diagram *captioning*
falls back to metadata (see library/images.py). Everything else works the same.
"""
from __future__ import annotations

import httpx

from ..config import settings
from .provider import AIProvider


class _Usage:
    """Duck-types the slice of Anthropic's Usage object that callers read."""

    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_input_tokens = 0
        self.cache_creation_input_tokens = 0


def _text_only(content) -> str:
    """Flatten Claude-style content (str or block list) to plain text, dropping images."""
    if isinstance(content, str):
        return content
    return "\n".join(
        b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
    ).strip()


class OllamaProvider(AIProvider):
    supports_vision = False

    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.ollama_model
        self.host = settings.ollama_host.rstrip("/")
        self.last_usage = None  # token usage from the most recent call
        try:
            httpx.get(f"{self.host}/api/tags", timeout=3)
        except Exception as e:
            raise RuntimeError(
                f"Can't reach Ollama at {self.host} — is it running?\n"
                f"Start it with `ollama serve`, and fetch the model once with "
                f"`ollama pull {self.model}`."
            ) from e

    def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 4096,
        cache: bool = False,
        thinking: bool = False,
    ) -> str:
        # cache/thinking are Claude-only knobs — accepted so callers don't have to
        # care which brain is loaded.
        chat = [{"role": "system", "content": system}]
        chat += [{"role": m["role"], "content": _text_only(m["content"])} for m in messages]
        resp = httpx.post(
            f"{self.host}/api/chat",
            json={
                "model": self.model,
                "messages": chat,
                "stream": False,
                # num_ctx must fit the full interview context (20 excerpts ≈ 6k
                # tokens) or Ollama silently truncates from the top — which eats
                # the system prompt and with it the QUESTION:/DIAGNOSIS: protocol.
                "options": {"num_predict": max_tokens, "num_ctx": 16384, "temperature": 0.3},
            },
            timeout=600.0,
        )
        resp.raise_for_status()
        data = resp.json()
        self.last_usage = _Usage(data.get("prompt_eval_count", 0), data.get("eval_count", 0))
        return data["message"]["content"].strip()
