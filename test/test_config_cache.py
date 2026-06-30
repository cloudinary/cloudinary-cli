"""The parsed-config cache in load_config(): it skips the re-read+parse when the file is unchanged
on disk, but must return a fresh copy each call (callers mutate in place), must invalidate on our
own save, and must reload when a peer rewrites the file (os.replace stamps a new mtime)."""
import os
import tempfile
import unittest
from unittest.mock import patch

import cloudinary_cli.utils.config_utils as cu


class TestLoadConfigCache(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self._path = os.path.join(self._dir, "config.json")
        self._patch = patch.object(cu, "CLOUDINARY_CLI_CONFIG_FILE", self._path)
        self._patch.start()
        cu._invalidate_config_cache()
        self.addCleanup(self._patch.stop)
        self.addCleanup(cu._invalidate_config_cache)

    def _write(self, text):
        with open(self._path, "w") as f:
            f.write(text)

    def test_returns_fresh_copy_so_caller_mutation_does_not_leak(self):
        self._write('{"a": "cloudinary://k:s@a"}')
        first = cu.load_config()
        first["injected"] = "mutated"  # callers do cfg.update(...) on the result
        second = cu.load_config()
        self.assertNotIn("injected", second)  # the cache was not poisoned by the caller's mutation

    def test_cache_hit_skips_reparse_when_unchanged(self):
        self._write('{"a": "cloudinary://k:s@a"}')
        cu.load_config()  # populates the cache
        with patch.object(cu, "read_json_from_file") as read:
            cu.load_config()
        read.assert_not_called()  # served from cache: no second read+parse

    def test_reloads_when_file_changes_on_disk(self):
        self._write('{"a": "cloudinary://k:s@a"}')
        self.assertIn("a", cu.load_config())
        # A peer rewrite changes mtime/size; os.utime forces a distinct mtime even on a fast disk.
        self._write('{"a": "cloudinary://k:s@a", "b": "cloudinary://k:s@b"}')
        os.utime(self._path, (1, 1))
        self.assertIn("b", cu.load_config())

    def test_save_config_invalidates_cache(self):
        self._write('{"a": "cloudinary://k:s@a"}')
        cu.load_config()  # warm the cache
        cu.save_config({"a": "cloudinary://k:s@a", "c": "cloudinary://k:s@c"})
        self.assertIn("c", cu.load_config())  # invalidated -> reloaded our own write

    def test_missing_file_caches_empty_without_error(self):
        self.assertEqual({}, cu.load_config())  # no file: empty dict, no exception
        self._write('{"a": "cloudinary://k:s@a"}')
        os.utime(self._path, (2, 2))
        self.assertIn("a", cu.load_config())  # appears once the file is created


if __name__ == "__main__":
    unittest.main()
