"""Tests for tools/build_exe.py (no PyInstaller, no network). Run: python -m pytest tests/test_build_exe.py -q"""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "build_exe.py"
spec = importlib.util.spec_from_file_location("build_exe", SCRIPT)
be = importlib.util.module_from_spec(spec)
sys.modules["build_exe"] = be
spec.loader.exec_module(be)

PROD = 'KEYING_URL = "https://azkeying.ecrash.lexisnexisrisk.com/ecrash/"\n'
UAT = 'KEYING_URL = "https://keying-uat.green.usgov-ecrash-prod.azuregov.lnrsg.io/ecrash/"\n'


def project(tmp_path, entry=PROD, files=None):
    (tmp_path / "app" / "ui" / "static").mkdir(parents=True)
    (tmp_path / "app" / "rid_export" / "sounds").mkdir(parents=True)
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "run_web_ui.py").write_text(entry + "print('x')\n")
    for rel, data in {"app/ui/static/app.js": "x", "app/ui/static/style.css": "x", "app/ui/index.html": "x",
                      "app/rid_export/sounds/copy_successfully.wav": "w", **(files or {})}.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data)
    return tmp_path


def git_init(root, branch="main", commit=True):
    run = lambda *a: subprocess.run(["git", *a], cwd=root, capture_output=True, text=True, check=True)
    run("init", "-b", branch)
    run("config", "user.email", "t@t.t")
    run("config", "user.name", "t")
    run("add", ".")
    if commit:
        run("commit", "-m", "x")


# ------------------------------------------------------------------ KEYING_URL
@pytest.mark.parametrize("src,state", [
    (PROD, "production"), (UAT, "uat"),
    ("# KEYING_URL = 'https://x'\n" + UAT, "uat"),                              # a commented line is ignored
    ("# TESTING\n# " + PROD.strip() + "\n" + UAT, "uat"),
    ("x = 1\n", "unknown"), ("", "unknown"),
])
def test_keying_url_state(src, state):
    assert be.keying_url_state(src)[0] == state


def test_uat_is_refused_unless_allowed_and_unknown_is_always_refused():
    with pytest.raises(be.BuildError, match="UAT"):
        be.check_keying_url(UAT, allow_uat=False)
    assert be.check_keying_url(UAT, allow_uat=True) == "uat"
    assert be.check_keying_url(PROD, allow_uat=False) == "production"
    with pytest.raises(be.BuildError, match="KEYING_URL"):
        be.check_keying_url("x = 1", allow_uat=True)


# ------------------------------------------------------------------ data discovery
def test_ui_assets_and_sounds_are_discovered_file_by_file(tmp_path):
    root = project(tmp_path)
    pairs, refusals = be.discover_data(root)
    dests = {d.replace("\\", "/") for _, d in pairs}
    names = {Path(s).name for s, _ in pairs}
    assert refusals == [] and dests == {"app/ui", "app/ui/static", "app/rid_export/sounds"}
    assert names == {"app.js", "style.css", "index.html", "copy_successfully.wav"}
    assert all(Path(s).is_file() for s, _ in pairs)                         # files, never whole folders


def test_code_tests_and_caches_are_not_bundled(tmp_path):
    root = project(tmp_path, files={"app/core/x.py": "x", "app/core/__pycache__/x.pyc": "x", "app/tests/t.txt": "x", "app/ui/notes.md": "x"})
    pairs = be.discover_data(root)[0]
    dests = {d.replace("\\", "/") for _, d in pairs}
    assert "app/core" not in dests and "app/tests" not in dests and "app/core/__pycache__" not in dests
    assert not any(Path(s).suffix in (".py", ".pyc", ".md") for s, _ in pairs)


@pytest.mark.parametrize("name", ["app/ui/.env", "app/ui/.env.local", "app/x/report.pdf", "app/x/run.log", "app/x/data.db",
                                  "app/x/id.pem", "app/x/api.key", "app/x/credentials.json", "app/x/my_secret.txt", "app/x/token.json"])
def test_secrets_and_report_data_are_refused_not_skipped(tmp_path, name):
    root = project(tmp_path, files={name: "s"})
    pairs, refusals = be.discover_data(root)
    assert refusals == [name]
    assert not any(Path(s).name == Path(name).name for s, _ in pairs)             # the secret itself is never in the bundle list


def test_extra_data_parsing_and_refusal(tmp_path):
    (tmp_path / "ui_static").mkdir()
    assert be.parse_extra_data([f"{tmp_path / 'ui_static'}=ui_static"])[0][1] == "ui_static"
    with pytest.raises(be.BuildError, match="SOURCE=DEST"):
        be.parse_extra_data(["nodest"])
    with pytest.raises(be.BuildError, match="secret"):
        be.parse_extra_data(["C:/x/.env=cfg"])


