"""Unit tests for which questions the answer-quality run uses and where it writes."""
from eval import grounding_eval
from eval.grounding_eval import ANSWERABLE_SAMPLE, _sample, results_name


def _gold(monkeypatch, answerable: int = 100, unanswerable: int = 5) -> None:
    rows = [{"id": f"a-{i}", "answerable": True} for i in range(answerable)]
    rows += [{"id": f"u-{i}", "answerable": False} for i in range(unanswerable)]
    monkeypatch.setattr(
        grounding_eval, "load_gold",
        lambda car, answerable=None: [r for r in rows if answerable is None or r["answerable"] is answerable],
    )


def _answerable_ids(rows: list[dict]) -> set[str]:
    return {r["id"] for r in rows if r["answerable"]}


def test_the_held_out_sample_shares_no_answerable_question_with_the_main_sample(monkeypatch):
    _gold(monkeypatch)

    main = _answerable_ids(_sample("car"))
    held_out = _answerable_ids(_sample("car", holdout=True))

    assert len(main) == len(held_out) == ANSWERABLE_SAMPLE
    assert not main & held_out


def test_the_held_out_sample_is_the_same_every_run(monkeypatch):
    _gold(monkeypatch)

    assert _sample("car", holdout=True) == _sample("car", holdout=True)


def test_the_held_out_sample_keeps_every_unanswerable_question(monkeypatch):
    _gold(monkeypatch, unanswerable=5)

    assert sum(not r["answerable"] for r in _sample("car", holdout=True)) == 5


def test_each_kind_of_run_writes_its_own_file():
    assert results_name("expand", True) == "grounding.jsonl"
    assert results_name("rerank", True) == "grounding_rerank.jsonl"
    assert results_name("rerank", False) == "grounding_rerank_nofixdb.jsonl"
    assert results_name("rerank", True, holdout=True) == "grounding_rerank_holdout.jsonl"
    assert results_name("rerank", True, holdout=True, tag="split") == "grounding_rerank_holdout_split.jsonl"
