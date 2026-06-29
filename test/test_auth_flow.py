import base64
import hashlib
import unittest
from unittest.mock import patch, MagicMock
from urllib.parse import urlparse, parse_qs

import requests

from cloudinary_cli.auth import flow


def _http_error(body=None, no_response=False, not_json=False):
    e = requests.HTTPError("400 Client Error: Bad Request for url: https://oauth.cloudinary.com/oauth2/token")
    if no_response:
        return e
    resp = MagicMock()
    if not_json:
        resp.json.side_effect = ValueError("no json")
        resp.text = body if body is not None else "<html>500</html>"
    else:
        resp.json.return_value = body
        resp.text = str(body)
    e.response = resp
    return e


class TestAuthFlow(unittest.TestCase):
    def test_pkce_pair_s256_no_padding(self):
        verifier, challenge = flow.generate_pkce_pair()
        self.assertNotIn("=", verifier)
        self.assertNotIn("=", challenge)
        # challenge must be the S256 of the verifier
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
        self.assertEqual(expected, challenge)

    def test_build_authorize_url(self):
        url = flow.build_authorize_url("the_challenge", "the_state", "http://127.0.0.1:49421/callback", "api")
        q = parse_qs(urlparse(url).query)
        self.assertTrue(url.startswith("https://oauth.cloudinary.com/oauth2/auth?"))
        self.assertEqual("code", q["response_type"][0])
        self.assertEqual("S256", q["code_challenge_method"][0])
        self.assertEqual("the_challenge", q["code_challenge"][0])
        self.assertEqual("the_state", q["state"][0])
        self.assertEqual("http://127.0.0.1:49421/callback", q["redirect_uri"][0])
        self.assertIn("client_id", q)

    def test_build_authorize_url_region_drives_host(self):
        url = flow.build_authorize_url("c", "s", "http://127.0.0.1:49421/callback", "test")
        self.assertTrue(url.startswith("https://oauth-test.cloudinary.com/oauth2/auth?"))

    def test_exchange_code_posts_pkce_no_secret(self):
        resp = MagicMock()
        resp.json.return_value = {"access_token": "tok"}
        with patch("cloudinary_cli.auth.flow.requests.post", return_value=resp) as post:
            flow.exchange_code("the_code", "the_verifier", "http://127.0.0.1:49421/callback", "test")
        self.assertEqual("https://oauth-test.cloudinary.com/oauth2/token", post.call_args.args[0])
        data = post.call_args.kwargs["data"]
        self.assertEqual("authorization_code", data["grant_type"])
        self.assertEqual("the_code", data["code"])
        self.assertEqual("the_verifier", data["code_verifier"])
        self.assertNotIn("client_secret", data)
        self.assertIn("timeout", post.call_args.kwargs)

    def test_refresh_posts_refresh_token(self):
        resp = MagicMock()
        resp.json.return_value = {"access_token": "tok2"}
        with patch("cloudinary_cli.auth.flow.requests.post", return_value=resp) as post:
            flow.refresh("rt_abc", "api-eu")
        self.assertEqual("https://oauth.cloudinary.com/oauth2/token", post.call_args.args[0])
        data = post.call_args.kwargs["data"]
        self.assertEqual("refresh_token", data["grant_type"])
        self.assertEqual("rt_abc", data["refresh_token"])
        self.assertIn("timeout", post.call_args.kwargs)

    def test_revoke_posts_token_to_revoke_endpoint(self):
        resp = MagicMock()
        with patch("cloudinary_cli.auth.flow.requests.post", return_value=resp) as post:
            flow.revoke("rt_abc", "api-eu")
        self.assertEqual("https://oauth.cloudinary.com/oauth2/revoke", post.call_args.args[0])
        data = post.call_args.kwargs["data"]
        self.assertEqual("rt_abc", data["token"])
        self.assertEqual("refresh_token", data["token_type_hint"])
        self.assertIn("client_id", data)
        self.assertIn("timeout", post.call_args.kwargs)
        resp.raise_for_status.assert_called_once()


class TestOAuthErrorDetail(unittest.TestCase):
    """flow.oauth_error_detail extracts the RFC 6749 error code, appending a short description but
    never the multi-sentence boilerplate the token endpoint returns for invalid_grant."""

    def test_short_description_is_appended(self):
        e = _http_error({"error": "invalid_client", "error_description": "Unknown client"})
        self.assertEqual("invalid_client: Unknown client", flow.oauth_error_detail(e))

    def test_long_description_is_suppressed(self):
        # The real invalid_grant body is a >80-char paragraph; only the code should surface.
        long_desc = ("The provided authorization grant or refresh token is invalid, expired, "
                     "revoked, or was issued to another client. The refresh token is malformed.")
        e = _http_error({"error": "invalid_grant", "error_description": long_desc})
        self.assertEqual("invalid_grant", flow.oauth_error_detail(e))

    def test_error_only_no_description(self):
        e = _http_error({"error": "invalid_grant"})
        self.assertEqual("invalid_grant", flow.oauth_error_detail(e))

    def test_description_exactly_at_limit_is_kept(self):
        desc = "x" * 80
        e = _http_error({"error": "invalid_request", "error_description": desc})
        self.assertEqual(f"invalid_request: {desc}", flow.oauth_error_detail(e))

    def test_description_one_over_limit_is_dropped(self):
        e = _http_error({"error": "invalid_request", "error_description": "x" * 81})
        self.assertEqual("invalid_request", flow.oauth_error_detail(e))

    def test_no_error_key_returns_none(self):
        self.assertIsNone(flow.oauth_error_detail(_http_error({"foo": "bar"})))

    def test_non_json_body_returns_none(self):
        self.assertIsNone(flow.oauth_error_detail(_http_error(not_json=True)))

    def test_no_response_returns_none(self):
        self.assertIsNone(flow.oauth_error_detail(_http_error(no_response=True)))


class TestOAuthErrorBody(unittest.TestCase):
    """flow.oauth_error_body returns the raw response text verbatim for debug logging."""

    def test_returns_raw_text(self):
        raw = '{"error":"invalid_grant","error_description":"long boilerplate here"}'
        e = _http_error(not_json=True, body=raw)
        self.assertEqual(raw, flow.oauth_error_body(e))

    def test_no_response_returns_none(self):
        self.assertIsNone(flow.oauth_error_body(_http_error(no_response=True)))
