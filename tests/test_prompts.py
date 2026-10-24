"""The shared KEY WHAT YOU SEE prompt. Run: python -m pytest tests/test_prompts.py -q"""
import importlib

import pytest

from app.extraction import prompts

STATES = ("CA", "NC", "NJ", "PA", "NM")
UNIFIED = [('app.extraction.ca_extractor', 'RULES', 'CA'), ('app.extraction.nc_extractor', 'KEY_WHAT_YOU_SEE', 'NC'), ('app.extraction.nj_extractor', 'KEY_WHAT_YOU_SEE', 'NJ'), ('app.extraction.pa_extractor', 'KEY_WHAT_YOU_SEE', 'PA'), ('app.extraction.nm_extractor', 'KEY_WHAT_YOU_SEE', 'NM')]


def test_core_is_in_every_state_prompt():
    for state in STATES:
        text = prompts.key_what_you_see(state)
        assert text.startswith(prompts.CORE)
        for needle in ("KEY WHAT YOU SEE", "exactly as printed", "Never correct", "Return null", "warnings"):
            assert needle in text, (state, needle)


def test_state_exceptions_are_present():
    assert "checkboxes" in prompts.key_what_you_see("CA") and "MM/DD/YYYY" in prompts.key_what_you_see("CA")
    assert "series of X" in prompts.key_what_you_see("NC")
    assert "row of dashes" in prompts.key_what_you_see("NJ")
    assert "{code, text}" in prompts.key_what_you_see("PA")
    assert prompts.key_what_you_see("NM") == prompts.CORE
    assert prompts.KEY_WHAT_YOU_SEE == prompts.key_what_you_see("NM")


def test_unknown_state_is_an_error_not_a_silent_core():
    with pytest.raises(KeyError):
        prompts.key_what_you_see("ZZ")
    assert prompts.key_what_you_see() == prompts.CORE


@pytest.mark.parametrize("module,attr,state", UNIFIED)
def test_extractor_uses_the_shared_prompt(module, attr, state):
    mod = importlib.import_module(module)
    assert getattr(mod, attr) == prompts.key_what_you_see(state)
