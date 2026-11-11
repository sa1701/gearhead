"""Turn the raw result files into the numbers: summary.json and REPORT.md.

Run:  python -m eval.report
"""
from __future__ import annotations

import json
import statistics
import sys

from .metrics import (
    answer_outcome,
    citation_is_valid,
    hit_rate,
    paired_change,
    mean_reciprocal_rank,
    normalise_section,
    parse_citations,
    wilson_interval,
)
from .store import RESULTS_DIR, read_results

KS = (1, 3, 6, 20)          # the one-shot diagnosis passes 6 chunks, the interview 20
CONFIGS = ("raw", "expanded", "manual", "rerank")
GROUNDING_RUNS = (           # results file stem -> report heading
    ("grounding", "Grounding: expansion pipeline (baseline), Fix DB on"),
    ("grounding_nofixdb", "Grounding: expansion pipeline (baseline), Fix DB off"),
    ("grounding_rerank", "Grounding: rerank pipeline, Fix DB on"),
    ("grounding_rerank_nofixdb", "Grounding: rerank pipeline, Fix DB off"),
)
HEADLINE_K = 6               # chunks the one-shot diagnosis passes to the model


def _rate(successes: int, total: int) -> dict:
    low, high = wilson_interval(successes, total)
    return {
        "rate": round(successes / total, 3) if total else None,
        "n": total,
        "ci95": [round(low, 3), round(high, 3)],
    }


def merge_by_id(rows: list[dict], extra: list[dict], field: str) -> list[dict]:
    """Copy one field from a second results file onto the rows with the same id."""
    by_id = {r["id"]: r[field] for r in extra}
    return [{**r, field: by_id[r["id"]]} if r["id"] in by_id else r for r in rows]


def retrieval_summary(rows: list[dict]) -> dict:
    summary = {}
    for config in CONFIGS:
        if not all(config in r for r in rows):
            continue  # that search mode has not been run on every question yet
        section = [r[config]["section_rank"] for r in rows]
        page = [r[config]["page_rank"] for r in rows]
        summary[config] = {
            "n": len(rows),
            "section_hit": {f"@{k}": round(hit_rate(section, k), 3) for k in KS},
            "page_hit": {f"@{k}": round(hit_rate(page, k), 3) for k in KS},
            "section_mrr": round(mean_reciprocal_rank(section), 3),
            "page_mrr": round(mean_reciprocal_rank(page), 3),
        }
    if "rerank" in summary:
        summary[f"rerank_vs_raw_page@{HEADLINE_K}"] = paired_change(
            [r["raw"]["page_rank"] for r in rows], [r["rerank"]["page_rank"] for r in rows], HEADLINE_K)
    return summary


def _outcome_rate(scored: list[dict], outcome: str) -> dict:
    return _rate(sum(s["outcome"] == outcome for s in scored), len(scored))


def _score_answer(row: dict) -> dict:
    allowed = {(normalise_section(s), p) for s, p in row["context"] + row["fix_context"]}
    citations = parse_citations(row["answer"])
    valid = [c for c in citations if citation_is_valid(c, allowed)]
    scored = {
        "citations": len(citations),
        "valid": len(valid),
        "outcome": "refused" if row.get("gated") else answer_outcome(row["answer"]),
    }
    if row["answerable"]:
        gold = {(normalise_section(row["gold"]["section"]), p) for p in row["gold"]["pages"]}
        retrieved = {(normalise_section(s), p) for s, p in row["context"]}
        scored["gold_retrieved"] = bool(gold & retrieved)      # raw manual chunks only
        scored["gold_in_context"] = bool(gold & allowed)       # chunks plus the Fix DB block
        scored["gold_cited"] = any(citation_is_valid(c, gold) for c in citations)
    return scored


