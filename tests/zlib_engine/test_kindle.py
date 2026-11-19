from __future__ import annotations

import email
import os
import tempfile
import unittest

from StreamingCommunity.zlib_engine.kindle import (
    KindleConfig,
    build_kindle_message,
    send_to_kindle,
    validate_kindle_attachment,
)


def config(**overrides) -> KindleConfig:
    values = {
        "to": "reader@kindle.com",
        "from_": "you@example.com",
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
    }
    values.update(overrides)
    return KindleConfig(**values)


class KindleConfigTests(unittest.TestCase):
    def test_security_follows_port_unless_explicit(self) -> None:
        self.assertEqual(config(smtp_port=465).security(), "tls")
        self.assertEqual(config(smtp_port=587).security(), "starttls")
        self.assertEqual(config(smtp_port=465, smtp_security="starttls").security(), "starttls")

    def test_validate_requires_fields(self) -> None:
        for bad in (
            config(to=""),
            config(from_=""),
            config(smtp_host=""),
            config(smtp_port=0),
            config(smtp_security="plain"),
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                bad.validate()

    def test_attachment_type_and_limits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            plain = os.path.join(directory, "book.epub")
            with open(plain, "wb") as handle:
                handle.write(b"x")
            validate_kindle_attachment(plain, config())

            no_ext = os.path.join(directory, "book")
            open(no_ext, "wb").close()
            with self.assertRaises(ValueError):
                validate_kindle_attachment(no_ext, config())

            bad = os.path.join(directory, "book.exe")
            open(bad, "wb").close()
            with self.assertRaises(ValueError):
                validate_kindle_attachment(bad, config())

            huge = os.path.join(directory, "huge.pdf")
            with open(huge, "wb") as handle:
                handle.truncate(200 * 1024 * 1024 + 1)
            with self.assertRaises(ValueError) as caught:
                validate_kindle_attachment(huge, config())
            self.assertIn("200 MB", str(caught.exception))

            gmail = os.path.join(directory, "gmail.epub")
            with open(gmail, "wb") as handle:
                handle.truncate(20 * 1024 * 1024)
            with self.assertRaises(ValueError) as caught:
                validate_kindle_attachment(gmail, config(smtp_host="smtp.gmail.com"))
            self.assertIn("25 MB", str(caught.exception))

    def test_send_requires_password_before_network(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "book.epub")
            with open(path, "wb") as handle:
                handle.write(b"x")
            with self.assertRaises(ValueError):
                send_to_kindle(path, config(), "")

    def test_build_message_encodes_ascii_attachment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "Dune.epub")
            with open(path, "wb") as handle:
                handle.write(b"book-bytes")
            message = email.message_from_bytes(build_kindle_message(path, config()))
            self.assertEqual(message["Subject"], "Send to Kindle")
            self.assertEqual(message.get_content_type(), "multipart/mixed")
            parts = list(message.walk())
            attachment = parts[-1]
            self.assertEqual(attachment.get_filename(), "Dune.epub")
            self.assertEqual(attachment.get_payload(decode=True), b"book-bytes")

    def test_build_message_encodes_unicode_filename(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "Дюна.epub")
            with open(path, "wb") as handle:
                handle.write(b"book-bytes")
            raw = build_kindle_message(path, config())
            text = raw.decode("utf-8")
            self.assertIn("filename*=UTF-8''", text)
            self.assertIn("attachment.epub", text)
            message = email.message_from_bytes(raw)
            attachment = list(message.walk())[-1]
            self.assertEqual(attachment.get_payload(decode=True), b"book-bytes")


if __name__ == "__main__":
    unittest.main()
