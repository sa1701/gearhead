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


class _BrainThatMustNotBeCalled:
    def complete(self, **kwargs):
        raise AssertionError("the other-vehicle check needs no model call")


def _hit(score: float) -> dict:
    return {"text": "chunk", "section": "Engine", "page": 3, "source_file": "em.pdf",
            "distance": 0.4, "rerank_score": score}


def test_gate_declines_a_well_matched_question_about_another_vehicle(monkeypatch):
    monkeypatch.setattr(settings, "gate_min_score", 0.1)

    assert not gate.covers("timing belt on a Honda Civic", CAR, [_hit(0.95)], _BrainThatMustNotBeCalled())


def test_gate_still_covers_a_well_matched_question_about_this_car(monkeypatch):
    monkeypatch.setattr(settings, "gate_min_score", 0.1)

    assert gate.covers("timing belt on my Patrol", CAR, [_hit(0.95)], _BrainThatMustNotBeCalled())


def test_gate_skips_the_subject_check_for_another_vehicle(monkeypatch):
    monkeypatch.setattr(settings, "gate_min_score", 0.1)
    monkeypatch.setattr(settings, "gate_subject_min_score", 0.5)
    monkeypatch.setattr(subject, "subject_score", lambda name, car: 0.99)

    assert not gate.covers("hilux clutch slipping", CAR, [_hit(0.01)], _BrainThatMustNotBeCalled())


@pytest.mark.parametrize("question", [
    "I towed my mate's Hilux with my Patrol and now the clutch slips",
    "my old Land Cruiser never did this but my Y61 has a diff whine",
    "patrol auto slips into neutral when towing a broken down Prado",
])
def test_a_passing_mention_does_not_decline_a_question_that_names_this_car(question):
    assert other_vehicle_named(question, CAR) is None


def test_naming_only_the_make_of_this_car_is_not_naming_this_car():
    assert other_vehicle_named("my Nissan Navara has a clunk from the rear", CAR) == "navara"


@pytest.mark.parametrize("question, car, name", [
    # a number or a short word in the car id is not the car's name
    ("my Toyota Corolla 5 speed clunk", "mazda-cx-5", "corolla"),
    ("my 2020 Corolla clutch", "toyota-hilux-2020", "corolla"),
    ("V8 Commodore misfire", "honda-cr-v", "commodore"),
    # a make can be two words
    ("Range Rover gearbox slips", "land-rover-defender", "range rover"),
    # a word shared with another vehicle's name is not this car's name
    ("Land Rover clutch slips", "toyota-land-cruiser-80", "land rover"),
])
def test_part_of_the_car_id_alone_does_not_name_this_car(question, car, name):
    assert other_vehicle_named(question, car) == name


@pytest.mark.parametrize("question, car", [
    ("Hilux clutch is fine but my CX5 clutch slips", "mazda-cx-5"),
    ("my cx-5 rattles since I followed a Ranger down a track", "mazda-cx-5"),
    ("my land cruiser towed a Navara and now the clutch slips", "toyota-land-cruiser-80"),
    ("my Defender pulled a Hilux out and now it overheats", "land-rover-defender"),
])
def test_this_car_is_recognised_however_its_model_is_written(question, car):
    assert other_vehicle_named(question, car) is None
