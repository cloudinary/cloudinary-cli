import unittest
from unittest.mock import patch

from click.testing import CliRunner

from cloudinary_cli.cli import cli
from test.helper_test import http_response_mock, URLLIB3_REQUEST, CONFIG_PRESENT, REQUIRES_CONFIG

DERIVED = '"derived": [{"public_id": "p1", "type": "upload", "resource_type": "image"}]'


class TestCLIRegenDerived(unittest.TestCase):
    runner = CliRunner()

    @unittest.skipUnless(CONFIG_PRESENT, REQUIRES_CONFIG)
    @patch(URLLIB3_REQUEST)
    def test_regen_derived_warns_about_more_pages(self, http_mock):
        http_mock.return_value = http_response_mock('{"named": false, ' + DERIVED + ', "next_cursor": "abc"}')
        result = self.runner.invoke(cli, ['regen_derived', '-F', 'w_100'])

        self.assertEqual(0, result.exit_code, result.output)
        self.assertIn("Only the first 1 derived assets will be regenerated. Use -A", result.output)

    @unittest.skipUnless(CONFIG_PRESENT, REQUIRES_CONFIG)
    @patch(URLLIB3_REQUEST)
    def test_regen_derived_single_page_does_not_warn(self, http_mock):
        http_mock.return_value = http_response_mock('{"named": false, ' + DERIVED + '}')
        result = self.runner.invoke(cli, ['regen_derived', '-F', 'w_100'])

        self.assertEqual(0, result.exit_code, result.output)
        self.assertNotIn("Only the first", result.output)
