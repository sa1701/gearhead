"""Unit tests for the aggregation in eval/report.py (no model, no files)."""
from eval.report import grounding_summary, merge_by_id, retrieval_summary, to_markdown
from eval.store import read_results


def _retrieval_row(raw_page: int | None, expanded_page: int | None) -> dict:
    return {
        "raw": {"section_rank": 1, "page_rank": raw_page},
        "expanded": {"section_rank": 2, "page_rank": expanded_page},
        "manual": {"section_rank": 1, "page_rank": 1},
    }


def test_retrieval_summary_reports_hit_rates_per_search_mode():
    summary = retrieval_summary([_retrieval_row(1, None), _retrieval_row(7, 4)])

    assert summary["raw"]["page_hit"] == {"@1": 0.5, "@3": 0.5, "@6": 0.5, "@20": 1.0}
    assert summary["expanded"]["page_hit"]["@6"] == 0.5
    assert summary["expanded"]["section_hit"]["@1"] == 0.0
    assert summary["manual"]["page_mrr"] == 1.0


def test_retrieval_summary_skips_a_search_mode_that_was_not_run():
    summary = retrieval_summary([_retrieval_row(1, 2)])

    assert "rerank" not in summary


def test_retrieval_summary_compares_rerank_against_the_plain_question():
    rows = [
        {**_retrieval_row(9, 9), "rerank": {"section_rank": 1, "page_rank": 2}},
        {**_retrieval_row(1, 1), "rerank": {"section_rank": 1, "page_rank": 1}},
    ]

    summary = retrieval_summary(rows)

    assert summary["rerank"]["page_hit"]["@6"] == 1.0
    assert summary["rerank_vs_raw_page@6"]["gained"] == 1
    assert summary["rerank_vs_raw_page@6"]["lost"] == 0


def test_merge_by_id_adds_fields_only_where_the_id_matches():
    base = [{"id": "a", "raw": 1}, {"id": "b", "raw": 2}]
    extra = [{"id": "b", "rerank": 9, "seconds": 3}]

    assert merge_by_id(base, extra, field="rerank") == [{"id": "a", "raw": 1}, {"id": "b", "raw": 2, "rerank": 9}]


ANSWERED_WITH_GOLD = {
    "answerable": True,
    "answer": "### The Fix\n1. Replace pads [Brakes, p.30].\n2. Bleed the system [Brakes, p.99].",
    "context": [["Brakes", 30], ["Brakes", 4]],
    "fix_context": [],
    "gold": {"section": "Brakes", "pages": [30]},
    "seconds": 100.0,
}
REFUSED_UNANSWERABLE = {
    "answerable": False,
    "answer": "The excerpts do not contain anything about CarPlay.",
    "context": [["Electrical & Wiring", 184]],
    "fix_context": [],
    "seconds": 50.0,
}
HEDGED_UNANSWERABLE = {
    "answerable": False,
    "answer": "### The Fix\n1. Reset it.\n2. Drive.\n\nNote: the excerpts do not contain this.",
    "context": [["Brakes", 41]],
    "fix_context": [["Brakes", 49]],
    "seconds": 150.0,
}


def test_grounding_summary_counts_only_citations_that_were_in_context():
    summary = grounding_summary([ANSWERED_WITH_GOLD])

    assert summary["citation_validity"]["rate"] == 0.5
    assert summary["citation_validity"]["n"] == 2
    assert summary["attempts_with_a_bad_citation"]["rate"] == 1.0


def test_grounding_summary_checks_the_gold_page_reached_and_was_cited():
    summary = grounding_summary([ANSWERED_WITH_GOLD])

    assert summary["gold_page_in_context"]["rate"] == 1.0
    assert summary["gold_page_cited"]["rate"] == 1.0


def test_grounding_summary_separates_clean_refusals_from_hedged_answers():
    summary = grounding_summary([ANSWERED_WITH_GOLD, REFUSED_UNANSWERABLE, HEDGED_UNANSWERABLE])

    assert summary["unanswerable_refused"]["rate"] == 0.5
    assert summary["unanswerable_hedged"]["rate"] == 0.5
    assert summary["unanswerable_answered"]["rate"] == 0.0
    assert summary["answerable_refused"]["rate"] == 0.0
    assert summary["median_seconds"] == 100.0


def test_gold_page_from_the_fix_db_block_is_not_counted_as_retrieved():
    row = {**ANSWERED_WITH_GOLD, "context": [["Brakes", 4]], "fix_context": [["Brakes", 30]]}

    summary = grounding_summary([row])

    assert summary["gold_page_retrieved"]["rate"] == 0.0
    assert summary["gold_page_in_context"]["rate"] == 1.0


def test_read_results_skips_a_cut_off_last_line_and_repeated_ids(tmp_path):
    path = tmp_path / "run.jsonl"
    path.write_text('{"id": "a", "v": 1}\n{"id": "a", "v": 2}\n{"id": "b", "v": 3}\n{"id": "c", "v', encoding="utf-8")

    assert read_results(path) == [{"id": "a", "v": 1}, {"id": "b", "v": 3}]


def test_grounding_summary_of_no_rows_is_empty():
    assert grounding_summary([]) == {}


def test_markdown_report_has_a_row_per_search_mode():
    report = to_markdown({"retrieval": retrieval_summary([_retrieval_row(1, 2)])})

    assert "| raw | 100% |" in report
    assert "| expanded | 0% |" in report
