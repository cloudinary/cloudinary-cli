import unittest

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
