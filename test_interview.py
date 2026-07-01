"""Simulate a full diagnostic interview (Step 3) with scripted answers.

Run from the project root:  python test_interview.py
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

from src.brain.interview import run_interview

PROBLEM = "My Patrol shakes when I brake."

# Canned answers so the interview runs without live typing.
SCRIPTED = [
    "Mostly through the steering wheel and the pedal, worse at highway speed. "
    "It also pulls a little to the left when braking.",
    "The pedal feels firm, not spongy, and the brake fluid level looks fine.",
    "The pads still have a decent amount of material left, maybe half worn.",
]
_answers = iter(SCRIPTED)


def ask_fn(question: str) -> str:
    print(f"\n🔧 GEARHEAD asks:  {question}")
    try:
        ans = next(_answers)
    except StopIteration:
        ans = "Not sure."
    print(f"🧑 You:            {ans}")
    return ans


def on_event(kind: str, text: str) -> None:
    if kind in ("search", "cache"):
        print(f"   [{kind}] {text}")


print(f"PROBLEM: {PROBLEM}\n")
result = run_interview(PROBLEM, ask_fn=ask_fn, on_event=on_event)

print("\n" + "=" * 62)
print("FINAL DIAGNOSIS")
print("=" * 62)
print(result["diagnosis"])
print("=" * 62)
print(f"Questions asked: {result['questions_asked']}")
print(f"Tokens served FROM CACHE across the interview: {result['total_cache_read_tokens']}")
print("Sources:", ", ".join(f"{s} p.{p}" for s, p in result["sources"]))
