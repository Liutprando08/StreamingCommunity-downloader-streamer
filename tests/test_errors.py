import errno
import json
import subprocess
import unittest
from unittest import mock

from StreamingCommunity.utils.errors import (
    ErrorInfo,
    friendly_error,
    report_fatal_error,
)
from StreamingCommunity.utils.logging_setup import reset_logging


class _Response:
    def __init__(self, status_code):
        self.status_code = status_code


class _HTTPError(Exception):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.response = _Response(status_code)


class _ReadTimeout(Exception):
    pass


class TestFriendlyError(unittest.TestCase):
    def test_http_auth_error(self):
        info = friendly_error(_HTTPError(403))
        self.assertIn("Access denied", info.message)
        self.assertIn("login", info.hint)

    def test_http_not_found(self):
        info = friendly_error(_HTTPError(404))
        self.assertIn("not found", info.message)
        self.assertIn("domain", info.hint)

    def test_http_rate_limit(self):
        info = friendly_error(_HTTPError(429))
        self.assertIn("Too many requests", info.message)

    def test_http_server_error(self):
        info = friendly_error(_HTTPError(503))
        self.assertIn("503", info.message)

    def test_timeout(self):
        info = friendly_error(_ReadTimeout("slow"))
        self.assertIn("timed out", info.message)

    def test_connection_error(self):
        info = friendly_error(ConnectionError("refused"))
        self.assertIn("connect", info.message)

    def test_missing_external_tool(self):
        info = friendly_error(FileNotFoundError("ffmpeg"))
        self.assertEqual(info.message, "A required external tool is missing.")
        self.assertIn("ffmpeg", info.hint)

    def test_missing_python_dependency(self):
        exc = ModuleNotFoundError("No module named 'foo'", name="foo")
        info = friendly_error(exc)
        self.assertIn("foo", info.message)
        self.assertIn("pip install", info.hint)

    def test_invalid_json(self):
        try:
            json.loads("{")
        except json.JSONDecodeError as exc:
            info = friendly_error(exc)
        else:  # pragma: no cover - json.loads always raises here
            self.fail("expected JSONDecodeError")
        self.assertIn("not valid JSON", info.message)
        self.assertIn("line 1", info.hint)

    def test_no_disk_space(self):
        info = friendly_error(OSError(errno.ENOSPC, "no space"))
        self.assertIn("no space left", info.message.lower())

    def test_external_command(self):
        info = friendly_error(subprocess.CalledProcessError(2, ["ffmpeg"]))
        self.assertIn("exit code 2", info.message)

    def test_keyboard_interrupt(self):
        info = friendly_error(KeyboardInterrupt())
        self.assertEqual(info, ErrorInfo("Interrupted by user."))

    def test_fallback_uses_exception_message(self):
        info = friendly_error(ValueError("boom"))
        self.assertEqual(info.message, "boom")


class TestReportFatalError(unittest.TestCase):
    def setUp(self):
        reset_logging()

    def tearDown(self):
        reset_logging()

    def test_prints_message_and_hint(self):
        with (
            mock.patch("StreamingCommunity.utils.errors.console") as fake_console,
            mock.patch("StreamingCommunity.utils.errors.logger"),
        ):
            report_fatal_error(FileNotFoundError("ffmpeg"))
            printed = " ".join(
                str(call.args[0]) for call in fake_console.print.call_args_list
            )
        self.assertIn("required external tool", printed)
        self.assertIn("ffmpeg", printed)
        fake_console.print_exception.assert_not_called()

    def test_debug_prints_traceback(self):
        with (
            mock.patch("StreamingCommunity.utils.errors.console") as fake_console,
            mock.patch("StreamingCommunity.utils.errors.logger"),
        ):
            report_fatal_error(ValueError("boom"), debug=True)
        fake_console.print_exception.assert_called_once_with(show_locals=False)


if __name__ == "__main__":
    unittest.main()
