import importlib
import unittest
from unittest.mock import patch

import cloudinary_cli.defaults as defaults
from cloudinary_cli.defaults import normalize_region, _oauth_host_for, api_host_for_region


class TestAuthRegion(unittest.TestCase):
    def test_normalize_region(self):
        self.assertEqual('api', normalize_region(None))
        self.assertEqual('api', normalize_region(''))
        self.assertEqual('api', normalize_region('api'))
        self.assertEqual('api-eu', normalize_region('eu'))
        self.assertEqual('api-ap', normalize_region('ap'))
        self.assertEqual('api-eu', normalize_region('api-eu'))
        self.assertEqual('api-eu', normalize_region(' api-eu '))
        self.assertEqual('api-test', normalize_region('test'))
        self.assertEqual('api-test', normalize_region('api-test'))

    def test_api_host_for_region(self):
        self.assertEqual('https://api.cloudinary.com', api_host_for_region('api'))
        self.assertEqual('https://api-eu.cloudinary.com', api_host_for_region('api-eu'))
        # short codes are normalized first
        self.assertEqual('https://api-ap.cloudinary.com', api_host_for_region('ap'))
        self.assertEqual('https://api-test.cloudinary.com', api_host_for_region('test'))
        self.assertEqual('https://api-test.cloudinary.com', api_host_for_region('api-test'))

    def test_oauth_host_central_for_geo_regions(self):
        # <= 2-char suffixes (and bare 'api') use the central authz server
        self.assertEqual('oauth.cloudinary.com', _oauth_host_for('api'))
        self.assertEqual('oauth.cloudinary.com', _oauth_host_for('api-eu'))
        self.assertEqual('oauth.cloudinary.com', _oauth_host_for('api-ap'))

    def test_oauth_host_dedicated_for_long_suffix(self):
        # longer suffixes route to their own oauth-<suffix> host
        self.assertEqual('oauth-test.cloudinary.com', _oauth_host_for('api-test'))


class TestOAuthClientConfig(unittest.TestCase):
    """OAUTH_CLIENT_ID / OAUTH_SCOPES are env-overridable (resolved at module import)."""

    def _reload(self, env):
        # The values are read at import time, so reload defaults under the patched environment.
        with patch.dict("os.environ", env, clear=False):
            for key in ("CLOUDINARY_OAUTH_CLIENT_ID", "CLOUDINARY_OAUTH_SCOPES"):
                if key not in env:
                    __import__("os").environ.pop(key, None)
            return importlib.reload(defaults)

    def tearDown(self):
        importlib.reload(defaults)  # restore the unpatched module for other tests

    def test_defaults_when_unset(self):
        d = self._reload({})
        self.assertEqual('a920ea9c-531b-4613-9783-1d4f4cc10655', d.OAUTH_CLIENT_ID)
        self.assertEqual('openid offline_access asset_management upload', d.OAUTH_SCOPES)

    def test_client_id_override(self):
        d = self._reload({"CLOUDINARY_OAUTH_CLIENT_ID": "non-prod-client"})
        self.assertEqual("non-prod-client", d.OAUTH_CLIENT_ID)

    def test_scopes_override(self):
        d = self._reload({"CLOUDINARY_OAUTH_SCOPES": "openid upload"})
        self.assertEqual("openid upload", d.OAUTH_SCOPES)
