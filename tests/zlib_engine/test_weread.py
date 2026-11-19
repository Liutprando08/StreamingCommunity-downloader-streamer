from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
import unittest

import StreamingCommunity.zlib_engine.weread.importer as importer
from StreamingCommunity.zlib_engine import Cancelled
from StreamingCommunity.zlib_engine.weread import (
    APIError,
    Client,
    Credentials,
    FileTooLarge,
    ImportParseFailed,
    ImportStage,
    ImportUnconfirmed,
    NotLoggedIn,
    QRCode,
    QRDeclined,
    QRExpired,
    RateLimited,
    SessionExpired,
    UnsupportedFormat,
    VerificationRequired,
    check_import_file,
    import_book,
    max_import_size,
    supported_format,
)
from StreamingCommunity.zlib_engine.weread import device
from StreamingCommunity.zlib_engine.weread.cos import (
    cos_authorization,
    cos_escape,
    hmac_sha1_hex,
    sha1_hex,
)
from StreamingCommunity.zlib_engine.weread.errors import ImportLimit
from StreamingCommunity.zlib_engine.weread.user import user_info

from .support import Reply, json_reply, server

CREDS = Credentials(
    vid="1001",
    access_token="token-old",
    refresh_token="refresh-old",
    device_id=device.new_device_id(),
)


class COSSignatureTests(unittest.TestCase):
    def test_authorization_format(self) -> None:
        got = cos_authorization(
            "AKIDexample",
            "secret",
            "PUT",
            "/a b.epub",
            {"host": "b-1.cos.accelerate.myqcloud.com", "content-length": "13"},
            100,
            200,
        )
        http_string = "put\n/a b.epub\n\ncontent-length=13&host=b-1.cos.accelerate.myqcloud.com\n"
        string_to_sign = "sha1\n100;200\n" + sha1_hex(http_string) + "\n"
        want = (
            "q-sign-algorithm=sha1&q-ak=AKIDexample&q-sign-time=100;200&q-key-time=100;200"
            "&q-header-list=content-length;host&q-url-param-list=&q-signature="
            + hmac_sha1_hex(hmac_sha1_hex("secret", "100;200"), string_to_sign)
        )
        self.assertEqual(got, want)
        self.assertEqual(cos_escape("a b+c/"), "a%20b%2Bc%2F")


class CallTests(unittest.TestCase):
    def test_refreshes_expired_token_once(self) -> None:
        logins = []
        tokens = []

        def app(request):
            if request.path == "/login":
                body = json.loads(request.body)
                assert body["signature"] == device.login_signature(
                    body["timestamp"], body["deviceId"], body["random"]
                )
                logins.append(body)
                return json_reply(
                    {"vid": 1001, "accessToken": "token-new", "refreshToken": "refresh-new"}
                )
            if request.path == "/user":
                tokens.append(request.header("accesstoken"))
                if request.header("accesstoken") == "token-old":
                    return json_reply({"errCode": -2012, "errMsg": "expired"}, status=401)
                return json_reply({"name": "Reader", "user": {"name": "Nested"}})
            return json_reply({}, 404)

        saved = []
        with server(app) as srv:
            client = Client(CREDS, save=saved.append, api_base=srv.url)
            info = user_info(client)
            self.assertEqual(info.name, "Reader")
            self.assertIn("user.name", info.keys)
            self.assertEqual(tokens, ["token-old", "token-new"])
            self.assertEqual(len(logins), 1)
            self.assertEqual(client.credentials().access_token, "token-new")
            self.assertEqual(client.credentials().refresh_token, "refresh-new")
            self.assertEqual(saved[-1].access_token, "token-new")

    def test_expired_session_after_retry(self) -> None:
        with server(lambda request: json_reply({"errCode": -2012}, status=401)) as srv:
            client = Client(CREDS, api_base=srv.url)
            with self.assertRaises(SessionExpired):
                user_info(client)

    def test_verification_challenge_and_api_errors(self) -> None:
        with server(lambda request: json_reply({"errCode": -2041}, status=200)) as srv:
            client = Client(CREDS, api_base=srv.url)
            with self.assertRaises(VerificationRequired):
                client._call("GET", "/user")

        with server(
            lambda request: json_reply({"errCode": -2999, "errMsg": "quota"}, status=200)
        ) as srv:
            client = Client(CREDS, api_base=srv.url)
            with self.assertRaises(ImportLimit) as caught:
                client._call("GET", "/cos/getcredential")
            self.assertIn("quota", str(caught.exception))

        with server(lambda request: json_reply({"errcode": -2014})) as srv:
            client = Client(CREDS, api_base=srv.url)
            with self.assertRaises(RateLimited):
                client._call("GET", "/x")

    def test_not_logged_in(self) -> None:
        client = Client(api_base="http://127.0.0.1:1")
        with self.assertRaises(NotLoggedIn):
            user_info(client)


class ImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self._interval = importer.notify_interval
        self._attempts = importer.notify_attempts
        importer.notify_interval = 0.0
        importer.notify_attempts = 90
        self.addCleanup(setattr, importer, "notify_interval", self._interval)
        self.addCleanup(setattr, importer, "notify_attempts", self._attempts)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _book(self, name: str = "Dune.epub", size: int = 6) -> str:
        path = os.path.join(self._tmp.name, name)
        with open(path, "wb") as handle:
            handle.write(b"x" * size)
        return path

    def _client(self, srv, replies=None, **kwargs):
        replies = list(replies or [{"status": 0, "bookId": "book-1"}])
        state = {"notifies": [], "uploaded": b"", "auth": ""}

        def cos_url(bucket, key):
            return srv.url + "/cos-put/" + bucket + "/" + key

        def app(request):
            if request.path == "/cos/getcredential":
                if request.query.get("name") != ["Dune"]:
                    raise AssertionError(f"credential name = {request.query.get('name')}")
                return json_reply(
                    {
                        "bucket": "weread-1258476243",
                        "ObjectName": "/import/1001/Dune.epub",
                        "Response": {
                            "Credentials": {
                                "TmpSecretId": "id-placeholder",
                                "TmpSecretKey": "key-placeholder",
                                "Token": "sts-placeholder",
                            },
                            "ExpiredTime": 4102444800,
                        },
                    }
                )
            if request.path.startswith("/cos-put/"):
                state["uploaded"] = request.body
                state["auth"] = request.header("authorization")
                return Reply(body=b"")
            if request.path == "/cos/notify":
                state["notifies"].append((request.query, request.body))
                reply = replies[min(len(state["notifies"]), len(replies)) - 1]
                return json_reply(reply)
            return json_reply({}, 404)

        client = Client(CREDS, api_base=srv.url, **kwargs)
        client.cos_url = cos_url
        client._app_state = state  # type: ignore[attr-defined]
        return client, state, app

    def test_import_uploads_and_notifies(self) -> None:
        path = self._book()
        progress = []
        holder = {}

        def app(request):
            return holder["app"](request)

        with server(app) as srv:
            client, state, inner = self._client(
                srv,
                replies=[
                    {"status": 1},
                    {"status": 0, "bookId": "book-1"},
                ],
            )
            holder["app"] = inner
            result = import_book(client, path, progress.append)
            self.assertEqual(result.book_id, "book-1")
            self.assertFalse(result.already_existed)
            self.assertEqual(state["uploaded"], b"x" * 6)
            self.assertTrue(state["auth"].startswith("q-sign-algorithm=sha1"))
            self.assertEqual(progress[0].stage, ImportStage.PREPARE)
            self.assertEqual(progress[1].stage, ImportStage.UPLOAD)
            self.assertEqual(progress[-1].stage, ImportStage.PROCESS)
            self.assertEqual(
                [item.attempt for item in progress if item.stage == ImportStage.PROCESS],
                [1, 2],
            )
            notify_query = state["notifies"][0][0]
            self.assertEqual(notify_query["name"], ["Dune.epub"])
            self.assertEqual(notify_query["path"], ["/import/1001/Dune.epub"])
            self.assertEqual(notify_query["cancel"], ["0"])

    def test_already_existing_book(self) -> None:
        path = self._book()
        holder = {}

        def app(request):
            return holder["app"](request)

        with server(app) as srv:
            client, _, inner = self._client(srv, replies=[{"status": 3, "bookId": "book-1"}])
            holder["app"] = inner
            result = import_book(client, path)
            self.assertTrue(result.already_existed)

    def test_parse_error(self) -> None:
        path = self._book()
        holder = {}

        def app(request):
            return holder["app"](request)

        with server(app) as srv:
            client, _, inner = self._client(srv, replies=[{"status": 2}])
            holder["app"] = inner
            with self.assertRaises(ImportParseFailed):
                import_book(client, path)

    def test_still_processing_is_unconfirmed(self) -> None:
        path = self._book()
        holder = {}

        def app(request):
            return holder["app"](request)

        with server(app) as srv:
            client, _, inner = self._client(srv, replies=[{"status": 1}])
            holder["app"] = inner
            importer.notify_attempts = 2
            with self.assertRaises(ImportUnconfirmed):
                import_book(client, path)

    def test_cancel_while_processing_abandons_import(self) -> None:
        path = self._book()
        import threading

        cancel = threading.Event()
        holder = {}
        state = {"notifies": 0}

        def app(request):
            if request.path == "/cos/notify":
                state["notifies"] += 1
                if state["notifies"] == 1:
                    cancel.set()
                    return json_reply({"status": 1})
            return holder["app"](request)

        with server(app) as srv:
            client, _, inner = self._client(srv, replies=[{"status": 1}])
            holder["app"] = inner
            with self.assertRaises(Cancelled):
                import_book(client, path, cancel_event=cancel)

    def test_first_notify_rejection_propagates(self) -> None:
        path = self._book()
        holder = {}

        def app(request):
            if request.path == "/cos/notify":
                return json_reply({"errCode": -2999, "errMsg": "quota"})
            return holder["app"](request)

        with server(app) as srv:
            client, _, inner = self._client(srv)
            holder["app"] = inner
            with self.assertRaises(ImportLimit):
                import_book(client, path)

    def test_server_error_after_upload_is_unconfirmed(self) -> None:
        path = self._book()
        holder = {}

        def app(request):
            if request.path == "/cos/notify":
                return Reply(status=500, body=b"boom")
            return holder["app"](request)

        with server(app) as srv:
            client, _, inner = self._client(srv)
            holder["app"] = inner
            with self.assertRaises(ImportUnconfirmed):
                import_book(client, path)

    def test_validates_file_before_network(self) -> None:
        path = os.path.join(self._tmp.name, "book.exe")
        with open(path, "wb") as handle:
            handle.write(b"x")
        client = Client(CREDS, api_base="http://127.0.0.1:1")
        with self.assertRaises(UnsupportedFormat):
            import_book(client, path)

    def test_check_import_file_limits(self) -> None:
        path = self._book("book.txt", 10)
        self.assertEqual(check_import_file(path), 10)
        self.assertEqual(max_import_size(path), 20 << 20)
        self.assertEqual(max_import_size("book.pdf"), 300 << 20)
        self.assertTrue(supported_format("BOOK.EPUB"))
        self.assertFalse(supported_format("book.exe"))

        empty = os.path.join(self._tmp.name, "empty.epub")
        open(empty, "wb").close()
        with self.assertRaises(Exception):
            check_import_file(empty)

        huge = os.path.join(self._tmp.name, "huge.txt")
        with open(huge, "wb") as handle:
            handle.truncate((20 << 20) + 1)
        with self.assertRaises(FileTooLarge):
            check_import_file(huge)

    def test_import_requires_login(self) -> None:
        path = self._book()
        with self.assertRaises(NotLoggedIn):
            import_book(Client(api_base="http://127.0.0.1:1"), path)


