"""The swappable AI brain interface.

Everything in the app talks to THIS, not to Claude directly. That means we can
drop in a local Ollama brain later (Phase 2) without changing the rest of the app.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class AIProvider(ABC):
    """A brain that can hold a conversation and reason over text (and images)."""

    @abstractmethod
    def complete(
        self,
        system: str,
        messages: list[dict],
        max_tokens: int = 4096,
    ) -> str:
        """Send a system prompt + conversation, return the assistant's text reply.

        `messages` is a list of {"role": "user"|"assistant", "content": ...}.
        `content` may be a plain string, or a list of blocks (text + images) in
        the Claude content format, so manual diagrams can be included.
        """
        raise NotImplementedError
