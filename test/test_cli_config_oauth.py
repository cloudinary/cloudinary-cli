import os
import time
import unittest
from unittest.mock import patch

import cloudinary
from click.testing import CliRunner

from cloudinary_cli.auth.session import Session, to_cloudinary_url
from cloudinary_cli.cli import cli
from cloudinary_cli.utils.config_resolver import config_to_api_kwargs, get_cloudinary_config
from cloudinary_cli.utils.config_utils import config_to_dict, show_cloudinary_config


def _oauth_url(cloud="eu-cloud", region="api-eu"):
    return to_cloudinary_url(Session(
        cloud_name=cloud, access_token="eyJ.secret_access.tok", refresh_token="rt_secret_value",
        expires_at=int(time.time()) + 300, region=region, issuer="https://oauth.cloudinary.com/"))


class _RestoresSdkConfig(unittest.TestCase):
    def setUp(self):
        self._env_snapshot = dict(os.environ)
        self.addCleanup(self._restore_sdk_config)

    def _restore_sdk_config(self):
        os.environ.clear()
        os.environ.update(self._env_snapshot)
        cloudinary.reset_config()


class TestLogoutScope(unittest.TestCase):
    """logout must only remove OAuth logins, never plain saved configs."""

    def test_removes_oauth_login(self):
        from cloudinary_cli.auth import logout
        saved = {"eu-cloud": _oauth_url()}
        with patch("cloudinary_cli.auth.load_config", return_value=saved), \
                patch("cloudinary_cli.auth.remove_config_keys") as remove:
            self.assertEqual("removed", logout("eu-cloud"))
            remove.assert_called_once_with("eu-cloud")

    def test_refuses_non_oauth_config(self):
        from cloudinary_cli.auth import logout
        saved = {"mykey": "cloudinary://key:secret@cloud"}
        with patch("cloudinary_cli.auth.load_config", return_value=saved), \
                patch("cloudinary_cli.auth.remove_config_keys") as remove:
            self.assertEqual("not_oauth", logout("mykey"))
            remove.assert_not_called()

    def test_missing_name(self):
        from cloudinary_cli.auth import logout
        with patch("cloudinary_cli.auth.load_config", return_value={}), \
                patch("cloudinary_cli.auth.remove_config_keys") as remove:
            self.assertEqual("not_found", logout("nope"))
            remove.assert_not_called()


class TestLogoutInteractiveSelect(unittest.TestCase):
    """`cld logout` with no name lists OAuth logins and removes the chosen one."""

    runner = CliRunner()

    def test_lists_only_oauth_and_removes_selected(self):
        saved = {"mykey": "cloudinary://key:secret@cloud",
                 "cloud-a": _oauth_url("cloud-a"), "cloud-b": _oauth_url("cloud-b")}
        with patch("cloudinary_cli.auth.load_config", return_value=saved), \
                patch("cloudinary_cli.auth.remove_config_keys") as remove:
            result = self.runner.invoke(cli, ["logout"], input="2\n")
        self.assertIn("cloud-a", result.output)
        self.assertIn("cloud-b", result.output)
        self.assertNotIn("mykey", result.output)  # non-oauth not offered
        remove.assert_called_once_with("cloud-b")

    def test_no_oauth_logins(self):
        with patch("cloudinary_cli.auth.load_config",
                   return_value={"mykey": "cloudinary://key:secret@cloud"}), \
                patch("cloudinary_cli.auth.remove_config_keys") as remove:
            result = self.runner.invoke(cli, ["logout"], input="\n")
        self.assertIn("No saved OAuth logins", result.output)
        remove.assert_not_called()

    def test_cancel_on_empty_input(self):
        with patch("cloudinary_cli.auth.load_config", return_value={"cloud-a": _oauth_url("cloud-a")}), \
                patch("cloudinary_cli.auth.remove_config_keys") as remove:
            result = self.runner.invoke(cli, ["logout"], input="\n")
        remove.assert_not_called()
        self.assertEqual(0, result.exit_code)

    def test_invalid_non_numeric_errors(self):
        with patch("cloudinary_cli.auth.load_config", return_value={"cloud-a": _oauth_url("cloud-a")}), \
                patch("cloudinary_cli.auth.remove_config_keys") as remove:
            result = self.runner.invoke(cli, ["logout"], input="sdfdsf\n", standalone_mode=False)
        self.assertIn("Invalid selection", result.output)
        self.assertFalse(result.return_value)  # main() maps falsy -> exit 1
        remove.assert_not_called()

    def test_out_of_range_errors(self):
        with patch("cloudinary_cli.auth.load_config", return_value={"cloud-a": _oauth_url("cloud-a")}), \
                patch("cloudinary_cli.auth.remove_config_keys") as remove:
            result = self.runner.invoke(cli, ["logout"], input="5\n", standalone_mode=False)
        self.assertIn("Invalid selection", result.output)
        self.assertFalse(result.return_value)
        remove.assert_not_called()


