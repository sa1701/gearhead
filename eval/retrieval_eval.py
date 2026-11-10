"""Retrieval eval: does the right manual section and page reach the top of the search?

Three ways of searching are compared on the same questions:
  raw       the owner's question straight into the vector search
  expanded  the real pipeline: the brain rewrites the question into search phrases first
  manual    the manual's own wording of the symptom (an upper bound, not a real user)

Run:  python -m eval.retrieval_eval [limit]
"""
from __future__ import annotations

import sys
import time

from src.ai import get_provider
from src.brain.diagnose import _retrieve
from src.library.search import search

from .build_gold import load_fixes, symptom_hash
from .metrics import first_hit_rank
from .store import CAR, RESULTS_DIR, append_jsonl, load_gold, pending

TOP_N = 20          # same depth the interview loop pulls
PER_QUERY = 5       # same per-phrase depth the interview loop uses
OUT = RESULTS_DIR / "retrieval.jsonl"


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
        expanded_hits, queries = _retrieve(question, car, brain, per_query=PER_QUERY, final=TOP_N)
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


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    run(limit=int(sys.argv[1]) if len(sys.argv) > 1 else None)
