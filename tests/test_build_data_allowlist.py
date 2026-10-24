"""The EXE data allowlist (tools/build_exe.discover_data): assets are bundled, secrets and report data never are.
Replaces the old test that read the removed build_exe.ps1. Run: python -m pytest tests/test_build_data_allowlist.py -q"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("keyforme_build_exe", ROOT / "tools" / "build_exe.py")
build = importlib.util.module_from_spec(spec)
sys.modules["keyforme_build_exe"] = build
spec.loader.exec_module(build)


def _make(root: Path, names):
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")


def test_assets_are_bundled_and_secrets_are_refused(tmp_path):
    _make(tmp_path, [
        "app/ui/static/index.html", "app/rid_export/sounds/on.wav",
        "app/ui/static/.env", "app/ui/static/.env.local", "app/x/report.pdf", "app/x/app.log",
        "app/x/api_token.json", "app/x/private.pem", "app/x/user_credentials.txt",
    ])
    pairs, refusals = build.discover_data(tmp_path)
    bundled = {Path(source).name for source, _dest in pairs}
    assert {"index.html", "on.wav"} <= bundled
    for secret in (".env", ".env.local", "report.pdf", "app.log", "api_token.json", "private.pem", "user_credentials.txt"):
        assert secret not in bundled
        assert any(item.endswith(secret) for item in refusals), secret


def test_code_caches_and_tests_are_not_bundled(tmp_path):
    _make(tmp_path, ["app/mod.py", "app/__pycache__/mod.pyc", "app/tests/data.json", "app/ui/static/app.css"])
    pairs, refusals = build.discover_data(tmp_path)
    assert {Path(source).name for source, _dest in pairs} == {"app.css"}
    assert refusals == []
