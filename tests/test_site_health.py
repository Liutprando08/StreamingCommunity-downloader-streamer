import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from StreamingCommunity.utils import site_health
from StreamingCommunity.utils.site_health import (
    UNKNOWN,
    UNREACHABLE,
    WORKING,
    SiteStatus,
    check_site,
    check_sites,
    discover_sites,
    render_table,
    status_text,
    summary_counts,
)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/error":
            self.send_response(503)
        elif self.path == "/forbidden":
            self.send_response(403)
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/ok")
        else:
            self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):  # silence test server output
        pass


class TestCheckSite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_working_site(self):
        result = check_site("site", f"{self.base}/ok", timeout=5)
        self.assertEqual(result.status, WORKING)
        self.assertEqual(result.http_status, 200)
        self.assertIsNotNone(result.latency_ms)

    def test_client_error_is_still_reachable(self):
        result = check_site("site", f"{self.base}/forbidden", timeout=5)
        self.assertEqual(result.status, WORKING)
        self.assertEqual(result.http_status, 403)
        self.assertIn("block bots", result.detail)

    def test_server_error_is_unreachable(self):
        result = check_site("site", f"{self.base}/error", timeout=5)
        self.assertEqual(result.status, UNREACHABLE)
        self.assertEqual(result.http_status, 503)

    def test_redirect_records_final_url(self):
        result = check_site("site", f"{self.base}/redirect", timeout=5)
        self.assertEqual(result.status, WORKING)
        self.assertIn("redirected to", result.detail)
        self.assertIn("/ok", result.detail)

    def test_missing_url_is_unknown(self):
        result = check_site("site", "", timeout=5)
        self.assertEqual(result.status, UNKNOWN)
        self.assertIn("no domain", result.detail)

    def test_connection_error_is_unreachable(self):
        result = check_site("dead", "http://127.0.0.1:1", timeout=1)
        self.assertEqual(result.status, UNREACHABLE)
        self.assertTrue(result.detail)

    def test_check_sites_preserves_registry_order(self):
        sites = [("second", f"{self.base}/ok"), ("first", f"{self.base}/ok")]
        results = check_sites(sites, timeout=5)
        self.assertEqual([result.name for result in results], ["second", "first"])


class TestDiscoveryAndReport(unittest.TestCase):
    def test_fallback_url_used_when_not_configured(self):
        with mock.patch.object(
            site_health.config_manager.domain, "get", return_value=""
        ):
            self.assertEqual(
                site_health.configured_url("raiplay"), "https://www.raiplay.it"
            )
            self.assertEqual(site_health.configured_url("torrent"), "")

    def test_discover_sites_covers_registry_in_order(self):
        with mock.patch.object(
            site_health.config_manager.domain, "get", return_value=""
        ):
            sites = discover_sites()
        names = [name for name, _ in sites]
        self.assertEqual(names[0], "streamingcommunity")
        self.assertIn("mangaworld", names)
        by_name = dict(sites)
        self.assertEqual(by_name["raiplay"], "https://www.raiplay.it")
        self.assertEqual(by_name["torrent"], "")

    def test_summary_counts(self):
        counts = summary_counts(
            [
                SiteStatus("a", "u", WORKING),
                SiteStatus("b", "u", UNREACHABLE),
                SiteStatus("c", "", UNKNOWN),
                SiteStatus("d", "u", WORKING),
            ]
        )
        self.assertEqual(counts, {WORKING: 2, UNREACHABLE: 1, UNKNOWN: 1})

    def test_status_text_is_localised(self):
        self.assertEqual(status_text(WORKING), "Working")
        self.assertEqual(status_text(WORKING, italian=True), "Funzionante")
        self.assertEqual(status_text("nonsense"), "Unknown")

    def test_render_table_contains_labels(self):
        table = render_table(
            [
                SiteStatus("alpha", "https://a.test", WORKING, 200, 12),
                SiteStatus("beta", "", UNKNOWN),
            ]
        )
        headers = [column.header for column in table.columns]
        self.assertEqual(headers, ["Site", "Status", "HTTP", "Latency", "URL / note"])


if __name__ == "__main__":
    unittest.main()
