"""Single-shot loopback HTTP server that captures the OAuth redirect: binds a localhost port,
serves until the `?code=&state=` (or `?error=`) redirect arrives or it times out."""
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

from cloudinary_cli.auth.callback_page import callback_page
from cloudinary_cli.defaults import (
    OAUTH_REDIRECT_HOST,
    OAUTH_REDIRECT_PORT,
    OAUTH_CALLBACK_PATH,
    OAUTH_CALLBACK_TIMEOUT_SECONDS,
)


class _CallbackHandler(BaseHTTPRequestHandler):
    """Captures the ?code=&state= redirect from the authorization server."""

    def do_GET(self):  # noqa: N802 (http.server API)
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        # Ignore stray requests (e.g. /favicon.ico, wrong path) so they don't consume the wait.
        if parsed.path != OAUTH_CALLBACK_PATH or ("code" not in params and "error" not in params):
            self.send_response(404)
            self.end_headers()
            return

        self.server.auth_code = params.get("code", [None])[0]
        self.server.auth_state = params.get("state", [None])[0]
        self.server.auth_error = params.get("error", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(callback_page(self.server.auth_error).encode("utf-8"))

    def log_message(self, *args):
        pass  # silence the default stderr request logging


def start_callback_server():
    """Bind the loopback server and return (httpd, redirect_uri)."""
    try:
        httpd = HTTPServer((OAUTH_REDIRECT_HOST, OAUTH_REDIRECT_PORT), _CallbackHandler)
    except OSError as e:
        raise RuntimeError(
            f"Could not start the local login server on {OAUTH_REDIRECT_HOST}:{OAUTH_REDIRECT_PORT} "
            f"({e.strerror or e}). Another login may be in progress, or the port is in use. "
            f"Close it and retry."
        ) from e
    httpd.auth_code = httpd.auth_state = httpd.auth_error = None
    httpd.timeout = OAUTH_CALLBACK_TIMEOUT_SECONDS
    redirect_uri = f"http://{OAUTH_REDIRECT_HOST}:{OAUTH_REDIRECT_PORT}{OAUTH_CALLBACK_PATH}"
    return httpd, redirect_uri


def wait_for_callback(httpd):
    """
    Serve requests until the redirect arrives (ignoring favicon/etc.) or the timeout elapses.
    Returns (auth_code, auth_state); raises on error or timeout.
    """
    deadline = time.monotonic() + OAUTH_CALLBACK_TIMEOUT_SECONDS
    try:
        while httpd.auth_code is None and httpd.auth_error is None:
            if time.monotonic() > deadline:
                break
            httpd.handle_request()
    finally:
        httpd.server_close()

    if httpd.auth_error:
        raise RuntimeError(f"Authorization failed: {httpd.auth_error}")
    if not httpd.auth_code:
        raise RuntimeError("Timed out waiting for the authorization redirect.")
    return httpd.auth_code, httpd.auth_state
