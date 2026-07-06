"""The interview loop (Step 3): the brain acts like a mechanic.

Each turn it either asks ONE clarifying question or, when confident, gives the
grounded fix. The manual context is loaded once up front and cached, so the
repeated turns are cheap.
"""
from __future__ import annotations

from typing import Callable

from ..ai import get_provider
from .diagnose import _retrieve, build_context

INTERVIEW_SYSTEM = """You are GEARHEAD, a master automotive technician guiding a
capable DIYer through a diagnosis, like a real mechanic standing next to them.

You have the workshop-manual excerpts at the bottom. Run a focused diagnostic
interview using this strict protocol — every reply must be EXACTLY ONE of:

  QUESTION: <one clear, plain-English diagnostic question>
      Use when you need more information to narrow the cause.

  DIAGNOSIS: <the full grounded fix>
      Use as soon as you are confident enough to give the fix.

Rules:
- Ask ONE question at a time, the single most useful next one. Keep it easy to answer.
- Don't over-interrogate. After a couple of good answers, give the DIAGNOSIS.
- The DIAGNOSIS must use ONLY the excerpts below, cite sources inline like
  [Brakes, p.30], and be structured: (1) most likely cause(s), (2) how to confirm,
  (3) the fix as numbered steps with any torque specs / measurements from the manual.
- If the excerpts lack what's needed, say so honestly in the DIAGNOSIS — never invent
  a procedure or a number.
- End every DIAGNOSIS with exactly:
  "⚠️ Always verify with a qualified professional before relying on this."

MANUAL EXCERPTS (use only these):
{context}
"""


def _mode_and_body(reply: str) -> tuple[str, str]:
    """Parse the protocol prefix. Returns ('question'|'diagnosis', text)."""
    cleaned = reply.lstrip().lstrip("*# ").strip()
    upper = cleaned.upper()
    if upper.startswith("QUESTION"):
        return "question", cleaned.split(":", 1)[-1].strip()
    if upper.startswith("DIAGNOSIS"):
        return "diagnosis", cleaned.split(":", 1)[-1].strip()
    # No recognizable prefix → treat as a diagnosis so we never loop forever.
    return "diagnosis", cleaned


def run_interview(
    problem: str,
    ask_fn: Callable[[str], str],
    car: str = "nissan-patrol-y61",
    max_questions: int = 5,
    on_event: Callable[[str, str], None] | None = None,
) -> dict:
    """Run the diagnostic interview.

    ask_fn(question) -> the user's answer (input() in a terminal; the UI later).
    on_event(kind, text) -> optional hook for progress ('search'|'question'|'cache').
    """
    def emit(kind: str, text: str) -> None:
        if on_event:
            on_event(kind, text)

    brain = get_provider()
    hits, queries = _retrieve(problem, car, brain, per_query=5, final=20)
    emit("search", f"Pulled {len(hits)} manual sections to reason over.")
    system = INTERVIEW_SYSTEM.format(context=build_context(problem, car, hits))

    messages = [{"role": "user", "content": f"PROBLEM: {problem}"}]
    cache_reads = 0

    for turn in range(max_questions + 1):
        force = turn == max_questions
        turn_messages = messages
        if force:
            turn_messages = messages + [
                {"role": "user", "content": "Give your best DIAGNOSIS now with what you know."}
            ]

        reply = brain.complete(system=system, messages=turn_messages, max_tokens=1600, cache=True)

        u = brain.last_usage
        if u is not None:
            cache_reads += getattr(u, "cache_read_input_tokens", 0) or 0
            emit(
                "cache",
                f"turn {turn + 1}: cache_write={getattr(u, 'cache_creation_input_tokens', 0)} "
                f"cache_read={getattr(u, 'cache_read_input_tokens', 0)} "
                f"fresh_input={u.input_tokens} output={u.output_tokens}",
            )

        mode, body = _mode_and_body(reply)
        if mode == "question" and not force:
            emit("question", body)
            messages.append({"role": "assistant", "content": reply})
            answer = ask_fn(body)
            messages.append({"role": "user", "content": answer})
        else:
            return {
                "diagnosis": body,
                "questions_asked": turn,
                "sources": [(h["section"], h["page"]) for h in hits],
                "total_cache_read_tokens": cache_reads,
            }

    # Unreachable, but keeps the type checker happy.
    return {"diagnosis": "", "questions_asked": max_questions, "sources": [], "total_cache_read_tokens": cache_reads}


# --- Web-friendly, step-based session (drives the UI; one turn per HTTP call) ---

_GAP_PHRASES = (
    "can't safely", "cannot safely", "not enough information", "do not contain",
    "don't contain", "not in these excerpts", "isn't in these excerpts",
    "do not give", "don't give", "verify those", "would be needed",
)


def _confidence(questions_asked: int, diagnosis_text: str) -> int:
    """Rough diagnostic-confidence score (30-95) for the tachometer gauge."""
    score = 60 + min(questions_asked, 3) * 9  # more narrowing → more confident
    if any(p in diagnosis_text.lower() for p in _GAP_PHRASES):
        score -= 28  # the model flagged gaps in the manual → lower confidence
    return max(30, min(95, score))


class DiagnosisSession:
    """Holds one diagnosis conversation. Each .answer() advances one turn."""

    def __init__(self, problem: str, car: str = "nissan-patrol-y61", max_questions: int = 4):
        self.problem = problem
        self.car = car
        self.max_questions = max_questions
        self.brain = get_provider()
        self.hits, _ = _retrieve(problem, car, self.brain, per_query=5, final=20)
        self.system = INTERVIEW_SYSTEM.format(context=build_context(problem, car, self.hits))
        self.messages = [{"role": "user", "content": f"PROBLEM: {problem}"}]
        self.questions_asked = 0
        self.done = False

    def sources(self) -> list[dict]:
        seen, out = set(), []
        for h in self.hits:
            key = (h["source_file"], h["page"])
            if key in seen:
                continue
            seen.add(key)
            out.append({"section": h["section"], "page": h["page"], "source_file": h["source_file"]})
        return out

    def _turn(self, force: bool = False) -> dict:
        msgs = self.messages
        if force:
            msgs = self.messages + [
                {"role": "user", "content": "Give your best DIAGNOSIS now with what you know."}
            ]
        reply = self.brain.complete(system=self.system, messages=msgs, max_tokens=1600, cache=True)
        mode, body = _mode_and_body(reply)
        if mode == "question" and not force:
            self.messages.append({"role": "assistant", "content": reply})
            self.questions_asked += 1
            return {"type": "question", "text": body, "questions_asked": self.questions_asked}
        self.done = True
        return {
            "type": "diagnosis",
            "text": body,
            "confidence": _confidence(self.questions_asked, body),
            "sources": self.sources(),
        }

    def start(self) -> dict:
        return self._turn()

    def answer(self, user_answer: str) -> dict:
        self.messages.append({"role": "user", "content": user_answer})
        return self._turn(force=self.questions_asked >= self.max_questions)
