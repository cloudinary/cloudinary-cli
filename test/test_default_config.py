import unittest
from contextlib import contextmanager
from unittest.mock import patch

import cloudinary_cli.utils.config_utils as config_utils
from cloudinary_cli.defaults import ACCOUNT_EMAIL_PARAM


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


class TestSaveNamedConfig(unittest.TestCase):
    def test_first_config_auto_defaults(self):
        with _in_memory_config(), \
                patch("cloudinary_cli.utils.config_utils.is_env_configured", return_value=False):
            status = config_utils.save_named_config("prod", "cloudinary://k:s@prod")
            self.assertEqual("made", status)
            self.assertEqual("prod", config_utils.get_default_config_name())

    def test_second_config_does_not_auto_default(self):
        with _in_memory_config({"prod": "cloudinary://k:s@prod", "__default__": "prod"}), \
                patch("cloudinary_cli.utils.config_utils.is_env_configured", return_value=False):
            status = config_utils.save_named_config("staging", "cloudinary://k:s@staging")
            self.assertEqual("no", status)
            self.assertEqual("prod", config_utils.get_default_config_name())

    def test_env_configured_suppresses_auto_default(self):
        with _in_memory_config(), \
                patch("cloudinary_cli.utils.config_utils.is_env_configured", return_value=True):
            status = config_utils.save_named_config("prod", "cloudinary://k:s@prod")
            self.assertEqual("no", status)
            self.assertIsNone(config_utils.get_default_config_name())

    def test_set_default_forces_default(self):
        with _in_memory_config({"prod": "cloudinary://k:s@prod", "__default__": "prod"}), \
                patch("cloudinary_cli.utils.config_utils.is_env_configured", return_value=False):
            status = config_utils.save_named_config("staging", "cloudinary://k:s@staging", set_default=True)
            self.assertEqual("made", status)
            self.assertEqual("staging", config_utils.get_default_config_name())

    def test_resaving_current_default_reports_already(self):
        with _in_memory_config({"prod": "cloudinary://k:s@prod", "__default__": "prod"}), \
                patch("cloudinary_cli.utils.config_utils.is_env_configured", return_value=False):
            status = config_utils.save_named_config("prod", "cloudinary://k:s@prod-new")
            self.assertEqual("already", status)
            self.assertEqual("prod", config_utils.get_default_config_name())
            self.assertEqual("cloudinary://k:s@prod-new", config_utils.load_config()["prod"])


def _agent_url(cloud, email, key="k", secret="s"):
    """A saved agent config URL carrying an account email, built the way production builds it."""
    return config_utils.build_config_url(cloud, params={ACCOUNT_EMAIL_PARAM: email},
                                         api_key=key, api_secret=secret)


class TestAccountEmailInUrl(unittest.TestCase):
    def test_email_encoded_and_read_back(self):
        url = _agent_url("cloud", "you@example.com")
        self.assertIn("account_email=you%40example.com", url)  # percent-encoded
        self.assertEqual("you@example.com", config_utils.email_from_url(url))

    def test_plus_addressing_roundtrips(self):
        url = _agent_url("cloud", "someone+agent@example.com")
        self.assertIn("account_email=someone%2Bagent%40example.com", url)
        self.assertEqual("someone+agent@example.com", config_utils.email_from_url(url))

    def test_email_from_url_normalizes(self):
        # email_from_url lower-cases/strips what it reads back
        url = config_utils.build_config_url("cloud", params={ACCOUNT_EMAIL_PARAM: "You@Example.com"},
                                            api_key="k", api_secret="s")
        self.assertEqual("you@example.com", config_utils.email_from_url(url))

    def test_email_from_url_none_when_absent(self):
        self.assertIsNone(config_utils.email_from_url("cloudinary://k:s@cloud"))

    def test_config_name_for_email_finds_match(self):
        with _in_memory_config({
            "agent1": _agent_url("c1", "you@example.com"),
            "plain": "cloudinary://k:s@c2",
        }):
            self.assertEqual("agent1", config_utils.config_name_for_email("YOU@example.com "))

    def test_config_name_for_email_unknown_returns_none(self):
        with _in_memory_config({"plain": "cloudinary://k:s@c2"}):
            self.assertIsNone(config_utils.config_name_for_email("you@example.com"))

    def test_config_name_for_email_self_heals_after_removal(self):
        with _in_memory_config({"agent1": _agent_url("c1", "you@example.com")}):
            self.assertEqual("agent1", config_utils.config_name_for_email("you@example.com"))
            config_utils.remove_config_keys("agent1")
            self.assertIsNone(config_utils.config_name_for_email("you@example.com"))

    def test_config_to_dict_surfaces_account_email(self):
        import cloudinary
        cfg = cloudinary.Config()
        # noinspection PyProtectedMember
        cfg._setup_from_parsed_url(cfg._parse_cloudinary_url(_agent_url("cloud", "you@example.com")))
        self.assertEqual("you@example.com", config_utils.config_to_dict(cfg).get("account_email"))


