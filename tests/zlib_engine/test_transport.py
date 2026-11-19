from __future__ import annotations

import os
import unittest

from StreamingCommunity.zlib_engine import Client, RedirectLoop, current_default_domain, set_default_domain
from StreamingCommunity.zlib_engine.constants import ENV_DOMAIN

from .support import Reply, server


class RedirectTests(unittest.TestCase):
    def test_redirect_loop_is_capped(self) -> None:
        def app(request):
            return Reply(status=302, headers={"Location": "/loop"})

        with server(app) as srv:
            client = Client(domain=srv.url)
            with self.assertRaises(RedirectLoop):
                client._request("GET", srv.url + "/start")

    def test_cross_origin_redirect_strips_remix_and_cookie_headers(self) -> None:
        captured = {}

        def destination(request):
            captured.update(request.headers)
            return Reply(body=b"ok")

        with server(destination) as target, server(
            lambda request: Reply(status=302, headers={"Location": target.url + "/final"})
        ) as origin:
            client = Client(domain=origin.url)
            client._request(
                "GET",
                origin.url + "/start",
                None,
                {
                    "remix-userid": "1",
                    "remix-userkey": "secret",
                    "Cookie": "remix_userid=1; remix_userkey=secret",
                },
            )
            self.assertNotIn("remix-userid", captured)
            self.assertNotIn("remix-userkey", captured)
            self.assertNotIn("cookie", captured)

    def test_post_303_becomes_get(self) -> None:
        seen = []

        def destination(request):
            seen.append(request)
            return Reply(body=b"ok")

        with server(destination) as target, server(
            lambda request: Reply(status=303, headers={"Location": target.url + "/done"})
        ) as origin:
            client = Client(domain=origin.url)
            status, _, body, _ = client._request(
                "POST", origin.url + "/submit", b"a=1", {"Content-Type": "application/x-www-form-urlencoded"}
            )
            self.assertEqual(status, 200)
            self.assertEqual(body, b"ok")
            self.assertEqual(seen[0].method, "GET")
            self.assertEqual(seen[0].body, b"")


class DomainResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old = os.environ.get(ENV_DOMAIN)
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        if self._old is None:
            os.environ.pop(ENV_DOMAIN, None)
        else:
            os.environ[ENV_DOMAIN] = self._old
        set_default_domain("")

    def test_environment_and_override(self) -> None:
        os.environ[ENV_DOMAIN] = "https://z-lib.gd/"
        self.assertEqual(current_default_domain(), "https://z-lib.gd")
        set_default_domain("https://zlib.bz")
        self.assertEqual(current_default_domain(), "https://zlib.bz")
        self.assertEqual(Client().domain, "https://zlib.bz")
        set_default_domain("")
        self.assertEqual(Client().domain, "https://z-lib.gd")


if __name__ == "__main__":
    unittest.main()
