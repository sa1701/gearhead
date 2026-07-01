"""Dry-run for the Fix Database: how many pages qualify, and what would it cost?"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

from src.library.fixdb import _batches, _page_records

records = _page_records("nissan-patrol-y61")
batches = _batches(records)

by_sec: dict[str, int] = {}
chars = 0
for r in records:
    by_sec[r["section"]] = by_sec.get(r["section"], 0) + 1
    chars += len(r["text"])

for sec, n in sorted(by_sec.items(), key=lambda kv: -kv[1]):
    print(f"  {sec:<38} {n:>4} pages")

in_tok = chars // 4 + len(batches) * 450  # text + system prompt per batch
out_tok = int(in_tok * 0.30)              # compact JSON back
cost = in_tok / 1e6 * 5 + out_tok / 1e6 * 25
print(f"\nTOTAL: {len(records)} diagnostic pages -> {len(batches)} Claude batches")
print(f"Estimated: ~{in_tok:,} tokens in / ~{out_tok:,} out  ≈ ${cost:.2f} (Opus 4.8)")
