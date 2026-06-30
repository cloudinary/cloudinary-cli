import unittest
from contextlib import contextmanager
from unittest.mock import patch

import cloudinary_cli.utils.config_utils as config_utils


@contextmanager
def _in_memory_config(initial=None):
    """Back load_config/save_config with an in-memory dict (no real config.json or lock)."""
    store = {"cfg": dict(initial or {})}

    def _load():
        return dict(store["cfg"])

    def _save(cfg):
        store["cfg"] = dict(cfg)

    @contextmanager
    def _noop_lock():
        yield

    with patch("cloudinary_cli.utils.config_utils.load_config", side_effect=_load), \
            patch("cloudinary_cli.utils.config_utils.save_config", side_effect=_save), \
            patch("cloudinary_cli.utils.config_utils.config_lock", _noop_lock):
        yield store


class TestDefaultConfigStorage(unittest.TestCase):
    def test_get_set_clear_round_trip(self):
        with _in_memory_config({"prod": "cloudinary://k:s@prod"}):
            self.assertIsNone(config_utils.get_default_config_name())
            config_utils.set_default_config("prod")
            self.assertEqual("prod", config_utils.get_default_config_name())
            config_utils.clear_default_config()
            self.assertIsNone(config_utils.get_default_config_name())

    def test_user_config_names_filters_reserved_key(self):
        with _in_memory_config({"prod": "cloudinary://k:s@prod"}):
            config_utils.set_default_config("prod")
            self.assertEqual(["prod"], config_utils.user_config_names())

    def test_default_key_present_in_raw_dict_only(self):
        with _in_memory_config({"a": "cloudinary://k:s@a", "b": "cloudinary://k:s@b"}):
            config_utils.set_default_config("b")
            self.assertIn("__default__", config_utils.load_config())
            self.assertNotIn("__default__", config_utils.user_config_names())

    def test_is_reserved_config_name(self):
        self.assertTrue(config_utils.is_reserved_config_name("__default__"))
        self.assertTrue(config_utils.is_reserved_config_name("__foo__"))
        self.assertFalse(config_utils.is_reserved_config_name("prod"))
        self.assertFalse(config_utils.is_reserved_config_name("__prod"))


if __name__ == "__main__":
    unittest.main()
