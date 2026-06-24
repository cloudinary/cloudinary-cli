import os
import stat
import sys
import tempfile
import unittest

from cloudinary_cli.utils.json_utils import (
    write_json_to_file,
    read_json_from_file,
    update_json_file,
)


class WriteJsonToFileTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "config.json")

    def _leftover(self):
        return [f for f in os.listdir(self.dir) if f != "config.json"]

    @unittest.skipIf(sys.platform == "win32", "POSIX directory modes not applicable on Windows")
    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root bypasses permission bits")
    def test_readonly_directory_raises_in_both_modes(self):
        os.chmod(self.dir, 0o500)
        try:
            with self.assertRaises(OSError):
                write_json_to_file({"a": 1}, self.path, atomic=True)
            with self.assertRaises(OSError):
                write_json_to_file({"a": 1}, self.path, atomic=False)
            self.assertFalse(os.path.exists(self.path))
            self.assertEqual([], os.listdir(self.dir))
        finally:
            os.chmod(self.dir, 0o700)

    def test_writes_valid_json(self):
        write_json_to_file({"a": 1, "b": "two"}, self.path)
        self.assertEqual({"a": 1, "b": "two"}, read_json_from_file(self.path))

    def test_overwrite_replaces_contents(self):
        write_json_to_file({"old": True}, self.path)
        write_json_to_file({"new": True}, self.path)
        self.assertEqual({"new": True}, read_json_from_file(self.path))

    def test_respects_indent_and_sort_keys(self):
        write_json_to_file({"b": 1, "a": 2}, self.path, indent=2, sort_keys=True)
        with open(self.path) as f:
            content = f.read()
        self.assertEqual('{\n  "a": 2,\n  "b": 1\n}', content)

    def test_atomic_writes_valid_json(self):
        write_json_to_file({"a": 1}, self.path, atomic=True)
        self.assertEqual({"a": 1}, read_json_from_file(self.path))

    def test_atomic_leaves_no_temp_files(self):
        write_json_to_file({"a": 1}, self.path, atomic=True)
        self.assertEqual([], self._leftover())

    def test_atomic_failed_write_removes_temp_and_keeps_original(self):
        write_json_to_file({"keep": True}, self.path, atomic=True)
        # An unserializable object makes json.dump raise mid-write.
        with self.assertRaises(TypeError):
            write_json_to_file({"bad": object()}, self.path, atomic=True)
        self.assertEqual({"keep": True}, read_json_from_file(self.path))
        self.assertEqual([], self._leftover())

    def test_non_atomic_is_default(self):
        # The non-atomic path writes in place: open('w') truncates the target up front, so a
        # mid-write failure leaves a corrupted file. This documents why atomic=True exists and
        # must be opted into for files that matter (config, sync meta).
        write_json_to_file({"keep": True}, self.path)
        with self.assertRaises(TypeError):
            write_json_to_file({"bad": object()}, self.path)
        with self.assertRaises(ValueError):  # JSONDecodeError on the partial write
            read_json_from_file(self.path)


class UpdateJsonFileTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "data.json")

    def test_creates_file_when_missing(self):
        update_json_file({"a": 1}, self.path)
        self.assertEqual({"a": 1}, read_json_from_file(self.path))

    def test_merges_into_existing(self):
        write_json_to_file({"a": 1, "b": 2}, self.path)
        update_json_file({"b": 20, "c": 3}, self.path)
        self.assertEqual({"a": 1, "b": 20, "c": 3}, read_json_from_file(self.path))

    def test_atomic_flag_merges_and_leaves_no_temp(self):
        write_json_to_file({"a": 1}, self.path)
        update_json_file({"b": 2}, self.path, atomic=True)
        self.assertEqual({"a": 1, "b": 2}, read_json_from_file(self.path))
        leftover = [f for f in os.listdir(self.dir) if f != "data.json"]
        self.assertEqual([], leftover)


if __name__ == "__main__":
    unittest.main()
