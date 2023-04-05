import time
import unittest
from unittest.mock import patch

from click.testing import CliRunner

from cloudinary_cli.cli import cli
from test.helper_test import unique_suffix, TEST_FILES_DIR, delete_cld_folder_if_exists, uploader_response_mock, \
    get_request_url, get_params

UPLOAD_MOCK_RESPONSE = uploader_response_mock()

class TestCLIUploadDir(unittest.TestCase):
    runner = CliRunner()

    CLD_UPLOAD_DIR = unique_suffix("test_upload_dir")

    def setUp(self) -> None:
        delete_cld_folder_if_exists(self.CLD_UPLOAD_DIR)
        time.sleep(1)

    def tearDown(self) -> None:
        delete_cld_folder_if_exists(self.CLD_UPLOAD_DIR)
        time.sleep(1)

    def test_cli_upload_dir(self):
        result = self.runner.invoke(cli, ["upload_dir", TEST_FILES_DIR, "-f", self.CLD_UPLOAD_DIR])

        self.assertEqual(0, result.exit_code)
        self.assertIn("12 resources uploaded", result.output)

    def test_cli_upload_dir_glob(self):
        result = self.runner.invoke(cli, ["upload_dir", TEST_FILES_DIR, "-g", "**/*.png", "-f", self.CLD_UPLOAD_DIR])

        self.assertEqual(0, result.exit_code)
        self.assertIn("1 resources uploaded", result.output)

        result = self.runner.invoke(cli, ["upload_dir", TEST_FILES_DIR, "-g", "**/*.jpg", "-f", self.CLD_UPLOAD_DIR])

        self.assertEqual(0, result.exit_code)
        self.assertIn("11 resources uploaded", result.output)

    def test_upload_dir_without_exclude_dir_name_option(self):
        result = self.runner.invoke(cli, ["upload_dir", TEST_FILES_DIR, "-f", self.CLD_UPLOAD_DIR])

        self.assertEqual(0, result.exit_code)
        self.assertIn("12 resources uploaded", result.output)
        self.assertIn("as " + self.CLD_UPLOAD_DIR + "/test_sync/", result.output)

    def test_upload_dir_with_exclude_dir_name_option(self):
        result = self.runner.invoke(cli, ["upload_dir", TEST_FILES_DIR, "-e", "-f", self.CLD_UPLOAD_DIR])

        self.assertEqual(0, result.exit_code)
        self.assertIn("12 resources uploaded", result.output)
        self.assertIn("as " + self.CLD_UPLOAD_DIR, result.output)
        self.assertNotIn("as " + self.CLD_UPLOAD_DIR + "/test_sync/", result.output)

    @patch('urllib3.request.RequestMethods.request')
    def test_upload_dir_override_defaults(self, mocker):
        mocker.return_value = UPLOAD_MOCK_RESPONSE

        result = self.runner.invoke(cli, ["upload_dir", TEST_FILES_DIR, "-f", self.CLD_UPLOAD_DIR,
                                          "-o", "resource_type", "raw", "-O", "unique_filename", "True"])

        self.assertEqual(0, result.exit_code)
        self.assertIn("12 resources uploaded", result.output)

        self.assertIn("raw/upload", get_request_url(mocker))
        self.assertTrue(get_params(mocker)['unique_filename'])
