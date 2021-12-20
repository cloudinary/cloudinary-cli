import os
import unittest
from unittest.mock import patch

import cloudinary.provisioning
from click.testing import CliRunner

from cloudinary_cli.cli import cli
from test.helper_test import api_response_mock, uploader_response_mock

API_MOCK_RESPONSE = api_response_mock()
UPLOAD_MOCK_RESPONSE = uploader_response_mock()


class TestCLIApi(unittest.TestCase):
    runner = CliRunner()

    @patch('urllib3.request.RequestMethods.request')
    def test_admin(self, mocker):
        mocker.return_value = API_MOCK_RESPONSE
        result = self.runner.invoke(cli, ['ping'])

        self.assertEqual(0, result.exit_code, result.output)
        self.assertIn('"foo": "bar"', result.output)

    @patch('urllib3.request.RequestMethods.request')
    def test_upload(self, mocker):
        mocker.return_value = UPLOAD_MOCK_RESPONSE
        result = self.runner.invoke(cli, ['upload', os.path.abspath(__file__)])

        self.assertEqual(0, result.exit_code, result.output)
        self.assertIn('"foo": "bar"', result.output)

    @patch('urllib3.request.RequestMethods.request')
    @unittest.skipUnless(cloudinary.provisioning.account_config().account_id, "requires account_id")
    def test_provisioning(self, mocker):
        mocker.return_value = API_MOCK_RESPONSE
        result = self.runner.invoke(cli, ['provisioning', 'users'])

        self.assertEqual(0, result.exit_code, result.output)
        self.assertIn('"foo": "bar"', result.output)
