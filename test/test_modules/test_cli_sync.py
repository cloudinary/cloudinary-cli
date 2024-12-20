import shutil
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from cloudinary_cli.cli import cli
from test.helper_test import unique_suffix, RESOURCES_DIR, TEST_FILES_DIR, delete_cld_folder_if_exists, retry_assertion, \
    get_request_url, get_params, URLLIB3_REQUEST
from test.test_modules.test_cli_upload_dir import UPLOAD_MOCK_RESPONSE
from cloudinary_cli.utils.api_utils import get_folder_mode


class TestCLISync(unittest.TestCase):
    runner = CliRunner()

    LOCAL_PARTIAL_SYNC_DIR = str(Path.joinpath(RESOURCES_DIR, "test_sync_partial"))
    LOCAL_SYNC_PULL_DIR = str(Path.joinpath(RESOURCES_DIR, unique_suffix("test_sync_pull")))
    CLD_SYNC_DIR = unique_suffix("test_sync")

    DUPLICATE_NAME = unique_suffix("duplicate_name")

    GRACE_PERIOD = 3  # seconds

    folder_mode = "fixed"

    def setUp(self) -> None:
        self.folder_mode = get_folder_mode()
        delete_cld_folder_if_exists(self.CLD_SYNC_DIR, self.folder_mode)
        time.sleep(1)

    def tearDown(self) -> None:
        delete_cld_folder_if_exists(self.CLD_SYNC_DIR, self.folder_mode)
        time.sleep(1)
        shutil.rmtree(self.LOCAL_SYNC_PULL_DIR, ignore_errors=True)

    @retry_assertion
    def test_cli_sync_push(self):
        result = self.runner.invoke(cli, ['sync', '--push', '-F', TEST_FILES_DIR, self.CLD_SYNC_DIR])

        self.assertEqual(0, result.exit_code)
        self.assertIn("Synced | 12", result.output)
        self.assertIn("Done!", result.output)

    def test_cli_sync_push_non_existing_folder(self):
        non_existing_dir = self.LOCAL_SYNC_PULL_DIR + "non_existing"
        result = self.runner.invoke(cli, ['sync', '--push', non_existing_dir, self.CLD_SYNC_DIR])

        self.assertIn(f"Cannot push a non-existent local folder '{non_existing_dir}'", result.output)
        self.assertIn("Aborting...", result.output)

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


    def test_cli_sync_pull_non_existing_folder(self):
        non_existing_dir = self.CLD_SYNC_DIR + "non_existing"
        result = self.runner.invoke(cli, ['sync', '--pull', self.LOCAL_SYNC_PULL_DIR, non_existing_dir])

        self.assertIn(f"Cannot pull from a non-existent Cloudinary folder '{non_existing_dir}'", result.output)
        self.assertIn("Aborting...", result.output)

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

    def _upload_sync_files(self, dir, optional_params=None):
        if optional_params is None:
            optional_params = []
        result = self.runner.invoke(cli, ['sync', '--push', '-F', dir, self.CLD_SYNC_DIR] + optional_params)

        self.assertEqual(0, result.exit_code)
        self.assertIn("Synced | 12", result.output)
        self.assertIn("Done!", result.output)

    @patch(URLLIB3_REQUEST)
    def test_sync_override_defaults(self, mocker):
        mocker.return_value = UPLOAD_MOCK_RESPONSE

        result = self.runner.invoke(cli, ['sync', '--push', '-fm', 'fixed', '-F', TEST_FILES_DIR, self.CLD_SYNC_DIR,
                                          "-o", "resource_type", "raw", "-O", "unique_filename", "True"])

        self.assertEqual(0, result.exit_code)

        self.assertIn("raw/upload", get_request_url(mocker))
        self.assertTrue(get_params(mocker)['unique_filename'])


    @unittest.skipUnless(get_folder_mode() == "dynamic", "requires dynamic folder mode")
    @retry_assertion
    def test_cli_sync_duplicate_file_names_dynamic_folder_mode(self):
        self._upload_sync_files(TEST_FILES_DIR, ['-o', 'display_name', self.DUPLICATE_NAME])

        # wait for indexing to be updated
        time.sleep(self.GRACE_PERIOD)

        result = self.runner.invoke(cli, ['sync', '--pull', '-F', self.LOCAL_SYNC_PULL_DIR, self.CLD_SYNC_DIR])

        self.assertEqual(0, result.exit_code)
        self.assertIn("Found 0 items in local folder", result.output)
        self.assertIn("Downloading 12 files", result.output)
        for index in range(1, 6):
            self.assertIn(f"{self.DUPLICATE_NAME} ({index})", result.output)
        self.assertIn("Done!", result.output)

        result = self.runner.invoke(cli, ['sync', '--push', '-F', self.LOCAL_SYNC_PULL_DIR, self.CLD_SYNC_DIR])

        self.assertEqual(0, result.exit_code)
        self.assertIn("Skipping 12 items", result.output)
        self.assertIn("Done!", result.output)


    @retry_assertion
    def test_cli_sync_push_dry_run(self):
        self._upload_sync_files(TEST_FILES_DIR)

        # wait for indexing to be updated
        time.sleep(self.GRACE_PERIOD)

        result = self.runner.invoke(cli, ['sync', '--push', '-F', self.LOCAL_PARTIAL_SYNC_DIR, self.CLD_SYNC_DIR, '--dry-run'])

        # check that no files were uploaded
        self.assertEqual(0, result.exit_code)
        self.assertIn("Dry run mode enabled. The following files would be uploaded:", result.output)
        self.assertIn("Done!", result.output)


    @retry_assertion
    def test_cli_sync_pull_dry_run(self):
        self._upload_sync_files(TEST_FILES_DIR)

        # wait for indexing to be updated
        time.sleep(self.GRACE_PERIOD)

        shutil.copytree(self.LOCAL_PARTIAL_SYNC_DIR, self.LOCAL_SYNC_PULL_DIR)

        result = self.runner.invoke(cli, ['sync', '--pull', '-F', self.LOCAL_SYNC_PULL_DIR, self.CLD_SYNC_DIR, '--dry-run'])

        # check that no files were downloaded
        self.assertEqual(0, result.exit_code)
        self.assertIn("Dry run mode enabled. The following files would be downloaded:", result.output)
        self.assertIn("Done!", result.output)
        