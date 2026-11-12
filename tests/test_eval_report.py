"""Unit tests for the aggregation in eval/report.py (no model, no files)."""
import pytest

from eval.report import (
    followup_summary,
    gate_summary,
    grounding_summary,
    merge_by_id,
    retrieval_summary,
    passing_summary,
    subject_summary,
    vehicle_summary,
    to_markdown,
    vague_summary,
)
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


def test_an_answer_stopped_by_the_gate_counts_as_a_refusal():
    gated = {"answerable": False, "gated": True, "answer": "I could not match this to a page.",
             "context": [], "fix_context": [], "seconds": 2.0}

    summary = grounding_summary([gated])

    assert summary["unanswerable_refused"]["rate"] == 1.0


GATE_ROWS = [
    {"id": "u-01", "answerable": False, "blocked": True},
    {"id": "u-02", "answerable": False, "blocked": False},
    {"id": "u-03", "answerable": False, "blocked": False},
    {"id": "a-01", "answerable": True, "blocked": False},
    {"id": "a-02", "answerable": True, "blocked": True},
]


def test_gate_summary_reports_what_was_blocked_on_each_side():
    summary = gate_summary(GATE_ROWS, model_rows=[])

    assert summary["unanswerable_blocked"]["rate"] == pytest.approx(1 / 3, abs=0.001)
    assert summary["unanswerable_blocked"]["n"] == 3
    assert summary["answerable_blocked"]["rate"] == 0.5
    assert "given_steps_before" not in summary


def test_gate_summary_combines_the_gate_with_what_the_model_did_on_its_own():
    model_rows = [
        {**HEDGED_UNANSWERABLE, "id": "u-01"},   # gate blocks it
        {**HEDGED_UNANSWERABLE, "id": "u-02"},   # gate misses it and the model gives steps
        {**REFUSED_UNANSWERABLE, "id": "u-03"},  # gate misses it but the model refuses
    ]

    summary = gate_summary(GATE_ROWS, model_rows)

    assert summary["given_steps_before"]["rate"] == pytest.approx(2 / 3, abs=0.001)
    assert summary["given_steps_after"]["rate"] == pytest.approx(1 / 3, abs=0.001)
    assert summary["given_steps_after"]["n"] == 3


VAGUE_ROWS = [
    {"id": "v-01", "confirmed": False, "blocked": False,
     "raw": {"rank": 1, "share": 0.5}, "rerank": {"rank": 3, "share": 0.5}},
    {"id": "v-02", "confirmed": False, "blocked": True,
     "raw": {"rank": None, "share": 0.0}, "rerank": {"rank": 1, "share": 1.0}},
]


def test_vague_summary_reports_right_system_rates_per_search_mode():
    summary = vague_summary(VAGUE_ROWS)

    assert summary["raw"]["first_chunk_right"]["rate"] == 0.5
    assert summary["raw"]["any_chunk_right"]["rate"] == 0.5
    assert summary["rerank"]["first_chunk_right"]["rate"] == 0.5
    assert summary["rerank"]["any_chunk_right"]["rate"] == 1.0
    assert summary["rerank"]["mean_share_right"] == 0.75


def test_vague_summary_reports_the_gate_and_whether_labels_are_confirmed():
    summary = vague_summary(VAGUE_ROWS)

    assert summary["asked_for_detail"]["rate"] == 0.5
    assert summary["labels_confirmed"] == 0
    assert summary["n"] == 2


def test_vague_summary_of_no_rows_is_empty():
    assert vague_summary([]) == {}


FOLLOWUP_ROWS = [
    {"id": "v-01", "kind": "vague", "blocked_first": False, "blocked_final": False, "rank": 1},
    {"id": "v-02", "kind": "vague", "blocked_first": True, "blocked_final": False, "rank": None},
    {"id": "v-03", "kind": "vague", "blocked_first": True, "blocked_final": False, "rank": 2},
    {"id": "v-04", "kind": "vague", "blocked_first": True, "blocked_final": True, "rank": None},
    {"id": "u-01", "kind": "unanswerable", "blocked_first": True, "blocked_final": True, "rank": None},
    {"id": "u-02", "kind": "unanswerable", "blocked_first": True, "blocked_final": False, "rank": None},
]


def test_followup_summary_splits_vague_complaints_by_when_they_got_through():
    summary = followup_summary(FOLLOWUP_ROWS)

    assert summary["vague_through_at_once"]["rate"] == 0.25
    assert summary["vague_through_after_detail"]["rate"] == 0.5
    assert summary["vague_declined"]["rate"] == 0.25


def test_followup_summary_checks_the_right_system_only_for_complaints_that_got_through():
    summary = followup_summary(FOLLOWUP_ROWS)

    assert summary["vague_through_with_right_system"]["n"] == 3
    assert summary["vague_through_with_right_system"]["rate"] == pytest.approx(2 / 3, abs=0.001)


def test_followup_summary_reports_unanswerable_questions_still_declined_after_detail():
    summary = followup_summary(FOLLOWUP_ROWS)

    assert summary["unanswerable_declined"]["rate"] == 0.5
    assert summary["unanswerable_declined"]["n"] == 2


def test_followup_summary_of_no_rows_is_empty():
    assert followup_summary([]) == {}


def test_grounding_summary_of_no_rows_is_empty():
    assert grounding_summary([]) == {}


def test_markdown_report_has_a_row_per_search_mode():
    report = to_markdown({"retrieval": retrieval_summary([_retrieval_row(1, 2)])})

    assert "| raw | 100% |" in report
    assert "| expanded | 0% |" in report


