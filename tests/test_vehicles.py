"""Unit tests for the other-vehicle check: a Patrol manual does not answer Hilux questions."""
import pytest

from src.brain import gate, subject
from src.brain.vehicles import other_vehicle_named
from src.config import settings

CAR = "nissan-patrol-y61"


@pytest.mark.parametrize("question, name", [
    ("How do I replace the timing belt on a Honda Civic 2008 1.8 petrol?", "civic"),
    ("my hilux wont start after rain", "hilux"),
    ("Clutch bleeding on a Land Rover Defender Td5?", "defender"),
    ("head bolt torque for a VE commodore", "commodore"),
    ("x-trail cvt shudder", "x trail"),
    ("my Nissan Navara has a clunk from the rear", "navara"),
    ("CX5 rattles over bumps", "cx 5"),
    ("F150 wont idle", "f 150"),
    ("Citroën C4 gearbox fault", "citroen"),
    ("Škoda Octavia DSG judder", "skoda"),
])
def test_names_another_vehicle(question, name):
    assert other_vehicle_named(question, CAR) == name


@pytest.mark.parametrize("question", [
    "My Nissan Patrol Y61 overheats when towing",
    "patrol idles rough at the lights",
    "the brakes squeal when I stop",
    "I fitted a Bosch battery and now the starter clicks",
    "fuel gauge reads empty in the outback",
    "the polonium seal",            # a model name inside a longer word does not count
    "my patrol ran over a golfball",
    "rust bubbles the size of a golf ball on my patrol",
    "I dodge the potholes but the front still clunks",
    "my jeep overheats on the dunes",   # in the Gulf 'jeep' means any 4WD
])
def test_does_not_flag_questions_about_this_car(question):
    assert other_vehicle_named(question, CAR) is None


def test_a_model_of_the_same_make_counts_as_another_vehicle():
    assert other_vehicle_named("Nissan Pathfinder timing chain noise", CAR) == "pathfinder"


def test_the_loaded_car_decides_what_counts_as_another_vehicle():
    assert other_vehicle_named("my hilux wont start", "toyota-hilux-n70") is None


def test_a_question_that_also_names_this_car_still_reports_the_other_vehicle():
    assert other_vehicle_named("I towed my mate's Hilux with my Patrol", CAR) == "hilux"


class _BrainThatMustNotBeCalled:
    def complete(self, **kwargs):
        raise AssertionError("no other vehicle is named, so no model call is needed")


class _BrainThatSays:
    """Answers the which-vehicle question, and counts how often it is asked."""

    def __init__(self, about: str):
        self.about = about
        self.calls = 0

    def complete(self, **kwargs):
        self.calls += 1
        return f'{{"about": "{self.about}"}}'


class _BrokenBrain:
    def complete(self, **kwargs):
        raise RuntimeError("model is down")


def _hit(score: float) -> dict:
    return {"text": "chunk", "section": "Engine", "page": 3, "source_file": "em.pdf",
            "distance": 0.4, "rerank_score": score}


def test_gate_declines_a_well_matched_question_about_another_vehicle(monkeypatch):
    monkeypatch.setattr(settings, "gate_min_score", 0.1)

    assert not gate.covers("timing belt on a Honda Civic", CAR, [_hit(0.95)], _BrainThatSays("other"))


def test_gate_covers_a_question_about_this_car_that_mentions_another(monkeypatch):
    monkeypatch.setattr(settings, "gate_min_score", 0.1)

    assert gate.covers("I towed a Hilux with my Patrol and the clutch slips", CAR, [_hit(0.95)],
                       _BrainThatSays("owner"))


def test_gate_asks_no_model_when_no_other_vehicle_is_named(monkeypatch):
    monkeypatch.setattr(settings, "gate_min_score", 0.1)

    assert gate.covers("timing belt on my Patrol", CAR, [_hit(0.95)], _BrainThatMustNotBeCalled())


def test_gate_declines_when_the_which_vehicle_call_fails(monkeypatch):
    monkeypatch.setattr(settings, "gate_min_score", 0.1)

    assert not gate.covers("hilux clutch slipping", CAR, [_hit(0.95)], _BrokenBrain())


def test_gate_skips_the_subject_check_for_another_vehicle(monkeypatch):
    monkeypatch.setattr(settings, "gate_min_score", 0.1)
    monkeypatch.setattr(settings, "gate_subject_min_score", 0.5)
    monkeypatch.setattr(subject, "subject_score", lambda name, car: 0.99)
    brain = _BrainThatSays("other")

    assert not gate.covers("hilux clutch slipping", CAR, [_hit(0.01)], brain)
    assert brain.calls == 1
