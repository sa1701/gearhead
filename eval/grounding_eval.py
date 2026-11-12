"""Grounding eval: run the real one-shot diagnosis and keep what it said and what it saw.

Stores the answer next to the exact pages that were in the model's context, so
report.py can check every citation and every refusal without re-running the model.

Run:  python -m eval.grounding_eval [limit] [--no-fixdb]
The retrieval pipeline under test is whatever GEARHEAD_RETRIEVAL selects.
"""
from __future__ import annotations

import random
import sys
import time
from itertools import chain, zip_longest

from src.brain import diagnose
from src.config import settings
from src.library.fixdb import search_fixes
from src.library.ingest import SECTION_NAMES

from .store import CAR, RESULTS_DIR, append_jsonl, load_gold, pending

SEED = 316
ANSWERABLE_SAMPLE = 30   # generation is slow on a laptop; retrieval uses the full set
FIXES_IN_CONTEXT = 4     # same number diagnose.build_context asks for


def _sample(car: str) -> list[dict]:
    """A fixed answerable sample plus every unanswerable question, interleaved so
    a run that is stopped early still covers both kinds."""
    answerable = load_gold(car, answerable=True)
    picked = random.Random(SEED).sample(answerable, min(ANSWERABLE_SAMPLE, len(answerable)))
    mixed = chain.from_iterable(zip_longest(picked, load_gold(car, answerable=False)))
    return [row for row in mixed if row is not None]


def _fix_pages(question: str, car: str) -> list[list]:
    """Pages the Fix DB block put in front of the model (search_fixes is deterministic)."""
    return [
        [fix.get("section", ""), page]
        for fix in search_fixes(question, n=FIXES_IN_CONTEXT, car=car)
        for page in fix.get("pages") or []
    ]


def results_name(retrieval: str, use_fixdb: bool) -> str:
    """One file per pipeline so runs never mix: grounding.jsonl is the expansion baseline."""
    mode = "" if retrieval == "expand" else f"_{retrieval}"
    return f"grounding{mode}{'' if use_fixdb else '_nofixdb'}.jsonl"


def run(limit: int | None = None, use_fixdb: bool = True, car: str = CAR) -> None:
    out = RESULTS_DIR / results_name(settings.retrieval, use_fixdb)
    if not use_fixdb:
        diagnose.search_fixes = lambda *args, **kwargs: []  # ablation: raw excerpts only
    todo = pending(_sample(car), out)[:limit]
    print(f"Grounding eval ({settings.retrieval} retrieval, fix DB {'on' if use_fixdb else 'off'}): "
          f"{len(todo)} to run -> {out}")

    for i, row in enumerate(todo, 1):
        started = time.perf_counter()
        result = diagnose.diagnose_once(row["question"], car=car)
        gated = result.get("refused", False)  # the coverage gate declined before any model call
        record = {
            "id": row["id"],
            "answerable": row["answerable"],
            "question": row["question"],
            "answer": result["answer"],
            "context": [list(source) for source in result["sources"]],
            "fix_context": _fix_pages(row["question"], car) if use_fixdb and not gated else [],
            "gated": gated,
            "seconds": round(time.perf_counter() - started, 1),
        }
        if row["answerable"]:
            record["gold"] = {"section": SECTION_NAMES[row["section_code"]], "pages": row["pages"]}
        append_jsonl(out, record)
        print(f"  {i}/{len(todo)} {row['id']} ({record['seconds']}s)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    numbers = [a for a in sys.argv[1:] if a.isdigit()]
    run(limit=int(numbers[0]) if numbers else None, use_fixdb="--no-fixdb" not in sys.argv)