class LoginTests(unittest.TestCase):
    def test_qr_flow(self) -> None:
        import StreamingCommunity.zlib_engine.weread.login as login

        old_delay = login.poll_delay
        login.poll_delay = 0.0
        self.addCleanup(setattr, login, "poll_delay", old_delay)

        state = {"polls": 0}

        def app(request):
            if request.path == "/wxticket":
                return json_reply({"signature": "sig", "timeStamp": 123})
            if request.path == "/connect/sdk/qrconnect":
                return json_reply({"errcode": 0, "uuid": "uuid-1"})
            if request.path == "/connect/l/qrconnect":
                state["polls"] += 1
                if state["polls"] == 1:
                    return json_reply({"wx_errcode": 404})
                return json_reply({"wx_errcode": 405, "wx_code": "auth-code"})
            return json_reply({}, 404)

        with server(app) as srv:
            client = Client(api_base=srv.url, open_base=srv.url, long_base=srv.url)
            qr = client.request_qr_code()
            self.assertIsInstance(qr, QRCode)
            self.assertEqual(qr.uuid, "uuid-1")
            self.assertIn("uuid=uuid-1", qr.url)
            scanned = []
            code = client.wait_for_confirmation(qr.uuid, on_scanned=lambda: scanned.append(True))
            self.assertEqual(code, "auth-code")
            self.assertEqual(scanned, [True])

    def test_qr_terminal_states(self) -> None:
        import StreamingCommunity.zlib_engine.weread.login as login

        old_delay = login.poll_delay
        login.poll_delay = 0.0
        self.addCleanup(setattr, login, "poll_delay", old_delay)
        for errcode, expected in ((402, QRExpired), (403, QRDeclined)):
            with server(lambda request, code=errcode: json_reply({"wx_errcode": code})) as srv:
                client = Client(api_base=srv.url, long_base=srv.url)
                with self.assertRaises(expected):
                    client.wait_for_confirmation("uuid")

    def test_exchange_stores_credentials(self) -> None:
        seen = []

        def app(request):
            if request.path == "/login":
                body = json.loads(request.body)
                seen.append(body)
                assert body["signature"] == device.login_signature(
                    body["timestamp"], body["deviceId"], body["random"]
                )
                return json_reply(
                    {"vid": 1001, "accessToken": "access", "refreshToken": "refresh"}
                )
            return json_reply({}, 404)

        with server(app) as srv:
            client = Client(api_base=srv.url)
            creds = client.exchange("code-1")
            self.assertTrue(creds.valid())
            self.assertEqual(creds.vid, "1001")
            self.assertEqual(creds.access_token, "access")
            self.assertEqual(seen[0]["code"], "code-1")
            self.assertEqual(client.credentials(), creds)

    def test_ping_requires_ticket(self) -> None:
        with server(lambda request: json_reply({})) as srv:
            client = Client(api_base=srv.url)
            with self.assertRaises(Exception):
                client.ping()


if __name__ == "__main__":
    unittest.main()
