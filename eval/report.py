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
    mean_reciprocal_rank,
    normalise_section,
    parse_citations,
    wilson_interval,
)
from .store import RESULTS_DIR, read_results

KS = (1, 3, 6, 20)          # the one-shot diagnosis passes 6 chunks, the interview 20
CONFIGS = ("raw", "expanded", "manual")


def _rate(successes: int, total: int) -> dict:
    low, high = wilson_interval(successes, total)
    return {
        "rate": round(successes / total, 3) if total else None,
        "n": total,
        "ci95": [round(low, 3), round(high, 3)],
    }


def retrieval_summary(rows: list[dict]) -> dict:
    summary = {}
    for config in CONFIGS:
        section = [r[config]["section_rank"] for r in rows]
        page = [r[config]["page_rank"] for r in rows]
        summary[config] = {
            "n": len(rows),
            "section_hit": {f"@{k}": round(hit_rate(section, k), 3) for k in KS},
            "page_hit": {f"@{k}": round(hit_rate(page, k), 3) for k in KS},
            "section_mrr": round(mean_reciprocal_rank(section), 3),
            "page_mrr": round(mean_reciprocal_rank(page), 3),
        }
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
        "outcome": answer_outcome(row["answer"]),
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
        for config in CONFIGS:
            r = retrieval[config]
            lines.append(
                f"| {config} | " + " | ".join(_pct(r["page_hit"][f"@{k}"]) for k in KS)
                + f" | {_pct(r['section_hit']['@1'])} | {_pct(r['section_hit']['@6'])}"
                + f" | {r['page_mrr']:.2f} |"
            )
        lines.append("")
    for key, title in (("grounding", "Grounding, Fix DB on"),
                       ("grounding_nofixdb", "Grounding, Fix DB off")):
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
    return "\n".join(lines)


def build_summary() -> dict:
    summary = {}
    retrieval_rows = read_results(RESULTS_DIR / "retrieval.jsonl")
    if retrieval_rows:
        summary["retrieval"] = retrieval_summary(retrieval_rows)
    for name in ("grounding", "grounding_nofixdb"):
        rows = read_results(RESULTS_DIR / f"{name}.jsonl")
        if rows:
            summary[name] = grounding_summary(rows)
    return summary


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    result = build_summary()
    (RESULTS_DIR / "summary.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    report = to_markdown(result)
    (RESULTS_DIR / "REPORT.md").write_text(report + "\n", encoding="utf-8")
    print(report)
