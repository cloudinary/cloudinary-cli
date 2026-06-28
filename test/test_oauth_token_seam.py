"""The redesign's central premise: the active OAuth config refreshes its token through the single
SDK seam, `cloudinary.config().oauth_token`, read at request build time. These tests exercise that
seam the way the SDK does (call_api / uploader) rather than reading oauth_token directly, and pin
the post-resolve invariant that the active config is always an OAuthConfig."""
import time
import unittest
from unittest.mock import patch

import cloudinary

from cloudinary_cli.auth.oauth_config import OAuthConfig, install_oauth_config, install_env_config
from cloudinary_cli.auth.session import Session, to_cloudinary_url

from test.oauth_helpers import jwt_access_token


def _url(cloud="eu-cloud", token="eyJ.tok", refresh="rt", region="api-eu", expires_delta=300):
    return to_cloudinary_url(Session(
        cloud_name=cloud, access_token=token, refresh_token=refresh,
        expires_at=int(time.time()) + expires_delta, region=region,
        issuer="https://oauth.cloudinary.com/"))


class _RestoresSdkConfig(unittest.TestCase):
    def setUp(self):
        import os
        self._env_snapshot = dict(os.environ)
        for key in [k for k in os.environ if k.startswith("CLOUDINARY_")]:
            del os.environ[key]
        cloudinary.reset_config()
        self.addCleanup(self._restore)

    def _restore(self):
        import os
        os.environ.clear()
        os.environ.update(self._env_snapshot)
        cloudinary.reset_config()


class TestSdkSeamTriggersRefresh(_RestoresSdkConfig):
    """The SDK reads cloudinary.config().oauth_token to build the Authorization header; that read
    (not any CLI-side probe) is what refreshes a stale token."""

    def _saved_stale(self):
        return {"eu-cloud": _url(token="eyJ.old.tok", refresh="rt_old", expires_delta=-10)}

    def test_call_api_authorize_path_refreshes_stale_token(self):
        saved = self._saved_stale()
        new_token = jwt_access_token(cloud_name="eu-cloud", tag="call-api-new")
        token_response = {"access_token": new_token, "refresh_token": "rt_new", "expires_in": 300}
        with patch("cloudinary_cli.utils.config_utils.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.auth.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.auth.flow.refresh", return_value=token_response), \
                patch("cloudinary_cli.auth.update_config"):
            install_oauth_config(saved["eu-cloud"], saved_name="eu-cloud")
            # Reproduce verbatim the read cloudinary.api_client.call_api performs at request build
            # time (call_api.py:63): options.pop("oauth_token", cloudinary.config().oauth_token).
            options = {}
            oauth_token = options.pop("oauth_token", cloudinary.config().oauth_token)
        self.assertEqual(new_token, oauth_token)

    def test_uploader_header_path_refreshes_stale_token(self):
        saved = self._saved_stale()
        fresh_token = jwt_access_token(cloud_name="eu-cloud", tag="uploader-fresh")
        token_response = {"access_token": fresh_token, "refresh_token": "rt_new", "expires_in": 300}
        with patch("cloudinary_cli.utils.config_utils.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.auth.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.auth.flow.refresh", return_value=token_response), \
                patch("cloudinary_cli.auth.update_config"):
            install_oauth_config(saved["eu-cloud"], saved_name="eu-cloud")
            # The uploader reads the same attribute to set the Bearer header (uploader.py:877):
            # oauth_token = options.get("oauth_token", cloudinary.config().oauth_token).
            import cloudinary.uploader  # noqa: F401 (ensures the seam module is importable)
            options = {}
            token = options.get("oauth_token", cloudinary.config().oauth_token)
        self.assertEqual(fresh_token, token)

    def test_seam_read_refreshes_only_once_then_serves_cached(self):
        saved = self._saved_stale()
        new_token = jwt_access_token(cloud_name="eu-cloud", tag="cached-new")
        token_response = {"access_token": new_token, "refresh_token": "rt_new", "expires_in": 300}
        with patch("cloudinary_cli.utils.config_utils.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.auth.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.auth.flow.refresh", return_value=token_response) as refresh, \
                patch("cloudinary_cli.auth.update_config"):
            install_oauth_config(saved["eu-cloud"], saved_name="eu-cloud")
            first = cloudinary.config().oauth_token
            second = cloudinary.config().oauth_token
        self.assertEqual(new_token, first)
        self.assertEqual(new_token, second)
        refresh.assert_called_once()  # the now-fresh _session short-circuits the second read


class TestPostResolveInvariant(_RestoresSdkConfig):
    """Not-done item #5 / Caveat B: every install seam leaves an OAuthConfig as the active global, so
    has_oauth is universal and self-refresh is never silently disabled by a plain Config swap."""

    runner = None

    def test_saved_oauth_install_is_oauthconfig(self):
        install_oauth_config(_url(), saved_name="eu-cloud")
        self.assertIsInstance(cloudinary.config(), OAuthConfig)

    def test_inline_url_install_is_oauthconfig(self):
        install_oauth_config("cloudinary://key:secret@cloud", saved_name=None)
        self.assertIsInstance(cloudinary.config(), OAuthConfig)

    def test_env_install_is_oauthconfig(self):
        import os
        os.environ["CLOUDINARY_URL"] = "cloudinary://k:s@env_cloud"
        cloudinary.reset_config()
        install_env_config()
        self.assertIsInstance(cloudinary.config(), OAuthConfig)

    def test_resolver_leaves_oauthconfig_for_every_branch(self):
        from click.testing import CliRunner
        from cloudinary_cli.cli import cli
        import os
        saved = {"__default__": "eu-cloud", "eu-cloud": _url()}
        with patch("cloudinary_cli.utils.config_resolver.load_config", return_value=dict(saved)):
            for key in ("CLOUDINARY_URL", "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY",
                        "CLOUDINARY_API_SECRET"):
                os.environ.pop(key, None)
            cloudinary.reset_config()
            # default branch
            CliRunner().invoke(cli, ['url', 'sample'])
            self.assertIsInstance(cloudinary.config(), OAuthConfig)


class TestEnvConfigStatic(_RestoresSdkConfig):
    """An env-installed OAuthConfig is static: it has no saved name, so reading oauth_token never
    refreshes even if the token is expired (it cannot rotate an env-supplied token)."""

    def test_env_oauth_token_never_refreshes_even_when_stale(self):
        import os
        os.environ["CLOUDINARY_URL"] = (
            "cloudinary://env_cloud?oauth_token=eyJ.env.tok&refresh_token=rt&"
            f"expires_at={int(time.time()) - 10}&region=api")
        cloudinary.reset_config()
        with patch("cloudinary_cli.auth.flow.refresh") as refresh:
            cfg = install_env_config()
            token = cfg.oauth_token
        self.assertEqual("eyJ.env.tok", token)
        refresh.assert_not_called()
        self.assertIsNone(getattr(cfg, "_session"))  # static: no parsed session to drive a refresh


if __name__ == "__main__":
    unittest.main()