def grounding_summary(rows: list[dict]) -> dict:
    if not rows:
        return {}
    scored = [(_score_answer(r), r) for r in rows]
    answerable = [s for s, r in scored if r["answerable"]]
    unanswerable = [s for s, r in scored if not r["answerable"]]
    attempted = [s for s in answerable if s["outcome"] != "refused"]
    return {
        "answers": len(rows),
        "citation_validity": _rate(sum(s["valid"] for s, _ in scored),
                                   sum(s["citations"] for s, _ in scored)),
        "attempts_with_a_citation": _rate(sum(s["citations"] > 0 for s in attempted), len(attempted)),
        "attempts_with_a_bad_citation": _rate(
            sum(s["citations"] > s["valid"] for s in attempted), len(attempted)),
        "unanswerable_refused": _outcome_rate(unanswerable, "refused"),
        "unanswerable_hedged": _outcome_rate(unanswerable, "hedged"),
        "unanswerable_answered": _outcome_rate(unanswerable, "answered"),
        "answerable_refused": _outcome_rate(answerable, "refused"),
        "gold_page_retrieved": _rate(sum(s["gold_retrieved"] for s in answerable), len(answerable)),
        "gold_page_in_context": _rate(sum(s["gold_in_context"] for s in answerable), len(answerable)),
        "gold_page_cited": _rate(sum(s["gold_cited"] for s in answerable), len(answerable)),
        "median_seconds": statistics.median(r["seconds"] for r in rows),
    }


def gate_summary(gate_rows: list[dict], model_rows: list[dict]) -> dict:
    """What the coverage gate blocks, and how that changes what reaches the user.

    model_rows are answers from a run WITHOUT the gate. For the unanswerable questions
    in that run: "before" is how often the model gave repair steps on its own, "after"
    is how often it still would once the gate has removed the questions it blocks.
    """
    if not gate_rows:
        return {}
    unanswerable = [r for r in gate_rows if not r["answerable"]]
    answerable = [r for r in gate_rows if r["answerable"]]
    summary = {
        "threshold": gate_rows[0].get("threshold"),
        "unanswerable_blocked": _rate(sum(r["blocked"] for r in unanswerable), len(unanswerable)),
        "answerable_blocked": _rate(sum(r["blocked"] for r in answerable), len(answerable)),
    }
    blocked = {r["id"]: r["blocked"] for r in gate_rows}
    judged = [(r["id"], _score_answer(r)["outcome"] != "refused")
              for r in model_rows if not r["answerable"] and r["id"] in blocked]
    if judged:
        summary["given_steps_before"] = _rate(sum(steps for _, steps in judged), len(judged))
        summary["given_steps_after"] = _rate(
            sum(steps and not blocked[qid] for qid, steps in judged), len(judged))
    return summary


def followup_summary(rows: list[dict]) -> dict:
    """The interview's ask-once-then-search-again flow, on vague and unanswerable questions."""
    if not rows:
        return {}
    vague = [r for r in rows if r["kind"] == "vague"]
    unanswerable = [r for r in rows if r["kind"] == "unanswerable"]
    through = [r for r in vague if not r["blocked_final"]]
    return {
        "vague_through_at_once": _rate(sum(not r["blocked_first"] for r in vague), len(vague)),
        "vague_through_after_detail": _rate(
            sum(r["blocked_first"] and not r["blocked_final"] for r in vague), len(vague)),
        "vague_declined": _rate(sum(r["blocked_final"] for r in vague), len(vague)),
        "vague_through_with_right_system": _rate(sum(r["rank"] is not None for r in through), len(through)),
        "unanswerable_declined": _rate(sum(r["blocked_final"] for r in unanswerable), len(unanswerable)),
    }


SUBJECT_KINDS = (
    ("unanswerable", "No answer in manual"),
    ("answerable", "Answer in manual, specific symptom"),
    ("vague", "Vague complaint"),
)


def _declined(rows: list[dict], field: str) -> dict:
    count = sum(bool(r[field]) for r in rows)
    return {**_rate(count, len(rows)), "successes": count}


def subject_summary(rows: list[dict]) -> dict:
    """How many questions of each kind are declined, by the score alone and after the
    subject check gives the declined ones a second look."""
    if not rows:
        return {}
    summary = {}
    for kind, _ in SUBJECT_KINDS:
        of_kind = [r for r in rows if r["kind"] == kind]
        if of_kind:
            summary[kind] = {"score_only": _declined(of_kind, "blocked_by_score"),
                             "with_subject_check": _declined(of_kind, "blocked")}
    return summary


