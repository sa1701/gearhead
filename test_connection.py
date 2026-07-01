"""Quick check that your API key works and the brain is reachable.

Run from the project root:  python test_connection.py
"""
from src.ai.claude_provider import ClaudeProvider


def main() -> None:
    print("Connecting to Claude...")
    brain = ClaudeProvider()
    reply = brain.complete(
        system="You are GEARHEAD, a master car mechanic assistant.",
        messages=[
            {
                "role": "user",
                "content": "Reply with exactly: 'GEARHEAD online and ready to wrench.'",
            }
        ],
        max_tokens=50,
    )
    print("Claude says:", reply)
    print("\n[OK] Your key works and the brain is connected.")


if __name__ == "__main__":
    main()
