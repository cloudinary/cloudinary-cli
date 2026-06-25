import socket
import threading
import unittest
import urllib.request
from http.server import HTTPServer
from unittest.mock import patch

import cloudinary_cli.auth.loopback_server as loopback_server
from cloudinary_cli.auth.loopback_server import _CallbackHandler, start_callback_server, wait_for_callback


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


class TestStartCallbackServerPortBusy(unittest.TestCase):
    """A2: a busy redirect port must surface a clear RuntimeError, not a raw OSError."""

    def test_port_in_use_raises_friendly_error(self):
        busy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        busy.bind(("127.0.0.1", 0))
        busy.listen(1)
        port = busy.getsockname()[1]
        self.addCleanup(busy.close)
        with patch.object(loopback_server, "OAUTH_REDIRECT_HOST", "127.0.0.1"), \
                patch.object(loopback_server, "OAUTH_REDIRECT_PORT", port):
            with self.assertRaises(RuntimeError) as ctx:
                start_callback_server()
        self.assertIn("local login server", str(ctx.exception))
        self.assertIn("in use", str(ctx.exception))
