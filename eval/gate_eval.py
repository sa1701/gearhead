"""Gate eval: which questions does the coverage gate stop before the model is called?

Uses the same retrieval and the same gate function as the app, on every question
in the gold set. No model call, so it runs in a few minutes.

Run:  python -m eval.gate_eval             # one-shot gate on the main question set
      python -m eval.gate_eval followup    # the interview flow: ask once, search again
      python -m eval.gate_eval subject     # the subject check. One short model call per declined question
"""
from __future__ import annotations

import sys

from src.ai import get_provider
from src.brain.diagnose import _retrieve
from src.brain.gate import manual_covers
from src.brain.subject import name_subject, subject_score
from src.config import settings

from .metrics import first_system_rank
from .store import CAR, RESULTS_DIR, append_jsonl, load_followups, load_gold, load_vague, pending

ONE_SHOT_CHUNKS = 6
OUT = RESULTS_DIR / "gate.jsonl"
OUT_FOLLOWUP = RESULTS_DIR / "gate_followup.jsonl"
OUT_SUBJECT = RESULTS_DIR / "gate_subject.jsonl"


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


def run_followup(car: str = CAR) -> None:
    """Replay the interview's opening: if the first search finds no good match, add the
    owner's follow-up detail and search again, exactly as DiagnosisSession does.

    Vague complaints should get through (with chunks from the right system).
    Unanswerable questions should still be declined after the extra detail.
    """
    if settings.retrieval != "rerank":
        raise SystemExit("The gate reads reranker scores; unset GEARHEAD_RETRIEVAL to score it.")
    followups = load_followups(car)
    questions = [{**r, "kind": "vague"} for r in load_vague(car)]
    questions += [{**r, "kind": "unanswerable"} for r in load_gold(car, answerable=False)]
    todo = pending([q for q in questions if q["id"] in followups], OUT_FOLLOWUP)
    print(f"Follow-up gate eval: {len(todo)} questions -> {OUT_FOLLOWUP}")

    for i, row in enumerate(todo, 1):
        hits, _ = _retrieve(row["question"], car, brain=None, final=ONE_SHOT_CHUNKS)
        blocked_first = not manual_covers(hits)
        if blocked_first:
            hits, _ = _retrieve(f"{row['question']}. {followups[row['id']]}", car, brain=None,
                                final=ONE_SHOT_CHUNKS)
        blocked_final = not manual_covers(hits)
        append_jsonl(OUT_FOLLOWUP, {
            "id": row["id"],
            "kind": row["kind"],
            "blocked_first": blocked_first,
            "blocked_final": blocked_final,
            "rank": None if blocked_final or row["kind"] != "vague"
                    else first_system_rank(hits, row["sections"]),
            "confirmed": bool(row.get("confirmed")),
        })
        print(f"  {i}/{len(todo)} {row['id']}")


def run_subject(car: str = CAR) -> None:
    """Run the gate with its second look on every question: specific symptoms, vague
    complaints and unanswerable ones. Only questions the score declines reach the model.

    This repeats the steps of gate.covers with the app's own functions, so that the
    subject and its score can be recorded for each question.
    """
    if settings.retrieval != "rerank":
        raise SystemExit("The gate reads reranker scores; unset GEARHEAD_RETRIEVAL to score it.")
    if settings.gate_subject_min_score <= 0:
        raise SystemExit("The subject check is switched off (GEARHEAD_GATE_SUBJECT_MIN_SCORE is 0).")
    questions = [{**r, "kind": "answerable"} for r in load_gold(car, answerable=True)]
    questions += [{**r, "kind": "vague"} for r in load_vague(car)]
    questions += [{**r, "kind": "unanswerable"} for r in load_gold(car, answerable=False)]
    todo = pending(questions, OUT_SUBJECT)
    print(f"Subject check eval (threshold {settings.gate_subject_min_score}): "
          f"{len(todo)} questions -> {OUT_SUBJECT}")
    brain = get_provider()

    for i, row in enumerate(todo, 1):
        hits, _ = _retrieve(row["question"], car, brain=None, final=ONE_SHOT_CHUNKS)
        blocked_by_score = not manual_covers(hits)
        subject, score = None, None
        if blocked_by_score:
            subject = name_subject(row["question"], brain)
            score = round(subject_score(subject, car), 4)
        append_jsonl(OUT_SUBJECT, {
            "id": row["id"],
            "kind": row["kind"],
            "blocked_by_score": blocked_by_score,
            "subject": subject,
            "subject_score": score,
            "blocked": blocked_by_score and score < settings.gate_subject_min_score,
            "threshold": settings.gate_subject_min_score,
        })
        print(f"  {i}/{len(todo)} {row['id']} {subject or ''}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "subject" in sys.argv[1:]:
        run_subject()
    elif "followup" in sys.argv[1:]:
        run_followup()
    else:
        numbers = [a for a in sys.argv[1:] if a.isdigit()]
        run(limit=int(numbers[0]) if numbers else None)
