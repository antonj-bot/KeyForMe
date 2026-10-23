"""Builds the one-file Windows EXE (dist\\KeyForMe.exe) from a clean, tested `main`.

Run from the KeyForMe project root, in the project's virtual environment, ON WINDOWS:

    python tools\\build_exe.py              # full build
    python tools\\build_exe.py --dry-run    # run every check and print the PyInstaller command, build nothing

What it does, in order (any failure stops it before PyInstaller runs):
  1. checks you are on `main`, the working tree is clean, and the app points at the right site
     (the UAT test site is refused unless you pass --allow-uat)
  2. checks every package the EXE needs is installed in this environment
  3. finds every data file under app\\ (UI assets, the Report ID .wav sounds, ...) and bundles it;
     refuses to bundle secrets or report data (.env, .pdf, .log, .db, keys)
  4. runs the NJ / hit-and-run / shared-core tests (skip with --skip-tests)
  5. runs PyInstaller (--onefile) and writes dist\\KeyForMe.build.txt with the commit, the site mode,
     the file size and the SHA-256 of the EXE

The EXE still needs the user's installed Google Chrome (the app launches it with channel="chrome") and
asks for an API key on first launch. Nothing secret is bundled.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
import platform
import re
import subprocess
import sys
from datetime import datetime
from importlib import util as importlib_util
from pathlib import Path

ENTRY = "run_web_ui.py"
EXE_NAME = "KeyForMe"
TEST_FILES = (
    "tests/test_hit_and_run.py", "tests/test_nj_rules.py", "tests/test_nj_extractor.py",
    "tests/test_nj_pipeline.py", "tests/test_dialogs.py", "tests/test_nj_form.py", "tests/test_rid_export.py",
)
SHARED_CORE_TEST = "tests/test_shared_core.py"

# Never bundled, wherever they are found under app\
FORBIDDEN_NAMES = re.compile(
    r"(^\.env.*$|\.pdf$|\.log$|\.db$|\.sqlite3?$|\.pem$|\.key$|\.pfx$|\.p12$|\.keys?$|credential|secret|token|password)", re.I)
IGNORED_SUFFIXES = {".py", ".pyc", ".pyo", ".pyd", ".md", ".txt~", ".bak"}
IGNORED_DIRS = {"__pycache__", "tests", ".git", ".venv", "venv", "node_modules", ".pytest_cache"}
KEEP_TXT_IN = {"sounds"}                  # app\rid_export\sounds\README.txt is harmless; other .txt files are bundled too

# (module to import, needed on Windows only, why)
REQUIRED_MODULES = (
    ("PyInstaller", False, "builds the EXE (pip install pyinstaller)"),
    ("playwright", False, "drives Chrome"),
    ("uvicorn", False, "the local control panel"),
    ("fastapi", False, "the local control panel"),
    ("pydantic", False, "extraction schemas"),
    ("pymupdf", False, "reads the report PDFs"),
    ("openai", False, "the enabled AI provider"),
    ("keyring", False, "stores the API key in Windows Credential Manager"),
    ("keyboard", True, "Report ID hotkeys (pip install keyboard==0.13.5)"),
    ("win32com", True, "Excel link (pip install pywin32==310)"),
    ("pythoncom", True, "Excel link (pip install pywin32==310)"),
)
# Imported by name at run time, so PyInstaller cannot see them on its own.
HIDDEN_IMPORTS = ("keyboard", "pythoncom", "pywintypes", "win32com", "win32com.client", "win32timezone",
                  "tkinter", "tkinter.messagebox", "keyring.backends.Windows",
                  "win32ctypes.pywin32.pywintypes", "win32ctypes.pywin32.win32cred")
COLLECT_SUBMODULES = ("app", "uvicorn", "keyring", "pydantic")
COLLECT_ALL = ("playwright", "pymupdf")        # Playwright ships a Node driver; PyMuPDF ships native libraries
COLLECT_DATA = ("certifi",)


class BuildError(Exception):
    pass


# ------------------------------------------------------------------ checks (pure; unit-tested)
def keying_url_state(source: str) -> tuple[str, str]:
    """('production' | 'uat' | 'unknown', the active KEYING_URL). Commented-out lines are ignored."""
    for line in source.splitlines():
        match = re.match(r"""\s*KEYING_URL\s*=\s*["']([^"']+)["']""", line)
        if match:
            url = match.group(1)
            return ("uat" if "keying-uat" in url.lower() else "production"), url
    return "unknown", ""


def check_keying_url(source: str, allow_uat: bool) -> str:
    state, url = keying_url_state(source)
    if state == "unknown":
        raise BuildError(f"Could not find an active KEYING_URL in {ENTRY}.")
    if state == "uat" and not allow_uat:
        raise BuildError(
            "KEYING_URL still points at the UAT test site. Switch it back to production in run_web_ui.py and "
            "commit, or pass --allow-uat to build a TEST EXE on purpose.")
    return state


def discover_data(root: Path) -> tuple[list[tuple[str, str]], list[str]]:
    """Every non-code file under app\\ -> [(file, destination FOLDER in the EXE)], one entry per file, so
    nothing that was not found and checked here (caches, a stray secret next to an asset) is ever copied.
    Returns (pairs, refusals). A secret-looking file is a refusal, not a silent skip."""
    app_dir = root / "app"
    files: list[Path] = []
    refusals: list[str] = []
    for path in sorted(app_dir.rglob("*")):
        if not path.is_file() or any(part in IGNORED_DIRS for part in path.relative_to(root).parts):
            continue
        if FORBIDDEN_NAMES.search(path.name):
            refusals.append(path.relative_to(root).as_posix())
            continue
        if path.suffix.lower() in IGNORED_SUFFIXES and not (path.suffix.lower() == ".txt" and path.parent.name in KEEP_TXT_IN):
            continue
        files.append(path)
    pairs = [(str(path), path.parent.relative_to(root).as_posix().replace("/", os.sep)) for path in files]
    return pairs, refusals


def missing_modules(is_windows: bool, find_spec=importlib_util.find_spec) -> list[str]:
    out = []
    for name, windows_only, why in REQUIRED_MODULES:
        if windows_only and not is_windows:
            continue
        try:
            found = find_spec(name) is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            out.append(f"{name}  ({why})")
    return out


def installed(name: str, find_spec=importlib_util.find_spec) -> bool:
    try:
        return find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def build_command(root: Path, data_pairs, extra_data, windowed: bool, find_spec=importlib_util.find_spec) -> list[str]:
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--name", EXE_NAME,
           "--distpath", str(root / "dist"), "--workpath", str(root / "build"), "--specpath", str(root / "build")]
    if windowed:
        cmd.append("--windowed")
    for module in HIDDEN_IMPORTS:
        if installed(module.split(".")[0], find_spec):           # only modules that exist in this environment
            cmd += ["--hidden-import", module]
    for module in COLLECT_SUBMODULES:
        if module == "app" or installed(module, find_spec):
            cmd += ["--collect-submodules", module]
    for module in COLLECT_ALL:
        if installed(module, find_spec):
            cmd += ["--collect-all", module]
    for module in COLLECT_DATA:
        if installed(module, find_spec):
            cmd += ["--collect-data", module]
    for source, dest in list(data_pairs) + list(extra_data):
        cmd += ["--add-data", f"{source}{os.pathsep}{dest}"]
    cmd.append(str(root / ENTRY))
    return cmd


def parse_extra_data(values) -> list[tuple[str, str]]:
    pairs = []
    for value in values or []:
        if "=" not in value:
            raise BuildError(f"--extra-data must look like SOURCE=DEST, got: {value}")
        source, dest = value.split("=", 1)
        if FORBIDDEN_NAMES.search(Path(source).name):
            raise BuildError(f"Refusing to bundle {source}: it looks like a secret or report data.")
        pairs.append((str(Path(source).resolve()), dest))
    return pairs


# ------------------------------------------------------------------ steps that touch the machine
def run(cmd, cwd: Path, *, capture=False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=capture)


def git(root: Path, *args) -> str:
    try:
        result = run(["git", *args], root, capture=True)
    except FileNotFoundError as error:
        raise BuildError("git was not found on PATH.") from error
    if result.returncode != 0:
        raise BuildError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def check_git(root: Path, allow_dirty: bool, allow_branch: bool) -> tuple[str, str]:
    branch = git(root, "branch", "--show-current")
    if branch != "main" and not allow_branch:
        raise BuildError(f"You are on '{branch}', not 'main'. Merge to main and build from there (or pass --allow-branch).")
    dirty = git(root, "status", "--porcelain")
    if dirty and not allow_dirty:
        raise BuildError("The working tree has uncommitted changes:\n" + "\n".join("    " + line for line in dirty.splitlines()[:15])
                         + "\nCommit or stash them so the EXE matches a commit (or pass --allow-dirty).")
    return branch, git(root, "rev-parse", "--short", "HEAD")


def run_tests(root: Path) -> None:
    present = [t for t in TEST_FILES if (root / t).is_file()]
    if present:
        print(f"  running {len(present)} pytest file(s)...")
        if run([sys.executable, "-m", "pytest", *present, "-q", "-p", "no:cacheprovider"], root).returncode != 0:
            raise BuildError("Tests failed. Fix them before building.")
    if (root / SHARED_CORE_TEST).is_file():
        print("  running the shared-core tests...")
        if run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_shared_core.py"], root).returncode != 0:
            raise BuildError("Shared-core tests failed. Fix them before building.")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(root: Path, exe: Path, branch: str, commit: str, state: str) -> Path:
    path = exe.with_name(EXE_NAME + ".build.txt")
    path.write_text(
        f"KeyForMe build\nbuilt:   {datetime.now():%Y-%m-%d %H:%M}\nbranch:  {branch}\ncommit:  {commit}\n"
        f"site:    {state.upper()}\nsize:    {exe.stat().st_size / 1_048_576:.1f} MB\nsha256:  {sha256(exe)}\n", encoding="utf-8")
    return path


# ------------------------------------------------------------------ main
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build dist\\KeyForMe.exe")
    parser.add_argument("--root", default=".", help="project root (default: current folder)")
    parser.add_argument("--dry-run", action="store_true", help="run every check, print the command, build nothing")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--allow-uat", action="store_true", help="allow a TEST build that points at the UAT site")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--allow-branch", action="store_true", help="build from a branch other than main")
    parser.add_argument("--windowed", action="store_true", help="no console window (the app logs to the console, so default is off)")
    parser.add_argument("--extra-data", action="append", metavar="SRC=DEST", help="bundle one more folder or file (repeatable)")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    is_windows = platform.system() == "Windows"

    try:
        if not (root / ENTRY).is_file() or not (root / "app").is_dir():
            raise BuildError(f"Not the KeyForMe project root (need {ENTRY} and app\\): {root}")
        print(f"[1/5] Source checks ({root})")
        source = (root / ENTRY).read_text(encoding="utf-8-sig")
        ast.parse(source)
        state = check_keying_url(source, args.allow_uat)
        branch, commit = check_git(root, args.allow_dirty, args.allow_branch)
        print(f"  branch {branch}, commit {commit}, site {state.upper()}")
        if not is_windows:
            print("  NOTE: not Windows. This build would produce a non-Windows binary; use --dry-run to inspect only.")
            if not args.dry_run:
                raise BuildError("Run the build on Windows (PyInstaller cannot cross-compile).")

        print("[2/5] Packages")
        missing = missing_modules(is_windows)
        if missing:
            raise BuildError("Missing in this environment:\n" + "\n".join("    " + m for m in missing)
                             + "\nInstall them in the project's virtual environment, then run again.")
        print("  all required packages are installed")

        print("[3/5] Data files")
        data_pairs, refusals = discover_data(root)
        if refusals:
            raise BuildError("Refusing to bundle files that look like secrets or report data:\n"
                             + "\n".join("    " + r for r in refusals) + "\nMove or delete them, then run again.")
        extra = parse_extra_data(args.extra_data)
        by_dest: dict[str, int] = {}
        for _, dest in data_pairs:
            by_dest[dest] = by_dest.get(dest, 0) + 1
        for dest, count in by_dest.items():
            print(f"  bundle {count} file(s)  ->  {dest}")
        for source_dir, dest in extra:
            print(f"  bundle {Path(source_dir).name}  ->  {dest}  (extra)")
        if not any("sounds" in dest for _, dest in data_pairs):
            print("  NOTE: no sounds folder content found; the Report ID widget will use plain Windows beeps.")
        if not any(dest.replace("\\", "/").startswith("app/ui") for _, dest in data_pairs) and not extra:
            print("  WARNING: no UI asset files found under app\\ui. If your control panel's HTML/JS/CSS live elsewhere, "
                  "pass them with --extra-data \"<folder>=<dest>\" or the EXE's control page will be empty.")

        command = build_command(root, data_pairs, extra, args.windowed)
        if args.dry_run:
            print("\n[dry run] PyInstaller command (one option per line):")
            lines: list[str] = []
            for token in command:
                if token.startswith("--") or not lines:
                    lines.append(token)
                else:
                    lines[-1] += f' "{token}"' if " " in token else f" {token}"
            print("  " + "\n  ".join(lines))
            print("\nDry run finished: nothing was built.")
            return 0

        print("[4/5] Tests")
        if args.skip_tests:
            print("  skipped (--skip-tests)")
        else:
            run_tests(root)

        print("[5/5] PyInstaller (this takes a few minutes)")
        if run(command, root).returncode != 0:
            raise BuildError("PyInstaller failed. Send me the last 30 lines above.")
        exe = root / "dist" / f"{EXE_NAME}.exe"
        if not exe.is_file():
            raise BuildError(f"PyInstaller finished but {exe} was not created.")
        manifest = write_manifest(root, exe, branch, commit, state)
        print(f"\nBuilt {exe}  ({exe.stat().st_size / 1_048_576:.1f} MB)\n{manifest.read_text(encoding='utf-8')}")
        print("Now run the EXE test checklist before giving it to anyone.")
        return 0
    except BuildError as error:
        print(f"\nSTOPPED: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
