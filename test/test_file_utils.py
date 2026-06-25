import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cloudinary_cli.utils.file_utils import (
    get_destination_folder,
    walk_dir,
    normalize_file_extension,
    atomic_write,
)
from test.helper_test import RESOURCES_DIR


class FileUtilsTest(unittest.TestCase):
    def test_get_destination_folder(self):
        """ should parse option values correctly """

        self.assertEqual("1/2/3", get_destination_folder("1", "2/3/file.jpg"))
        self.assertEqual("1", get_destination_folder("1", "file.jpg"))
        self.assertEqual("cloudinaryfolder/myfolder/subfolder",
                         get_destination_folder("cloudinaryfolder",
                                                "/Users/user/myfolder/subfolder/file.jpg",
                                                parent="/Users/user/"))

    def test_walk_dir(self):
        """ should skip hidden files in the directory """

        test_dir = str(Path.joinpath(RESOURCES_DIR, "test_file_utils"))

        self.assertEqual(1, len(walk_dir(test_dir, include_hidden=False)))
        self.assertEqual(4, len(walk_dir(test_dir, include_hidden=True)))

    def test_normalize_file_extension(self):
        for value, expected in {
            "sample.jpg": "sample.jpg",
            "sample": "sample",
            "sample.JPG": "sample.jpg",
            "sample.JPE": "sample.jpg",
            "SAMPLE.JPEG": "SAMPLE.jpg",
        }.items():
            self.assertEqual(expected, normalize_file_extension(value))


class AtomicWriteTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "out.txt")

    def _leftover(self):
        return [f for f in os.listdir(self.dir) if f != os.path.basename(self.path)]

    def test_writes_content(self):
        atomic_write(self.path, lambda f: f.write("hello"))
        with open(self.path) as f:
            self.assertEqual("hello", f.read())

    def test_overwrite_replaces_contents(self):
        atomic_write(self.path, lambda f: f.write("old"))
        atomic_write(self.path, lambda f: f.write("new"))
        with open(self.path) as f:
            self.assertEqual("new", f.read())

    def test_leaves_no_temp_files(self):
        atomic_write(self.path, lambda f: f.write("x"))
        self.assertEqual([], self._leftover())

    def test_failed_write_removes_temp_and_keeps_original(self):
        atomic_write(self.path, lambda f: f.write("keep"))

        def boom(f):
            f.write("partial")
            raise ValueError("write failed")

        with self.assertRaises(ValueError):
            atomic_write(self.path, boom)

        with open(self.path) as f:
            self.assertEqual("keep", f.read())
        self.assertEqual([], self._leftover())

    def test_missing_target_is_not_created_on_failure(self):
        with self.assertRaises(ValueError):
            atomic_write(self.path, lambda f: (_ for _ in ()).throw(ValueError()))
        self.assertFalse(os.path.exists(self.path))
        self.assertEqual([], os.listdir(self.dir))

    @unittest.skipIf(sys.platform == "win32", "POSIX file modes not applicable on Windows")
    def test_normalizes_to_umask_mode(self):
        # mkstemp creates the temp as 0600; atomic_write must relax it to the umask default
        # so output files are not silently owner-only.
        old_umask = os.umask(0o022)
        try:
            atomic_write(self.path, lambda f: f.write("x"))
        finally:
            os.umask(old_umask)
        mode = stat.S_IMODE(os.stat(self.path).st_mode)
        self.assertEqual(0o644, mode)

    @unittest.skipIf(sys.platform == "win32", "POSIX file modes not applicable on Windows")
    def test_respects_restrictive_umask(self):
        old_umask = os.umask(0o077)
        try:
            atomic_write(self.path, lambda f: f.write("x"))
        finally:
            os.umask(old_umask)
        mode = stat.S_IMODE(os.stat(self.path).st_mode)
        self.assertEqual(0o600, mode)

    @unittest.skipIf(sys.platform == "win32", "POSIX permission bits")
    def test_explicit_mode_overrides_umask(self):
        # A4: with an explicit mode the result is that mode regardless of a permissive umask, so the
        # config file is never widened to the umask default.
        old_umask = os.umask(0o000)
        try:
            atomic_write(self.path, lambda f: f.write("x"), mode=0o600)
        finally:
            os.umask(old_umask)
        self.assertEqual(0o600, stat.S_IMODE(os.stat(self.path).st_mode))

    @unittest.skipIf(sys.platform == "win32", "POSIX permission bits")
    def test_explicit_mode_temp_file_never_wider_during_write(self):
        # The temp file must already carry the final mode before the replace, so there is no instant
        # at which the destination is world-readable. Capture the temp file's mode at replace time.
        seen = {}
        real_replace = os.replace

        def capturing_replace(src, dst):
            seen["mode"] = stat.S_IMODE(os.stat(src).st_mode)
            return real_replace(src, dst)

        old_umask = os.umask(0o000)
        try:
            with patch("cloudinary_cli.utils.file_utils.os.replace", side_effect=capturing_replace):
                atomic_write(self.path, lambda f: f.write("x"), mode=0o600)
        finally:
            os.umask(old_umask)
        self.assertEqual(0o600, seen["mode"])  # 0600 on the temp file, before it becomes the target

    def test_writes_to_filename_in_cwd_without_dir(self):
        # path.dirname("") is "" -> must fall back to "." rather than failing.
        old_cwd = os.getcwd()
        os.chdir(self.dir)
        try:
            atomic_write("bare.txt", lambda f: f.write("x"))
            with open("bare.txt") as f:
                self.assertEqual("x", f.read())
        finally:
            os.chdir(old_cwd)

    @unittest.skipIf(sys.platform == "win32", "POSIX directory modes not applicable on Windows")
    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root bypasses permission bits")
    def test_readonly_directory_raises_and_leaves_nothing(self):
        # mkstemp needs to create the temp inside the directory, so a read-only directory must
        # fail loudly rather than silently writing nothing, and must not leave a temp file behind.
        os.chmod(self.dir, 0o500)
        try:
            with self.assertRaises(OSError):
                atomic_write(self.path, lambda f: f.write("x"))
            self.assertFalse(os.path.exists(self.path))
            self.assertEqual([], os.listdir(self.dir))
        finally:
            os.chmod(self.dir, 0o700)

    @unittest.skipIf(sys.platform == "win32", "POSIX file modes not applicable on Windows")
    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root bypasses permission bits")
    def test_overwrites_readonly_target_in_writable_dir(self):
        # os.replace only needs write permission on the directory, not the target, so atomic_write
        # can replace a read-only file (where a plain open(file, 'w') would fail) and normalizes
        # the result to the umask default.
        old_umask = os.umask(0o022)
        try:
            atomic_write(self.path, lambda f: f.write("old"))
            os.chmod(self.path, 0o400)
            atomic_write(self.path, lambda f: f.write("new"))
        finally:
            os.umask(old_umask)
        with open(self.path) as f:
            self.assertEqual("new", f.read())
        self.assertEqual(0o644, stat.S_IMODE(os.stat(self.path).st_mode))
        self.assertEqual([], self._leftover())
