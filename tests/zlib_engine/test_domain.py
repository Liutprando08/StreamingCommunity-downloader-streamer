from __future__ import annotations

import unittest
from unittest import mock

from StreamingCommunity.zlib_engine import (
    DomainCheck,
    DomainProbeOptions,
    DomainStatus,
    MirrorUnverified,
    is_built_in_domain,
    parse_allowed_domain,
    parse_mirror_origin,
    probe_domain,
    probe_domains,
    set_user_mirrors,
    user_mirrors,
    verify_user_mirror,
)
from StreamingCommunity.zlib_engine.domain_probe import EAPI_DOMAINS_INFO_PATH
from StreamingCommunity.zlib_engine.errors import ZlibError

from .support import Reply, json_reply, server


class DomainPolicyTests(unittest.TestCase):
    def tearDown(self) -> None:
        set_user_mirrors([])

    def test_parse_allowed_domain(self) -> None:
        cases = {
            "https://z-lib.gd/": "https://z-lib.gd",
            "https://api.z-lib.gl": "https://api.z-lib.gl",
            "https://Z-LIB.SK": "https://z-lib.sk",
            "https://z-library.ec": "https://z-library.ec",
            "https://zlib.bz": "https://zlib.bz",
            "https://z-lib.by": "https://z-lib.by",
            "https://z-library.qa": "https://z-library.qa",
            "https://z-library.website": "https://z-library.website",
            "https://z-library.im": "https://z-library.im",
            "https://z-library.sk": "https://z-library.sk",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(parse_allowed_domain(raw), expected)

    def test_parse_allowed_domain_rejects_unsafe_origins(self) -> None:
        for raw in (
            "https://z-library.gs",
            "https://evil-z-lib.sk",
            "https://z-lib.sk.evil.example",
            "http://z-lib.gd",
            "https://z-lib.gd:8443",
            "https://z-lib.gd/eapi",
            "https://user@z-lib.gd",
            "https://z-lib.gd?x=1",
            "https://z-lib.gd#frag",
            "z-lib.gd",
        ):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_allowed_domain(raw)

    def test_parse_mirror_origin(self) -> None:
        self.assertEqual(parse_mirror_origin("mirror.example"), "https://mirror.example")
        self.assertEqual(parse_mirror_origin("https://Mirror.Example/"), "https://mirror.example")
        for raw in (
            "http://mirror.example",
            "https://mirror.example:8443",
            "https://mirror.example/path",
            "https://user@mirror.example",
            "https://127.0.0.1",
            "https://localhost",
            "https://bad_host.example",
            "https://-bad.example",
        ):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_mirror_origin(raw)

    def test_user_mirrors_apply_valid_entries_and_report_invalid(self) -> None:
        with self.assertRaises(ValueError) as caught:
            set_user_mirrors(["mirror.example", "http://bad.example"])
        self.assertIn("bad.example", str(caught.exception))
        self.assertEqual(user_mirrors(), ["https://mirror.example"])
        self.assertEqual(parse_allowed_domain("https://mirror.example"), "https://mirror.example")
        with self.assertRaises(ValueError):
            parse_allowed_domain("https://sub.mirror.example")
        self.assertFalse(is_built_in_domain("mirror.example"))
        self.assertTrue(is_built_in_domain("https://z-lib.gd"))

    def test_user_mirrors_are_exact_hosts(self) -> None:
        set_user_mirrors(["mirror.example"])
        # User mirrors never widen to another zone.
        with self.assertRaises(ValueError):
            parse_allowed_domain("https://notmirror.example")

    def test_allowed_suffixes_returns_copy(self) -> None:
        from StreamingCommunity.zlib_engine import allowed_domain_suffixes

        first = allowed_domain_suffixes()
        first.append("evil.example")
        self.assertNotIn("evil.example", allowed_domain_suffixes())


class DomainProbeTests(unittest.TestCase):
    def test_healthy(self) -> None:
        with server(lambda request: Reply(body="<html>ok</html>", headers={"Content-Type": "text/html"})) as srv:
            check = probe_domain(srv.url)
            self.assertEqual(check.status, DomainStatus.HEALTHY)
            self.assertEqual(check.http_status, 200)

    def test_challenge(self) -> None:
        body = "<html><script>'%s','c_token=abc'</script></html>" % ("A" * 40)
        with server(lambda request: Reply(body=body, headers={"Content-Type": "text/html"})) as srv:
            check = probe_domain(srv.url)
            self.assertEqual(check.status, DomainStatus.CHALLENGED)

    def test_diamwall_status(self) -> None:
        with server(lambda request: Reply(status=513, body="blocked")) as srv:
            check = probe_domain(srv.url)
            self.assertEqual(check.status, DomainStatus.DIAMWALL_BLOCKED)
            self.assertEqual(check.http_status, 513)

    def test_diamwall_title(self) -> None:
        body = "<html><title>Verifying your browser - DiamWall</title></html>"
        with server(lambda request: Reply(body=body, headers={"Content-Type": "text/html"})) as srv:
            check = probe_domain(srv.url)
            self.assertEqual(check.status, DomainStatus.DIAMWALL_BLOCKED)

    def test_mentioning_diamwall_is_still_healthy(self) -> None:
        body = "<html><body>books about diamwall</body></html>"
        with server(lambda request: Reply(body=body, headers={"Content-Type": "text/html"})) as srv:
            check = probe_domain(srv.url)
            self.assertEqual(check.status, DomainStatus.HEALTHY)

    def test_clearance_cookie_does_not_mean_blocked(self) -> None:
        def app(request):
            return Reply(
                body="<html>ok</html>",
                headers={"Content-Type": "text/html", "Set-Cookie": "__diamwall=clearance"},
            )

        with server(app) as srv:
            check = probe_domain(srv.url)
            self.assertEqual(check.status, DomainStatus.HEALTHY)

    def test_redirect_loop(self) -> None:
        def app(request):
            return Reply(status=302, headers={"Location": "/a" if request.path == "/" else "/"})

        with server(app) as srv:
            check = probe_domain(srv.url)
            self.assertEqual(check.status, DomainStatus.REDIRECT_LOOP)

    def test_redirect_to_healthy(self) -> None:
        def app(request):
            if request.path == "/":
                return Reply(status=301, headers={"Location": "/ok"})
            return Reply(body="<html>ok</html>", headers={"Content-Type": "text/html"})

        with server(app) as srv:
            check = probe_domain(srv.url)
            self.assertEqual(check.status, DomainStatus.HEALTHY)
            self.assertTrue(check.final_url.endswith("/ok"))

    def test_eapi_requires_json(self) -> None:
        with server(lambda request: Reply(body="<html>not json</html>")) as srv:
            check = probe_domain(srv.url, DomainProbeOptions(path=EAPI_DOMAINS_INFO_PATH))
            self.assertEqual(check.status, DomainStatus.HTTP_ERROR)
            self.assertIn("non-JSON", check.detail)

    def test_eapi_domains_probe_recognizes_zlibrary(self) -> None:
        with server(
            lambda request: json_reply({"success": 1, "domains": ["https://z-lib.gd"]})
        ) as srv:
            check = probe_domain(srv.url, DomainProbeOptions(path=EAPI_DOMAINS_INFO_PATH))
            self.assertEqual(check.status, DomainStatus.HEALTHY)
            self.assertTrue(check.zlib_eapi)

    def test_eapi_domains_probe_rejects_other_json(self) -> None:
        with server(lambda request: json_reply({"success": 0})) as srv:
            check = probe_domain(srv.url, DomainProbeOptions(path=EAPI_DOMAINS_INFO_PATH))
            self.assertEqual(check.status, DomainStatus.HEALTHY)
            self.assertFalse(check.zlib_eapi)

    def test_http_failure(self) -> None:
        with server(lambda request: Reply(status=500, body="boom")) as srv:
            check = probe_domain(srv.url)
            self.assertEqual(check.status, DomainStatus.HTTP_ERROR)
            self.assertEqual(check.http_status, 500)

    def test_invalid_domain_and_path(self) -> None:
        self.assertEqual(probe_domain("z-lib.gd").status, DomainStatus.INVALID_DOMAIN)
        with server(lambda request: Reply(body="ok")) as srv:
            check = probe_domain(srv.url, DomainProbeOptions(path="https://evil.example/x"))
            self.assertEqual(check.status, DomainStatus.INVALID_DOMAIN)

    def test_probe_domains_preserves_order(self) -> None:
        with server(lambda request: Reply(body="ok")) as srv:
            checks = probe_domains([srv.url, srv.url])
            self.assertEqual([check.status for check in checks], [DomainStatus.HEALTHY] * 2)

    def test_verify_user_mirror(self) -> None:
        check = DomainCheck(
            domain="https://mirror.example",
            status=DomainStatus.HEALTHY,
            final_url="https://mirror.example",
            zlib_eapi=True,
        )
        with mock.patch("StreamingCommunity.zlib_engine.domain_probe.probe_domain_with_options", return_value=check):
            self.assertIs(verify_user_mirror("mirror.example"), check)

        for bad in (
            DomainCheck("https://mirror.example", DomainStatus.HTTP_ERROR, detail="boom"),
            DomainCheck(
                "https://mirror.example",
                DomainStatus.HEALTHY,
                final_url="https://other.example",
                zlib_eapi=True,
            ),
            DomainCheck(
                "https://mirror.example",
                DomainStatus.HEALTHY,
                final_url="https://mirror.example",
                zlib_eapi=False,
            ),
        ):
            with mock.patch(
                "StreamingCommunity.zlib_engine.domain_probe.probe_domain_with_options", return_value=bad
            ), self.assertRaises(MirrorUnverified):
                verify_user_mirror("mirror.example")

    def test_verify_user_mirror_rejects_plain_http(self) -> None:
        with self.assertRaises(ValueError):
            verify_user_mirror("http://mirror.example")

    def test_probe_reports_network_error(self) -> None:
        check = probe_domain("http://127.0.0.1:1")
        self.assertEqual(check.status, DomainStatus.NETWORK_ERROR)


__all__ = ["ZlibError"]
