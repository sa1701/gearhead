"""Unit tests for reading the question set."""
from eval.store import apply_page_corrections, rescore_with_corrections


def test_a_corrected_question_gets_its_new_gold_pages():
    rows = [{"id": "a-1", "pages": [41, 50]}, {"id": "a-2", "pages": [7]}]

    fixed = apply_page_corrections(rows, [{"id": "a-1", "pages": [70]}])

    assert fixed == [{"id": "a-1", "pages": [70]}, {"id": "a-2", "pages": [7]}]


def test_correcting_pages_leaves_the_original_rows_untouched():
    rows = [{"id": "a-1", "pages": [41, 50]}]

    apply_page_corrections(rows, [{"id": "a-1", "pages": [70]}])

    assert rows == [{"id": "a-1", "pages": [41, 50]}]


def test_no_corrections_means_no_change():
    rows = [{"id": "a-1", "pages": [41, 50]}]

    assert apply_page_corrections(rows, []) == rows


def test_a_stored_answer_is_scored_against_the_corrected_pages():
    stored = [{"id": "a-1", "answer": "x", "gold": {"section": "Brakes", "pages": [41, 50]}}]

    rescored = rescore_with_corrections(stored, [{"id": "a-1", "pages": [70]}])

    assert rescored == [{"id": "a-1", "answer": "x", "gold": {"section": "Brakes", "pages": [70]}}]
    assert stored[0]["gold"]["pages"] == [41, 50]


def test_a_stored_answer_to_an_unanswerable_question_is_left_alone():
    stored = [{"id": "u-01", "answer": "x"}]

    assert rescore_with_corrections(stored, [{"id": "a-1", "pages": [70]}]) == stored
