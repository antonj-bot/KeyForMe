"""Selector helpers shared by every *_field_mapping.py.

Person and vehicle field ids end in -tN, a form-wide counter that keeps growing as units and other parties
are added, so ids are not predictable. These helpers match the id PREFIX and keep only the visible control
(only the active tab's fields are visible).
"""


def person(name):
    return f"[id^='Person_{name}-']:visible"


def vehicle(name):
    return f"[id^='Vehicle_{name}-']:visible"
