import argparse
import unittest
from unittest import mock

from StreamingCommunity.cli.run import _should_launch_tui, setup_argument_parser


def _args(**overrides):
    """Build a Namespace with just the fields the router inspects."""
    base = {
        "cli": False,
        "tui": False,
        "site": None,
        "search": None,
        "auto_first": False,
        "global": False,
        "update": False,
        "stream": False,
        "player": None,
        "stream_port": 0,
        "extension": None,
        "s_video": None,
        "s_audio": None,
        "s_subtitle": None,
        "use_proxy": False,
        "not_close": None,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


class TestShouldLaunchTui(unittest.TestCase):
    def _route(self, args, *, tty):
        with mock.patch("sys.stdout.isatty", return_value=tty):
            return _should_launch_tui(args)

    def test_bare_interactive_launches_tui(self):
        self.assertTrue(self._route(_args(), tty=True))

    def test_bare_non_tty_falls_back_to_cli(self):
        self.assertFalse(self._route(_args(), tty=False))

    def test_cli_flag_forces_cli(self):
        self.assertFalse(self._route(_args(cli=True), tty=True))

    def test_tui_flag_forces_tui(self):
        self.assertTrue(self._route(_args(tui=True), tty=False))

    def test_tui_wins_over_cli_only_flags(self):
        self.assertTrue(self._route(_args(tui=True, search="dune"), tty=False))

    def test_cli_wins_over_tui_when_both_given(self):
        self.assertFalse(self._route(_args(cli=True, tui=True), tty=True))

    def test_site_search_flags_fall_back_to_cli(self):
        self.assertFalse(self._route(_args(site="1", search="dune"), tty=True))

    def test_each_cli_only_flag_falls_back_to_cli(self):
        cases = {
            "site": "streamingcommunity",
            "search": "dune",
            "auto_first": True,
            "global": True,
            "update": True,
            "stream": True,
            "player": "mpv",
            "stream_port": 8080,
            "extension": "mkv",
            "s_video": "best",
            "s_audio": "all",
            "s_subtitle": "all",
            "use_proxy": True,
            "not_close": True,
        }
        for name, value in cases.items():
            with self.subTest(flag=name):
                self.assertFalse(self._route(_args(**{name: value}), tty=True))


class TestArgumentParserInterfaceFlags(unittest.TestCase):
    def setUp(self):
        # An empty registry keeps the parser build cheap (no site discovery).
        self.parser = setup_argument_parser({})

    def test_cli_flag_is_accepted(self):
        args = self.parser.parse_args(["--cli"])
        self.assertTrue(args.cli)
        self.assertFalse(args.tui)

    def test_tui_flag_still_accepted(self):
        args = self.parser.parse_args(["--tui"])
        self.assertTrue(args.tui)
        self.assertFalse(args.cli)

    def test_both_default_to_false(self):
        args = self.parser.parse_args([])
        self.assertFalse(args.cli)
        self.assertFalse(args.tui)

    def test_routing_of_parsed_bare_invocation(self):
        args = self.parser.parse_args([])
        with mock.patch("sys.stdout.isatty", return_value=True):
            self.assertTrue(_should_launch_tui(args))

    def test_routing_of_parsed_cli_invocation(self):
        args = self.parser.parse_args(["--site", "1", "--search", "dune"])
        with mock.patch("sys.stdout.isatty", return_value=True):
            self.assertFalse(_should_launch_tui(args))


if __name__ == "__main__":
    unittest.main()
