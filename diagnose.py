"""Ask GEARHEAD to diagnose a Patrol problem (one-shot, Step 2).

Run from the project root:
  python diagnose.py "the car shakes when I brake at high speed"
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

from src.brain.diagnose import diagnose_once

DEFAULT = (
    "When I brake at highway speed the steering wheel and pedal shudder, "
    "and the car pulls slightly to the left."
)


def main() -> None:
    problem = " ".join(sys.argv[1:]).strip() or DEFAULT
    print(f"PROBLEM: {problem}\n")
    print("Searching the manual + asking Claude...\n")
    result = diagnose_once(problem)
    print("Search terms it generated:")
    for q in result["queries"]:
        print(f"   • {q}")
    print("\n" + "=" * 60)
    print(result["answer"])
    print("=" * 60)
    print("Sources pulled:", ", ".join(f"{s} p.{p}" for s, p in result["sources"]))


if __name__ == "__main__":
    main()
