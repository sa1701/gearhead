"""Prove the Fix Database works: symptom -> matched curated entries (free, local)."""
import sys

sys.stdout.reconfigure(encoding="utf-8")

from src.library.fixdb import search_fixes

QUERIES = [
    "steering wheel shudders when braking at highway speed",
    "engine cranks but won't start in the morning",
    "A/C blows warm air",
    "clunk from rear when accelerating from a stop",
    "transmission slips when shifting into drive",
]

for q in QUERIES:
    print(f"\n=== {q}")
    for f in search_fixes(q, n=2, car="nissan-patrol-y61"):
        pages = ", ".join(f"p.{p}" for p in f.get("pages", []))
        print(f"  [{f['section']} {pages}] dist={f['distance']}")
        print(f"    SYMPTOM: {f['symptom']}")
        print(f"    CAUSES : {'; '.join(f.get('causes', []))[:160]}")
        if f.get("specs"):
            print(f"    SPECS  : {'; '.join(f['specs'])[:160]}")
