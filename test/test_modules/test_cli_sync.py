import shutil
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from cloudinary_cli.cli import cli
from test.helper_test import unique_suffix, RESOURCES_DIR, TEST_FILES_DIR, delete_cld_folder_if_exists, retry_assertion, \
    get_request_url, get_params
from test.test_modules.test_cli_upload_dir import UPLOAD_MOCK_RESPONSE


class TestCLISync(unittest.TestCase):
    runner = CliRunner()

    LOCAL_PARTIAL_SYNC_DIR = str(Path.joinpath(RESOURCES_DIR, "test_sync_partial"))
    LOCAL_SYNC_PULL_DIR = str(Path.joinpath(RESOURCES_DIR, unique_suffix("test_sync_pull")))
    CLD_SYNC_DIR = unique_suffix("test_sync")

    GRACE_PERIOD = 3  # seconds

    def setUp(self) -> None:
        delete_cld_folder_if_exists(self.CLD_SYNC_DIR)
        time.sleep(1)

    def tearDown(self) -> None:
        delete_cld_folder_if_exists(self.CLD_SYNC_DIR)
        time.sleep(1)
        shutil.rmtree(self.LOCAL_SYNC_PULL_DIR, ignore_errors=True)

    @retry_assertion
    def test_cli_sync_push(self):
        result = self.runner.invoke(cli, ['sync', '--push', '-F', TEST_FILES_DIR, self.CLD_SYNC_DIR])

        self.assertEqual(0, result.exit_code)
        self.assertIn("Synced | 12", result.output)
        self.assertIn("Done!", result.output)

    @retry_assertion
    def test_cli_sync_push_twice(self):
        self._upload_sync_files(TEST_FILES_DIR)

        # wait for indexing to be updated
        time.sleep(self.GRACE_PERIOD)

        result = self.runner.invoke(cli, ['sync', '--push', '-F', TEST_FILES_DIR, self.CLD_SYNC_DIR])

        self.assertEqual(0, result.exit_code)
        self.assertIn("Skipping 12 items", result.output)
        self.assertIn("Done!", result.output)

    @retry_assertion
    def test_cli_sync_push_out_of_sync(self):
        self._upload_sync_files(TEST_FILES_DIR)

        # wait for indexing to be updated
        time.sleep(self.GRACE_PERIOD)

        result = self.runner.invoke(cli, ['sync', '--push', '-F', self.LOCAL_PARTIAL_SYNC_DIR, self.CLD_SYNC_DIR])

        self.assertEqual(0, result.exit_code)
        self.assertIn("Found 2 items in local folder", result.output)
        self.assertIn("Skipping 1 items", result.output)
        self.assertIn("Deleting 11 resources", result.output)
        self.assertIn("In Sync| 1", result.output)
        self.assertIn("Synced | 1", result.output)
        self.assertIn("Done!", result.output)

    @retry_assertion
    def test_cli_sync_pull(self):
        self._upload_sync_files(TEST_FILES_DIR)

        # wait for indexing to be updated
        time.sleep(self.GRACE_PERIOD)

        result = self.runner.invoke(cli, ['sync', '--pull', '-F', self.LOCAL_SYNC_PULL_DIR, self.CLD_SYNC_DIR])

        self.assertEqual(0, result.exit_code, result.output)
        self.assertIn("Synced | 12", result.output)
        self.assertIn("Done!", result.output)

    @retry_assertion
    def test_cli_sync_pull_twice(self):
        self._upload_sync_files(TEST_FILES_DIR)

        # wait for indexing to be updated
        time.sleep(self.GRACE_PERIOD)

        result = self.runner.invoke(cli, ['sync', '--pull', '-F', self.LOCAL_SYNC_PULL_DIR, self.CLD_SYNC_DIR])

        self.assertEqual(0, result.exit_code)
        self.assertIn("Done!", result.output)

        result = self.runner.invoke(cli, ['sync', '--pull', '-F', self.LOCAL_SYNC_PULL_DIR, self.CLD_SYNC_DIR])

        self.assertEqual(0, result.exit_code)
        self.assertIn("Skipping 12 items", result.output)
        self.assertIn("Done!", result.output)

    @retry_assertion
    def test_cli_sync_pull_out_of_sync(self):
        self._upload_sync_files(TEST_FILES_DIR)

        # wait for indexing to be updated
        time.sleep(self.GRACE_PERIOD)

        shutil.copytree(self.LOCAL_PARTIAL_SYNC_DIR, self.LOCAL_SYNC_PULL_DIR)

        result = self.runner.invoke(cli, ['sync', '--pull', '-F', self.LOCAL_SYNC_PULL_DIR, self.CLD_SYNC_DIR])

        self.assertEqual(0, result.exit_code)
        self.assertIn("Found 2 items in local folder", result.output)
        self.assertIn("Skipping 1 items", result.output)
        self.assertIn("Deleting 1 local files", result.output)
        self.assertIn("Downloading 11 files", result.output)
        self.assertIn("In Sync| 1", result.output)
        self.assertIn("Synced | 11", result.output)
        self.assertIn("Done!", result.output)

    def _upload_sync_files(self, dir):
        result = self.runner.invoke(cli, ['sync', '--push', '-F', dir, self.CLD_SYNC_DIR])

        self.assertEqual(0, result.exit_code)
        self.assertIn("Synced | 12", result.output)
        self.assertIn("Done!", result.output)

    @patch('urllib3.request.RequestMethods.request')
    def test_sync_override_defaults(self, mocker):
        mocker.return_value = UPLOAD_MOCK_RESPONSE

        result = self.runner.invoke(cli, ['sync', '--push', '-fm', 'fixed', '-F', TEST_FILES_DIR, self.CLD_SYNC_DIR,
                                          "-o", "resource_type", "raw", "-O", "unique_filename", "True"])

        self.assertEqual(0, result.exit_code)

        self.assertIn("raw/upload", get_request_url(mocker))
        self.assertTrue(get_params(mocker)['unique_filename'])
