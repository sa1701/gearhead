"""Questions about a different vehicle.

A workshop manual for one car has pages on the same jobs every car needs: timing
belts, clutch bleeding, head bolts. So "timing belt on a Honda Civic" matches a Patrol
page well, and the score gate lets it through. On the held-out questions, four of
five about another make got through that way.

This check needs no model. If the question names a make or model other than the
car that is loaded, this car's manual does not answer it.

How the names were chosen:
- Makes and models sold in Australia and the Gulf, written as owners type them.
- Names that are also everyday English words are left out, because owners use those
  words in ordinary questions: outback, territory, discovery, accord, liberty,
  charger, pilot, leaf, swift, focus, seat, smart, mini, ram, city, jazz, dodge
  ("dodge the potholes"), golf ("golf ball size"), and jeep, which in the Gulf and
  elsewhere means any 4WD. Ford stays in although "ford a creek" is a risk, because
  it is one of the most common makes in Australia.
- Names that already appear in the Patrol manual text are left out, because an owner
  may use them for a part (the manual names Mitsubishi as a parts maker).

A question that also names this car's model is not declined. "I towed my mate's Hilux
with my Patrol and now the clutch slips" is about the Patrol. The make alone does not
count, because "my Nissan Navara" is still another vehicle.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

MAKES = frozenset({
    "toyota", "ford", "holden", "mazda", "hyundai", "kia", "isuzu", "subaru",
    "volkswagen", "vw", "honda", "lexus", "land rover", "range rover",
    "chevrolet", "chevy", "gmc", "tesla", "bmw", "mercedes", "mercedes benz",
    "benz", "audi", "suzuki", "haval", "gwm", "great wall", "byd", "chery", "geely",
    "renault", "peugeot", "citroen", "volvo", "porsche", "infiniti", "cadillac",
    "lincoln", "jaguar", "skoda", "fiat", "alfa romeo", "lada", "ssangyong", "mahindra",
    "tata", "proton", "perodua", "daihatsu", "datsun", "opel", "vauxhall", "chrysler",
    "rolls royce", "bentley", "ferrari", "lamborghini", "maserati", "mclaren",
    "aston martin", "polestar", "cupra", "ldv", "foton", "changan", "jetour", "dacia",
    "acura", "buick", "scion", "hummer", "rivian", "omoda",
})

MODELS = frozenset({
    # Toyota
    "hilux", "landcruiser", "land cruiser", "prado", "rav4", "corolla", "camry",
    "fortuner", "yaris", "kluger", "hiace", "tacoma", "tundra", "4runner", "fj cruiser",
    "innova",
    # Ford, Holden, Chevrolet, GMC, Dodge, Jeep
    "ranger", "everest", "falcon", "mustang", "f 150", "commodore", "cruze", "captiva",
    "silverado", "tahoe", "camaro", "corvette", "yukon", "durango", "wrangler", "cherokee",
    # Mazda, Mitsubishi
    "cx 3", "cx 5", "cx 9", "cx 30", "triton", "pajero", "outlander", "asx", "lancer",
    # Hyundai, Kia
    "i30", "tucson", "santa fe", "kona", "elantra", "sonata", "sportage", "cerato",
    "sorento", "seltos",
    # Nissan models other than the Patrol
    "navara", "x trail", "xtrail", "pathfinder", "qashqai", "altima", "sentra", "micra",
    "juke", "armada", "tiida", "gt r",
    # Isuzu, Subaru, Volkswagen, Honda, Suzuki, Land Rover
    "mu x", "forester", "impreza", "wrx", "amarok", "polo", "tiguan", "touareg",
    "passat", "jetta", "civic", "cr v", "hr v", "jimny", "vitara", "defender",
})

VEHICLE_NAMES = MAKES | MODELS


def _normalise(text: str) -> str:
    """Lower case with accents dropped ("Citroën" is "citroen"), every run of other
    characters turned into one space, padded with spaces so a name only matches as
    whole words ("x-trail" and "X Trail" both match)."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return " " + re.sub(r"[^a-z0-9]+", " ", plain.lower()).strip() + " "


@lru_cache(maxsize=1)
def _keys() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Each name with the forms it matches: as written, and run together when it has a
    space ("cx 5" also matches "CX5", "f 150" also matches "F150")."""
    keys = []
    for name in sorted(VEHICLE_NAMES):
        spaced = _normalise(name)
        joined = " " + spaced.replace(" ", "") + " "
        keys.append((name, (spaced, joined) if joined != spaced else (spaced,)))
    return tuple(keys)


MIN_MODEL_WORD_CHARS = 3


@lru_cache(maxsize=None)
def _model_forms(car: str) -> tuple[str, ...]:
    """The ways a question can name the loaded car's model, as padded strings.

    The car id is make first ("nissan-patrol-y61", "land-rover-defender"). After the
    make, these count as naming the model:
    - the whole model, spaced or run together ("cx 5", "cx5");
    - a model from the name list made only of the car's words ("land cruiser");
    - one word of the model on its own ("patrol", "y61"), unless it is a number, is
      under three characters, or is also a word in another vehicle's name. So "5" in
      "5 speed" does not name a CX-5, and "land" does not name a Land Cruiser.
    """
    words = _normalise(car).split()
    make_length = max((n for n in range(1, len(words)) if " ".join(words[:n]) in MAKES), default=1)
    model = words[make_length:]
    if not model:
        return ()
    own = set(words)
    own_names = {name for name in MODELS if set(name.split()) <= own}
    shared = {word for name in VEHICLE_NAMES - own_names for word in name.split()}
    names = {" ".join(model)} | own_names
    names |= {word for word in model
              if len(word) >= MIN_MODEL_WORD_CHARS and not word.isdigit() and word not in shared}
    forms = {f" {name} " for name in names} | {" " + name.replace(" ", "") + " " for name in names}
    return tuple(sorted(forms))


def _names_this_model(text: str, car: str) -> bool:
    """True if the normalised question names the loaded car's model."""
    return any(form in text for form in _model_forms(car))


def other_vehicle_named(problem: str, car: str) -> str | None:
    """The first make or model named in the question that is not the loaded car, or None.

    The car's own words (for "nissan-patrol-y61": nissan, patrol, y61) never count,
    so "my Nissan Patrol" passes and "my Nissan Navara" does not. If the question
    names this car's model, another vehicle is treated as a passing mention, so None.
    That also lets through a question that is really about the other vehicle but
    mentions this one ("Hilux clutch slips, I also own a Patrol"). The score gate and
    the subject check still apply to it.
    """
    own_words = set(_normalise(car).split())
    text = _normalise(problem)
    if _names_this_model(text, car):
        return None
    for name, forms in _keys():
        if set(_normalise(name).split()) <= own_words:
            continue
        if any(form in text for form in forms):
            return name
    return None
