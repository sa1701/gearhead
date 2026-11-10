"""Pure scoring functions for the eval. No I/O, no model calls."""
from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence

Citation = tuple[str, int]  # (normalised section name, page)

_BRACKET = re.compile(r"\[([^\[\]]+)\]")
_PAGE_MARK = re.compile(r"\b(?:pp?\.?|pages?)\s*:?\s*(?=\d)", re.IGNORECASE)
_PAGE_SPAN = re.compile(r"(\d+)\s*[-–]\s*(\d+)|(\d+)")
_MAX_RANGE = 20          # "[Brakes, p.3-400]" is a typo, not 398 citations
_PAGE_LIST = re.compile(
    r"\d+(?:\s*[-\u2013]\s*\d+)?"
    r"(?:\s*(?:,|&|and)\s*(?:pp?\.?\s*)?\d+(?:\s*[-\u2013]\s*\d+)?)*"
)
_MIN_SHORT_NAME_WORDS = 2  # "restraint system" may stand for the full section name
_Z_95 = 1.96


# --- retrieval ---------------------------------------------------------------

def first_hit_rank(
    hits: Sequence[dict], source_file: str, pages: Iterable[int] | None = None
) -> int | None:
    """1-based rank of the first chunk from the gold section (and gold page, if given)."""
    gold_pages = None if pages is None else set(pages)
    for rank, hit in enumerate(hits, start=1):
        if hit["source_file"] != source_file:
            continue
        if gold_pages is None or hit["page"] in gold_pages:
            return rank
    return None


def hit_rate(ranks: Sequence[int | None], k: int) -> float:
    """Share of questions whose first correct chunk is in the top k."""
    if not ranks:
        return 0.0
    return sum(1 for r in ranks if r is not None and r <= k) / len(ranks)


def mean_reciprocal_rank(ranks: Sequence[int | None]) -> float:
    if not ranks:
        return 0.0
    return sum(1 / r for r in ranks if r is not None) / len(ranks)


# --- citations ---------------------------------------------------------------

def normalise_section(name: str) -> str:
    """Lower-case words only, so "Lubrication & Cooling" equals "lubrication and cooling"."""
    cleaned = re.sub(r"[^a-z0-9]+", " ", name.lower())
    words = [w for w in cleaned.split() if w != "and"]
    return " ".join(words[1:] if words[:1] == ["section"] else words)


def _pages_in(text: str) -> list[int]:
    pages: list[int] = []
    for start, end, single in _PAGE_SPAN.findall(text):
        if single:
            pages.append(int(single))
        elif 0 <= int(end) - int(start) <= _MAX_RANGE:
            pages.extend(range(int(start), int(end) + 1))
        else:
            pages.append(int(start))
    return pages


def parse_citations(answer: str) -> list[Citation]:
    """Every (section, page) the answer cites, e.g. "[Brakes, p.30]".

    A bracket may hold several sources. Each page list ends at the first thing
    that is not a page, so "[Brakes, p.30 (120 N·m)]" cites page 30 only.
    """
    found: list[Citation] = []
    for bracket in _BRACKET.findall(answer):
        position, section = 0, ""
        while (mark := _PAGE_MARK.search(bracket, position)) is not None:
            section = normalise_section(bracket[position:mark.start()]) or section
            page_list = _PAGE_LIST.match(bracket, mark.end())
            found.extend((section, page) for page in _pages_in(page_list.group()))
            position = page_list.end()
    return found


def _same_section(cited: str, allowed: str) -> bool:
    """Exact name, the name plus extra words, or a shortened name of 2+ words.

    One word is not enough for a shortened name: "engine" could be any of three sections.
    """
    if cited == allowed or cited.startswith(allowed + " "):
        return True
    return len(cited.split()) >= _MIN_SHORT_NAME_WORDS and allowed.startswith(cited + " ")


def citation_is_valid(citation: Citation, allowed: Iterable[Citation]) -> bool:
    """True if that section and page were actually in the context given to the model."""
    section, page = citation
    return any(page == p and _same_section(section, s) for s, p in allowed)


# --- refusals ----------------------------------------------------------------

_SAYS_MANUAL_LACKS_IT = re.compile(
    r"(?:\bdo(?:es)?\s+not|\bdon.t|\bdoesn.t)\s+(?:\w+\s+){0,2}?"
    r"(?:contain|cover|include|provide|address|mention|specify|give|list|describe)\b"
    r"|(?:\bnot|n.t)\s+(?:\w+\s+){0,2}?"
    r"(?:addressed|covered|mentioned|included|specified|described|found\s+in)\b"
    r"|\bno\s+(?:\w+\s+){0,2}?(?:information|mention|instructions?|procedures?|details)\b"
    r"|\bnot\s+enough\s+information|\binsufficient\s+information"
    r"|\bcan(?:not|.t)\s+(?:safely|find|provide|give|answer)\b"
    r"|\bunable\s+to\s+(?:provide|find|give|answer)\b",
    re.IGNORECASE,
)
_FIX_HEADING = re.compile(r"^[\s#*\d.)]*(?:the\s+)?fix\b", re.IGNORECASE | re.MULTILINE)
_STEP_LINE = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)
_MIN_STEPS = 2


def answer_outcome(answer: str) -> str:
    """Classify an answer as "refused", "hedged" or "answered".

    refused   says the manual does not cover it and gives no repair steps
    hedged    says the manual does not cover it but gives repair steps anyway
    answered  gives an answer without flagging any gap
    """
    if _SAYS_MANUAL_LACKS_IT.search(answer) is None:
        return "answered"
    heading = _FIX_HEADING.search(answer)
    gave_steps = heading is not None and len(_STEP_LINE.findall(answer[heading.end():])) >= _MIN_STEPS
    return "hedged" if gave_steps else "refused"



# --- uncertainty -------------------------------------------------------------

def wilson_interval(successes: int, total: int) -> tuple[float, float]:
    """95% Wilson score interval for a proportion."""
    if total == 0:
        return (0.0, 1.0)
    p = successes / total
    denom = 1 + _Z_95**2 / total
    centre = (p + _Z_95**2 / (2 * total)) / denom
    half = _Z_95 * math.sqrt(p * (1 - p) / total + _Z_95**2 / (4 * total**2)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))
