"""Unit tests for how the brain picks manual chunks (search and model are faked)."""
import pytest

from src.brain import diagnose
from src.config import settings


def _hit(page: int, distance: float) -> dict:
    return {"text": f"chunk {page}", "section": "Brakes", "page": page,
            "source_file": "br.pdf", "distance": distance}


class _BrainThatMustNotBeCalled:
    def complete(self, **kwargs):
        raise AssertionError("rerank mode must not spend a model call on query expansion")


class _BrainWithFixedPhrases:
    def complete(self, **kwargs):
        return "brake rotor runout\nbrake pedal pulsation"


@pytest.fixture
def searches(monkeypatch):
    """Record every search call and answer with 40 fake hits."""
    calls = []

    def fake_search(query: str, n: int = 5, car: str | None = None) -> list[dict]:
        calls.append({"query": query, "n": n, "car": car})
        return [_hit(page, distance=page / 100) for page in range(1, 41)][:n]

    monkeypatch.setattr(diagnose, "search", fake_search)
    return calls


def test_rerank_mode_searches_wide_once_and_returns_the_reranked_top(monkeypatch, searches):
    monkeypatch.setattr(settings, "retrieval", "rerank")
    monkeypatch.setattr(settings, "rerank_pool", 30)
    monkeypatch.setattr(diagnose, "rerank", lambda query, hits, top_n: list(reversed(hits))[:top_n])

    hits, queries = diagnose._retrieve("brakes shudder", "some-car", _BrainThatMustNotBeCalled(), final=6)

    assert searches == [{"query": "brakes shudder", "n": 30, "car": "some-car"}]
    assert [h["page"] for h in hits] == [30, 29, 28, 27, 26, 25]
    assert queries == ["brakes shudder"]


def test_rerank_mode_never_searches_for_fewer_chunks_than_it_must_return(monkeypatch, searches):
    monkeypatch.setattr(settings, "retrieval", "rerank")
    monkeypatch.setattr(settings, "rerank_pool", 30)
    monkeypatch.setattr(diagnose, "rerank", lambda query, hits, top_n: hits[:top_n])

    hits, _ = diagnose._retrieve("brakes shudder", "some-car", _BrainThatMustNotBeCalled(), final=35)

    assert searches[0]["n"] == 35
    assert len(hits) == 35


def test_expand_mode_still_searches_each_phrase_and_merges_by_distance(monkeypatch, searches):
    monkeypatch.setattr(settings, "retrieval", "expand")

    hits, queries = diagnose._retrieve("brakes shudder", "some-car", _BrainWithFixedPhrases(),
                                       per_query=4, final=6)

    assert queries == ["brakes shudder", "brake rotor runout", "brake pedal pulsation"]
    assert [call["n"] for call in searches] == [4, 4, 4]
    assert [h["page"] for h in hits] == [1, 2, 3, 4]