SUBJECT_ROWS = [
    {"id": "a-1", "kind": "answerable", "blocked_by_score": False, "blocked": False},
    {"id": "a-2", "kind": "answerable", "blocked_by_score": True, "blocked": False},
    {"id": "v-1", "kind": "vague", "blocked_by_score": True, "blocked": False},
    {"id": "v-2", "kind": "vague", "blocked_by_score": True, "blocked": True},
    {"id": "u-1", "kind": "unanswerable", "blocked_by_score": True, "blocked": True},
    {"id": "u-2", "kind": "unanswerable", "blocked_by_score": True, "blocked": False},
    {"id": "u-3", "kind": "unanswerable", "blocked_by_score": False, "blocked": False},
]


def test_subject_summary_reports_each_kind_before_and_after_the_subject_check():
    summary = subject_summary(SUBJECT_ROWS)

    assert summary["answerable"]["score_only"]["rate"] == 0.5
    assert summary["answerable"]["with_subject_check"]["rate"] == 0.0
    assert summary["vague"]["score_only"]["rate"] == 1.0
    assert summary["vague"]["with_subject_check"]["rate"] == 0.5
    assert summary["unanswerable"]["score_only"]["successes"] == 2
    assert summary["unanswerable"]["with_subject_check"]["successes"] == 1
    assert summary["unanswerable"]["with_subject_check"]["n"] == 3


def test_subject_summary_of_no_rows_is_empty():
    assert subject_summary([]) == {}


def test_report_shows_the_subject_check_table():
    report = to_markdown({"subject": subject_summary(SUBJECT_ROWS)})

    assert "## Subject check" in report
    assert "| No answer in manual | 67% (2 of 3) | 33% (1 of 3) |" in report


def test_report_shows_the_held_out_subject_check_under_its_own_heading():
    report = to_markdown({"subject_holdout": subject_summary(SUBJECT_ROWS)})

    assert "## Subject check on held-out questions" in report
    assert "| Vague complaint | 100% (2 of 2) | 50% (1 of 2) |" in report


VEHICLE_ROWS = [
    {"id": "u-1", "set": "holdout", "kind": "unanswerable", "named": None},
    {"id": "u-2", "set": "holdout", "kind": "unanswerable", "named": "civic"},
    {"id": "u-3", "set": "holdout", "kind": "unanswerable", "named": "hilux"},
    {"id": "a-1", "set": "holdout", "kind": "answerable", "named": None},
    {"id": "a-2", "set": "holdout", "kind": "answerable", "named": "golf"},
]
EARLIER = [
    {"id": "u-1", "blocked": True}, {"id": "u-2", "blocked": False}, {"id": "u-3", "blocked": True},
    {"id": "a-1", "blocked": False}, {"id": "a-2", "blocked": False},
]


def test_vehicle_summary_adds_the_check_on_top_of_the_earlier_decisions():
    summary = vehicle_summary(VEHICLE_ROWS, EARLIER)

    assert summary["unanswerable"]["before"]["successes"] == 2
    assert summary["unanswerable"]["named_another_vehicle"]["successes"] == 2
    assert summary["unanswerable"]["with_vehicle_check"]["successes"] == 3
    assert summary["answerable"]["with_vehicle_check"]["successes"] == 1


def test_vehicle_summary_without_earlier_decisions_counts_only_the_check():
    summary = vehicle_summary(VEHICLE_ROWS, [])

    assert "before" not in summary["unanswerable"]
    assert summary["unanswerable"]["with_vehicle_check"]["successes"] == 2


def test_vehicle_summary_of_no_rows_is_empty():
    assert vehicle_summary([], EARLIER) == {}


def test_report_marks_a_set_with_no_earlier_run():
    report = to_markdown({"vehicles_vehicles": vehicle_summary(VEHICLE_ROWS, [])})

    assert "## Other-vehicle check: questions written after the name list was frozen" in report
    assert "| No answer in manual | not run | 67% (2 of 3) | 67% (2 of 3) |" in report


PASSING_ROWS = [
    {"id": "p-1", "group": "patrol_named_other_mentioned", "named_before": "hilux", "named": None, "declined": False},
    {"id": "p-2", "group": "patrol_named_other_mentioned", "named_before": "prado", "named": None, "declined": True},
    {"id": "p-3", "group": "other_vehicle_only", "named_before": "civic", "named": "civic", "declined": True},
    {"id": "p-4", "group": "other_vehicle_only", "named_before": None, "named": None, "declined": False},
]


def test_passing_summary_counts_each_stage_per_group():
    summary = passing_summary(PASSING_ROWS)

    named = summary["patrol_named_other_mentioned"]
    assert named["vehicle_check_before"]["successes"] == 2
    assert named["vehicle_check_now"]["successes"] == 0
    assert named["whole_gate"]["successes"] == 1
    assert named["whole_gate"]["n"] == 2
    assert summary["other_vehicle_only"]["vehicle_check_now"]["successes"] == 1


def test_passing_summary_leaves_out_groups_with_no_questions():
    assert "patrol_unnamed_other_mentioned" not in passing_summary(PASSING_ROWS)


def test_passing_summary_of_no_rows_is_empty():
    assert passing_summary([]) == {}


def test_report_shows_the_passing_mention_table():
    report = to_markdown({"passing": passing_summary(PASSING_ROWS)})

    assert "## Questions that mention two vehicles" in report
    assert "| About this car, names it, mentions another | should go ahead | 100% (2 of 2) | 0% (0 of 2) | 50% (1 of 2) |" in report
