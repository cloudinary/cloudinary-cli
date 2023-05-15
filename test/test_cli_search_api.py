import unittest
from unittest.mock import patch

from click.testing import CliRunner

from cloudinary_cli.cli import cli
from test.helper_test import api_response_mock, uploader_response_mock

API_MOCK_RESPONSE = api_response_mock()
UPLOAD_MOCK_RESPONSE = uploader_response_mock()


class TestCLISearchApi(unittest.TestCase):
    runner = CliRunner()

    @patch('urllib3.request.RequestMethods.request')
    def test_search(self, mocker):
        mocker.return_value = API_MOCK_RESPONSE
        result = self.runner.invoke(cli, ['search', 'cat'])

        self.assertEqual(0, result.exit_code)
        self.assertIn('"foo": "bar"', result.output)

    def test_search_url(self):
        result = self.runner.invoke(cli, ['search', 'cat', '-c', 'NEXT_CURSOR', '--ttl', '1000', '--url'])

        self.assertEqual(0, result.exit_code)
        self.assertTrue(result.output.startswith("http"))
        self.assertIn('/search/', result.output)
        self.assertIn('eyJleHByZXNzaW9uIjoiY2F0IiwibWF4X3Jlc3VsdHMiOjEwfQ==', result.output)
        self.assertIn('1000', result.output)
        self.assertIn('NEXT_CURSOR', result.output)
