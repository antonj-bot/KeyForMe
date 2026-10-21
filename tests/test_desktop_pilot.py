"""Offline unit tests. No real key, browser, or API requests."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("desktop_settings_test", ROOT / "app/desktop_settings.py")
settings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(settings)


class FakeVault:
    def __init__(self):
        self.value = None
    def get_password(self, service, account):
        return self.value
    def set_password(self, service, account, value):
        self.value = value
    def delete_password(self, service, account):
        self.value = None


class CredentialTests(unittest.TestCase):
    def test_save_load_remove(self):
        vault = FakeVault()
        with patch.object(settings, "_vault", return_value=vault), patch.dict(os.environ, {}, clear=False):
            settings.save_key("  FAKE-TEST-CREDENTIAL  ")
            self.assertTrue(settings.sync_environment())
            self.assertEqual(os.environ["OPENAI_API_KEY"], "FAKE-TEST-CREDENTIAL")
            settings.delete_key()
            self.assertFalse(settings.sync_environment())
            self.assertNotIn("OPENAI_API_KEY", os.environ)
    def test_reject_blank_and_whitespace(self):
        with patch.object(settings, "_vault", return_value=FakeVault()):
            for value in ("", " ", "fake key"):
                with self.assertRaises(ValueError):
                    settings.save_key(value)
    def test_vault_failure_has_no_plaintext_fallback(self):
        with patch.object(settings, "_vault", side_effect=RuntimeError("test")):
            with self.assertRaises(RuntimeError):
                settings.save_key("FAKE-TEST-CREDENTIAL")
    def test_no_http_secret_endpoint(self):
        text = (ROOT / "app/ui/server.py").read_text(encoding="utf-8")
        self.assertNotIn("OPENAI_API_KEY", text)
        self.assertIn('"/api/settings"', text)
    def test_build_data_allowlist(self):
        text = (ROOT / "build_exe.ps1").read_text(encoding="utf-8")
        self.assertIn('"app/ui/static:app/ui/static"', text)
        self.assertNotIn('"--add-data", ".', text)


if __name__ == "__main__":
    unittest.main()
