"""Render the manual pages for a brake problem and have Claude caption them.

Run from the project root:  python test_images.py
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

from src.library.images import illustrate
from src.library.search import search

PROBLEM = "front brake rotor and caliper service, pad replacement"

hits = search(PROBLEM, n=8, car="nissan-patrol-y61")
result = illustrate(PROBLEM, hits, subdir="nissan-patrol-y61", max_images=2)

print("Rendered manual pages:")
for p in result["images"]:
    print("  ", p)

print("\nClaude looked at them and says:\n")
print(result["captions"])
