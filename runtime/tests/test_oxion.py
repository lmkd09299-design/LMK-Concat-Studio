"""Oxion provider setup and Windows DPAPI persistence tests."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.oxion_keys import is_oxion, store, load, clear
from core.media import MediaError


class OxionTests(unittest.TestCase):
    def test_oxion_urls(self):
        self.assertTrue(is_oxion("https://www.oxionai.com/v1"))
        self.assertTrue(is_oxion("https://oxionai.com/v1/"))
        self.assertTrue(is_oxion("https://oxionai.com/v1/chat/completions"))
        self.assertFalse(is_oxion("http://oxionai.com/v1"))
        self.assertFalse(is_oxion("https://oxionai.com.attacker.tld/v1"))
        self.assertFalse(is_oxion("https://other.example/v1"))

    def test_empty_key_refused(self):
        with self.assertRaises(MediaError):
            store("")

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI only")
    def test_current_user_dpapi_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {"LOCALAPPDATA": folder}):
                self.assertEqual(load(), "")
                store("cc_local_test_secret_do_not_publish")
                blob = Path(folder, "LMK-Concat-Studio", "oxion.dpapi").read_bytes()
                self.assertNotIn(b"cc_local_test_secret", blob)
                self.assertEqual(load(), "cc_local_test_secret_do_not_publish")
                clear()
                self.assertEqual(load(), "")


if __name__ == "__main__":
    unittest.main()
