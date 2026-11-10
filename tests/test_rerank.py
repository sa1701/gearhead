"""Unit tests for the reranking step (no model download: the scorer is injected)."""
from src.library import rerank as rerank_module
from src.library.rerank import rerank, rerank_hits

HITS = [
    {"text": "front brake pad wear limit", "page": 21, "distance": 0.40},
    {"text": "brake pedal goes to the floor", "page": 4, "distance": 0.45},
    {"text": "rear axle oil seal", "page": 9, "distance": 0.50},
]


def _score_by_word_overlap(query: str, texts: list[str]) -> list[float]:
    wanted = set(query.split())
    return [float(len(wanted & set(text.split()))) for text in texts]


def test_rerank_hits_puts_the_best_scoring_chunk_first():
    ranked = rerank_hits("brake pedal floor", HITS, top_n=3, scorer=_score_by_word_overlap)

    assert [h["page"] for h in ranked] == [4, 21, 9]


def test_rerank_hits_keeps_only_the_top_n():
    ranked = rerank_hits("brake pedal floor", HITS, top_n=1, scorer=_score_by_word_overlap)

    assert [h["page"] for h in ranked] == [4]


def test_rerank_hits_keeps_the_search_order_on_a_tie():
    ranked = rerank_hits("gearbox", HITS, top_n=3, scorer=_score_by_word_overlap)

    assert [h["page"] for h in ranked] == [21, 4, 9]


def test_rerank_hits_records_the_score_without_changing_the_input():
    ranked = rerank_hits("brake pedal floor", HITS, top_n=1, scorer=_score_by_word_overlap)

    assert ranked[0]["rerank_score"] == 3.0
    assert ranked[0]["distance"] == 0.45
    assert "rerank_score" not in HITS[1]


def test_rerank_hits_of_nothing_is_nothing():
    assert rerank_hits("anything", [], top_n=5, scorer=_score_by_word_overlap) == []


def test_rerank_falls_back_to_search_order_when_no_model_is_available(monkeypatch):
    monkeypatch.setattr(rerank_module, "_load_scorer", lambda: None)

    assert rerank("brake pedal floor", HITS, top_n=2) == HITS[:2]


def test_rerank_uses_the_loaded_model(monkeypatch):
    monkeypatch.setattr(rerank_module, "_load_scorer", lambda: _score_by_word_overlap)

    assert [h["page"] for h in rerank("brake pedal floor", HITS, top_n=2)] == [4, 21]
