import base64
import hashlib
import unittest
from unittest.mock import patch, MagicMock
from urllib.parse import urlparse, parse_qs

from cloudinary_cli.auth import flow


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
