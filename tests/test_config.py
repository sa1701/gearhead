"""Unit tests for settings that depend on which brain is loaded."""
from src.config import Settings


def _settings(provider: str, interview_chunks: str | None = None) -> Settings:
    settings = Settings()
    settings.provider = provider
    settings.interview_chunks = interview_chunks
    return settings


def test_local_model_gets_a_small_interview_context():
    assert _settings("ollama").interview_chunk_count() == 8


def test_cloud_model_keeps_the_wide_interview_context():
    assert _settings("claude").interview_chunk_count() == 20


def test_interview_context_can_be_set_explicitly():
    assert _settings("ollama", interview_chunks="12").interview_chunk_count() == 12
