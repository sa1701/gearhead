"""Unit tests for the coverage gate: no guessing when the manual has no good match."""
import pytest

from src.brain import diagnose, interview, subject
from src.brain.gate import NOT_FOUND_MESSAGE, manual_covers
from src.brain.subject import SUBJECT_SYSTEM
from src.config import settings


def _hit(score: float | None, page: int = 30) -> dict:
    hit = {"text": "chunk", "section": "Brakes", "page": page, "source_file": "br.pdf", "distance": 0.4}
    return hit if score is None else {**hit, "rerank_score": score}


class _BrainThatOnlyNamesTheSubject:
    """Stands in for the model on a declined question: it may be asked to name the
    subject, and nothing else."""
    last_usage = None

    def __init__(self):
        self.systems = []

    def complete(self, **kwargs):
        self.systems.append(kwargs["system"])
        return '{"subject": "Apple CarPlay"}'


class _BrainThatAnswers:
    last_usage = None

    def complete(self, **kwargs):
        return "DIAGNOSIS: Replace the pads [Brakes, p.30]."


@pytest.fixture(autouse=True)
def gate_threshold(monkeypatch):
    monkeypatch.setattr(settings, "gate_min_score", 0.1)
    monkeypatch.setattr(settings, "gate_subject_min_score", 0.5)
    monkeypatch.setattr(subject, "subject_score", lambda name, car: 0.0004)


def test_manual_covers_a_question_whose_best_chunk_scores_above_the_threshold():
    assert manual_covers([_hit(0.93), _hit(0.02)])


def test_manual_does_not_cover_a_question_whose_best_chunk_scores_below_the_threshold():
    assert not manual_covers([_hit(0.04), _hit(0.01)])


def test_manual_does_not_cover_a_question_with_no_chunks_at_all():
    assert not manual_covers([])


def test_gate_stays_open_when_the_reranker_gave_no_scores():
    assert manual_covers([_hit(None)])


def test_gate_can_be_switched_off_with_a_zero_threshold(monkeypatch):
    monkeypatch.setattr(settings, "gate_min_score", 0.0)

    assert manual_covers([_hit(0.0001)])


def test_one_shot_diagnosis_declines_without_asking_the_model_for_a_fix(monkeypatch):
    brain = _BrainThatOnlyNamesTheSubject()
    monkeypatch.setattr(diagnose, "get_provider", lambda: brain)
    monkeypatch.setattr(diagnose, "_retrieve", lambda *a, **k: ([_hit(0.004)], ["reset the TPMS"]))

    result = diagnose.diagnose_once("reset the TPMS")

    assert brain.systems == [SUBJECT_SYSTEM]

    assert result["refused"] is True
    assert result["answer"] == NOT_FOUND_MESSAGE
    assert result["sources"] == []


def test_one_shot_diagnosis_answers_when_the_manual_covers_it(monkeypatch):
    monkeypatch.setattr(diagnose, "get_provider", lambda: _BrainThatAnswers())
    monkeypatch.setattr(diagnose, "_retrieve", lambda *a, **k: ([_hit(0.9)], ["brakes grind"]))
    monkeypatch.setattr(diagnose, "search_fixes", lambda *a, **k: [])

    result = diagnose.diagnose_once("brakes grind")

    assert result["refused"] is False
    assert result["sources"] == [("Brakes", 30)]
    assert "Replace the pads" in result["answer"]


def test_interview_session_declines_at_the_start_without_asking_the_model_for_a_fix(monkeypatch):
    brain = _BrainThatOnlyNamesTheSubject()
    monkeypatch.setattr(interview, "get_provider", lambda: brain)
    monkeypatch.setattr(interview, "_retrieve", lambda *a, **k: ([_hit(0.004)], ["carplay drops out"]))

    session = interview.DiagnosisSession("carplay drops out")
    step = session.start()

    assert brain.systems == [SUBJECT_SYSTEM]

    assert step["type"] == "diagnosis"
    assert step["text"] == NOT_FOUND_MESSAGE
    assert step["sources"] == []
    assert step["confidence"] == interview.MIN_CONFIDENCE
    assert session.done is True
    assert session.hits == []


def test_one_shot_diagnosis_answers_a_vague_complaint_about_a_part_in_the_manual(monkeypatch):
    class _BrainThatNamesThenAnswers:
        last_usage = None

        def complete(self, **kwargs):
            if kwargs["system"] == SUBJECT_SYSTEM:
                return '{"subject": "brake pads"}'
            return "DIAGNOSIS: Replace the pads [Brakes, p.30]."

    monkeypatch.setattr(diagnose, "get_provider", lambda: _BrainThatNamesThenAnswers())
    monkeypatch.setattr(diagnose, "_retrieve", lambda *a, **k: ([_hit(0.004)], ["grinding noise"]))
    monkeypatch.setattr(diagnose, "search_fixes", lambda *a, **k: [])
    monkeypatch.setattr(subject, "subject_score", lambda name, car: 0.93 if name == "brake pads" else 0.0)

    result = diagnose.diagnose_once("grinding noise")

    assert result["refused"] is False
    assert "Replace the pads" in result["answer"]


def test_interview_session_runs_normally_when_the_manual_covers_it(monkeypatch):
    monkeypatch.setattr(interview, "get_provider", lambda: _BrainThatAnswers())
    monkeypatch.setattr(interview, "_retrieve", lambda *a, **k: ([_hit(0.9)], ["brakes grind"]))
    monkeypatch.setattr(interview, "build_context", lambda problem, car, hits: "excerpts")

    step = interview.DiagnosisSession("brakes grind").start()

    assert step["type"] == "diagnosis"
    assert "Replace the pads" in step["text"]
    assert step["sources"] == [{"section": "Brakes", "page": 30, "source_file": "br.pdf"}]


def test_terminal_interview_declines_without_asking_the_model_for_a_fix(monkeypatch):
    brain = _BrainThatOnlyNamesTheSubject()
    monkeypatch.setattr(interview, "get_provider", lambda: brain)
    monkeypatch.setattr(interview, "_retrieve", lambda *a, **k: ([_hit(0.004)], ["carplay drops out"]))

    result = interview.run_interview("carplay drops out", ask_fn=lambda question: "")

    assert brain.systems == [SUBJECT_SYSTEM]

    assert result["diagnosis"] == NOT_FOUND_MESSAGE
    assert result["sources"] == []
    assert result["questions_asked"] == 0
