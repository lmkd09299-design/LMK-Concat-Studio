"""Oxion provider setup and Windows DPAPI persistence tests."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.oxion_keys import is_oxion, store, load, clear, verify_model_access
from core.media import MediaError


class OxionTests(unittest.TestCase):
    def test_oxion_urls(self):
        self.assertTrue(is_oxion("https://www.oxionai.com/v1"))
        self.assertTrue(is_oxion("https://oxionai.com/v1/"))
        self.assertTrue(is_oxion("https://oxionai.com/v1/chat/completions"))
        self.assertFalse(is_oxion("http://oxionai.com/v1"))
        self.assertFalse(is_oxion("https://oxionai.com.attacker.tld/v1"))
        self.assertFalse(is_oxion("https://other.example/v1"))

    def test_api_preflight_does_not_send_video_or_publish_key(self):
        import io
        import json
        from unittest.mock import patch

        class Response(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *args): self.close()

        def fake_urlopen(req, timeout):
            self.assertEqual(req.full_url, "https://www.oxionai.com/v1/models/deepseek-v4-flash-0731")
            self.assertEqual(req.get_header("Authorization"), "Bearer cc_test_only")
            self.assertEqual(timeout, 15)
            return Response(json.dumps({"id": "deepseek-v4-flash-0731"}).encode("utf-8"))

        with patch("urllib.request.urlopen", fake_urlopen):
            verify_model_access("https://www.oxionai.com/v1", "deepseek-v4-flash-0731", "cc_test_only")

    def test_inference_only_key_can_skip_models_read(self):
        import io
        import json
        from urllib.error import HTTPError

        response = json.dumps({
            "error": {"code": "insufficient_scope", "message": "models:read required"}
        }).encode("utf-8")
        failure = HTTPError("https://www.oxionai.com/v1/models/test-model",
                            403, "Forbidden", {}, io.BytesIO(response))
        with patch("urllib.request.urlopen", side_effect=failure):
            self.assertFalse(verify_model_access(
                "https://www.oxionai.com/v1", "test-model", "cc_inference_only"))

    def test_other_forbidden_models_error_stays_blocking(self):
        import io
        import json
        from urllib.error import HTTPError

        response = json.dumps({
            "error": {"code": "account_suspended", "message": "Blocked"}
        }).encode("utf-8")
        failure = HTTPError("https://www.oxionai.com/v1/models/test-model",
                            403, "Forbidden", {}, io.BytesIO(response))
        with patch("urllib.request.urlopen", side_effect=failure):
            with self.assertRaises(MediaError):
                verify_model_access("https://www.oxionai.com/v1",
                                    "test-model", "cc_account_blocked")

    def test_bad_key_still_rejected(self):
        import io
        from urllib.error import HTTPError
        failure = HTTPError("https://www.oxionai.com/v1/models/test-model",
                            401, "Unauthorized", {}, io.BytesIO(b'{}'))
        with patch("urllib.request.urlopen", side_effect=failure):
            with self.assertRaisesRegex(MediaError, "không hợp lệ"):
                verify_model_access("https://www.oxionai.com/v1",
                                    "test-model", "cc_bad_key")

    def test_missing_key_is_rejected_before_network(self):
        with self.assertRaises(MediaError):
            verify_model_access("https://www.oxionai.com/v1", "deepseek-v4-flash-0731", "")

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
