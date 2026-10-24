"""Tests for tools/set_site.py. Run: python -m pytest tests/test_set_site.py -q"""
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "set_site.py"
spec = importlib.util.spec_from_file_location("set_site", SCRIPT)
ss = importlib.util.module_from_spec(spec)
sys.modules["set_site"] = ss
spec.loader.exec_module(ss)

PROD_LINE = f'KEYING_URL = "{ss.PROD}"\n'
UAT_LINE = f'KEYING_URL = "{ss.UAT}"\n'


def test_current_and_site_of():
    assert ss.site_of(ss.current(PROD_LINE)) == "production"
    assert ss.site_of(ss.current(UAT_LINE)) == "uat"
    assert ss.current("x = 1\n") is None


def test_commented_lines_are_ignored():
    source = "# " + PROD_LINE + UAT_LINE
    assert ss.current(source) == ss.UAT
    assert ss.switch(source, "prod") == "# " + PROD_LINE + PROD_LINE


def test_switch_both_ways_and_idempotent():
    assert ss.switch(UAT_LINE, "prod") == PROD_LINE
    assert ss.switch(PROD_LINE, "uat") == UAT_LINE
    assert ss.switch(PROD_LINE, "prod") == PROD_LINE


def test_other_lines_and_crlf_are_kept():
    source = "import os\r\n" + UAT_LINE.replace("\n", "\r\n") + "print(1)\r\n"
    assert ss.switch(source, "prod") == "import os\r\n" + PROD_LINE.replace("\n", "\r\n") + "print(1)\r\n"


def test_missing_line_raises():
    with pytest.raises(ValueError):
        ss.switch("x = 1\n", "prod")


def test_command_line(tmp_path, capsys):
    (tmp_path / "run_web_ui.py").write_text(UAT_LINE + "print('x')\n")
    assert ss.main(["status", "--root", str(tmp_path)]) == 0
    assert "UAT" in capsys.readouterr().out
    assert ss.main(["prod", "--root", str(tmp_path)]) == 0
    assert (tmp_path / "run_web_ui.py").read_text() == PROD_LINE + "print('x')\n"
    assert ss.main(["status", "--root", str(tmp_path / "missing")]) == 2