class TestBuildConfigUrl(unittest.TestCase):
    def _parsed(self, url):
        import cloudinary
        cfg = cloudinary.Config()
        # noinspection PyProtectedMember
        cfg._setup_from_parsed_url(cfg._parse_cloudinary_url(url))
        return cfg

    def test_api_key_url_roundtrips_through_sdk(self):
        url = config_utils.build_config_url("mycloud", api_key="111", api_secret="sek")
        cfg = self._parsed(url)
        self.assertEqual(("111", "sek", "mycloud"), (cfg.api_key, cfg.api_secret, cfg.cloud_name))

    def test_api_key_url_with_email_param(self):
        url = config_utils.build_config_url(
            "mycloud", params={ACCOUNT_EMAIL_PARAM: "you@example.com"}, api_key="111", api_secret="sek")
        cfg = self._parsed(url)
        self.assertEqual("111", cfg.api_key)
        self.assertEqual("you@example.com", cfg.__dict__.get(ACCOUNT_EMAIL_PARAM))

    def test_keyless_oauth_url(self):
        url = config_utils.build_config_url("mycloud", {"oauth_token": "abc", "region": "api"})
        self.assertTrue(url.startswith("cloudinary://mycloud?"))
        cfg = self._parsed(url)
        self.assertIsNone(cfg.api_key)
        self.assertEqual("abc", cfg.__dict__.get("oauth_token"))

    def test_build_rejects_missing_cloud_name(self):
        with self.assertRaises(ValueError):
            config_utils.build_config_url("", api_key="111", api_secret="sek")


class TestValidateConfigUrl(unittest.TestCase):
    def test_accepts_valid(self):
        self.assertEqual("cloudinary://k:s@cloud",
                         config_utils.validate_config_url("cloudinary://k:s@cloud"))

    def test_rejects_bad_scheme(self):
        with self.assertRaises(ValueError):
            config_utils.validate_config_url("http://k:s@cloud")

    def test_rejects_missing_cloud_name(self):
        with self.assertRaises(ValueError):
            config_utils.validate_config_url("cloudinary://")


class TestConfigTableEmailColumn(unittest.TestCase):
    def _row(self, name, cloud, **extra):
        return dict({"name": name, "cloud_name": cloud, "type": "api_key",
                     "default": False, "active": False}, **extra)

    def test_email_column_hidden_when_no_emails(self):
        from cloudinary_cli.utils.config_listing import render_config_table
        table = render_config_table([self._row("a", "c1")])
        self.assertNotIn("EMAIL", table)

    def test_email_column_shown_when_any_email(self):
        from cloudinary_cli.utils.config_listing import render_config_table
        table = render_config_table([
            self._row("a", "c1"),
            self._row("b", "c2", email="you@example.com"),
        ])
        self.assertIn("EMAIL", table)
        self.assertIn("you@example.com", table)


if __name__ == "__main__":
    unittest.main()
