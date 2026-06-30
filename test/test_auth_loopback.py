import threading
import unittest
import urllib.request
from http.server import HTTPServer
from unittest.mock import patch

from cloudinary_cli.auth.callback_page import callback_page
from cloudinary_cli.auth.loopback_server import (
    _CallbackHandler,
    start_callback_server,
    wait_for_callback,
)


class TestLoopbackServer(unittest.TestCase):
    def setUp(self):
        # Bind an OS-assigned port on loopback so tests don't collide with the real default.
        self.httpd = HTTPServer(("127.0.0.1", 0), _CallbackHandler)
        self.httpd.auth_code = self.httpd.auth_state = self.httpd.auth_error = None
        self.httpd.timeout = 5
        self.port = self.httpd.server_address[1]

    def tearDown(self):
        try:
            self.httpd.server_close()
        except Exception:
            pass

    def _get(self, path):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5).read()
        except Exception:
            pass

    def test_captures_code_and_state(self):
        waiter = threading.Thread(target=lambda: setattr(self, "result", wait_for_callback(self.httpd)))
        waiter.start()
        self._get("/callback?code=the_code&state=the_state")
        waiter.join(timeout=5)
        self.assertEqual(("the_code", "the_state"), self.result)

    def test_ignores_favicon_then_captures(self):
        waiter = threading.Thread(target=lambda: setattr(self, "result", wait_for_callback(self.httpd)))
        waiter.start()
        self._get("/favicon.ico")  # must NOT end the wait
        self._get("/callback?code=c2&state=s2")
        waiter.join(timeout=5)
        self.assertEqual(("c2", "s2"), self.result)

    def test_ignores_code_on_wrong_path_then_captures(self):
        waiter = threading.Thread(target=lambda: setattr(self, "result", wait_for_callback(self.httpd)))
        waiter.start()
        self._get("/anything?code=stray&state=s")  # wrong path must NOT end the wait
        self._get("/callback?code=real&state=s3")
        waiter.join(timeout=5)
        self.assertEqual(("real", "s3"), self.result)

    def test_error_raises(self):
        error = {}

        def run():
            try:
                wait_for_callback(self.httpd)
            except Exception as e:
                error["e"] = e

        waiter = threading.Thread(target=run)
        waiter.start()
        self._get("/callback?error=access_denied")
        waiter.join(timeout=5)
        self.assertIsInstance(error.get("e"), RuntimeError)
        self.assertIn("access_denied", str(error["e"]))


class TestCallbackPage(unittest.TestCase):
    """auth_error comes from the redirect query string (untrusted) and must be HTML-escaped
    before being rendered into the callback page."""

    def test_error_is_html_escaped(self):
        page = callback_page("<script>alert(1)</script>")
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)

    def test_normal_error_rendered(self):
        page = callback_page("access_denied")
        self.assertIn("Login failed", page)
        self.assertIn("access_denied", page)

    def test_success_page(self):
        page = callback_page(None)
        self.assertIn("Login successful", page)


class TestStartCallbackServerPortBusy(unittest.TestCase):
    """A2: a failed bind (e.g. busy redirect port) must surface a clear RuntimeError, not a raw
    OSError. The bind is mocked to fail so the test is deterministic across OSes (Windows does not
    raise on a double-bind the way POSIX does)."""

    def test_bind_failure_raises_friendly_error(self):
        with patch("cloudinary_cli.auth.loopback_server.HTTPServer",
                   side_effect=OSError(48, "Address already in use")):
            with self.assertRaises(RuntimeError) as ctx:
                start_callback_server()
        msg = str(ctx.exception)
        self.assertIn("local login server", msg)
        self.assertIn("in use", msg)
        self.assertIsInstance(ctx.exception.__cause__, OSError)  # chains the original