class TestConfigSecretMasking(unittest.TestCase):
    """show_cloudinary_config must never print a secret in the clear."""

    def test_masks_api_secret(self):
        config = cloudinary.Config()
        config.update(cloud_name="c", api_key="k", api_secret="abcdefghIJKLMNOP")
        with patch("cloudinary_cli.utils.config_utils.echo") as echo:
            show_cloudinary_config(config)
        out = echo.call_args[0][0]
        self.assertNotIn("abcdefghIJKLMNOP", out)
        self.assertIn("MNOP", out)  # last 4 kept

    def test_masks_account_url_password(self):
        config = cloudinary.Config()
        config.update(account_url="account://acc_key:SUPERSECRETPASSWORD@account_id")
        with patch("cloudinary_cli.utils.config_utils.echo") as echo:
            show_cloudinary_config(config)
        out = echo.call_args[0][0]
        self.assertNotIn("SUPERSECRETPASSWORD", out)
        self.assertIn("acc_key", out)      # identifier kept
        self.assertIn("account_id", out)   # host kept

    def test_masks_oauth_and_refresh_tokens(self):
        config = cloudinary.Config()
        config.update(cloud_name="c", oauth_token="eyJ.secret_access.tok",
                      refresh_token="rt_secret_value")
        with patch("cloudinary_cli.utils.config_utils.echo") as echo:
            show_cloudinary_config(config)
        out = echo.call_args[0][0]
        self.assertNotIn("eyJ.secret_access.tok", out)
        self.assertNotIn("rt_secret_value", out)


class TestOAuthConfigCoexistence(_RestoresSdkConfig):
    runner = CliRunner()

    CONFIG = {
        "prod-account": "cloudinary://key:secret@prod_cloud",
        "eu-cloud": _oauth_url(),
    }

    def test_ls_shows_both(self):
        with patch("cloudinary_cli.core.config.load_config", return_value=dict(self.CONFIG)):
            result = self.runner.invoke(cli, ['config', '--ls'])
        self.assertEqual(0, result.exit_code)
        self.assertIn("prod-account", result.output)
        self.assertIn("eu-cloud", result.output)

    def test_show_oauth_masks_token(self):
        with patch("cloudinary_cli.core.config.load_config", return_value=dict(self.CONFIG)):
            result = self.runner.invoke(cli, ['config', '--show', 'eu-cloud'])
        self.assertEqual(0, result.exit_code)
        self.assertIn("eu-cloud", result.output)
        self.assertNotIn("eyJ.secret_access.tok", result.output)
        self.assertNotIn("rt_secret_value", result.output)

    def test_select_oauth_login_configures_sdk(self):
        with patch("cloudinary_cli.utils.config_resolver.load_config", return_value=dict(self.CONFIG)):
            result = self.runner.invoke(cli, ['-C', 'eu-cloud', 'url', 'sample'])
        self.assertEqual(0, result.exit_code, result.output)
        self.assertIn("eu-cloud", result.output)


