"""Claude implementation of the AIProvider interface (Phase 1 brain)."""
from __future__ import annotations

import anthropic

from ..config import settings
from .provider import AIProvider


class ClaudeProvider(AIProvider):
    supports_vision = True

    def __init__(self, model: str | None = None) -> None:
        settings.check()
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = model or settings.model
        self.last_usage = None  # token usage from the most recent call

    def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 4096,
        cache: bool = False,
        thinking: bool = True,
    ) -> str:
        # When cache=True, mark the (large, stable) system prompt as cacheable so
        # repeated turns in an interview re-read it cheaply instead of re-paying.
        system_param = system
        if cache:
            system_param = [
                {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
            ]
        kwargs = {}
        if thinking:
            kwargs["thinking"] = {"type": "adaptive"}  # model decides how hard to think
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_param,
            messages=messages,
            **kwargs,
        )
        self.last_usage = resp.usage
        # Skip thinking blocks; return only the visible text.
        return "".join(b.text for b in resp.content if b.type == "text").strip()
