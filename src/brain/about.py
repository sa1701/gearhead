"""The which-vehicle check: when a question names another vehicle, whose fault is it about?

A name list can say that a question mentions a Hilux. It cannot say whether the Hilux
is the car with the fault ("Hilux clutch slips, my Patrol never did this") or just
part of the story ("I towed a Hilux with my Patrol and now the clutch slips"). On
fresh questions, treating every mention as a reason to decline turned away real
questions about this car, and letting through every question that also named this car
let through questions about the other one.

So the model is asked one small thing: which vehicle has the fault. It is only asked
when the name list has found another vehicle. If the model is unclear or the call
fails, the question counts as being about the other vehicle and is declined, because
answering a Hilux question from a Patrol manual is the worse mistake.
"""
from __future__ import annotations

import logging
import re

from ..ai.provider import AIProvider
from .vehicles import car_names

log = logging.getLogger(__name__)

ABOUT_MAX_TOKENS = 16
MAX_QUESTION_CHARS = 2000   # the other vehicle can be named anywhere, so the model reads it all

# (other vehicle named, question, answer). An example is left out when the loaded car
# is the vehicle it calls "other", so the prompt never contradicts itself.
_EXAMPLES = (
    ("corolla", "Corolla 1.8 idles rough and stalls at the lights. My {model} never did this.", "other"),
    ("ranger", "Pulled a bogged Ranger out with my {model} and now the clutch smells burnt.", "owner"),
    ("pajero", "Mine is leaking coolant from the water pump. My old Pajero did the same thing.", "owner"),
    ("civic", "How do I change the timing belt on a Civic?", "other"),
    ("navara", "Is the Navara diff the same as the {model} one? My Navara diff is whining.", "other"),
    ("land cruiser", "The steering shakes at 90. My mate's Land Cruiser on the same tyres is smooth.", "owner"),
    ("tucson", "Tucson check engine light with P0420. Had a {model} before and never saw this code.", "other"),
)

_SYSTEM = """You sort car questions for a workshop-manual assistant.
The owner's car is a {full}. The question also names another vehicle.
Decide which vehicle has the fault or needs the repair:
- "owner": the owner's {model}, or the owner's own car when it is not named ("my car", "mine", "the truck"). The other vehicle is only mentioned in passing.
- "other": the other vehicle. The {model} is not mentioned, or is only mentioned in passing.
Reply with ONLY a JSON object and nothing else: {{"about": "owner"}} or {{"about": "other"}}

Examples:
{examples}"""

_ABOUT_FIELD = re.compile(r'"about"\s*:\s*"(owner|other)"', re.IGNORECASE)


def about_system(car: str) -> str:
    """The prompt for the loaded car."""
    full, model = car_names(car)
    own = set(car.replace("-", " ").lower().split())
    examples = "\n".join(f'Q: {question.format(model=model)}\n{{"about": "{answer}"}}'
                         for other, question, answer in _EXAMPLES if not set(other.split()) <= own)
    return _SYSTEM.format(full=full, model=model, examples=examples)


def parse_about(reply: str) -> str:
    """"owner" or "other" if the reply says so clearly, else "".

    Small models wrap the JSON in other text, so the field is picked out by pattern.
    A reply that gives both answers (for example by repeating the question) is unclear.
    """
    answers = {answer.lower() for answer in _ABOUT_FIELD.findall(reply)}
    return answers.pop() if len(answers) == 1 else ""


def is_about_another_vehicle(problem: str, car: str, brain: AIProvider) -> bool:
    """True unless the model clearly says the question is about the owner's car."""
    try:
        reply = brain.complete(
            system=about_system(car),
            messages=[{"role": "user", "content": f"Q: {problem[:MAX_QUESTION_CHARS]}"}],
            max_tokens=ABOUT_MAX_TOKENS,
            thinking=False,  # thinking would spend the whole token budget
        )
    except Exception:
        log.exception("Which-vehicle check failed; the question is declined.")
        return True
    return parse_about(reply) != "owner"
