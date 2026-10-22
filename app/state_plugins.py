"""New state adapters, explicitly imported for frozen-build compatibility.
Example:
    from app.states import xx
    PLUGINS = {"XX": xx}
CA/NM remain registered in app/states/__init__.py.
Only adapters with ENABLED = True are added.
"""
PLUGINS = {}
