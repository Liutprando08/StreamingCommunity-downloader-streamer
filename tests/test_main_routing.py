import argparse
import unittest
from unittest import mock

from StreamingCommunity.cli.run import (
    _keep_console_open,
    _run,
    _should_launch_tui,
    apply_config_updates,
    setup_argument_parser,
)
from StreamingCommunity.utils.site_health import UNREACHABLE, SiteStatus


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
        "use_proxy": None,
        "not_close": None,
        "debug": False,
        "check_sites": False,
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

    def test_not_close_is_a_real_flag(self):
        self.assertIs(self.parser.parse_args(["--not_close"]).not_close, True)
        self.assertIsNone(self.parser.parse_args([]).not_close)

    def test_use_proxy_defaults_to_none(self):
        self.assertIs(self.parser.parse_args(["--use_proxy"]).use_proxy, True)
        self.assertIsNone(self.parser.parse_args([]).use_proxy)

    def test_debug_flag_is_accepted(self):
        self.assertTrue(self.parser.parse_args(["--debug"]).debug)

    def test_check_sites_is_a_cli_only_flag(self):
        args = self.parser.parse_args(["--check-sites"])
        self.assertTrue(args.check_sites)
        with mock.patch("sys.stdout.isatty", return_value=True):
            self.assertFalse(_should_launch_tui(args))

    def test_help_is_grouped(self):
        help_text = self.parser.format_help()
        for heading in (
            "Search:",
            "Interface:",
            "Download and streaming:",
            "Configuration:",
            "Maintenance:",
            "Debugging:",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, help_text)


class TestConfigFlags(unittest.TestCase):
    def test_not_close_forces_keep_open(self):
        with mock.patch("StreamingCommunity.cli.run.config_manager") as cm:
            cm.config.get_bool.return_value = True
            self.assertTrue(_keep_console_open(_args(not_close=True)))

    def test_keep_open_follows_saved_config(self):
        with mock.patch("StreamingCommunity.cli.run.config_manager") as cm:
            cm.config.get_bool.return_value = False
            self.assertTrue(_keep_console_open(_args(not_close=None)))

            cm.config.get_bool.return_value = True
            self.assertFalse(_keep_console_open(_args(not_close=None)))

    def test_absent_flags_do_not_touch_config(self):
        with mock.patch("StreamingCommunity.cli.run.config_manager") as cm:
            apply_config_updates(_args())
            cm.config.set_key.assert_not_called()
            cm.save_config.assert_not_called()

    def test_use_proxy_is_written_only_when_given(self):
        with mock.patch("StreamingCommunity.cli.run.config_manager") as cm:
            apply_config_updates(_args(use_proxy=True))
            cm.config.set_key.assert_called_once_with("REQUESTS", "use_proxy", True)
            cm.save_config.assert_called_once()

    def test_not_close_disables_close_console(self):
        with mock.patch("StreamingCommunity.cli.run.config_manager") as cm:
            apply_config_updates(_args(not_close=True))
            cm.config.set_key.assert_called_once_with("DEFAULT", "close_console", False)
            cm.save_config.assert_called_once()


class TestSiteCheckCommand(unittest.TestCase):
    def _run_check(self, results):
        with (
            mock.patch(
                "StreamingCommunity.cli.run.load_search_functions", return_value={}
            ),
            mock.patch("StreamingCommunity.cli.run.initialize") as initialize,
            mock.patch("StreamingCommunity.cli.run.check_sites", return_value=results),
            mock.patch("StreamingCommunity.cli.run.console"),
        ):
            code = _run(["--check-sites"], debug=False)
        initialize.assert_not_called()
        return code

    def test_all_working_exits_zero(self):
        results = [SiteStatus("site", "https://x.test", "working", 200, 10)]
        self.assertEqual(self._run_check(results), 0)

    def test_unreachable_site_exits_one(self):
        results = [SiteStatus("site", "https://x.test", UNREACHABLE, None, 10, "boom")]
        self.assertEqual(self._run_check(results), 1)

    def test_unknown_does_not_fail_the_command(self):
        results = [SiteStatus("site", "", "unknown")]
        self.assertEqual(self._run_check(results), 0)


if __name__ == "__main__":
    unittest.main()
