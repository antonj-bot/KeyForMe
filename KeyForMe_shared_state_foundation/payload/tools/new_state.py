"""Create a disabled adapter. Does not invent selectors, mappings or extraction rules."""
import argparse
from pathlib import Path
import re

TEMPLATE = """
# {code}: implement and test before enabling.
ENABLED = False
NAME = "{code} - not configured"

def extract(pdf_path, model):
    # Use a state-specific schema, page plan, extractor and mapper.
    # Return incident, units, other_parties and notes.
    raise NotImplementedError("{code} extraction is not configured")

def fill(page, payload):
    # Use app.core.tabs and app.core.vin with verified form settings.
    # Preserve state-specific dropdown meanings. Never Save or Submit.
    raise NotImplementedError("{code} filling is not configured")
"""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("state", type=str.upper)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Z]{2}", args.state):
        parser.error("Use a two-letter state code.")
    target = args.project_root / "app" / "states" / (args.state.lower() + ".py")
    if not target.parent.is_dir():
        parser.error("Run from the KeyForMe project root.")
    with target.open("x", encoding="utf-8") as handle:
        handle.write(TEMPLATE.format(code=args.state).lstrip())
    print(f"Created disabled adapter: {target}")
    print("Add an explicit import and PLUGINS entry in app/state_plugins.py.")
    print("Implement and test before setting ENABLED = True.")

if __name__ == "__main__":
    main()
