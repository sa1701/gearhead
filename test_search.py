"""Sanity check: do searches land on the right manual section?

Run from the project root:  python test_search.py
"""
import sys

# Manual PDFs contain typographic characters (e.g. the "fi" ligature) that the
# default Windows console encoding can't print. Force UTF-8 output.
sys.stdout.reconfigure(encoding="utf-8")

from src.library.search import search

QUERIES = [
    "brake disc rotor replacement",
    "engine cranks but will not start",
    "headlight wiring diagram",
    "automatic transmission fluid change",
    "airbag SRS warning light on",
]

for q in QUERIES:
    print(f"\n=== '{q}' ===")
    for r in search(q, n=3):
        snippet = " ".join(r["text"][:130].split())
        print(f"  [{r['section']} | p.{r['page']} | dist {r['distance']}]")
        print(f"     {snippet}...")
