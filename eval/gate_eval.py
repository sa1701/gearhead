"""Gate eval: which questions does the coverage gate stop before the model is called?

Uses the same retrieval and the same gate function as the app, on every question
in the gold set. No model call, so it runs in a few minutes.

Run:  python -m eval.gate_eval             # one-shot gate on the main question set
      python -m eval.gate_eval followup    # the interview flow: ask once, search again
      python -m eval.gate_eval subject     # the subject check. One short model call per declined question
      python -m eval.gate_eval subject holdout   # the same, on questions never used for tuning
      python -m eval.gate_eval vehicles    # the other-vehicle check on every question set. No model call
      python -m eval.gate_eval passing     # the whole gate on questions that mention two vehicles
      python -m eval.gate_eval passing holdout   # the same, on questions written after the check was frozen
"""
from __future__ import annotations

import json
import sys

from src.ai import get_provider
from src.brain.diagnose import _retrieve
from src.brain.gate import manual_covers
from src.brain.subject import name_subject, subject_score
from src.brain.about import is_about_another_vehicle
from src.brain.vehicles import other_vehicle_named
from src.config import settings

from .metrics import first_system_rank
from .store import (CAR, RESULTS_DIR, append_jsonl, load_followups, load_gold, load_holdout,
                    load_passing_set, load_vague, load_vehicle_set, pending)

ONE_SHOT_CHUNKS = 6
OUT = RESULTS_DIR / "gate.jsonl"
OUT_FOLLOWUP = RESULTS_DIR / "gate_followup.jsonl"
OUT_SUBJECT = RESULTS_DIR / "gate_subject.jsonl"
OUT_SUBJECT_HOLDOUT = RESULTS_DIR / "gate_subject_holdout.jsonl"
OUT_VEHICLES = RESULTS_DIR / "gate_vehicles.jsonl"
OUT_PASSING = RESULTS_DIR / "gate_passing.jsonl"
OUT_PASSING_HOLDOUT = RESULTS_DIR / "gate_passing_holdout.jsonl"


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


def _tuning_questions(car: str) -> list[dict]:
    questions = [{**r, "kind": "answerable"} for r in load_gold(car, answerable=True)]
    questions += [{**r, "kind": "vague"} for r in load_vague(car)]
    return questions + [{**r, "kind": "unanswerable"} for r in load_gold(car, answerable=False)]


def run_subject(car: str = CAR, holdout: bool = False) -> None:
    """Run the gate with its second look on every question: specific symptoms, vague
    complaints and unanswerable ones. Only questions the score declines reach the model.

    This repeats the steps of gate.covers with the app's own functions, so that the
    subject and its score can be recorded for each question.
    """
    if settings.retrieval != "rerank":
        raise SystemExit("The gate reads reranker scores; unset GEARHEAD_RETRIEVAL to score it.")
    if settings.gate_subject_min_score <= 0:
        raise SystemExit("The subject check is switched off (GEARHEAD_GATE_SUBJECT_MIN_SCORE is 0).")
    out = OUT_SUBJECT_HOLDOUT if holdout else OUT_SUBJECT
    todo = pending(load_holdout(car) if holdout else _tuning_questions(car), out)
    print(f"Subject check eval (threshold {settings.gate_subject_min_score}): "
          f"{len(todo)} questions -> {out}")
    brain = get_provider()

    for i, row in enumerate(todo, 1):
        hits, _ = _retrieve(row["question"], car, brain=None, final=ONE_SHOT_CHUNKS)
        blocked_by_score = not manual_covers(hits)
        subject, score = None, None
        if blocked_by_score:
            subject = name_subject(row["question"], brain)
            score = round(subject_score(subject, car), 4)
        append_jsonl(out, {
            "id": row["id"],
            "kind": row["kind"],
            "top_score": max((h.get("rerank_score", 1.0) for h in hits), default=0.0),
            "blocked_by_score": blocked_by_score,
            "subject": subject,
            "subject_score": score,
            "blocked": blocked_by_score and score < settings.gate_subject_min_score,
            "threshold": settings.gate_subject_min_score,
        })
        print(f"  {i}/{len(todo)} {row['id']} {subject or ''}")


