"""The Intake: read manual PDFs, chunk them, store them in the local search DB.

Runs locally and free — no Claude/API calls here. Each chunk remembers which
manual section and page it came from, so answers can cite the source.
"""
from __future__ import annotations

import re

import chromadb
import fitz  # PyMuPDF

from ..config import settings

# Nissan factory manuals name sections by short codes. Map them to human names
# so citations read nicely ("Brakes p.142" instead of "br p.142").
SECTION_NAMES = {
    "gi": "General Information",
    "ma": "Maintenance",
    "em": "Engine Mechanical",
    "ec": "Engine Control System",
    "lc": "Engine Lubrication & Cooling",
    "fe": "Fuel & Emission",
    "at": "Automatic Transmission",
    "mt": "Manual Transmission",
    "tf": "Transfer Case (4x4)",
    "pd": "Propeller Shaft & Differential",
    "fa": "Front Axle & Suspension",
    "ra": "Rear Axle & Suspension",
    "fwd": "Front Wheel Drive",
    "br": "Brakes",
    "st": "Steering",
    "rs": "Restraint System (Airbags/Seatbelts)",
    "bt": "Battery",
    "cl": "Clutch",
    "el": "Electrical & Wiring",
    "ha": "Heater & Air Conditioning",
    "foldout": "Wiring Foldout Diagrams",
    "idx": "Index",
}

COLLECTION = "manuals"


def _chunk_text(text: str, max_chars: int = 900, overlap: int = 150) -> list[str]:
    """Squash whitespace and cut into overlapping windows for good retrieval."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < 40:  # skip near-empty pages
        return []
    if len(text) <= max_chars:
        return [text]
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start : start + max_chars])
        start += max_chars - overlap
    return chunks


def get_collection():
    client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    return client.get_or_create_collection(COLLECTION)


def ingest(subdir: str = "nissan-patrol-y61", reset: bool = True) -> int:
    """Read every PDF in manuals/<subdir>/ into the search DB. Returns chunk count."""
    manuals_path = settings.manuals_dir / subdir
    pdfs = sorted(manuals_path.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No PDFs found in {manuals_path}")

    client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    if reset:
        try:
            client.delete_collection(COLLECTION)
        except Exception:
            pass
    col = client.get_or_create_collection(COLLECTION)

    print(f"Ingesting {len(pdfs)} PDFs from {manuals_path}\n")
    total = 0
    for pdf in pdfs:
        code = pdf.stem.lower()
        section = SECTION_NAMES.get(code, code.upper())
        doc = fitz.open(pdf)
        ids, docs, metas = [], [], []
        for pno in range(len(doc)):
            for ci, chunk in enumerate(_chunk_text(doc[pno].get_text())):
                ids.append(f"{subdir}:{code}:{pno + 1}:{ci}")
                docs.append(chunk)
                metas.append(
                    {
                        "car": subdir,
                        "section_code": code,
                        "section": section,
                        "source_file": pdf.name,
                        "page": pno + 1,
                    }
                )
        doc.close()
        for i in range(0, len(docs), 200):  # add in batches
            col.add(
                ids=ids[i : i + 200],
                documents=docs[i : i + 200],
                metadatas=metas[i : i + 200],
            )
        total += len(docs)
        print(f"  {pdf.name:<16} {section:<38} {len(docs):>5} chunks")

    print(f"\nDone. {total} chunks indexed from {len(pdfs)} PDFs.")
    return total
