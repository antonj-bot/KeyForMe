"""Tests for tools/make_requirements.py. Run: python -m pytest tests/test_make_requirements.py -q"""
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "make_requirements.py"
spec = importlib.util.spec_from_file_location("make_requirements", SCRIPT)
mr = importlib.util.module_from_spec(spec)
sys.modules["make_requirements"] = mr
spec.loader.exec_module(mr)
REAL_BUILD = mr.build                      # the tests below replace mr.build, so keep the real one

DISTS = {"playwright": ["playwright"], "uvicorn": ["uvicorn"], "fastapi": ["fastapi"], "fitz": ["PyMuPDF"], "pymupdf": ["PyMuPDF"],
         "openai": ["openai"], "keyring": ["keyring"], "keyboard": ["keyboard"], "win32com": ["pywin32"], "pythoncom": ["pywin32"],
         "pytest": ["pytest"], "PIL": ["pillow"], "PyInstaller": ["pyinstaller"], "pydantic": ["pydantic"]}
VERSIONS = {"playwright": "1.64.0", "uvicorn": "0.54.0", "fastapi": "0.136.3", "PyMuPDF": "1.26.1", "openai": "2.1.0", "keyring": "25.6.0",
            "keyboard": "0.13.5", "pywin32": "310", "pytest": "9.1.1", "pillow": "11.0.0", "pyinstaller": "6.22.3", "pydantic": "2.11.0",
            "pytest-timeout": "2.5.0"}


def project(tmp_path, runtime=None, dev=None):
    (tmp_path / "app" / "core").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tools").mkdir()
    for p in (tmp_path / "app", tmp_path / "app" / "core"):
        (p / "__init__.py").write_text("")
    (tmp_path / "run_web_ui.py").write_text("import os, sys\nimport uvicorn\nfrom app.core import x\nfrom playwright.sync_api import sync_playwright\n")
    (tmp_path / "app" / "core" / "x.py").write_text(runtime or "import json\nfrom pydantic import BaseModel\n")
    (tmp_path / "tests" / "test_a.py").write_text(dev or "import pytest\nimport uvicorn\nfrom app.core import x\n")
    return tmp_path


def build(root, versions=VERSIONS, mapping=DISTS):
    return REAL_BUILD(root, mapping=mapping, version_of=lambda d: versions.get(d))


def test_runtime_dev_split_and_pins(tmp_path):
    runtime, dev, rmiss, dmiss = build(project(tmp_path))
    assert runtime == ["playwright==1.64.0", "pydantic==2.11.0", "uvicorn==0.54.0"]
    assert "pytest==9.1.1" in dev and "pyinstaller==6.22.3" in dev and "pytest-timeout==2.5.0" in dev
    assert not any(line.startswith(("uvicorn", "playwright")) for line in dev)           # a runtime package is never repeated in dev
    assert rmiss == [] and dmiss == []


def test_stdlib_local_modules_and_relative_imports_are_ignored(tmp_path):
    root = project(tmp_path, runtime="import json, os, tkinter, dataclasses\nfrom . import sibling\nfrom .core import y\nimport app\nimport run_web_ui\n")
    runtime, *_ = build(root)
    assert runtime == ["playwright==1.64.0", "uvicorn==0.54.0"]


def test_imports_inside_functions_and_try_blocks_are_found(tmp_path):
    root = project(tmp_path, runtime="def f():\n    import keyring\ntry:\n    import openai\nexcept ImportError:\n    openai = None\n")
    runtime, *_ = build(root)
    assert "keyring==25.6.0" in runtime and "openai==2.1.0" in runtime


def test_windows_only_package_gets_a_marker_and_two_imports_give_one_line(tmp_path):
    root = project(tmp_path, runtime="import win32com.client\nimport pythoncom\nimport keyboard\n")
    runtime, *_ = build(root)
    assert runtime.count('pywin32==310; sys_platform == "win32"') == 1 and "keyboard==0.13.5" in runtime


