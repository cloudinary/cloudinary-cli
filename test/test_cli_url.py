import unittest

from click.testing import CliRunner

from cloudinary_cli.cli import cli
from test.helper_test import CONFIG_PRESENT, REQUIRES_CONFIG


class TestCLIURL(unittest.TestCase):
    runner = CliRunner()

    def test_url_no_public_id(self):
        result = self.runner.invoke(cli, 'url')

        self.assertEqual(2, result.exit_code)
        self.assertIn("Error: Missing argument 'PUBLIC_ID'", result.output)

    @unittest.skipUnless(CONFIG_PRESENT, REQUIRES_CONFIG)
    def test_url(self):
        result = self.runner.invoke(cli, ['url', 'sample'])

        self.assertEqual(0, result.exit_code)
        self.assertIn('image/upload/sample', result.output)

    @unittest.skipUnless(CONFIG_PRESENT, REQUIRES_CONFIG)
    def test_url_list(self):
        result = self.runner.invoke(cli, ['url', 'sample', '--type', 'list'])

        self.assertEqual(0, result.exit_code)
        self.assertIn('image/list/sample.json', result.output)

    @unittest.skipUnless(CONFIG_PRESENT, REQUIRES_CONFIG)
    def test_url_authenticated(self):
        result = self.runner.invoke(cli, ['url', 'sample', '--type', 'authenticated'])

        self.assertEqual(0, result.exit_code)
        self.assertIn('image/authenticated', result.output)
        self.assertIn('/s--', result.output)
