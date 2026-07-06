"""AI brains. get_provider() hands back Claude or local Ollama per settings."""
from __future__ import annotations

from ..config import settings
from .provider import AIProvider


def get_provider(model: str | None = None) -> AIProvider:
    """The configured brain. `model` overrides the Claude model; ignored for Ollama."""
    if settings.resolved_provider() == "ollama":
        from .ollama_provider import OllamaProvider

        return OllamaProvider()
    from .claude_provider import ClaudeProvider

    return ClaudeProvider(model=model)
