"""Unit tests for the pure scoring functions in eval/metrics.py."""
import pytest

from eval.metrics import (
    citation_is_valid,
    first_hit_rank,
    hit_rate,
    mean_reciprocal_rank,
    normalise_section,
    paired_change,
    parse_citations,
    wilson_interval,
)


def _hit(source_file: str, page: int) -> dict:
    return {"source_file": source_file, "page": page}


HITS = [_hit("el.pdf", 12), _hit("br.pdf", 4), _hit("br.pdf", 30), _hit("at.pdf", 60)]


def test_first_hit_rank_matches_section_when_no_pages_given():
    assert first_hit_rank(HITS, "br.pdf") == 2


def test_first_hit_rank_needs_a_gold_page_when_pages_given():
    assert first_hit_rank(HITS, "br.pdf", pages=[30, 31]) == 3


def test_first_hit_rank_ignores_right_page_number_in_wrong_section():
    assert first_hit_rank(HITS, "br.pdf", pages=[60]) is None


def test_first_hit_rank_is_none_for_empty_hits():
    assert first_hit_rank([], "br.pdf") is None


def test_hit_rate_counts_ranks_within_k():
    assert hit_rate([1, 3, None, 7], k=3) == 0.5


def test_hit_rate_of_no_questions_is_zero():
    assert hit_rate([], k=5) == 0.0


def test_mean_reciprocal_rank_treats_misses_as_zero():
    assert mean_reciprocal_rank([1, 2, None, 4]) == pytest.approx((1 + 0.5 + 0 + 0.25) / 4)


def test_normalise_section_drops_case_punctuation_and_label():
    assert normalise_section(" Section: Transfer Case (4x4) ") == "transfer case 4x4"


def test_parse_citations_reads_the_prompted_format():
    assert parse_citations("Replace the pads [Brakes, p.30].") == [("brakes", 30)]


def test_parse_citations_expands_page_ranges_and_lists():
    text = "See [Automatic Transmission, p.60-62] and [Brakes, pp. 4, 21]."
    assert parse_citations(text) == [
        ("automatic transmission", 60), ("automatic transmission", 61),
        ("automatic transmission", 62), ("brakes", 4), ("brakes", 21),
    ]


def test_parse_citations_reads_the_context_header_format():
    assert parse_citations("[Section: Brakes | Page: 30]") == [("brakes", 30)]


def test_parse_citations_splits_two_sources_in_one_bracket():
    assert parse_citations("[Brakes, p.30; Steering, p.4]") == [("brakes", 30), ("steering", 4)]


def test_parse_citations_ignores_brackets_without_a_page():
    assert parse_citations("Check the fuse [see note] and the relay [1].") == []


def test_citation_is_valid_when_section_and_page_were_in_context():
    assert citation_is_valid(("brakes", 30), {("brakes", 30), ("steering", 4)})


def test_citation_is_invalid_when_page_was_not_in_context():
    assert not citation_is_valid(("brakes", 31), {("brakes", 30)})


def test_citation_is_invalid_when_page_belongs_to_another_section():
    assert not citation_is_valid(("steering", 30), {("brakes", 30)})


def test_citation_accepts_a_shortened_section_name():
    allowed = {("restraint system airbags seatbelts", 12)}
    assert citation_is_valid(("restraint system", 12), allowed)


def test_wilson_interval_brackets_the_observed_rate():
    low, high = wilson_interval(successes=80, total=100)
    assert low < 0.8 < high
    assert low == pytest.approx(0.711, abs=0.002)
    assert high == pytest.approx(0.867, abs=0.002)


def test_paired_change_counts_questions_gained_and_lost_at_k():
    before = [1, 9, None, 2, 8]
    after = [1, 3, 5, 9, None]

    change = paired_change(before, after, k=6)

    assert (change["gained"], change["lost"]) == (2, 1)


def test_paired_change_p_value_is_the_exact_two_sided_sign_test():
    before = [None] * 10
    after = [1] * 9 + [None]

    change = paired_change(before, after, k=6)

    assert (change["gained"], change["lost"]) == (9, 0)
    assert change["p_value"] == pytest.approx(2 * 0.5**9)


