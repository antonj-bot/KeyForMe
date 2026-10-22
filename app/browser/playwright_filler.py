"""Compatibility entrypoint. All filling is implemented in the shared engine."""
from app.browser.engine import fill_form

def fill_keying_form(page,payload):
    warnings=fill_form(page,payload,state="CA",log=print)
    for warning in warnings:
        print("  WARNING: "+warning)
    for note in payload.get("notes",[]):
        print("  NOTE: "+str(note))
