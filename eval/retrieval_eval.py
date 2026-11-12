"""Retrieval eval: does the right manual section and page reach the top of the search?

Four ways of searching are compared on the same questions:
  raw       the owner's question straight into the vector search
  expanded  the older pipeline: the brain rewrites the question into search phrases first
  manual    the manual's own wording of the symptom (an upper bound, not a real user)
  rerank    the current pipeline: search wide, then a local cross-encoder re-orders

Run:  python -m eval.retrieval_eval            # raw, expanded, manual (needs the model)
      python -m eval.retrieval_eval rerank     # rerank only (no model call)
      python -m eval.retrieval_eval vague      # vague complaints, scored by system (no model call)
"""
from __future__ import annotations

import sys
import time

from src.ai import get_provider
from src.brain.diagnose import _retrieve, _retrieve_expanded
from src.brain.gate import manual_covers
from src.config import settings
from src.library.search import search

from .build_gold import load_fixes, symptom_hash
from .metrics import first_hit_rank, first_system_rank, share_from_systems
from .store import CAR, RESULTS_DIR, append_jsonl, load_gold, load_vague, pending

TOP_N = 20          # same depth the interview loop pulls
PER_QUERY = 5       # same per-phrase depth the interview loop uses
OUT = RESULTS_DIR / "retrieval.jsonl"
OUT_RERANK = RESULTS_DIR / "retrieval_rerank.jsonl"
OUT_VAGUE = RESULTS_DIR / "retrieval_vague.jsonl"
ONE_SHOT_CHUNKS = 6  # what the one-shot diagnosis passes to the model


def _ranks(hits: list[dict], row: dict) -> dict:
    return {
        "section_rank": first_hit_rank(hits, row["source_file"]),
        "page_rank": first_hit_rank(hits, row["source_file"], row["pages"]),
    }


def run(limit: int | None = None, car: str = CAR) -> None:
    manual_wording = {symptom_hash(e["symptom"]): e["symptom"] for e in load_fixes(car)}
    todo = pending(load_gold(car, answerable=True), OUT)[:limit]
    brain = get_provider()
    print(f"Retrieval eval: {len(todo)} questions to run -> {OUT}")

    for i, row in enumerate(todo, 1):
        question = row["question"]
        started = time.perf_counter()
        expanded_hits, queries = _retrieve_expanded(question, car, brain, PER_QUERY, TOP_N)
        append_jsonl(OUT, {
            "id": row["id"],
            "section_code": row["section_code"],
            "raw": _ranks(search(question, n=TOP_N, car=car), row),
            "expanded": _ranks(expanded_hits, row),
            "manual": _ranks(search(manual_wording[row["fix_hash"]], n=TOP_N, car=car), row),
            "queries": queries[1:],
            "seconds": round(time.perf_counter() - started, 1),
        })
        print(f"  {i}/{len(todo)} {row['id']}")


def run_rerank(limit: int | None = None, car: str = CAR) -> None:
    """Score the rerank pipeline through the same function the app calls."""
    if settings.retrieval != "rerank":
        raise SystemExit("GEARHEAD_RETRIEVAL is not 'rerank'; unset it to score the rerank pipeline.")
    todo = pending(load_gold(car, answerable=True), OUT_RERANK)[:limit]
    print(f"Rerank retrieval eval: {len(todo)} questions to run -> {OUT_RERANK}")

    for i, row in enumerate(todo, 1):
        started = time.perf_counter()
        hits, _ = _retrieve(row["question"], car, brain=None, final=TOP_N)
        append_jsonl(OUT_RERANK, {
            "id": row["id"],
            "section_code": row["section_code"],
            "rerank": _ranks(hits, row),
            "pool": max(settings.rerank_pool, TOP_N),
            "model": settings.rerank_model,
            "seconds": round(time.perf_counter() - started, 1),
        })
        print(f"  {i}/{len(todo)} {row['id']}")


def _system_score(hits: list[dict], sections: list[str]) -> dict:
    return {"rank": first_system_rank(hits, sections), "share": round(share_from_systems(hits, sections), 3)}


def run_vague(limit: int | None = None, car: str = CAR) -> None:
    """Vague complaints have no single right page, so score whether the chunks come
    from the right system, and whether the gate asks for more detail instead."""
    if settings.retrieval != "rerank":
        raise SystemExit("GEARHEAD_RETRIEVAL is not 'rerank'; unset it to score the current pipeline.")
    todo = pending(load_vague(car), OUT_VAGUE)[:limit]
    print(f"Vague complaint eval: {len(todo)} questions to run -> {OUT_VAGUE}")

    for i, row in enumerate(todo, 1):
        question = row["question"]
        hits, _ = _retrieve(question, car, brain=None, final=ONE_SHOT_CHUNKS)
        append_jsonl(OUT_VAGUE, {
            "id": row["id"],
            "system": row["system"],
            "confirmed": row["confirmed"],
            "raw": _system_score(search(question, n=ONE_SHOT_CHUNKS, car=car), row["sections"]),
            "rerank": _system_score(hits, row["sections"]),
            "blocked": not manual_covers(hits),
            "top_score": max((h.get("rerank_score", 1.0) for h in hits), default=0.0),
        })
        print(f"  {i}/{len(todo)} {row['id']}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    numbers = [a for a in sys.argv[1:] if a.isdigit()]
    count = int(numbers[0]) if numbers else None
    if "vague" in sys.argv[1:]:
        run_vague(limit=count)
    elif "rerank" in sys.argv[1:]:
        run_rerank(limit=count)
    else:
        run(limit=count)
