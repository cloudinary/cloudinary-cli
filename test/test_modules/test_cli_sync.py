import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from cloudinary_cli.cli import cli
from test.helper_test import unique_suffix, RESOURCES_DIR, TEST_FILES_DIR, delete_cld_folder_if_exists, retry_assertion, \
    get_request_url, get_params, URLLIB3_REQUEST
from test.test_modules.test_cli_upload_dir import UPLOAD_MOCK_RESPONSE
from cloudinary_cli.utils.api_utils import get_folder_mode, _display_path, query_cld_folder
from cloudinary_cli.modules.sync import SyncDir
from cloudinary_cli.utils.utils import etag

# the package exports the `sync` command under the same name as the module
sync_module = sys.modules[SyncDir.__module__]


class TestDisplayPath(unittest.TestCase):
    @staticmethod
    def _asset(resource_type, public_id, display_name, fmt=None):
        return {"resource_type": resource_type, "type": "upload", "public_id": public_id,
                "display_name": display_name, "format": fmt, "asset_folder": "folder"}

    def test_image_display_path_adds_format(self):
        self.assertEqual("folder/red.png", _display_path(self._asset("image", "abc123", "red", "png")))

    def test_raw_display_path_adds_missing_extension(self):
        self.assertEqual("folder/notes.txt", _display_path(self._asset("raw", "abc123.txt", "notes")))

    def test_raw_display_path_keeps_existing_extension(self):
        self.assertEqual("folder/notes.txt", _display_path(self._asset("raw", "abc123.txt", "notes.txt")))
        self.assertEqual("folder/notes.TXT", _display_path(self._asset("raw", "abc123.txt", "notes.TXT")))

    def test_raw_display_path_without_extension(self):
        self.assertEqual("folder/notes", _display_path(self._asset("raw", "abc123", "notes")))


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
        # the upload banner names both the destination folder and the active cloud
        self.assertIn(f"to Cloudinary folder '{self.CLD_SYNC_DIR}'", result.output)
        self.assertIn("in cloud '", result.output)

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


    def _local_files(self, files):
        local_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, local_dir, True)
        for name, content in files.items():
            Path(local_dir, name).write_text(content)
        return local_dir

    def _sync(self, direction, local_dir, *expected):
        result = self.runner.invoke(cli, ['sync', direction, '-F', local_dir, self.CLD_SYNC_DIR])
        self.assertEqual(0, result.exit_code, result.output)
        for text in expected:
            self.assertIn(text, result.output)
        return result

    def _wait_for_cld_files(self, count):
        for _ in range(10):
            if len(query_cld_folder(self.CLD_SYNC_DIR, self.folder_mode)) == count:
                return
            time.sleep(1)

    def _assert_nothing_to_sync(self, direction, local_dir, count):
        result = self._sync(direction, local_dir, f"Skipping {count} items", "Done!")
        self.assertNotIn("Deleting", result.output)
        self.assertNotIn("Uploading", result.output)
        self.assertNotIn("Downloading", result.output)

    @unittest.skipUnless(get_folder_mode() == "dynamic", "requires dynamic folder mode")
    def test_cli_sync_push_raw_files_with_cld_sync_entries_without_extension(self):
        local_dir = self._local_files({"notes.txt": "txt", "notes.csv": "csv"})
        self._sync('--push', local_dir, "Synced | 2")
        self._wait_for_cld_files(2)
        # entries saved by versions that did not keep the extension of raw files
        Path(local_dir, ".cld-sync").write_text(json.dumps({"notes.txt": "notes", "notes.csv": "notes"}))

        self._assert_nothing_to_sync('--push', local_dir, 2)
        self._assert_nothing_to_sync('--push', local_dir, 2)
        self._assert_nothing_to_sync('--pull', local_dir, 2)

    @unittest.skipUnless(get_folder_mode() == "dynamic", "requires dynamic folder mode")
    def test_cli_sync_raw_file_saved_without_extension(self):
        self._sync('--push', self._local_files({"notes.txt": "txt"}), "Synced | 1")
        self._wait_for_cld_files(1)
        # file pulled by versions that did not keep the extension of raw files
        local_dir = self._local_files({"notes": "txt"})

        self._assert_nothing_to_sync('--push', local_dir, 1)
        self._assert_nothing_to_sync('--pull', local_dir, 1)

    @unittest.skipUnless(get_folder_mode() == "dynamic", "requires dynamic folder mode")
    def test_cli_sync_push_raw_duplicates_saved_without_extension(self):
        result = self.runner.invoke(cli, ['sync', '--push', '-F', self._local_files({"b.txt": "b", "c.txt": "c"}),
                                          self.CLD_SYNC_DIR, '-o', 'display_name', 'notes'])
        self.assertEqual(0, result.exit_code, result.output)
        self._wait_for_cld_files(2)
        # files pulled by versions that did not keep the extension of raw files, the first one deleted remotely
        local_dir = self._local_files({"notes (1)": "a", "notes (2)": "b", "notes (3)": "c"})

        result = self._sync('--push', local_dir, "Skipping 2 items", "Synced | 1")
        self.assertNotIn("Deleting", result.output)
        self._wait_for_cld_files(3)

    @unittest.skipUnless(get_folder_mode() == "dynamic", "requires dynamic folder mode")
    def test_cli_sync_raw_file_keeps_extension(self):
        local_dir = self._local_files({"notes.txt": "txt"})
        self._sync('--push', local_dir, "Synced | 1")
        self.assertFalse(Path(local_dir, ".cld-sync").exists())
        self._wait_for_cld_files(1)

        self._sync('--pull', self.LOCAL_SYNC_PULL_DIR, "Synced | 1")
        self.assertTrue(Path(self.LOCAL_SYNC_PULL_DIR, "notes.txt").is_file())
        self._assert_nothing_to_sync('--push', self.LOCAL_SYNC_PULL_DIR, 1)

    def test_cli_sync_push_include_hidden_skips_meta_file(self):
        local_dir = self._local_files({"notes.txt": "txt", ".hidden.txt": "hidden", ".cld-sync": "{}"})
        result = self.runner.invoke(cli, ['sync', '--push', '-F', '-H', local_dir, self.CLD_SYNC_DIR])
        self.assertEqual(0, result.exit_code, result.output)
        self.assertIn("Synced | 2", result.output)
        self._wait_for_cld_files(2)

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


