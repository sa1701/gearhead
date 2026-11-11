"""The subject check: a second look at a question the coverage gate would decline.

The reranker score says whether the question's wording matches a page. It cannot
tell "vague, but about a part this car has" ("turn key and just a click") from
"about a part this car does not have" ("CarPlay keeps disconnecting"). Both score low.

So the model is asked one small thing it is good at: name the part or feature the
question is about, in workshop wording. That name is then looked up in the manual
by the same search and reranker as everything else. The model never judges whether
the manual covers the question; the manual lookup does.
"""
from __future__ import annotations

import logging
import re

from ..ai.provider import AIProvider
from ..config import settings
from ..library.rerank import rerank
from ..library.search import search

log = logging.getLogger(__name__)

SUBJECT_POOL = 20       # chunks the reranker reads when looking a subject up
SUBJECT_MAX_TOKENS = 40
MAX_QUESTION_CHARS = 500   # the model only needs the gist to name a part
MAX_SUBJECT_CHARS = 60     # a part name is a few words; anything longer is not one

SUBJECT_SYSTEM = """You label car questions for a workshop-manual search.
Name the ONE part, system or feature the question is about, in standard workshop-manual wording, 1 to 4 words.
If the question is about a different vehicle, or is not about repairing a vehicle at all, say so in the subject.
Reply with ONLY a JSON object and nothing else: {"subject": "..."}

Examples:
Q: fan belt squeals on a cold start
{"subject": "drive belt"}
Q: The heated steering wheel has stopped working. Which fuse is it?
{"subject": "heated steering wheel"}
Q: horn sounds weak and croaky
{"subject": "horn"}
Q: How do I top up the oil in a Ford Ranger 3.2?
{"subject": "Ford Ranger engine oil"}
Q: The wireless phone charging pad gets hot and stops charging.
{"subject": "wireless phone charger"}
Q: fuel gauge reads empty after I fill up
{"subject": "fuel gauge"}
Q: What is the best roof rack to buy?
{"subject": "roof rack purchase advice"}"""

_SUBJECT_FIELD = re.compile(r'"subject"\s*:\s*"([^"]*)"')


def parse_subject(reply: str) -> str:
    """The subject named in the model's reply, or "" if the reply does not name one.

    Small models wrap the JSON in other text, so the field is picked out by pattern.
    A reply with no subject field, or with a sentence where a part name should be,
    counts as no subject: it must not be searched as if it were one.
    """
    found = _SUBJECT_FIELD.search(reply)
    subject = found.group(1).strip() if found else ""
    return subject if len(subject) <= MAX_SUBJECT_CHARS else ""


def name_subject(problem: str, brain: AIProvider) -> str:
    """Ask the model what part or feature the question is about. Empty if the call fails."""
    try:
        reply = brain.complete(
            system=SUBJECT_SYSTEM,
            messages=[{"role": "user", "content": f"Q: {problem[:MAX_QUESTION_CHARS]}"}],
            max_tokens=SUBJECT_MAX_TOKENS,
            thinking=False,  # thinking would spend the whole 40-token budget
        )
    except Exception:
        log.exception("Subject check failed; the question stays declined.")
        return ""
    return parse_subject(reply)


def subject_score(subject: str, car: str) -> float:
    """How well the best manual chunk matches the subject, 0 to 1. 0 if nothing can be scored."""
    if not subject:
        return 0.0
    best = rerank(subject, search(subject, n=SUBJECT_POOL, car=car), top_n=1)
    return best[0].get("rerank_score", 0.0) if best else 0.0


def subject_is_in_manual(subject: str, car: str) -> bool:
    """True if the manual has a good match for the subject. False if the lookup fails."""
    try:
        return subject_score(subject, car) >= settings.gate_subject_min_score
    except Exception:
        log.exception("Subject lookup failed; the question stays declined.")
        return False
