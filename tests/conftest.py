"""Shared test setup."""
import pytest

from src.config import settings


@pytest.fixture(autouse=True)
def no_gate_model_from_the_local_env(monkeypatch):
    """A developer's .env may name a separate gate model. Tests start without one,
    so they never reach for a real Ollama server."""
    monkeypatch.setattr(settings, "ollama_gate_model", None)