class TestCLISyncDuplicateNamesOffline(unittest.TestCase):
    runner = CliRunner()

    def setUp(self) -> None:
        self.local_dir = tempfile.mkdtemp()
        self.notes_path = os.path.join(self.local_dir, "notes.txt")
        with open(self.notes_path, "w") as f:
            f.write("notes")
        # mapping that an earlier push of a raw file saves in dynamic folder mode
        with open(os.path.join(self.local_dir, ".cld-sync"), "w") as f:
            json.dump({"notes.txt": "notes"}, f)

    def tearDown(self) -> None:
        shutil.rmtree(self.local_dir, ignore_errors=True)

    def _remote_notes(self, asset_id, created_at):
        return {
            "asset_id": asset_id, "normalized_path": "notes", "normalized_unique_path": "notes",
            "type": "upload", "resource_type": "raw", "public_id": f"pid_{asset_id}", "format": None,
            "etag": etag(self.notes_path), "relative_path": f"pid_{asset_id}", "access_mode": "public",
            "created_at": created_at,
        }

    def test_local_candidates_exact_match(self):
        sync_dir = SyncDir.__new__(SyncDir)
        sync_dir.local_files = {f: {"etag": f} for f in ["notes.txt", "notes", "notes (1)", "notes (12)",
                                                         "notes (1).txt", "notesX", "a+b.jpg", "aab.jpg"]}

        self.assertEqual(["notes", "notes (1)", "notes (12)"], sorted(sync_dir._local_candidates("notes")))
        self.assertEqual(["notes (1).txt", "notes.txt"], sorted(sync_dir._local_candidates("notes.txt")))
        self.assertEqual(["a+b.jpg"], list(sync_dir._local_candidates("a+b.jpg")))

    @patch.object(sync_module, "call_api")
    @patch.object(sync_module, "query_cld_folder")
    @patch.object(sync_module, "cld_folder_exists", return_value=True)
    def test_sync_push_does_not_delete_all_duplicates_of_synced_file(self, _, query_mock, call_api_mock):
        query_mock.return_value = {"a1": self._remote_notes("a1", "2026-01-01"),
                                   "a2": self._remote_notes("a2", "2026-01-02")}
        call_api_mock.return_value = {"deleted": {"pid_a1": "deleted", "pid_a2": "deleted"}}

        with patch.object(sync_module, "upload_file") as upload_mock:
            result = self.runner.invoke(cli, ['sync', '--push', '-F', '-fm', 'dynamic', self.local_dir, 'folder'])

        self.assertEqual(0, result.exit_code, result.output)
        deleted = [pid for c in call_api_mock.call_args_list for pid in c.args[1]]
        uploaded = [c.args[0] for c in upload_mock.call_args_list]
        # notes.txt must stay on Cloudinary: either a remote copy is kept, or the file is uploaded again.
        self.assertTrue(len(deleted) < 2 or uploaded, f"deleted {deleted}, uploaded {uploaded}")