# ------------------------------------------------------------------ packages
def test_missing_modules_are_reported_and_windows_only_ones_are_skipped_elsewhere():
    nothing = lambda name: None
    on_windows = be.missing_modules(True, find_spec=nothing)
    elsewhere = be.missing_modules(False, find_spec=nothing)
    assert any(m.startswith("keyboard") for m in on_windows) and any(m.startswith("win32com") for m in on_windows)
    assert not any(m.startswith(("keyboard", "win32com", "pythoncom")) for m in elsewhere) and elsewhere
    assert be.missing_modules(True, find_spec=lambda n: object()) == []

    def boom(name):
        raise ImportError

    assert len(be.missing_modules(True, find_spec=boom)) == len(on_windows)


# ------------------------------------------------------------------ the PyInstaller command
def test_command_has_the_flags_the_app_needs(tmp_path):
    root = project(tmp_path)
    pairs, _ = be.discover_data(root)
    cmd = be.build_command(root, pairs, [], windowed=False, find_spec=lambda n: object())
    joined = " ".join(cmd)
    assert cmd[1:3] == ["-m", "PyInstaller"] and "--onefile" in cmd and "--noconfirm" in cmd and "--clean" in cmd
    assert cmd[cmd.index("--name") + 1] == "KeyForMe" and cmd[-1].endswith("run_web_ui.py")
    assert "--windowed" not in cmd
    for needed in ("--collect-submodules app", "--collect-all playwright", "--hidden-import keyboard", "--hidden-import pythoncom",
                   "--hidden-import keyring.backends.Windows", "--collect-submodules uvicorn"):
        assert needed in joined, needed
    adds = [cmd[i + 1] for i, c in enumerate(cmd) if c == "--add-data"]
    assert len(adds) == 4 and all(os.pathsep in a for a in adds)                 # one --add-data per file
    assert any(a.endswith("rid_export" + os.sep + "sounds") for a in adds)


def test_command_skips_modules_that_are_not_installed_but_always_collects_app(tmp_path):
    root = project(tmp_path)
    cmd = be.build_command(root, [], [], windowed=True, find_spec=lambda n: None)
    joined = " ".join(cmd)
    assert "--collect-submodules app" in joined and "--windowed" in cmd
    assert "--hidden-import" not in cmd and "--collect-all" not in cmd and "--collect-submodules uvicorn" not in joined


def test_command_never_contains_a_secret_looking_path(tmp_path):
    root = project(tmp_path, files={"app/ui/.env": "KEY=1"})
    pairs, refusals = be.discover_data(root)
    assert refusals == ["app/ui/.env"]
    assert not any(a.endswith(".env") for a in be.build_command(root, pairs, [], False, find_spec=lambda n: object()))
    assert ".env" not in " ".join(be.build_command(root, pairs, [], False, find_spec=lambda n: object()))


# ------------------------------------------------------------------ git checks
def test_main_and_clean_pass(tmp_path):
    root = project(tmp_path)
    git_init(root)
    branch, commit = be.check_git(root, False, False)
    assert branch == "main" and len(commit) >= 7


def test_other_branch_and_dirty_tree_are_refused(tmp_path):
    root = project(tmp_path)
    git_init(root, branch="feature/x")
    with pytest.raises(be.BuildError, match="not 'main'"):
        be.check_git(root, False, False)
    assert be.check_git(root, False, True)[0] == "feature/x"
    git_init_main = project(tmp_path / "b")
    git_init(git_init_main)
    (git_init_main / "run_web_ui.py").write_text("changed\n")
    with pytest.raises(be.BuildError, match="uncommitted"):
        be.check_git(git_init_main, False, False)
    assert be.check_git(git_init_main, True, False)[0] == "main"


# ------------------------------------------------------------------ the whole script (dry run, no PyInstaller needed)
def dry(root, *args):
    env = dict(os.environ)
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), "--dry-run", *args], capture_output=True, text=True, env=env)


def test_dry_run_prints_the_command_and_builds_nothing(tmp_path, monkeypatch):
    root = project(tmp_path)
    git_init(root)
    monkeypatch.setattr(be, "missing_modules", lambda is_windows, find_spec=None: [])
    code = be.main(["--root", str(root), "--dry-run"])
    assert code == 0 and not (root / "dist").exists() and not (root / "build").exists()


