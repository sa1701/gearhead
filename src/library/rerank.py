"""Reranking: re-order search candidates by reading each one against the question.

The vector search is good at finding the right neighbourhood of the manual but
weak at putting the exact page first. A small cross-encoder reads the question
and each candidate chunk together and scores how well the chunk answers it.

Runs locally on the CPU (ONNX, no GPU, no API call). The model is downloaded once
into models/ and works offline after that. If it is not available, the search
order is kept, so the app still works.
"""
from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from ..config import settings

Scorer = Callable[[str, list[str]], list[float]]  # (question, chunk texts) -> one score per chunk


def rerank_hits(query: str, hits: list[dict], top_n: int, scorer: Scorer) -> list[dict]:
    """The top_n hits by score, best first. Ties keep their search order."""
    if not hits:
        return []
    scores = scorer(query, [hit["text"] for hit in hits])
    order = sorted(range(len(hits)), key=lambda i: (-scores[i], i))
    return [{**hits[i], "rerank_score": round(float(scores[i]), 4)} for i in order[:top_n]]


@lru_cache(maxsize=1)
def _load_scorer() -> Scorer | None:
    """The local cross-encoder, or None if it cannot be loaded (not installed, or offline on first run)."""
    try:
        from flashrank import Ranker, RerankRequest

        ranker = Ranker(model_name=settings.rerank_model, cache_dir=str(settings.models_dir))
    except Exception as error:  # missing package, failed download, corrupt model file
        print(f"Reranker unavailable ({type(error).__name__}: {error}). Keeping search order.")
        return None

    def score(query: str, texts: list[str]) -> list[float]:
        passages = [{"id": i, "text": text} for i, text in enumerate(texts)]
        scored = {p["id"]: p["score"] for p in ranker.rerank(RerankRequest(query=query, passages=passages))}
        return [scored[i] for i in range(len(texts))]

    return score


def rerank(query: str, hits: list[dict], top_n: int) -> list[dict]:
    """Best top_n hits for the question. Falls back to search order without a model."""
    scorer = _load_scorer()
    if scorer is None:
        return hits[:top_n]
    return rerank_hits(query, hits, top_n, scorer)