class TestCLISyncMetaFileOffline(unittest.TestCase):
    runner = CliRunner()

    def setUp(self) -> None:
        self.local_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.local_dir, True)
        self.notes_path = os.path.join(self.local_dir, "notes.txt")
        Path(self.notes_path).write_text("notes")
        os.mkdir(os.path.join(self.local_dir, "sub"))
        for meta_file in [".cld-sync", "sub/.cld-sync"]:
            Path(self.local_dir, meta_file).write_text("{}")

        self.query_mock = self._patch("query_cld_folder", return_value={})
        self._patch("cld_folder_exists", return_value=True)
        self.call_api_mock = self._patch("call_api")
        self.upload_mock = self._patch("upload_file")
        self.download_mock = self._patch("download_file")

    def _patch(self, name, **kwargs):
        patcher = patch.object(sync_module, name, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def _remote_files(self, *names):
        return {name: {
            "asset_id": name, "normalized_path": name, "normalized_unique_path": name,
            "type": "upload", "resource_type": "raw", "public_id": name, "format": None,
            "etag": etag(self.notes_path), "relative_path": name, "access_mode": "public",
            "created_at": "2026-01-01",
        } for name in names}

    def _sync(self, direction):
        result = self.runner.invoke(cli, ['sync', direction, '-F', '-H', '-fm', 'fixed', self.local_dir, 'folder'])
        self.assertEqual(0, result.exit_code, result.output)

    def test_sync_push_include_hidden_does_not_upload_meta_file(self):
        self._sync('--push')

        self.assertEqual([self.notes_path], [c.args[0] for c in self.upload_mock.call_args_list])

    def test_sync_pull_include_hidden_does_not_delete_meta_file(self):
        self.query_mock.return_value = self._remote_files("notes.txt")

        self._sync('--pull')

        self.assertTrue(Path(self.local_dir, ".cld-sync").is_file())
        self.assertTrue(Path(self.local_dir, "sub/.cld-sync").is_file())

    def test_sync_push_does_not_delete_remote_meta_file(self):
        self.query_mock.return_value = self._remote_files("notes.txt", ".cld-sync", "sub/.cld-sync")

        self._sync('--push')

        self.call_api_mock.assert_not_called()

    def test_sync_pull_does_not_download_remote_meta_file(self):
        self.query_mock.return_value = self._remote_files("notes.txt", ".cld-sync", "sub/.cld-sync")

        self._sync('--pull')

        self.download_mock.assert_not_called()
