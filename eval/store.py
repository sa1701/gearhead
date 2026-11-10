"""Reading the gold set and checkpointing results as JSON lines."""
from __future__ import annotations

import json
from pathlib import Path

EVAL_DIR = Path(__file__).parent
GOLD_DIR = EVAL_DIR / "gold"
RESULTS_DIR = EVAL_DIR / "results"
CAR = "nissan-patrol-y61"


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def append_jsonl(path: Path, row: dict) -> None:
    """One row per question, written straight away so a crashed run can resume."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_results(path: Path) -> list[dict]:
    """Result rows, first row per id. A last line cut off by a killed run is skipped."""
    if not path.exists():
        return []
    rows: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows.setdefault(row["id"], row)
    return list(rows.values())


def load_gold(car: str = CAR, answerable: bool | None = None) -> list[dict]:
    rows = read_jsonl(GOLD_DIR / f"{car}.jsonl")
    if not rows:
        raise FileNotFoundError(f"No gold set for {car}. Run: python -m eval.build_gold merge")
    if answerable is None:
        return rows
    return [r for r in rows if r["answerable"] is answerable]


def pending(rows: list[dict], path: Path) -> list[dict]:
    """Rows not yet present in a results file (matched on id)."""
    done = {r["id"] for r in read_results(path)}
    return [r for r in rows if r["id"] not in done]
