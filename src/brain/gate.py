"""The coverage gate: do not let the model guess when the manual has no good match.

A small local model will write confident repair steps for a part this car does not
even have. The reranker already scores how well each chunk answers the question, so
a low best score means one of two things: the manual does not cover it, or the
question is too vague to match to a page. Either way the right move is the same:
say so and ask for more detail, before any model call.

On the eval set a threshold of 0.1 stops 28 of 30 unanswerable questions. It also
stops 17 of 112 answerable ones, most of them one-line complaints such as
"My Patrol won't start", which need more detail anyway.
"""
from __future__ import annotations

from ..config import settings

NOT_FOUND_MESSAGE = (
    "I could not match this to a page in the manual for this car, so I am not going to "
    "guess at a fix.\n\n"
    "Two things to check:\n"
    "- If the car has this part, describe what happens in more detail: what you see, "
    "hear or feel, when it happens, and any warning light that comes on.\n"
    "- If it is an accessory or a feature this model does not have, the factory manual "
    "will not cover it.\n\n"
    "⚠️ Always verify with a qualified professional before relying on this."
)


def manual_covers(hits: list[dict]) -> bool:
    """True if the best chunk is a good enough match to reason from.

    With no reranker scores (reranker unavailable, or the older expansion path) there
    is nothing to judge by, so the gate stays open.
    """
    if not hits:
        return False
    scores = [hit["rerank_score"] for hit in hits if "rerank_score" in hit]
    if not scores:
        return True
    return max(scores) >= settings.gate_min_score
