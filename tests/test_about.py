"""Unit tests for the which-vehicle check: is the question about the owner's car?"""
import pytest

from src.brain.about import about_system, is_about_another_vehicle, parse_about
from src.brain.vehicles import car_names

CAR = "nissan-patrol-y61"


class _Brain:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return self.reply


class _BrokenBrain:
    def complete(self, **kwargs):
        raise RuntimeError("model is down")


@pytest.mark.parametrize("reply, about", [
    ('{"about": "owner"}', "owner"),
    ('{"about": "other"}', "other"),
    ('Sure. {"about":"OTHER"} because it names a Civic', "other"),
    ("the owner's car", ""),
    ('Q says {"about": "owner"} but really {"about": "other"}', ""),   # two answers is no answer
    ('{"about": "both"}', ""),
    ("", ""),
])
def test_parse_about_reads_only_a_clear_answer(reply, about):
    assert parse_about(reply) == about


def test_a_question_about_the_owners_car_is_not_about_another_vehicle():
    assert not is_about_another_vehicle("towed a Hilux with my Patrol, clutch slips", CAR, _Brain('{"about": "owner"}'))


def test_a_question_about_the_other_vehicle_is():
    assert is_about_another_vehicle("Hilux clutch slips, my Patrol is fine", CAR, _Brain('{"about": "other"}'))


def test_an_unclear_reply_counts_as_another_vehicle():
    assert is_about_another_vehicle("Hilux clutch slips", CAR, _Brain("not sure"))


def test_a_failed_model_call_counts_as_another_vehicle():
    assert is_about_another_vehicle("Hilux clutch slips", CAR, _BrokenBrain())


def test_the_model_is_told_which_car_is_loaded_and_asked_briefly():
    brain = _Brain('{"about": "owner"}')

    is_about_another_vehicle("towed a Hilux with my Patrol", CAR, brain)

    call = brain.calls[0]
    assert "Nissan Patrol Y61" in call["system"]
    assert "towed a Hilux with my Patrol" in call["messages"][0]["content"]
    assert call["thinking"] is False
    assert call["max_tokens"] <= 20


def test_an_example_that_names_the_loaded_car_is_left_out():
    assert "Corolla 1.8 idles rough" in about_system(CAR)
    assert "Corolla 1.8 idles rough" not in about_system("toyota-corolla-e120")
    assert "Corolla 1.8 idles rough" in about_system("toyota-corollagt-x")   # whole words only


def test_the_model_sees_a_vehicle_named_late_in_a_long_question():
    brain = _Brain('{"about": "other"}')
    question = "It rattles. " * 60 + "This is on my Hilux."

    is_about_another_vehicle(question, CAR, brain)

    assert "Hilux" in brain.calls[0]["messages"][0]["content"]


@pytest.mark.parametrize("car, full, model", [
    ("nissan-patrol-y61", "Nissan Patrol Y61", "Patrol"),
    ("land-rover-defender", "Land Rover Defender", "Defender"),
    ("toyota-hilux-n70", "Toyota Hilux N70", "Hilux"),
    ("toyota-land-cruiser-80", "Toyota Land Cruiser 80", "Land Cruiser 80"),
    ("mazda-cx-5", "Mazda Cx 5", "Cx 5"),
    ("toyota-hilux-2020", "Toyota Hilux 2020", "Hilux"),
    ("", "", ""),
])
def test_car_names_come_from_the_car_id(car, full, model):
    assert car_names(car) == (full, model)
