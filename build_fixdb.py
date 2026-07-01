"""Build the Fix Database: one-time Claude pass over the manual's diagnostic pages.

  python build_fixdb.py          -> full build (all sections)
  python build_fixdb.py 2        -> smoke test: first 2 batches only
"""
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from src.library.fixdb import build_fixdb

from src.config import settings

limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
t0 = time.time()
print(f"Extraction model: {settings.extract_model}")
stats = build_fixdb("nissan-patrol-y61", limit_batches=limit)
mins = (time.time() - t0) / 60
rate_in, rate_out = (1, 5) if "haiku" in settings.extract_model else (5, 25)
cost = stats["usage"]["input"] / 1e6 * rate_in + stats["usage"]["output"] / 1e6 * rate_out
print(f"\nDONE in {mins:.1f} min — {stats['entries']} fix entries from {stats['batches']} batches")
print(f"Tokens: {stats['usage']['input']:,} in / {stats['usage']['output']:,} out  ≈ ${cost:.2f}")
print(f"Saved + indexed: {stats['file']}")
