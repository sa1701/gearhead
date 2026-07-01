"""The Index search: find the manual chunks most relevant to a question.

Runs locally and free (Chroma matches on your machine). No Claude call here.
"""
from __future__ import annotations

import chromadb

from ..config import settings

COLLECTION = "manuals"


def search(query: str, n: int = 5, car: str | None = None) -> list[dict]:
    """Return the top-n most relevant manual chunks, with their source + page."""
    client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    col = client.get_or_create_collection(COLLECTION)

    res = col.query(
        query_texts=[query],
        n_results=n,
        where={"car": car} if car else None,
    )

    hits = []
    for doc, meta, dist in zip(
        res["documents"][0], res["metadatas"][0], res["distances"][0]
    ):
        hits.append(
            {
                "text": doc,
                "section": meta["section"],
                "page": meta["page"],
                "source_file": meta["source_file"],
                "distance": round(dist, 3),  # lower = closer match
            }
        )
    return hits
