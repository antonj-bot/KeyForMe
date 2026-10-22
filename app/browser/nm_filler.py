"""Compatibility entrypoint. All filling is implemented in the shared engine."""
from app.browser.engine import fill_form

def fill_nm_form(page,payload,log=None):
    return fill_form(page,payload,state="NM",log=log)
