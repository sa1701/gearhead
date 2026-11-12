"""Unit tests for the subject check: the second look at a question the gate would decline."""
import pytest

from src.brain import gate, subject
from src.brain.subject import SUBJECT_SYSTEM, name_subject, parse_subject, subject_is_in_manual
from src.config import settings

CAR = "nissan-patrol-y61"


class _Brain:
    """Replies with a fixed string and records what it was asked."""

    def __init__(self, reply: str = "", error: Exception | None = None):
        self.reply, self.error, self.calls = reply, error, []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.reply


def _hit(score: float | None) -> dict:
    hit = {"text": "chunk", "section": "Brakes", "page": 30, "source_file": "br.pdf", "distance": 0.4}
    return hit if score is None else {**hit, "rerank_score": score}


@pytest.fixture(autouse=True)
def thresholds(monkeypatch):
    monkeypatch.setattr(settings, "gate_min_score", 0.1)
    monkeypatch.setattr(settings, "gate_subject_min_score", 0.5)


def _manual_scores_subjects(monkeypatch, scores: dict[str, float]) -> None:
    monkeypatch.setattr(subject, "search", lambda query, n, car: [{"query": query}])
    monkeypatch.setattr(subject, "rerank",
                        lambda query, hits, top_n: [_hit(scores[query])] if query in scores else [])


def test_parse_subject_reads_the_json_reply():
    assert parse_subject('{"subject": "starting system"}') == "starting system"


def test_parse_subject_reads_json_wrapped_in_other_text():
    assert parse_subject('Sure.\n```json\n{"subject" : "drive belt"}\n```') == "drive belt"


def test_parse_subject_of_a_reply_with_no_subject_field_is_empty():
    assert parse_subject("I cannot help with that request.") == ""


def test_parse_subject_rejects_a_sentence_where_a_part_name_should_be():
    assert parse_subject('{"subject": "' + "the engine and also everything else " * 3 + '"}') == ""


def test_parse_subject_of_an_empty_reply_is_empty():
    assert parse_subject("") == ""


def test_name_subject_asks_the_model_one_small_question():
    brain = _Brain('{"subject": "fuel gauge"}')

    assert name_subject("gauge says empty after I fill up", brain) == "fuel gauge"
    assert brain.calls[0]["system"] == SUBJECT_SYSTEM
    assert brain.calls[0]["messages"] == [{"role": "user", "content": "Q: gauge says empty after I fill up"}]
    assert brain.calls[0]["max_tokens"] <= 40
    assert brain.calls[0]["thinking"] is False


def test_name_subject_sends_only_the_start_of_a_very_long_question():
    brain = _Brain('{"subject": "horn"}')

    name_subject("horn " * 1000, brain)

    assert len(brain.calls[0]["messages"][0]["content"]) <= 510


def test_name_subject_is_empty_when_the_model_call_fails():
    assert name_subject("anything", _Brain(error=RuntimeError("model is down"))) == ""


def test_subject_found_on_a_manual_page_is_in_the_manual(monkeypatch):
    _manual_scores_subjects(monkeypatch, {"starting system": 0.93})

    assert subject_is_in_manual("starting system", CAR)


def test_subject_with_only_weak_matches_is_not_in_the_manual(monkeypatch):
    _manual_scores_subjects(monkeypatch, {"Apple CarPlay": 0.0004})

    assert not subject_is_in_manual("Apple CarPlay", CAR)


def test_empty_subject_is_not_in_the_manual(monkeypatch):
    _manual_scores_subjects(monkeypatch, {})

    assert not subject_is_in_manual("", CAR)


def test_subject_is_not_in_the_manual_when_the_search_finds_nothing(monkeypatch):
    _manual_scores_subjects(monkeypatch, {})

    assert not subject_is_in_manual("hybrid battery", CAR)


def test_subject_is_not_in_the_manual_when_the_lookup_fails(monkeypatch):
    def broken_search(query, n, car):
        raise RuntimeError("vector store is down")

    monkeypatch.setattr(subject, "search", broken_search)

    assert not subject_is_in_manual("starting system", CAR)


def test_subject_is_not_in_the_manual_when_the_reranker_gave_no_score(monkeypatch):
    monkeypatch.setattr(subject, "search", lambda query, n, car: [_hit(None)])
    monkeypatch.setattr(subject, "rerank", lambda query, hits, top_n: hits)

    assert not subject_is_in_manual("starting system", CAR)


def test_a_good_page_match_is_covered_without_asking_the_model():
    brain = _Brain(error=AssertionError("no model call needed"))

    assert gate.covers("starter clicks", CAR, [_hit(0.9)], brain)
    assert brain.calls == []


def test_a_vague_complaint_about_a_part_in_the_manual_is_covered(monkeypatch):
    _manual_scores_subjects(monkeypatch, {"starting system": 0.93})
    brain = _Brain('{"subject": "starting system"}')

    assert gate.covers("turn key and just a click", CAR, [_hit(0.01)], brain)


def test_a_question_about_a_part_the_manual_never_mentions_is_not_covered(monkeypatch):
    _manual_scores_subjects(monkeypatch, {"Apple CarPlay": 0.0004})
    brain = _Brain('{"subject": "Apple CarPlay"}')

    assert not gate.covers("carplay drops out", CAR, [_hit(0.01)], brain)


def test_a_question_with_no_chunks_is_not_covered_and_the_model_is_not_asked():
    brain = _Brain(error=AssertionError("no model call needed"))

    assert not gate.covers("anything", CAR, [], brain)
    assert brain.calls == []


def test_the_subject_check_can_be_switched_off_with_a_zero_threshold(monkeypatch):
    monkeypatch.setattr(settings, "gate_subject_min_score", 0.0)
    brain = _Brain(error=AssertionError("no model call needed"))

    assert not gate.covers("carplay drops out", CAR, [_hit(0.01)], brain)
    assert brain.calls == []


def test_a_failed_model_call_leaves_the_question_declined(monkeypatch):
    monkeypatch.setattr(subject, "subject_score", lambda name, car: 0.99 if name else 0.0)

    assert not gate.covers("turn key and just a click", CAR, [_hit(0.01)],
                           _Brain(error=RuntimeError("model is down")))
