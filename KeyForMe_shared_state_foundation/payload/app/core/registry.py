"""Extend the current registry explicitly; never enable a state by filename."""
import re

def extend_pipelines(existing):
    from app.state_plugins import PLUGINS
    result = dict(existing)
    for code, pipeline in PLUGINS.items():
        if not re.fullmatch(r"[A-Z]{2}", code):
            raise ValueError("State codes must be two uppercase letters.")
        if code in result:
            raise ValueError(f"Duplicate state registration: {code}")
        if not getattr(pipeline, "ENABLED", False):
            continue
        if not callable(getattr(pipeline, "extract", None)) or not callable(getattr(pipeline, "fill", None)):
            raise TypeError(f"State {code} needs extract(path, model) and fill(page, payload).")
        result[code] = pipeline
    return result
