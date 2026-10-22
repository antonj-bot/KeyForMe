"""Reusable identity completeness gate; never invents missing units."""
class IncompleteExtractionError(ValueError):
    pass

def missing_units(expected, actual):
    expected=set(expected); actual=set(actual)
    if not expected or any(not isinstance(n,int) or isinstance(n,bool) or n<1 for n in expected):
        raise IncompleteExtractionError("Unit inventory is empty or invalid; filling cancelled.")
    unexpected=actual-expected
    if unexpected:
        raise IncompleteExtractionError("Extracted units disagree with observed inventory; filling cancelled.")
    return expected-actual
