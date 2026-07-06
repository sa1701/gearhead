"""The Fix Database: a one-time offline pass that turns the manual's messy
diagnostic pages into clean, structured symptom -> cause -> fix entries.

Build once (costs a few dollars of Claude), then every diagnosis gets a free,
instant, curated knowledge layer on top of raw RAG chunks.

  build_fixdb(subdir)   -> extract entries with Claude, save JSON + index in Chroma
  search_fixes(query)   -> semantic match of a user symptom against the entries
"""
from __future__ import annotations

import json
import re

import chromadb
import fitz  # PyMuPDF

from ..config import settings
from .ingest import SECTION_NAMES

FIX_COLLECTION = "fixes"
FIXES_DIR = settings.manuals_dir.parent / "fixes"

# A page is "diagnostic" if it links symptoms to causes/actions — trouble
# diagnosis charts, symptom matrices, DTC procedures. Pure how-to-remove-a-bolt
# pages are skipped (RAG still covers those).
_DIAG_KEYS = (
    "trouble diagnos", "symptom", "probable cause", "diagnostic procedure",
    "diagnosis chart", "malfunction", "does not", "noise",
)

# Sections that never contain symptom->fix knowledge.
_SKIP_SECTIONS = {"idx", "foldout", "gi"}

_EXTRACT_SYSTEM = """You read pages from a factory workshop manual and extract \
DIAGNOSTIC knowledge as structured JSON.

Extract every distinct symptom -> cause -> fix pattern the pages actually contain
(trouble-diagnosis charts, symptom tables, DTC procedures, noise charts).

Output ONLY a JSON array (no prose, no code fences). Each element:
{
  "symptom": "one plain-English sentence describing the complaint as an owner would say it",
  "system": "the vehicle system (e.g. Brakes)",
  "causes": ["likely causes, most likely first"],
  "checks": ["how to confirm, in order"],
  "fix": ["repair actions"],
  "specs": ["name = value unit, for any torque/measurement/clearance tied to this fix"],
  "pages": [page numbers the info came from]
}

Rules:
- Use ONLY what the pages say. No outside knowledge, no invented values.
- One entry per distinct symptom. Merge duplicate rows about the same complaint.
- Skip content that has no symptom/complaint/fault-code linkage.
- If the pages contain nothing diagnostic, output []."""


def _page_records(subdir: str) -> list[dict]:
    """All diagnostic-relevant pages of every section PDF, with their text."""
    records = []
    for pdf in sorted((settings.manuals_dir / subdir).glob("*.pdf")):
        code = pdf.stem.lower()
        if code in _SKIP_SECTIONS:
            continue
        doc = fitz.open(pdf)
        for pno in range(len(doc)):
            text = re.sub(r"\s+", " ", doc[pno].get_text()).strip()
            low = text.lower()
            if text.count("....") > 5:  # table-of-contents page (leader dots)
                continue
            if len(text) >= 80 and any(k in low for k in _DIAG_KEYS):
                records.append(
                    {
                        "section_code": code,
                        "section": SECTION_NAMES.get(code, code.upper()),
                        "source_file": pdf.name,
                        "page": pno + 1,
                        "text": text,
                    }
                )
        doc.close()
    return records


def _batches(records: list[dict], max_chars: int = 14000) -> list[list[dict]]:
    """Group same-section pages into Claude-sized batches (keeps charts together)."""
    out, cur, size = [], [], 0
    for r in records:
        if cur and (size + len(r["text"]) > max_chars or r["section_code"] != cur[0]["section_code"]):
            out.append(cur)
            cur, size = [], 0
        cur.append(r)
        size += len(r["text"])
    if cur:
        out.append(cur)
    return out


def _parse_entries(reply: str) -> list[dict]:
    """Pull the JSON array out of Claude's reply, tolerating stray text/fences."""
    cleaned = re.sub(r"```(?:json)?", "", reply).strip()
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return []
    return [e for e in data if isinstance(e, dict) and e.get("symptom") and e.get("causes")]


