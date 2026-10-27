import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from StreamingCommunity.utils.logging_setup import (
    LOG_FILENAME,
    get_log_path,
    redact,
    reset_logging,
    setup_logging,
)


class TestRedact(unittest.TestCase):
    def test_query_token_and_signature_are_masked(self):
        text = redact("https://cdn.example/x.m3u8?token=abc123&sig=deadbeef&n=1")
        self.assertIn("token=***", text)
        self.assertIn("sig=***", text)
        self.assertIn("n=1", text)
        self.assertNotIn("abc123", text)
        self.assertNotIn("deadbeef", text)

    def test_bearer_token_is_masked(self):
        text = redact("Bearer abc.def-123")
        self.assertEqual(text, "Bearer ***")

    def test_cookie_header_is_masked(self):
        text = redact("Cookie: sessionid=supersecret")
        self.assertIn("Cookie: ***", text)
        self.assertNotIn("supersecret", text)

    def test_authorization_header_is_masked(self):
        text = redact("Authorization: Bearer abc.def-123")
        self.assertEqual(text, "Authorization: ***")

    def test_plain_text_is_unchanged(self):
        self.assertEqual(redact("hello world"), "hello world")


class TestSetupLogging(unittest.TestCase):
    def setUp(self):
        reset_logging()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def tearDown(self):
        reset_logging()

    def _managed(self, predicate):
        return [
            handler for handler in logging.getLogger().handlers if predicate(handler)
        ]

    def test_writes_redacted_lines_to_file(self):
        path = setup_logging(log_dir=self._tmp.name)
        self.assertEqual(Path(path).name, LOG_FILENAME)

        logging.getLogger("StreamingCommunity.tests").warning(
            "request %s", "https://x/y?token=secret"
        )
        for handler in logging.getLogger().handlers:
            handler.flush()

        contents = Path(path).read_text(encoding="utf-8")
        self.assertIn("StreamingCommunity.tests", contents)
        self.assertIn("token=***", contents)
        self.assertNotIn("secret", contents)

    def test_repeated_calls_do_not_duplicate_handlers(self):
        setup_logging(log_dir=self._tmp.name)
        setup_logging(log_dir=self._tmp.name)

        file_handlers = self._managed(
            lambda handler: getattr(handler, "_oste_file_handler", False)
        )
        self.assertEqual(len(file_handlers), 1)

    def test_stream_handler_only_when_requested(self):
        setup_logging(log_dir=self._tmp.name)
        self.assertEqual(
            len(
                self._managed(
                    lambda handler: getattr(handler, "_oste_stream_handler", False)
                )
            ),
            0,
        )

        setup_logging(debug=True, stream=True, log_dir=self._tmp.name)
        self.assertEqual(
            len(
                self._managed(
                    lambda handler: getattr(handler, "_oste_stream_handler", False)
                )
            ),
            1,
        )

        setup_logging(log_dir=self._tmp.name)
        self.assertEqual(
            len(
                self._managed(
                    lambda handler: getattr(handler, "_oste_stream_handler", False)
                )
            ),
            0,
        )

    def test_sc_log_dir_override(self):
        with mock.patch.dict(os.environ, {"SC_LOG_DIR": self._tmp.name}):
            self.assertEqual(get_log_path(), Path(self._tmp.name) / LOG_FILENAME)

    def test_reset_removes_managed_handlers(self):
        setup_logging(log_dir=self._tmp.name)
        reset_logging()
        self.assertEqual(
            self._managed(
                lambda handler: getattr(handler, "_oste_file_handler", False)
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
