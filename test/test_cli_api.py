import os
import unittest
from unittest.mock import patch

import cloudinary.provisioning
from click.testing import CliRunner

from cloudinary_cli.cli import cli
from test.helper_test import api_response_mock, uploader_response_mock, URLLIB3_REQUEST, \
    CONFIG_PRESENT, REQUIRES_CONFIG

API_MOCK_RESPONSE = api_response_mock()
UPLOAD_MOCK_RESPONSE = uploader_response_mock()

CONFIRM_ACTION_PATCH = "cloudinary_cli.utils.api_utils.confirm_action"


class TestCLIApi(unittest.TestCase):
    runner = CliRunner()

    @unittest.skipUnless(CONFIG_PRESENT, REQUIRES_CONFIG)
    @patch(URLLIB3_REQUEST)
    def test_admin(self, mocker):
        mocker.return_value = API_MOCK_RESPONSE
        result = self.runner.invoke(cli, ['ping'])

        self.assertEqual(0, result.exit_code, result.output)
        self.assertIn('"foo": "bar"', result.output)

    @unittest.skipUnless(CONFIG_PRESENT, REQUIRES_CONFIG)
    @patch(URLLIB3_REQUEST)
    def test_upload(self, mocker):
        mocker.return_value = UPLOAD_MOCK_RESPONSE
        result = self.runner.invoke(cli, ['upload', os.path.abspath(__file__)])

        self.assertEqual(0, result.exit_code, result.output)
        self.assertIn('"foo": "bar"', result.output)

    @patch(URLLIB3_REQUEST)
    @unittest.skipUnless(cloudinary.provisioning.account_config().account_id, "requires account_id")
    def test_provisioning(self, mocker):
        mocker.return_value = API_MOCK_RESPONSE
        result = self.runner.invoke(cli, ['provisioning', 'users'])

        self.assertEqual(0, result.exit_code, result.output)
        self.assertIn('"foo": "bar"', result.output)


class TestDestructiveBulkConfirmation(unittest.TestCase):
    runner = CliRunner()

    @patch(CONFIRM_ACTION_PATCH, return_value=False)
    @patch(URLLIB3_REQUEST)
    def test_delete_all_resources_decline_skips_call(self, http_mock, confirm_mock):
        http_mock.return_value = API_MOCK_RESPONSE
        result = self.runner.invoke(cli, ['admin', 'delete_all_resources'])

        self.assertEqual(0, result.exit_code, result.output)
        confirm_mock.assert_called_once()
        self.assertFalse(http_mock.called, "SDK should not be called when user declines")

    @unittest.skipUnless(CONFIG_PRESENT, REQUIRES_CONFIG)
    @patch(CONFIRM_ACTION_PATCH, return_value=True)
    @patch(URLLIB3_REQUEST)
    def test_delete_all_resources_accept_calls_sdk(self, http_mock, confirm_mock):
        http_mock.return_value = API_MOCK_RESPONSE
        result = self.runner.invoke(cli, ['admin', 'delete_all_resources'])

        self.assertEqual(0, result.exit_code, result.output)
        confirm_mock.assert_called_once()
        self.assertTrue(http_mock.called, "SDK should be called when user accepts")

    @unittest.skipUnless(CONFIG_PRESENT, REQUIRES_CONFIG)
    @patch(CONFIRM_ACTION_PATCH, return_value=False)
    @patch(URLLIB3_REQUEST)
    def test_delete_all_resources_force_skips_prompt(self, http_mock, confirm_mock):
        http_mock.return_value = API_MOCK_RESPONSE
        result = self.runner.invoke(cli, ['admin', '-F', 'delete_all_resources'])

        self.assertEqual(0, result.exit_code, result.output)
        self.assertFalse(confirm_mock.called, "--force should bypass the confirmation prompt")
        self.assertTrue(http_mock.called, "SDK should be called when --force is set")

    @patch(CONFIRM_ACTION_PATCH, return_value=False)
    @patch(URLLIB3_REQUEST)
    def test_delete_resources_by_tag_decline_skips_call(self, http_mock, confirm_mock):
        http_mock.return_value = API_MOCK_RESPONSE
        result = self.runner.invoke(cli, ['admin', 'delete_resources_by_tag', 'mytag'])

        self.assertEqual(0, result.exit_code, result.output)
        confirm_mock.assert_called_once()
        self.assertFalse(http_mock.called, "SDK should not be called when user declines")

    @unittest.skipUnless(CONFIG_PRESENT, REQUIRES_CONFIG)
    @patch(CONFIRM_ACTION_PATCH, return_value=False)
    @patch(URLLIB3_REQUEST)
    def test_delete_resources_explicit_ids_no_prompt(self, http_mock, confirm_mock):
        http_mock.return_value = API_MOCK_RESPONSE
        result = self.runner.invoke(cli, ['admin', 'delete_resources', 'public_id1', 'public_id2'])

        self.assertEqual(0, result.exit_code, result.output)
        self.assertFalse(confirm_mock.called, "Explicit-ID delete must not prompt")
        self.assertTrue(http_mock.called, "SDK should be called for explicit-ID delete")

    @unittest.skipUnless(CONFIG_PRESENT, REQUIRES_CONFIG)
    @patch(CONFIRM_ACTION_PATCH, return_value=False)
    @patch(URLLIB3_REQUEST)
    def test_uploader_add_tag_no_prompt(self, http_mock, confirm_mock):
        http_mock.return_value = UPLOAD_MOCK_RESPONSE
        result = self.runner.invoke(cli, ['uploader', 'add_tag', 'mytag', 'public_id1'])

        self.assertEqual(0, result.exit_code, result.output)
        self.assertFalse(confirm_mock.called, "Non-destructive bulk methods must not prompt")
        self.assertTrue(http_mock.called, "SDK should be called for non-destructive bulk methods")

    @unittest.skipUnless(CONFIG_PRESENT, REQUIRES_CONFIG)
    @patch(CONFIRM_ACTION_PATCH, return_value=False)
    @patch(URLLIB3_REQUEST)
    def test_admin_resources_read_no_prompt(self, http_mock, confirm_mock):
        http_mock.return_value = API_MOCK_RESPONSE
        result = self.runner.invoke(cli, ['admin', 'resources'])

        self.assertEqual(0, result.exit_code, result.output)
        self.assertFalse(confirm_mock.called, "Read commands must not prompt")
        self.assertTrue(http_mock.called, "SDK should be called for read commands")

    @unittest.skipUnless(CONFIG_PRESENT, REQUIRES_CONFIG)
    @patch(CONFIRM_ACTION_PATCH, return_value=False)
    @patch(URLLIB3_REQUEST)
    def test_admin_resources_read_with_force_no_prompt(self, http_mock, confirm_mock):
        http_mock.return_value = API_MOCK_RESPONSE
        result = self.runner.invoke(cli, ['admin', '-F', 'resources'])

        self.assertEqual(0, result.exit_code, result.output)
        self.assertFalse(confirm_mock.called, "Read commands must not prompt regardless of --force")
        self.assertTrue(http_mock.called)
