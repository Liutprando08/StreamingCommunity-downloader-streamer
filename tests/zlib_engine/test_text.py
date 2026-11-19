from __future__ import annotations

import unittest

from StreamingCommunity.zlib_engine.text import clean_structure, clean_text, is_bidi_control, loads_clean, strip_control


class TextTests(unittest.TestCase):
    def test_strip_control_keeps_newline_and_tab(self) -> None:
        self.assertEqual(strip_control("a\x1b[31m\n\tb"), "a[31m\n\tb")
        self.assertEqual(strip_control("a\x1bb", ""), "ab")
        self.assertEqual(strip_control("ok\x07"), "ok")

    def test_clean_text_drops_bidi_and_trim(self) -> None:
        self.assertEqual(clean_text("  ok\u202Ehidden\n "), "okhidden")
        self.assertEqual(clean_text("\x1b]52;c;ZXZpbA==\x07title"), "]52;c;ZXZpbA==title")

    def test_bidi_control(self) -> None:
        for char in ("\u200e", "\u200f", "\u061c", "\u202a", "\u202e", "\u2066", "\u2069"):
            self.assertTrue(is_bidi_control(char))
        for char in ("a", "\u200d", "\n"):
            self.assertFalse(is_bidi_control(char))

    def test_clean_structure_rebuilds_keys_and_values(self) -> None:
        cleaned = clean_structure({"a\x1b": ["b\x07", {"c": "d\x1b"}]})
        self.assertEqual(cleaned, {"a": ["b", {"c": "d"}]})

    def test_loads_clean(self) -> None:
        self.assertEqual(
            loads_clean(b'{"title":"Dune\\u001b[31m","authors":["Frank\\u0007"]}'),
            {"title": "Dune[31m", "authors": ["Frank"]},
        )


if __name__ == "__main__":
    unittest.main()