def test_import_name_differs_from_package_name(tmp_path):
    root = project(tmp_path, runtime="import fitz\n")
    assert "PyMuPDF==1.26.1" in build(root)[0]


def test_imported_but_not_installed_is_reported_not_guessed(tmp_path):
    root = project(tmp_path, runtime="import anthropic\nimport boto3\nimport openai\n")
    runtime, dev, rmiss, dmiss = build(root)
    assert "openai==2.1.0" in runtime and not any("anthropic" in line or "boto3" in line for line in runtime)
    assert sorted(rmiss) == ["anthropic", "boto3"]
    runtime, dev, rmiss, dmiss = build(root, versions={k: v for k, v in VERSIONS.items() if k != "openai"})
    assert any("openai" in m and "package 'openai'" in m for m in rmiss)


def test_dev_tools_used_by_name_are_added_only_when_installed(tmp_path):
    root = project(tmp_path)
    _, dev, _, dmiss = build(root, versions={k: v for k, v in VERSIONS.items() if k != "pyinstaller"})
    assert not any(line.startswith("pyinstaller") for line in dev) and any("pyinstaller" in m for m in dmiss)


def test_broken_source_files_do_not_stop_the_scan(tmp_path):
    root = project(tmp_path)
    (root / "app" / "core" / "broken.py").write_text("def (:\n")
    assert "uvicorn==0.54.0" in build(root)[0]


def test_files_in_ignored_folders_are_not_scanned(tmp_path):
    root = project(tmp_path)
    (root / "app" / "build").mkdir()
    (root / "app" / "build" / "old.py").write_text("import openai\n")
    (root / "app" / "__pycache__").mkdir()
    (root / "app" / "__pycache__" / "z.py").write_text("import keyring\n")
    runtime, *_ = build(root)
    assert not any(line.startswith(("openai", "keyring")) for line in runtime)


def test_normalize_and_rendering():
    assert mr.normalize("PyMuPDF") == "pymupdf" and mr.normalize("Typing_Extensions") == "typing-extensions"
    text = mr.render_runtime(["a==1", "b==2"])
    assert text.endswith("a==1\nb==2\n") and "Generated by tools/make_requirements.py" in text
    assert "-r requirements.txt" in mr.render_dev(["pytest==9"])


def test_main_writes_both_files_keeps_crlf_and_check_detects_drift(tmp_path, monkeypatch, capsys):
    root = project(tmp_path)
    monkeypatch.setattr(mr.metadata, "packages_distributions", lambda: DISTS)
    monkeypatch.setattr(mr, "installed_version", lambda d: VERSIONS.get(d))
    monkeypatch.setattr(mr, "build", lambda r, mapping=None, version_of=None: build(r))
    (root / "requirements.txt").write_bytes(b"old\r\n")
    assert mr.main(["--root", str(root), "--check"]) == 1 and "Out of date" in capsys.readouterr().out
    assert (root / "requirements.txt").read_bytes() == b"old\r\n"                       # --check writes nothing
    assert mr.main(["--root", str(root)]) == 0
    raw = (root / "requirements.txt").read_bytes()
    assert b"\r\n" in raw and b"playwright==1.64.0" in raw and b"uvicorn==0.54.0" in raw        # CRLF kept
    assert (root / "requirements-dev.txt").read_text().startswith("# Generated")
    assert mr.main(["--root", str(root), "--check"]) == 0 and "Up to date" in capsys.readouterr().out


def test_main_fails_when_a_runtime_import_has_no_installed_package(tmp_path, monkeypatch, capsys):
    root = project(tmp_path, runtime="import anthropic\n")
    monkeypatch.setattr(mr, "build", lambda r, mapping=None, version_of=None: build(r))
    assert mr.main(["--root", str(root)]) == 1 and "NO installed package" in capsys.readouterr().out


def test_main_refuses_a_folder_that_is_not_the_project(tmp_path, capsys):
    assert mr.main(["--root", str(tmp_path)]) == 2