class TestSoleOAuthLoginFallbackGate(_RestoresSdkConfig):
    runner = CliRunner()

    def _invoke(self, args, sole_login, saved=None, env=None):
        env = dict(env or {})
        with patch("cloudinary_cli.utils.config_resolver.find_sole_oauth_login", return_value=sole_login), \
                patch("cloudinary_cli.utils.config_resolver.load_config", return_value=dict(saved or {})), \
                patch.dict("os.environ", env, clear=False):
            for key in ("CLOUDINARY_URL", "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY",
                        "CLOUDINARY_API_SECRET"):
                if key not in env:
                    os.environ.pop(key, None)
            cloudinary.reset_config()
            return self.runner.invoke(cli, args)

    def test_fires_when_no_explicit_config(self):
        sole = ("eu-cloud", _oauth_url())
        result = self._invoke(['url', 'sample'], sole_login=sole)
        self.assertEqual(0, result.exit_code, result.output)
        self.assertEqual("eu-cloud", cloudinary.config().cloud_name)

    def test_does_not_hijack_explicit_invalid_minus_C(self):
        saved = {"myaccount": "cloudinary://key@chosen_cloud"}  # incomplete: no secret -> invalid
        sole = ("eu-cloud", _oauth_url())
        result = self._invoke(['-C', 'myaccount', 'url', 'sample'], sole_login=sole, saved=saved)
        self.assertEqual("chosen_cloud", cloudinary.config().cloud_name)
        self.assertIsNone(cloudinary.config().oauth_token)

    def test_does_not_hijack_explicit_cloudinary_url(self):
        sole = ("eu-cloud", _oauth_url())
        self._invoke(['url', 'sample'], sole_login=sole,
                     env={"CLOUDINARY_URL": "cloudinary://key@env_cloud"})
        self.assertEqual("env_cloud", cloudinary.config().cloud_name)
        self.assertIsNone(cloudinary.config().oauth_token)



class TestConfigToApiKwargs(unittest.TestCase):
    def _oauth_config(self):
        config = cloudinary.Config()
        config._setup_from_parsed_url(config._parse_cloudinary_url(_oauth_url()))
        return config

    def test_drops_oauth_bookkeeping(self):
        config = self._oauth_config()
        kwargs = config_to_api_kwargs(config)
        for leaked in ("refresh_token", "expires_at", "region", "issuer"):
            self.assertNotIn(leaked, kwargs)
        self.assertEqual("eyJ.secret_access.tok", kwargs["oauth_token"])
        self.assertEqual("eu-cloud", kwargs["cloud_name"])

    def test_config_to_dict_still_faithful(self):
        full = config_to_dict(self._oauth_config())
        self.assertIn("refresh_token", full)
        self.assertIn("region", full)


class TestGetCloudinaryConfigOAuth(_RestoresSdkConfig):
    def _stale_url(self):
        return to_cloudinary_url(Session(
            cloud_name="eu-cloud", access_token="eyJ.old.tok", refresh_token="rt_old",
            expires_at=int(time.time()) - 10, region="api-eu",
            issuer="https://oauth.cloudinary.com/"))

    def test_refreshes_stale_target_before_use(self):
        config = {"eu-cloud": self._stale_url()}
        token_response = {"access_token": "eyJ.new.tok", "refresh_token": "rt_new", "expires_in": 300}
        with patch("cloudinary_cli.utils.config_resolver.load_config", return_value=config), \
                patch("cloudinary_cli.auth.load_config", return_value=config), \
                patch("cloudinary_cli.auth.flow.refresh", return_value=token_response), \
                patch("cloudinary_cli.auth.update_config"), \
                patch("cloudinary_cli.utils.config_resolver.ping_cloudinary", return_value=True):
            target_config = get_cloudinary_config("eu-cloud")
        self.assertTrue(target_config)
        self.assertEqual("eyJ.new.tok", target_config.oauth_token)

    def test_ping_receives_sanitized_config(self):
        config = {"eu-cloud": _oauth_url()}
        with patch("cloudinary_cli.utils.config_resolver.load_config", return_value=config), \
                patch("cloudinary_cli.auth.load_config", return_value=config), \
                patch("cloudinary_cli.utils.config_resolver.ping_cloudinary", return_value=True) as ping:
            get_cloudinary_config("eu-cloud")
        ping_kwargs = ping.call_args.kwargs
        for leaked in ("refresh_token", "expires_at", "region", "issuer"):
            self.assertNotIn(leaked, ping_kwargs)
        self.assertEqual("eyJ.secret_access.tok", ping_kwargs["oauth_token"])
