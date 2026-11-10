"""Gate eval: which questions does the coverage gate stop before the model is called?

Uses the same retrieval and the same gate function as the app, on every question
in the gold set. No model call, so it runs in a few minutes.

Run:  python -m eval.gate_eval
"""
from __future__ import annotations

import sys

from src.brain.diagnose import _retrieve
from src.brain.gate import manual_covers
from src.config import settings

from .store import CAR, RESULTS_DIR, append_jsonl, load_gold, pending

ONE_SHOT_CHUNKS = 6
OUT = RESULTS_DIR / "gate.jsonl"


def run(limit: int | None = None, car: str = CAR) -> None:
    if settings.retrieval != "rerank":
        raise SystemExit("The gate reads reranker scores; unset GEARHEAD_RETRIEVAL to score it.")
    todo = pending(load_gold(car), OUT)[:limit]
    print(f"Gate eval (threshold {settings.gate_min_score}): {len(todo)} questions -> {OUT}")

    for i, row in enumerate(todo, 1):
        hits, _ = _retrieve(row["question"], car, brain=None, final=ONE_SHOT_CHUNKS)
        append_jsonl(OUT, {
            "id": row["id"],
            "answerable": row["answerable"],
            "top_score": max((h.get("rerank_score", 1.0) for h in hits), default=0.0),
            "blocked": not manual_covers(hits),
            "threshold": settings.gate_min_score,
        })
        print(f"  {i}/{len(todo)} {row['id']}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    run(limit=int(sys.argv[1]) if len(sys.argv) > 1 else None)
