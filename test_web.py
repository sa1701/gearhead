"""End-to-end smoke test of the web app (no browser needed).

Run from the project root:  python test_web.py
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient

from src.web.server import app

c = TestClient(app)

print("GET /        ->", c.get("/").status_code, "(serves the page)")
print("GET /api/cars ->", c.get("/api/cars").json())

print("\n--- starting a diagnosis ---")
start = c.post("/api/start", json={
    "problem": "brakes shudder through the wheel at highway speed and it pulls left",
    "car": "nissan-patrol-y61",
}).json()
sid = start["session_id"]
step = start
print(f"[{step['type']}] {step['text'][:110]}")

answers = [
    "Through the steering wheel and pedal, worse at speed, and it pulls left. Pedal feels firm.",
    "Pads look about half worn, fluid level is fine.",
    "Not sure about that one.",
]
i = 0
while step["type"] == "question":
    a = answers[i] if i < len(answers) else "Not sure."
    i += 1
    step = c.post("/api/answer", json={"session_id": sid, "answer": a}).json()
    print(f"[{step['type']}] {step['text'][:110]}")

print("\n--- DIAGNOSIS ---")
print("confidence:", step.get("confidence"))
print("sources:", [f"{s['section']} p.{s['page']}" for s in step["sources"]][:5])

print("\n--- illustrate ---")
ill = c.post("/api/illustrate", json={"session_id": sid}).json()
print("images:", ill["images"])
print("caption:", ill["captions"][:180])
print("\n[OK] Full web flow works.")