def run_vehicles(car: str = CAR) -> None:
    """Which questions in each set name a different vehicle. Rewritten in full each run,
    since it takes a moment and the name list may change. Written to a temporary file
    first, so a crash never leaves a half-written result that looks complete."""
    sets = {"tuning": _tuning_questions(car), "holdout": load_holdout(car),
            "vehicles": load_vehicle_set(car)}
    empty = [name for name, questions in sets.items() if not questions]
    if empty:
        raise SystemExit(f"No questions found for: {', '.join(empty)}")
    rows = [{"id": row["id"], "set": set_name, "kind": row["kind"],
             "named": other_vehicle_named(row["question"], car)}
            for set_name, questions in sets.items() for row in questions]
    partial = OUT_VEHICLES.with_suffix(".partial")
    partial.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    partial.replace(OUT_VEHICLES)
    for set_name, questions in sets.items():
        print(f"  {set_name}: {len(questions)} questions")


def gate_decision(about_other: bool | None, blocked_by_score: bool, has_hits: bool,
                  subject_score: float | None, threshold: float) -> bool:
    """True if the gate declines, given what each stage found. The same order as
    gate.covers: another vehicle first, then the page match, then the subject check,
    which is skipped when there are no pages or it is switched off."""
    if about_other:
        return True
    if not blocked_by_score:
        return False
    if not has_hits or threshold <= 0 or subject_score is None:
        return True
    return subject_score < threshold


def run_passing(car: str = CAR, holdout: bool = False) -> None:
    """The whole gate, stage by stage, on questions that mention two vehicles.

    This repeats the steps of gate.covers with the app's own functions, so that each
    stage can be recorded. The model is asked which vehicle the question is about only
    when another vehicle is named, and asked for the subject only when the score declines.
    """
    if settings.retrieval != "rerank":
        raise SystemExit("The gate reads reranker scores; unset GEARHEAD_RETRIEVAL to score it.")
    questions = load_passing_set(car, holdout)
    if not questions:
        raise SystemExit("No questions found for this two-vehicle set.")
    out = OUT_PASSING_HOLDOUT if holdout else OUT_PASSING
    todo = pending(questions, out)
    print(f"Two-vehicle eval: {len(todo)} questions -> {out}")
    brain = get_provider()

    for i, row in enumerate(todo, 1):
        named = other_vehicle_named(row["question"], car)
        about_other = is_about_another_vehicle(row["question"], car, brain) if named else None
        hits, _ = _retrieve(row["question"], car, brain=None, final=ONE_SHOT_CHUNKS)
        blocked_by_score = not manual_covers(hits)
        subject, score = None, None
        if not about_other and blocked_by_score and hits and settings.gate_subject_min_score > 0:
            subject = name_subject(row["question"], brain)
            score = round(subject_score(subject, car), 4)
        append_jsonl(out, {
            "id": row["id"],
            "kind": row["kind"],
            "group": row["group"],
            "named": named,
            "about_other": about_other,
            "top_score": max((h.get("rerank_score", 1.0) for h in hits), default=0.0),
            "blocked_by_score": blocked_by_score,
            "subject": subject,
            "subject_score": score,
            "declined": gate_decision(about_other, blocked_by_score, bool(hits), score,
                                      settings.gate_subject_min_score),
        })
        print(f"  {i}/{len(todo)} {row['id']} named={named} about_other={about_other} {subject or ''}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "passing" in sys.argv[1:]:
        run_passing(holdout="holdout" in sys.argv[1:])
    elif "vehicles" in sys.argv[1:]:
        run_vehicles()
    elif "subject" in sys.argv[1:]:
        run_subject(holdout="holdout" in sys.argv[1:])
    elif "followup" in sys.argv[1:]:
        run_followup()
    else:
        numbers = [a for a in sys.argv[1:] if a.isdigit()]
        run(limit=int(numbers[0]) if numbers else None)