def test_main_stops_on_uat_dirty_branch_missing_packages_and_secrets(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(be, "missing_modules", lambda is_windows, find_spec=None: [])
    root = project(tmp_path / "a", entry=UAT)
    git_init(root)
    assert be.main(["--root", str(root), "--dry-run"]) == 1 and "UAT" in capsys.readouterr().out
    assert be.main(["--root", str(root), "--dry-run", "--allow-uat"]) == 0

    root = project(tmp_path / "b", files={"app/ui/.env": "K=1"})
    git_init(root)
    assert be.main(["--root", str(root), "--dry-run"]) == 1 and "secrets" in capsys.readouterr().out

    root = project(tmp_path / "c")
    git_init(root, branch="work")
    assert be.main(["--root", str(root), "--dry-run"]) == 1 and "not 'main'" in capsys.readouterr().out

    monkeypatch.setattr(be, "missing_modules", lambda is_windows, find_spec=None: ["PyInstaller  (builds the EXE)"])
    root = project(tmp_path / "d")
    git_init(root)
    assert be.main(["--root", str(root), "--dry-run"]) == 1 and "Missing" in capsys.readouterr().out
    assert be.main(["--root", str(tmp_path / "nowhere"), "--dry-run"]) == 1


def test_a_real_build_is_refused_off_windows(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(be, "missing_modules", lambda is_windows, find_spec=None: [])
    monkeypatch.setattr(be.platform, "system", lambda: "Linux")
    root = project(tmp_path)
    git_init(root)
    assert be.main(["--root", str(root)]) == 1 and "Windows" in capsys.readouterr().out


def test_failed_tests_stop_before_pyinstaller(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(be, "missing_modules", lambda is_windows, find_spec=None: [])
    monkeypatch.setattr(be.platform, "system", lambda: "Windows")
    monkeypatch.setattr(be, "run_tests", lambda root: (_ for _ in ()).throw(be.BuildError("Tests failed. Fix them before building.")))
    calls = []
    monkeypatch.setattr(be, "run", lambda cmd, cwd, capture=False: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0, "", ""))
    root = project(tmp_path)
    git_init(root)
    assert be.main(["--root", str(root)]) == 1
    assert not any("PyInstaller" in " ".join(map(str, c)) for c in calls)


def test_a_successful_build_writes_a_manifest_with_the_hash(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(be, "missing_modules", lambda is_windows, find_spec=None: [])
    monkeypatch.setattr(be.platform, "system", lambda: "Windows")
    root = project(tmp_path)
    git_init(root)

    def fake_run(cmd, cwd, capture=False):
        if "PyInstaller" in " ".join(map(str, cmd)):
            (root / "dist").mkdir(exist_ok=True)
            (root / "dist" / "KeyForMe.exe").write_bytes(b"MZ" + b"0" * 2048)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(be, "run", fake_run)
    monkeypatch.setattr(be, "git", lambda root_, *a: {"branch": "main", "status": "", "rev-parse": "abc1234"}[a[0]])
    assert be.main(["--root", str(root), "--skip-tests"]) == 0
    text = (root / "dist" / "KeyForMe.build.txt").read_text()
    exe = root / "dist" / "KeyForMe.exe"
    assert "commit:  abc1234" in text and "site:    PRODUCTION" in text and be.sha256(exe) in text


def test_a_pyinstaller_failure_is_reported(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(be, "missing_modules", lambda is_windows, find_spec=None: [])
    monkeypatch.setattr(be.platform, "system", lambda: "Windows")
    monkeypatch.setattr(be, "git", lambda root_, *a: {"branch": "main", "status": "", "rev-parse": "abc1234"}[a[0]])
    monkeypatch.setattr(be, "run", lambda cmd, cwd, capture=False: subprocess.CompletedProcess(cmd, 1, "", ""))
    root = project(tmp_path)
    assert be.main(["--root", str(root), "--skip-tests"]) == 1
    assert "PyInstaller failed" in capsys.readouterr().out


# ------------------------------------------------------------------ the test step itself
def fake_runner(results):
    calls = []

    def runner(cmd, cwd, capture=False):
        calls.append(cmd)
        key = "pytest" if "pytest" in cmd else "unittest"
        return subprocess.CompletedProcess(cmd, results.get(key, 0), "", "")
    return runner, calls


def test_run_tests_stops_on_a_pytest_failure_and_on_a_shared_core_failure(tmp_path, monkeypatch):
    root = project(tmp_path, files={"tests/test_nj_rules.py": "", "tests/test_shared_core.py": ""})
    runner, calls = fake_runner({"pytest": 1})
    monkeypatch.setattr(be, "run", runner)
    with pytest.raises(be.BuildError, match="Tests failed"):
        be.run_tests(root)
    assert len(calls) == 1                                                       # it did not go on to the next step
    runner, calls = fake_runner({"unittest": 1})
    monkeypatch.setattr(be, "run", runner)
    with pytest.raises(be.BuildError, match="Shared-core"):
        be.run_tests(root)


def test_run_tests_passes_and_only_runs_files_that_exist(tmp_path, monkeypatch):
    root = project(tmp_path, files={"tests/test_nj_rules.py": ""})
    runner, calls = fake_runner({})
    monkeypatch.setattr(be, "run", runner)
    be.run_tests(root)
    pytest_call = next(c for c in calls if "pytest" in c)
    assert "tests/test_nj_rules.py" in pytest_call and "tests/test_nj_form.py" not in pytest_call
    assert not any("unittest" in c for c in calls)                              # no shared-core test file here, none run