def _count_cell(result: dict) -> str:
    return f"{_pct(result['rate'])} ({result['successes']} of {result['n']})"


VAGUE_MODES = ("raw", "rerank")


def vague_summary(rows: list[dict]) -> dict:
    """Vague complaints: are the chunks from the right system, and how often does the gate step in?"""
    if not rows:
        return {}
    summary = {
        "n": len(rows),
        "labels_confirmed": sum(bool(r.get("confirmed")) for r in rows),
        "asked_for_detail": _rate(sum(r["blocked"] for r in rows), len(rows)),
    }
    for mode in VAGUE_MODES:
        summary[mode] = {
            "first_chunk_right": _rate(sum(r[mode]["rank"] == 1 for r in rows), len(rows)),
            "any_chunk_right": _rate(sum(r[mode]["rank"] is not None for r in rows), len(rows)),
            "mean_share_right": round(statistics.mean(r[mode]["share"] for r in rows), 3),
        }
    return summary


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def _rate_line(label: str, result: dict) -> str:
    low, high = result["ci95"]
    return f"| {label} | {_pct(result['rate'])} | {_pct(low)} to {_pct(high)} | {result['n']} |"


def to_markdown(summary: dict) -> str:
    lines = ["# GEARHEAD eval results", ""]
    retrieval = summary.get("retrieval")
    if retrieval:
        n = retrieval["raw"]["n"]
        lines += [
            f"## Retrieval ({n} answerable questions)", "",
            "Share of questions where a chunk from the correct page is in the top k.", "",
            "| Search | page@1 | page@3 | page@6 | page@20 | section@1 | section@6 | page MRR |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for config in (c for c in CONFIGS if c in retrieval):
            r = retrieval[config]
            lines.append(
                f"| {config} | " + " | ".join(_pct(r["page_hit"][f"@{k}"]) for k in KS)
                + f" | {_pct(r['section_hit']['@1'])} | {_pct(r['section_hit']['@6'])}"
                + f" | {r['page_mrr']:.2f} |"
            )
        lines.append("")
        change = retrieval.get(f"rerank_vs_raw_page@{HEADLINE_K}")
        if change:
            lines += [
                f"Rerank against the plain question at page@{HEADLINE_K}: {change['gained']} questions "
                f"gained, {change['lost']} lost (exact sign test p = {change['p_value']:.3f}).", "",
            ]
    for key, title in GROUNDING_RUNS:
        g = summary.get(key)
        if not g:
            continue
        lines += [
            f"## {title} ({g['answers']} answers)", "",
            "| Measure | Result | 95% interval | n |", "|---|---|---|---|",
            _rate_line("Citations that point at a page the model was given", g["citation_validity"]),
            _rate_line("Attempted answers with at least one citation", g["attempts_with_a_citation"]),
            _rate_line("Attempted answers citing a page outside their context", g["attempts_with_a_bad_citation"]),
            _rate_line("No answer in manual: refused cleanly", g["unanswerable_refused"]),
            _rate_line("No answer in manual: flagged the gap but gave steps anyway", g["unanswerable_hedged"]),
            _rate_line("No answer in manual: answered with no warning", g["unanswerable_answered"]),
            _rate_line("Answer in manual: refused anyway", g["answerable_refused"]),
            _rate_line("Correct page among the retrieved manual chunks", g["gold_page_retrieved"]),
            _rate_line("Correct page in context once the Fix DB block is added (circular: "
                       "the questions come from the Fix DB)", g["gold_page_in_context"]),
            _rate_line("Answer cites the correct page", g["gold_page_cited"]),
            "", f"Median time per answer: {g['median_seconds']:.0f} s.", "",
        ]
    vague = summary.get("vague")
    if vague:
        status = (f"{vague['labels_confirmed']} of {vague['n']} labels confirmed by hand"
                  if vague["labels_confirmed"] else "labels are provisional, not yet confirmed by hand")
        lines += [
            f"## Vague complaints ({vague['n']} questions, {status})", "",
            "A chunk is right if it comes from a manual section that covers that system.", "",
            "| Search | First chunk right | Any of 6 right | Average share of the 6 that are right |",
            "|---|---|---|---|",
        ]
        for mode in VAGUE_MODES:
            v = vague[mode]
            lines.append(f"| {mode} | {_pct(v['first_chunk_right']['rate'])} | "
                         f"{_pct(v['any_chunk_right']['rate'])} | {_pct(v['mean_share_right'])} |")
        lines += ["", f"The gate asks for more detail on {_pct(vague['asked_for_detail']['rate'])} of them.", ""]
    followup = summary.get("followup")
    if followup:
        lines += [
            "## Interview opening: ask for detail once, then search again", "",
            "| Measure | Result | 95% interval | n |", "|---|---|---|---|",
            _rate_line("Vague complaint: good match straight away", followup["vague_through_at_once"]),
            _rate_line("Vague complaint: good match after one round of detail", followup["vague_through_after_detail"]),
            _rate_line("Vague complaint: still declined", followup["vague_declined"]),
            _rate_line("Of those that got through: a chunk from the right system in the top 6",
                       followup["vague_through_with_right_system"]),
            _rate_line("No answer in manual: still declined after the owner adds detail",
                       followup["unanswerable_declined"]),
            "",
        ]
    subject = summary.get("subject")
    if subject:
        lines += [
            "## Subject check: a second look at questions the score would decline", "",
            "| Question type | Declined by score alone | Declined with the subject check |", "|---|---|---|",
        ]
        lines += [f"| {label} | {_count_cell(subject[kind]['score_only'])} | "
                  f"{_count_cell(subject[kind]['with_subject_check'])} |"
                  for kind, label in SUBJECT_KINDS if kind in subject]
        lines.append("")
    gate = summary.get("gate")
    if gate:
        lines += [
            f"## Coverage gate (decline when the best rerank score is under {gate['threshold']})", "",
            "| Measure | Result | 95% interval | n |", "|---|---|---|---|",
            _rate_line("No answer in manual: stopped before the model", gate["unanswerable_blocked"]),
            _rate_line("Answer in manual: stopped anyway (asked for more detail)", gate["answerable_blocked"]),
        ]
        if "given_steps_before" in gate:
            lines += [
                _rate_line("No answer in manual: model gives repair steps, no gate", gate["given_steps_before"]),
                _rate_line("No answer in manual: model gives repair steps, with the gate", gate["given_steps_after"]),
            ]
        lines.append("")
    return "\n".join(lines)


def build_summary() -> dict:
    summary = {}
    retrieval_rows = merge_by_id(read_results(RESULTS_DIR / "retrieval.jsonl"),
                                 read_results(RESULTS_DIR / "retrieval_rerank.jsonl"), field="rerank")
    if retrieval_rows:
        summary["retrieval"] = retrieval_summary(retrieval_rows)
    for name, _ in GROUNDING_RUNS:
        rows = read_results(RESULTS_DIR / f"{name}.jsonl")
        if rows:
            summary[name] = grounding_summary(rows)
    followup = followup_summary(read_results(RESULTS_DIR / "gate_followup.jsonl"))
    if followup:
        summary["followup"] = followup
    vague = vague_summary(read_results(RESULTS_DIR / "retrieval_vague.jsonl"))
    if vague:
        summary["vague"] = vague
    subject = subject_summary(read_results(RESULTS_DIR / "gate_subject.jsonl"))
    if subject:
        summary["subject"] = subject
    gate = gate_summary(read_results(RESULTS_DIR / "gate.jsonl"), read_results(RESULTS_DIR / "grounding.jsonl"))
    if gate:
        summary["gate"] = gate
    return summary


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    result = build_summary()
    (RESULTS_DIR / "summary.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    report = to_markdown(result)
    (RESULTS_DIR / "REPORT.md").write_text(report + "\n", encoding="utf-8")
    print(report)