def build_fixdb(subdir: str = "nissan-patrol-y61", limit_batches: int | None = None) -> dict:
    """The offline extraction pass. Returns {'entries', 'batches', 'usage'} stats.

    Checkpoints after EVERY batch (fixes/<subdir>.progress.json), so a crash or
    an empty credit balance never loses paid work — just re-run to resume.
    """
    from ..ai import get_provider

    records = _page_records(subdir)
    batches = _batches(records)
    if limit_batches:
        batches = batches[:limit_batches]

    FIXES_DIR.mkdir(exist_ok=True)
    out_file = FIXES_DIR / f"{subdir}.json"
    ckpt_file = FIXES_DIR / f"{subdir}.progress.json"

    entries: list[dict] = []
    done: set[str] = set()
    usage = {"input": 0, "output": 0}
    if ckpt_file.exists():
        state = json.loads(ckpt_file.read_text(encoding="utf-8"))
        entries, done, usage = state["entries"], set(state["done"]), state["usage"]
        print(f"  resuming: {len(done)} batches already extracted ({len(entries)} entries)")

    # Extraction is mechanical chart-to-JSON work — Haiku does it at 1/5th the
    # price. The diagnosis brain stays on the main (Opus) model untouched.
    brain = get_provider(model=settings.extract_model)
    for i, batch in enumerate(batches, 1):
        key = f"{batch[0]['section_code']}:{batch[0]['page']}-{batch[-1]['page']}"
        if key in done:
            continue
        body = "\n\n".join(
            f"[Section: {r['section']} | Page: {r['page']}]\n{r['text']}" for r in batch
        )
        reply = brain.complete(
            system=_EXTRACT_SYSTEM,
            messages=[{"role": "user", "content": f"MANUAL PAGES:\n\n{body}"}],
            max_tokens=6000,
            thinking=False,
        )
        got = _parse_entries(reply)
        for e in got:
            e["section"] = batch[0]["section"]
            e["section_code"] = batch[0]["section_code"]
            e["source_file"] = batch[0]["source_file"]
        entries.extend(got)
        done.add(key)
        u = brain.last_usage
        if u is not None:
            usage["input"] += u.input_tokens
            usage["output"] += u.output_tokens
        ckpt_file.write_text(
            json.dumps({"entries": entries, "done": sorted(done), "usage": usage},
                       ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  batch {i}/{len(batches)} [{batch[0]['section']}] "
              f"pages {batch[0]['page']}-{batch[-1]['page']} -> {len(got)} entries", flush=True)

    out_file.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    ckpt_file.unlink(missing_ok=True)
    index_fixdb(subdir)
    return {"entries": len(entries), "batches": len(batches), "usage": usage, "file": str(out_file)}


def index_fixdb(subdir: str = "nissan-patrol-y61") -> int:
    """(Re)index the saved entries into the local Chroma 'fixes' collection."""
    entries = json.loads((FIXES_DIR / f"{subdir}.json").read_text(encoding="utf-8"))
    client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    try:
        client.delete_collection(FIX_COLLECTION)
    except Exception:
        pass
    col = client.get_or_create_collection(FIX_COLLECTION)
    ids, docs, metas = [], [], []
    for i, e in enumerate(entries):
        ids.append(f"{subdir}:fix:{i}")
        docs.append(f"{e['symptom']} | causes: {'; '.join(e.get('causes', []))}")
        metas.append({"car": subdir, "section": e.get("section", ""), "entry": json.dumps(e, ensure_ascii=False)})
    for i in range(0, len(docs), 200):
        col.add(ids=ids[i : i + 200], documents=docs[i : i + 200], metadatas=metas[i : i + 200])
    return len(docs)


def search_fixes(query: str, n: int = 4, car: str | None = None) -> list[dict]:
    """Semantic match of a symptom against the Fix DB. Empty list if not built."""
    client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    try:
        col = client.get_collection(FIX_COLLECTION)
    except Exception:
        return []
    if col.count() == 0:
        return []
    res = col.query(query_texts=[query], n_results=min(n, col.count()),
                    where={"car": car} if car else None)
    hits = []
    for meta, dist in zip(res["metadatas"][0], res["distances"][0]):
        entry = json.loads(meta["entry"])
        entry["distance"] = round(dist, 3)
        hits.append(entry)
    return hits
