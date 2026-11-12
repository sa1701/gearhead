"""Unit tests for how Fix DB entries are written into the model's context.

The Fix DB is extracted by a model, so its items are not always plain strings.
"""
from src.brain.diagnose import _format_fixes

ENTRY = {
    "symptom": "Engine lacks power",
    "causes": ["Low compression"],
    "checks": ["Measure compression pressure"],
    "fix": ["Repair as needed"],
    "section": "Engine Mechanical",
    "pages": [12],
}


def test_format_fixes_writes_text_specs_as_they_are():
    block = _format_fixes([{**ENTRY, "specs": ["Limit = 2452 kPa"]}])

    assert "SPECS: Limit = 2452 kPa" in block


def test_format_fixes_accepts_specs_stored_as_name_value_unit_objects():
    specs = [{"name": "Compression pressure", "value": "3040", "unit": "kPa"},
             {"name": "Limit", "value": "2452 kPa", "unit": ""}]

    block = _format_fixes([{**ENTRY, "specs": specs}])

    assert "SPECS: Compression pressure = 3040 kPa; Limit = 2452 kPa" in block


def test_format_fixes_does_not_crash_on_an_unexpected_item():
    block = _format_fixes([{**ENTRY, "causes": ["Low compression", 42]}])

    assert "CAUSES: Low compression; 42" in block


def test_format_fixes_of_nothing_is_an_empty_string():
    assert _format_fixes([]) == ""