def test_paired_change_with_no_differences_has_p_value_one():
    assert paired_change([1, None], [2, None], k=6)["p_value"] == 1.0


def test_wilson_interval_of_no_data_is_the_full_range():
    assert wilson_interval(0, 0) == (0.0, 1.0)


# --- answer_outcome: built from real answers the local model gave ---------------

from eval.metrics import answer_outcome  # noqa: E402

CLEAN_REFUSAL = (
    "The provided excerpts do not contain any information about a tyre pressure "
    "monitoring system, so I cannot give a procedure. The Electrical section for a "
    "later model would be needed."
)

HEDGED_ANSWER = """### Most Likely Cause:
One or more TPMS sensors need to be reset.

### The Fix:
1. **Step 1:** Park the vehicle safely.
2. **Step 2:** Turn the ignition switch to ON.
3. **Step 3:** Use a TPMS reset tool.

Note: The provided excerpts do not contain specific instructions for resetting TPMS sensors."""

CONFIDENT_ANSWER = """### Most Likely Cause(s)
Faulty diagnosis sensor unit.

### The Fix
1. Replace the diagnosis sensor unit [Restraint System, p.12].
2. Reseat the connectors.
"""


def test_outcome_is_refused_when_it_admits_the_gap_and_gives_no_procedure():
    assert answer_outcome(CLEAN_REFUSAL) == "refused"


def test_outcome_is_hedged_when_it_admits_the_gap_but_still_gives_steps():
    assert answer_outcome(HEDGED_ANSWER) == "hedged"


def test_outcome_is_answered_when_no_gap_is_admitted():
    assert answer_outcome(CONFIDENT_ANSWER) == "answered"


def test_outcome_treats_not_directly_addressed_as_admitting_a_gap():
    text = "This issue is not directly addressed in the given sections.\n\n### The Fix\n1. Check grounds.\n2. Reseat plugs."
    assert answer_outcome(text) == "hedged"


@pytest.mark.parametrize("refusal", [
    "The provided excerpts do not specify a procedure.",
    "There is no relevant information in the excerpts.",
    "Bluetooth pairing isn't covered in the excerpts.",
    "I cannot find this in the manual.",
    "Not found in the provided manual excerpts.",
    "The manual doesn't give steps for this.",
    "Your issue might not be directly addressed here.",
])
def test_outcome_recognises_common_ways_of_admitting_a_gap(refusal):
    assert answer_outcome(refusal) == "refused"


def test_outcome_ignores_a_negation_that_is_about_the_car_not_the_manual():
    text = "### The Fix\n1. If the lamp does not come on, replace the bulb.\n2. Refit the lens."
    assert answer_outcome(text) == "answered"


def test_parse_citations_stops_at_a_number_that_is_not_a_page():
    assert parse_citations("[Brakes, p.30 (120 N·m)]") == [("brakes", 30)]


def test_parse_citations_keeps_the_second_section_in_a_comma_list():
    assert parse_citations("[Brakes, p.30, Steering p.40]") == [("brakes", 30), ("steering", 40)]


def test_parse_citations_reads_pages_joined_by_and():
    assert parse_citations("[Brakes, p.30 and p.31]") == [("brakes", 30), ("brakes", 31)]


def test_citation_rejects_a_one_word_prefix_shared_by_several_sections():
    assert not citation_is_valid(("engine", 5), {("engine mechanical", 5)})


def test_citation_treats_and_like_an_ampersand():
    allowed = {(normalise_section("Engine Lubrication & Cooling"), 9)}
    assert citation_is_valid((normalise_section("Engine Lubrication and Cooling"), 9), allowed)


def test_citation_accepts_a_code_added_after_a_full_section_name():
    assert citation_is_valid(("brakes br", 30), {("brakes", 30)})


def test_outcome_does_not_count_a_list_of_missing_information_as_a_procedure():
    text = ("The excerpts do not cover this. To answer safely I would need:\n"
            "1. The audio section of the manual.\n2. The wiring diagram for the head unit.")
    assert answer_outcome(text) == "refused"
