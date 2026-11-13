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


def get_gate_provider(brain: AIProvider) -> AIProvider:
    """The brain for the coverage gate's short checks.

    This is the answer brain, unless a separate local gate model is set. The two jobs
    suit different small models: one is better at deciding what a question is about,
    another at writing an answer that cites the manual.
    """
    if settings.resolved_provider() == "ollama" and settings.ollama_gate_model:
        from .ollama_provider import OllamaProvider

        return OllamaProvider(model=settings.ollama_gate_model)
    return brain
