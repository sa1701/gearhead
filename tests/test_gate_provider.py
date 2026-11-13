"""Unit tests for which brain the coverage gate's short checks go to."""
import httpx

from src.ai import get_gate_provider
from src.brain import diagnose, subject
from src.brain.subject import SUBJECT_SYSTEM
from src.config import settings


class _Brain:
    """Records every system prompt it is sent."""
    last_usage = None

    def __init__(self, reply: str):
        self.reply = reply
        self.systems = []

    def complete(self, **kwargs):
        self.systems.append(kwargs["system"])
        return self.reply


def _local(monkeypatch, gate_model: str | None) -> None:
    monkeypatch.setattr(settings, "provider", "ollama")
    monkeypatch.setattr(settings, "ollama_gate_model", gate_model)
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: None)


def test_the_gate_uses_the_answer_brain_when_no_gate_model_is_set(monkeypatch):
    _local(monkeypatch, gate_model=None)
    brain = _Brain("answer")

    assert get_gate_provider(brain) is brain


def test_the_gate_gets_its_own_local_model_when_one_is_set(monkeypatch):
    _local(monkeypatch, gate_model="small-gate-model")
    brain = _Brain("answer")

    gate_brain = get_gate_provider(brain)

    assert gate_brain is not brain
    assert gate_brain.model == "small-gate-model"


def test_the_gate_model_setting_is_ignored_for_the_cloud_brain(monkeypatch):
    monkeypatch.setattr(settings, "provider", "claude")
    monkeypatch.setattr(settings, "ollama_gate_model", "small-gate-model")
    brain = _Brain("answer")

    assert get_gate_provider(brain) is brain


def test_one_shot_diagnosis_sends_the_gate_check_and_the_answer_to_different_brains(monkeypatch):
    answer_brain = _Brain("DIAGNOSIS: Replace the pads [Brakes, p.30].")
    gate_brain = _Brain('{"subject": "brake pads"}')
    low_score_hit = {"text": "chunk", "section": "Brakes", "page": 30, "source_file": "br.pdf",
                     "distance": 0.4, "rerank_score": 0.004}
    monkeypatch.setattr(settings, "gate_min_score", 0.1)
    monkeypatch.setattr(settings, "gate_subject_min_score", 0.5)
    monkeypatch.setattr(diagnose, "get_provider", lambda: answer_brain)
    monkeypatch.setattr(diagnose, "get_gate_provider", lambda brain: gate_brain)
    monkeypatch.setattr(diagnose, "_retrieve", lambda *a, **k: ([low_score_hit], ["grinding noise"]))
    monkeypatch.setattr(diagnose, "search_fixes", lambda *a, **k: [])
    monkeypatch.setattr(subject, "subject_score", lambda name, car: 0.93)

    result = diagnose.diagnose_once("grinding noise")

    assert gate_brain.systems == [SUBJECT_SYSTEM]
    assert answer_brain.systems == [diagnose.SYSTEM]
    assert result["refused"] is False
