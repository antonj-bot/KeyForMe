"""Switch the eCrash site KeyForMe points at, without hand-editing run_web_ui.py.

    python tools/set_site.py status     # which site is active
    python tools/set_site.py prod       # production (what the EXE must use)
    python tools/set_site.py uat        # the UAT test site (tools/build_exe.py refuses to build from this)

Only the first ACTIVE `KEYING_URL = "..."` line is changed; commented lines are ignored (same rule as
tools/build_exe.py). Line endings are kept. Nothing is committed.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROD = "https://azkeying.ecrash.lexisnexisrisk.com/ecrash/"
UAT = "https://keying-uat.green.usgov-ecrash-prod.azuregov.lnrsg.io/ecrash/"
ENTRY = "run_web_ui.py"
ACTIVE = re.compile(r"""^(\s*KEYING_URL\s*=\s*)(["'])([^"']+)\2(.*)$""")


def site_of(url: str) -> str:
    return "production" if url == PROD else "uat" if url == UAT else "other"


def current(source: str) -> str | None:
    for line in source.splitlines():
        match = ACTIVE.match(line)
        if match:
            return match.group(3)
    return None


def switch(source: str, target: str) -> str:
    url = {"prod": PROD, "uat": UAT}[target]
    lines = source.splitlines(keepends=True)
    for index, raw in enumerate(lines):
        body = raw.rstrip("\r\n")
        match = ACTIVE.match(body)
        if match:
            newline = raw[len(body):]
            lines[index] = f"{match.group(1)}{match.group(2)}{url}{match.group(2)}{match.group(4)}{newline}"
            return "".join(lines)
    raise ValueError(f"no active KEYING_URL line found in {ENTRY}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Show or switch the eCrash site in run_web_ui.py")
    parser.add_argument("command", choices=("status", "prod", "uat"))
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    path = Path(args.root).resolve() / ENTRY
    if not path.is_file():
        print(f"Not the KeyForMe project root (need {ENTRY}): {path.parent}")
        return 2
    raw = path.read_bytes()
    source = raw.decode("utf-8-sig")
    url = current(source)
    if url is None:
        print(f"STOPPED: no active KEYING_URL line in {ENTRY}.")
        return 1
    if args.command == "status":
        print(f"{site_of(url).upper()}: {url}")
        return 0
    updated = switch(source, args.command)
    if updated == source:
        print(f"Already on {site_of(url).upper()}: {url}")
        return 0
    path.write_bytes((b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b"") + updated.encode("utf-8"))
    print(f"Switched to {args.command.upper()}: {current(updated)}")
    if args.command == "uat":
        print("Reminder: switch back with `python tools/set_site.py prod` before committing or building the EXE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
