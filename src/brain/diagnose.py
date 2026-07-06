"""The brain (Step 2): turn a problem + manual pages into a grounded fix.

Flow: search the Library (free) -> hand the best pages to Claude -> Claude
answers using ONLY those pages and cites them. No interview loop yet (Step 3).
"""
from __future__ import annotations

from ..ai import get_provider
from ..ai.provider import AIProvider
from ..library.fixdb import search_fixes
from ..library.search import search

SYSTEM = """You are GEARHEAD, a master automotive technician assistant.

You diagnose and fix car problems using ONLY the workshop-manual excerpts provided
to you in each message. Follow these rules strictly:

- Base every statement on the provided excerpts. Do NOT use outside knowledge or
  guess. The manual is the source of truth.
- Cite the source for key steps, specs, and values inline, like: [Brakes, p.30].
- If the excerpts do not contain enough information to answer safely, say so plainly
  and state what section or detail would be needed. Never invent a procedure or a number.
- Structure the answer:
    1. Most likely cause(s)
    2. How to confirm it (quick checks)
    3. The fix — clear numbered steps, including any torque specs or measurements
       found in the excerpts
- Write like a senior tech talking to a capable DIYer: practical, concise, no fluff.
- ALWAYS end with this exact line:
  "⚠️ Always verify with a qualified professional before relying on this."
"""


_QUERY_SYSTEM = """You turn a car owner's plain-English problem into focused
workshop-manual search phrases. Think about which vehicle SYSTEM is really at
fault (e.g. brake shudder under braking = brakes, not steering, even if the
steering wheel shakes). Output 3-5 short phrases of component + symptom
keywords, one per line, no numbering, no extra text."""


def _format_context(hits: list[dict]) -> str:
    return "\n\n---\n\n".join(
        f"[Section: {h['section']} | Page: {h['page']}]\n{h['text']}" for h in hits
    )


def _format_fixes(fixes: list[dict]) -> str:
    if not fixes:
        return ""
    lines = []
    for f in fixes:
        pages = ", ".join(f"p.{p}" for p in f.get("pages", [])) or "p.?"
        parts = [f"SYMPTOM: {f['symptom']}", "CAUSES: " + "; ".join(f.get("causes", []))]
        if f.get("checks"):
            parts.append("CONFIRM: " + "; ".join(f["checks"]))
        if f.get("fix"):
            parts.append("FIX: " + "; ".join(f["fix"]))
        if f.get("specs"):
            parts.append("SPECS: " + "; ".join(f["specs"]))
        lines.append(f"- {' | '.join(parts)}  [{f.get('section', '?')}, {pages}]")
    return (
        "KNOWN FAILURE PATTERNS (pre-extracted from this car's manual — treat as "
        "manual content; cite their section + pages like the excerpts):\n" + "\n".join(lines)
    )


def build_context(problem: str, car: str, hits: list[dict]) -> str:
    """Fix-DB matches (if built) on top of the raw manual excerpts."""
    block = _format_fixes(search_fixes(problem, n=4, car=car))
    excerpts = _format_context(hits)
    if not block:
        return excerpts
    return f"{block}\n\n=====\n\nRAW MANUAL EXCERPTS:\n\n{excerpts}"


def _expand_queries(problem: str, brain: AIProvider) -> list[str]:
    """Ask the brain to rewrite a messy symptom into good manual search phrases."""
    out = brain.complete(
        system=_QUERY_SYSTEM,
        messages=[{"role": "user", "content": problem}],
        max_tokens=120,
    )
    phrases = [ln.strip("-•* \t") for ln in out.splitlines() if ln.strip()]
    return [problem] + phrases[:5]  # keep the raw problem too, as a fallback


def _retrieve(problem: str, car: str, brain: AIProvider,
              per_query: int = 4, final: int = 6) -> tuple[list[dict], list[str]]:
    """Multi-query search: expand the problem, search each, merge the best hits."""
    queries = _expand_queries(problem, brain)
    best: dict[tuple, dict] = {}
    for q in queries:
        for h in search(q, n=per_query, car=car):
            key = (h["section"], h["page"], h["text"][:60])
            if key not in best or h["distance"] < best[key]["distance"]:
                best[key] = h
    hits = sorted(best.values(), key=lambda h: h["distance"])[:final]
    return hits, queries


def diagnose_once(
    problem: str,
    car: str = "nissan-patrol-y61",
    max_tokens: int = 1500,
) -> dict:
    """One-shot grounded diagnosis. Returns {'answer', 'sources', 'queries'}."""
    brain = get_provider()
    hits, queries = _retrieve(problem, car, brain)
    user = (
        f"CAR: {car}\n"
        f"PROBLEM: {problem}\n\n"
        f"MANUAL EXCERPTS (use only these):\n{build_context(problem, car, hits)}"
    )
    answer = brain.complete(
        system=SYSTEM,
        messages=[{"role": "user", "content": user}],
        max_tokens=max_tokens,
    )
    return {
        "answer": answer,
        "sources": [(h["section"], h["page"]) for h in hits],
        "queries": queries,
    }
