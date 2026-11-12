"""Build the gold question set from the Fix DB.

Two stages, because the rewording is done by a different model than the one
under test (so the model never gets to search for its own phrasing):

  python -m eval.build_gold candidates   # sample Fix DB -> fixes/_eval_candidates.json
  (reword each candidate as a car owner would say it -> fixes/_eval_paraphrases.json)
  python -m eval.build_gold merge        # -> eval/gold/<car>.jsonl

The gold file holds only reworded questions plus section/page labels. The
manual wording stays in fixes/ (git-ignored) and is looked up by hash.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

import chromadb

from src.config import settings
from src.library.fixdb import FIXES_DIR
from src.library.ingest import COLLECTION

CAR = "nissan-patrol-y61"
SEED = 316
MIN_LABEL_OVERLAP = 0.5   # share of symptom words that must appear on a gold page
MAX_PER_PAGE_GROUP = 3    # one symptom chart must not dominate the set
MAX_PER_SECTION = 40
GOLD_DIR = Path(__file__).parent / "gold"
CANDIDATES = FIXES_DIR / "_eval_candidates.json"
PARAPHRASES = FIXES_DIR / "_eval_paraphrases.json"


def symptom_hash(symptom: str) -> str:
    return hashlib.sha1(symptom.strip().lower().encode("utf-8")).hexdigest()[:10]


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9/]{4,}", text.lower()))


def load_fixes(car: str = CAR) -> list[dict]:
    return json.loads((FIXES_DIR / f"{car}.json").read_text(encoding="utf-8"))


def _page_texts(car: str) -> dict[tuple[str, int], str]:
    """Indexed manual text per (source_file, page), to sanity-check labels."""
    col = chromadb.PersistentClient(path=str(settings.chroma_dir)).get_collection(COLLECTION)
    got = col.get(where={"car": car}, include=["documents", "metadatas"])
    pages: dict[tuple[str, int], str] = defaultdict(str)
    for doc, meta in zip(got["documents"], got["metadatas"]):
        pages[(meta["source_file"], meta["page"])] += " " + doc
    return pages


def label_overlap(entry: dict, pages: dict[tuple[str, int], str]) -> float:
    """Best share of the symptom words found on any one of its gold pages."""
    words = _words(entry["symptom"])
    if not words:
        return 0.0
    return max(
        (len(words & _words(pages.get((entry["source_file"], p), ""))) / len(words)
         for p in entry.get("pages") or []),
        default=0.0,
    )


def select_candidates(fixes: list[dict], pages: dict[tuple[str, int], str]) -> list[dict]:
    """De-duplicate, drop weak labels, then cap per page group and per section."""
    rng = random.Random(SEED)
    seen: set[str] = set()
    usable = []
    for entry in fixes:
        key = symptom_hash(entry["symptom"])
        if key in seen or not entry.get("pages"):
            continue
        seen.add(key)
        if label_overlap(entry, pages) >= MIN_LABEL_OVERLAP:
            usable.append({**entry, "fix_hash": key})

    rng.shuffle(usable)
    per_group: dict[tuple, int] = defaultdict(int)
    per_section: dict[str, int] = defaultdict(int)
    picked = []
    for entry in usable:
        group = (entry["source_file"], tuple(sorted(entry["pages"])))
        section = entry["section_code"]
        if per_group[group] >= MAX_PER_PAGE_GROUP or per_section[section] >= MAX_PER_SECTION:
            continue
        per_group[group] += 1
        per_section[section] += 1
        picked.append(entry)
    return sorted(picked, key=lambda e: (e["section_code"], e["fix_hash"]))


def write_candidates() -> None:
    picked = select_candidates(load_fixes(), _page_texts(CAR))
    slim = [
        {"fix_hash": e["fix_hash"], "system": e["section"], "symptom": e["symptom"],
         "causes": e["causes"][:2]}
        for e in picked
    ]
    CANDIDATES.write_text(json.dumps(slim, indent=1, ensure_ascii=False), encoding="utf-8")
    by_section: dict[str, int] = defaultdict(int)
    for e in picked:
        by_section[e["section_code"]] += 1
    print(f"{len(picked)} candidates -> {CANDIDATES}")
    print("per section:", dict(sorted(by_section.items())))


def merge() -> None:
    """Join reworded questions back onto their labels and add the unanswerable set."""
    by_hash = {symptom_hash(e["symptom"]): e for e in load_fixes()}
    reworded = json.loads(PARAPHRASES.read_text(encoding="utf-8"))
    rows, skipped = [], 0
    for item in reworded:
        entry = by_hash.get(item["fix_hash"])
        question = (item.get("question") or "").strip()
        if entry is None or not question:
            skipped += 1  # the rewording model marked it "not a real complaint"
            continue
        rows.append({
            "id": f"a-{item['fix_hash']}",
            "answerable": True,
            "question": question,
            "section_code": entry["section_code"],
            "source_file": entry["source_file"],
            "pages": sorted(entry["pages"]),
            "fix_hash": item["fix_hash"],
        })
    unanswerable = json.loads((GOLD_DIR / "unanswerable.json").read_text(encoding="utf-8"))
    rows += [
        {"id": f"u-{i:02d}", "answerable": False, "question": u["question"], "why": u["why"]}
        for i, u in enumerate(unanswerable, 1)
    ]
    out = GOLD_DIR / f"{CAR}.jsonl"
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    answerable = sum(r["answerable"] for r in rows)
    print(f"{answerable} answerable + {len(rows) - answerable} unanswerable -> {out}"
          f"  ({skipped} candidates skipped)")


def write_review_sheet(sample_size: int = 30) -> None:
    """A hand-check sheet: is the gold page really where this fault is covered?"""
    gold = [json.loads(line) for line in
            (GOLD_DIR / f"{CAR}.jsonl").read_text(encoding="utf-8").splitlines()]
    answerable = [r for r in gold if r["answerable"]]
    picked = random.Random(SEED).sample(answerable, min(sample_size, len(answerable)))
    manual_wording = {symptom_hash(e["symptom"]): e["symptom"] for e in load_fixes()}
    lines = ["# Gold label hand-check", "",
             "Open the PDF at the page given. Tick OK if that page covers the fault, "
             "otherwise write the right page.", ""]
    for i, row in enumerate(picked, 1):
        pages = ", ".join(str(p) for p in row["pages"])
        lines += [
            f"## {i}. {row['id']}",
            f"- Question: {row['question']}",
            f"- Manual wording: {manual_wording[row['fix_hash']]}",
            f"- Gold: manuals/{CAR}/{row['source_file']} page {pages}",
            "- [ ] OK    - [ ] Wrong, should be page: ____", "",
        ]
    out = GOLD_DIR.parent / "gold_review.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(picked)} labels to check -> {out}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    stage = sys.argv[1] if len(sys.argv) > 1 else ""
    if stage == "candidates":
        write_candidates()
    elif stage == "merge":
        merge()
    elif stage == "review":
        write_review_sheet()
    else:
        raise SystemExit("usage: python -m eval.build_gold candidates|merge|review")
