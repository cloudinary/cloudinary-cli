import json
import os
import time
import unittest
from unittest.mock import patch

import cloudinary
from click.testing import CliRunner

from cloudinary_cli.auth.session import Session, to_cloudinary_url
from test.oauth_helpers import jwt_access_token
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
        # Strip ambient CLOUDINARY_* so a bare cloudinary.Config() built in a test is not polluted by
        # the developer's env (e.g. a real account_url leaking into masking/display assertions).
        for key in [k for k in os.environ if k.startswith("CLOUDINARY_")]:
            del os.environ[key]
        cloudinary.reset_config()
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
                patch("cloudinary_cli.auth.remove_config_keys") as remove, \
                patch("cloudinary_cli.auth.flow.revoke") as revoke:
            self.assertEqual("removed", logout("eu-cloud"))
            remove.assert_called_once_with("eu-cloud")
            revoke.assert_called_once_with("rt_secret_value", "api-eu")

    def test_revoke_failure_still_removes_locally(self):
        import requests
        from cloudinary_cli.auth import logout
        saved = {"eu-cloud": _oauth_url()}
        with patch("cloudinary_cli.auth.load_config", return_value=saved), \
                patch("cloudinary_cli.auth.remove_config_keys") as remove, \
                patch("cloudinary_cli.auth.flow.revoke", side_effect=requests.ConnectionError()):
            self.assertEqual("revoke_failed", logout("eu-cloud"))
            remove.assert_called_once_with("eu-cloud")  # local entry removed despite revoke failure

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
                patch("cloudinary_cli.auth.refresh.load_config", return_value=saved), \
                patch("cloudinary_cli.auth.remove_config_keys") as remove, \
                patch("cloudinary_cli.auth.flow.revoke"):
            result = self.runner.invoke(cli, ["logout"], input="2\n")
        self.assertIn("cloud-a", result.output)
        self.assertIn("cloud-b", result.output)
        self.assertNotIn("mykey", result.output)  # non-oauth not offered
        remove.assert_called_once_with("cloud-b")

    def test_no_oauth_logins(self):
        with patch("cloudinary_cli.auth.refresh.load_config",
                   return_value={"mykey": "cloudinary://key:secret@cloud"}), \
                patch("cloudinary_cli.auth.remove_config_keys") as remove:
            result = self.runner.invoke(cli, ["logout"], input="\n")
        self.assertIn("No saved OAuth logins", result.output)
        remove.assert_not_called()

    def test_cancel_on_empty_input(self):
        with patch("cloudinary_cli.auth.refresh.load_config", return_value={"cloud-a": _oauth_url("cloud-a")}), \
                patch("cloudinary_cli.auth.remove_config_keys") as remove:
            result = self.runner.invoke(cli, ["logout"], input="\n")
        remove.assert_not_called()
        self.assertEqual(0, result.exit_code)

    def test_invalid_non_numeric_errors(self):
        with patch("cloudinary_cli.auth.refresh.load_config", return_value={"cloud-a": _oauth_url("cloud-a")}), \
                patch("cloudinary_cli.auth.remove_config_keys") as remove:
            result = self.runner.invoke(cli, ["logout"], input="sdfdsf\n", standalone_mode=False)
        self.assertIn("Invalid selection", result.output)
        self.assertFalse(result.return_value)  # main() maps falsy -> exit 1
        remove.assert_not_called()

    def test_out_of_range_errors(self):
        with patch("cloudinary_cli.auth.refresh.load_config", return_value={"cloud-a": _oauth_url("cloud-a")}), \
                patch("cloudinary_cli.auth.remove_config_keys") as remove:
            result = self.runner.invoke(cli, ["logout"], input="5\n", standalone_mode=False)
        self.assertIn("Invalid selection", result.output)
        self.assertFalse(result.return_value)
        remove.assert_not_called()

    def test_noninteractive_stdin_errors_with_hint(self):
        # Closed stdin (no input at all): the selection cannot be made, so error with the
        # non-interactive form (`cld logout <name>`) and exit non-zero, not a silent no-op.
        import builtins
        with patch("cloudinary_cli.auth.refresh.load_config", return_value={"cloud-a": _oauth_url("cloud-a")}), \
                patch("cloudinary_cli.auth.remove_config_keys") as remove, \
                patch.object(builtins, "input", side_effect=EOFError()):
            result = self.runner.invoke(cli, ["logout"], standalone_mode=False)
        self.assertIn("cld logout <name>", result.output)
        self.assertFalse(result.return_value)  # main() maps falsy -> exit 1
        remove.assert_not_called()


class TestLoginSetDefault(unittest.TestCase):
    """`login` sets the default explicitly with --set-default and auto-defaults a sole login."""

    def _patches(self, saved):
        session = Session(cloud_name="eu-cloud", access_token="a", refresh_token="r",
                          expires_at=int(time.time()) + 300, region="api-eu",
                          issuer="https://oauth.cloudinary.com/")
        return patch.multiple(
            "cloudinary_cli.auth",
            _run_browser_flow=lambda region: session,
            load_config=lambda: dict(saved),
            update_config=lambda *a, **k: None,
            is_env_configured=lambda: False,
        )

    def test_set_default_flag_marks_default(self):
        from cloudinary_cli import auth
        with self._patches({"eu-cloud": _oauth_url(), "other": _oauth_url("other")}), \
                patch("cloudinary_cli.auth.set_default_config") as set_default, \
                patch("cloudinary_cli.auth.get_default_config_name", return_value=None):
            auth.login(region="eu", name="eu-cloud", set_default=True)
        set_default.assert_called_once_with("eu-cloud")

    def test_auto_default_when_sole_config_no_env_no_default(self):
        from cloudinary_cli import auth
        with self._patches({"eu-cloud": _oauth_url()}), \
                patch("cloudinary_cli.auth.set_default_config") as set_default, \
                patch("cloudinary_cli.auth.get_default_config_name", return_value=None):
            name, is_default = auth.login(region="eu", name="eu-cloud")
        set_default.assert_called_once_with("eu-cloud")
        self.assertEqual(("eu-cloud", True), (name, is_default))

    def test_returns_not_default_when_other_configs_exist(self):
        from cloudinary_cli import auth
        with self._patches({"eu-cloud": _oauth_url(), "other": _oauth_url("other")}), \
                patch("cloudinary_cli.auth.set_default_config"), \
                patch("cloudinary_cli.auth.get_default_config_name", return_value=None):
            name, is_default = auth.login(region="eu", name="eu-cloud")
        self.assertEqual(("eu-cloud", False), (name, is_default))

    def test_no_auto_default_when_other_configs_exist(self):
        from cloudinary_cli import auth
        with self._patches({"eu-cloud": _oauth_url(), "other": _oauth_url("other")}), \
                patch("cloudinary_cli.auth.set_default_config") as set_default, \
                patch("cloudinary_cli.auth.get_default_config_name", return_value=None):
            auth.login(region="eu", name="eu-cloud")
        set_default.assert_not_called()

    def test_no_auto_default_when_env_configured(self):
        from cloudinary_cli import auth
        with self._patches({"eu-cloud": _oauth_url()}), \
                patch("cloudinary_cli.auth.is_env_configured", return_value=True), \
                patch("cloudinary_cli.auth.set_default_config") as set_default, \
                patch("cloudinary_cli.auth.get_default_config_name", return_value=None):
            auth.login(region="eu", name="eu-cloud")
        set_default.assert_not_called()

    def test_no_auto_default_when_default_already_stored(self):
        from cloudinary_cli import auth
        with self._patches({"eu-cloud": _oauth_url()}), \
                patch("cloudinary_cli.auth.set_default_config") as set_default, \
                patch("cloudinary_cli.auth.get_default_config_name", return_value="something"):
            auth.login(region="eu", name="eu-cloud")
        set_default.assert_not_called()

    def test_reserved_name_rejected(self):
        from cloudinary_cli import auth
        with patch("cloudinary_cli.auth._run_browser_flow"):
            with self.assertRaises(RuntimeError):
                auth.login(region="eu", name="__default__")

    def test_cli_message_when_default(self):
        with patch("cloudinary_cli.core.auth.run_login", return_value=("tttt", True)):
            result = CliRunner().invoke(cli, ["login", "tttt"])
        self.assertIn("default configuration", result.output)

    def test_cli_message_when_not_default_shows_how_to_default(self):
        with patch("cloudinary_cli.core.auth.run_login", return_value=("tttt", False)):
            result = CliRunner().invoke(cli, ["login", "tttt"])
        self.assertIn("cld -C tttt", result.output)
        self.assertIn("cld config -d tttt", result.output)  # how to make it default


class TestConfigSecretMasking(_RestoresSdkConfig):
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

    def test_mask_is_fixed_width_for_long_secret(self):
        config = cloudinary.Config()
        config.update(cloud_name="c", oauth_token="eyJ" + "A" * 2000 + "N2dQ")
        with patch("cloudinary_cli.utils.config_utils.echo") as echo:
            show_cloudinary_config(config)
        out = echo.call_args[0][0]
        self.assertIn("****N2dQ", out)        # fixed prefix + last 4
        self.assertNotIn("*" * 8, out)        # never a wall of asterisks

    def test_hides_empty_fields(self):
        config = cloudinary.Config()
        config.update(cloud_name="c", oauth_token="eyJ.tok", api_key=None, api_secret=None)
        with patch("cloudinary_cli.utils.config_utils.echo") as echo:
            show_cloudinary_config(config)
        out = echo.call_args[0][0]
        self.assertNotIn("api_key", out)
        self.assertNotIn("api_secret", out)
        self.assertNotIn("None", out)
        self.assertIn("cloud_name", out)

    def test_expires_at_human_readable_and_state(self):
        future = cloudinary.Config()
        future.update(cloud_name="c", oauth_token="eyJ.tok", expires_at=int(time.time()) + 3600)
        with patch("cloudinary_cli.utils.config_utils.echo") as echo:
            show_cloudinary_config(future)
        out = echo.call_args[0][0]
        self.assertIn("UTC", out)
        self.assertIn("valid", out)

        past = cloudinary.Config()
        past.update(cloud_name="c", oauth_token="eyJ.tok", expires_at=1782310673)
        with patch("cloudinary_cli.utils.config_utils.echo") as echo:
            show_cloudinary_config(past)
        out = echo.call_args[0][0]
        self.assertIn("1782310673", out)            # raw epoch kept
        self.assertIn("2026-06-24", out)            # human-readable date
        self.assertIn("expired", out)

    def test_issued_at_human_readable_no_state(self):
        config = cloudinary.Config()
        config.update(cloud_name="c", oauth_token="eyJ.tok", issued_at=1782310673)
        with patch("cloudinary_cli.utils.config_utils.echo") as echo:
            show_cloudinary_config(config)
        out = echo.call_args[0][0]
        self.assertIn("1782310673", out)            # raw epoch kept
        self.assertIn("2026-06-24", out)            # human-readable date
        self.assertIn("UTC", out)
        self.assertNotIn("valid", out)              # issuance has no validity state
        self.assertNotIn("expired", out)

    def test_issued_at_non_numeric_left_as_is(self):
        config = cloudinary.Config()
        config.update(cloud_name="c", oauth_token="eyJ.tok", issued_at="not-an-epoch")
        with patch("cloudinary_cli.utils.config_utils.echo") as echo:
            show_cloudinary_config(config)
        out = echo.call_args[0][0]
        self.assertIn("not-an-epoch", out)

    def test_account_url_shown_as_structured_section(self):
        config = cloudinary.Config()
        config.update(cloud_name="c", api_key="k", api_secret="abcdefghIJKLMNOP",
                      account_url="account://acc_key:SUPERSECRETPASSWORD@account_id")
        with patch("cloudinary_cli.utils.config_utils.echo") as echo:
            show_cloudinary_config(config)
        # two echo calls: the main block, then the account (provisioning) section
        self.assertEqual(2, echo.call_count)
        main = echo.call_args_list[0][0][0]
        account = echo.call_args_list[1][0][0]
        self.assertNotIn("account://", main)
        # the account URL is decomposed into labeled fields, secret masked
        self.assertIn("account_id:", account)
        self.assertIn("provisioning_api_key:", account)
        self.assertIn("provisioning_api_secret:", account)
        self.assertIn("acc_key", account)
        self.assertIn("account_id", account)
        self.assertNotIn("SUPERSECRETPASSWORD", account)
        self.assertNotIn("account://", account)  # no raw URL string

    def test_malformed_account_url_falls_back_to_raw_line(self):
        config = cloudinary.Config()
        config.update(cloud_name="c", account_url="account://garbage")
        with patch("cloudinary_cli.utils.config_utils.echo") as echo:
            show_cloudinary_config(config)
        account = echo.call_args_list[-1][0][0]
        self.assertIn("account_url: account://garbage", account)


class TestOAuthConfigCoexistence(_RestoresSdkConfig):
    runner = CliRunner()

    CONFIG = {
        "prod-account": "cloudinary://key:secret@prod_cloud",
        "eu-cloud": _oauth_url(),
    }

    def test_ls_shows_both(self):
        with patch("cloudinary_cli.utils.config_listing.load_config", return_value=dict(self.CONFIG)):
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

    def test_show_header_includes_name_type_and_flags(self):
        cfg = {"__default__": "eu-cloud", "prod-account": "cloudinary://key:secret@prod_cloud",
               "eu-cloud": _oauth_url()}
        with patch("cloudinary_cli.core.config.load_config", return_value=dict(cfg)), \
                patch("cloudinary_cli.utils.config_resolver.load_config", return_value=dict(cfg)), \
                patch.dict("os.environ", {}, clear=False):
            for key in ("CLOUDINARY_URL", "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY",
                        "CLOUDINARY_API_SECRET"):
                os.environ.pop(key, None)
            cloudinary.reset_config()
            default_active = self.runner.invoke(cli, ['config', '-s', 'eu-cloud'])
            plain = self.runner.invoke(cli, ['config', '-s', 'prod-account'])
        self.assertIn("name: eu-cloud (oauth) [default, active]", default_active.output)
        self.assertIn("name: prod-account (api_key)\n", plain.output)  # no flag bracket

    def test_bare_config_header_matches_active(self):
        cfg = {"__default__": "eu-cloud", "eu-cloud": _oauth_url()}
        with patch("cloudinary_cli.core.config.load_config", return_value=dict(cfg)), \
                patch("cloudinary_cli.utils.config_resolver.load_config", return_value=dict(cfg)), \
                patch.dict("os.environ", {}, clear=False):
            for key in ("CLOUDINARY_URL", "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY",
                        "CLOUDINARY_API_SECRET"):
                os.environ.pop(key, None)
            cloudinary.reset_config()
            bare = self.runner.invoke(cli, ['config'])
            shown = self.runner.invoke(cli, ['config', '-s', 'eu-cloud'])
        # bare `config` identifies the active config the same way `-s <name>` does
        self.assertIn("name: eu-cloud (oauth) [default, active]", bare.output)
        self.assertIn("name: eu-cloud (oauth) [default, active]", shown.output)

    def test_bare_config_header_for_command_line_url(self):
        cfg = {"__default__": "eu-cloud", "eu-cloud": _oauth_url()}
        with patch("cloudinary_cli.core.config.load_config", return_value=dict(cfg)), \
                patch("cloudinary_cli.utils.config_resolver.load_config", return_value=dict(cfg)), \
                patch.dict("os.environ", {}, clear=False):
            for key in ("CLOUDINARY_URL", "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY",
                        "CLOUDINARY_API_SECRET"):
                os.environ.pop(key, None)
            cloudinary.reset_config()
            result = self.runner.invoke(cli, ['-c', 'cloudinary://a:b@cmdcloud', 'config'])
        self.assertIn("name: (command-line) (api_key) [active]", result.output)

    def _show_json(self, args, cfg):
        with patch("cloudinary_cli.core.config.load_config", return_value=dict(cfg)), \
                patch("cloudinary_cli.utils.config_listing.load_config", return_value=dict(cfg)), \
                patch("cloudinary_cli.utils.config_resolver.load_config", return_value=dict(cfg)), \
                patch.dict("os.environ", {}, clear=False):
            for key in ("CLOUDINARY_URL", "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY",
                        "CLOUDINARY_API_SECRET"):
                os.environ.pop(key, None)
            cloudinary.reset_config()
            result = self.runner.invoke(cli, args)
        self.assertEqual(0, result.exit_code, result.output)
        return json.loads(result.output[result.output.index("{"):])

    def test_show_json_includes_meta_and_masks_secrets(self):
        cfg = {"__default__": "eu-cloud", "eu-cloud": _oauth_url()}
        data = self._show_json(['config', '-s', 'eu-cloud', '--json'], cfg)
        self.assertEqual("eu-cloud", data["name"])
        self.assertEqual("saved", data["source"])
        self.assertEqual("oauth", data["type"])
        self.assertTrue(data["default"])
        self.assertTrue(data["active"])
        self.assertEqual("eu-cloud", data["cloud_name"])
        # secrets masked, never in the clear
        self.assertNotIn("eyJ.secret_access.tok", json.dumps(data))
        self.assertNotIn("rt_secret_value", json.dumps(data))
        # expires_at expanded into a structured object
        self.assertIn("epoch", data["expires_at"])
        self.assertIn("expired", data["expires_at"])

    def test_details_expands_issued_at_without_state(self):
        from cloudinary_cli.utils.config_utils import cloudinary_config_details
        config = cloudinary.Config()
        config.update(cloud_name="c", oauth_token="eyJ.tok", issued_at=1782310673)
        details = cloudinary_config_details(config)
        self.assertEqual(1782310673, details["issued_at"]["epoch"])
        self.assertIn("2026-06-24", details["issued_at"]["utc"])
        self.assertNotIn("expired", details["issued_at"])  # issuance has no validity state

    def test_details_issued_at_non_numeric_left_as_is(self):
        from cloudinary_cli.utils.config_utils import cloudinary_config_details
        config = cloudinary.Config()
        config.update(cloud_name="c", oauth_token="eyJ.tok", issued_at="bogus")
        details = cloudinary_config_details(config)
        self.assertEqual("bogus", details["issued_at"])

    def test_bare_config_json_matches_show_json(self):
        cfg = {"__default__": "eu-cloud", "eu-cloud": _oauth_url()}
        bare = self._show_json(['config', '--json'], cfg)
        shown = self._show_json(['config', '-s', 'eu-cloud', '--json'], cfg)
        self.assertEqual(shown, bare)

    def test_bare_config_json_env_carries_source(self):
        # a synthetic active source is disambiguated by `source`, matching the -ls -j rows
        with patch("cloudinary_cli.core.config.load_config", return_value={}), \
                patch("cloudinary_cli.utils.config_resolver.load_config", return_value={}), \
                patch.dict("os.environ", {"CLOUDINARY_URL": "cloudinary://ek:es@env_cloud"}, clear=False):
            cloudinary.reset_config()
            result = self.runner.invoke(cli, ['config', '--json'])
        data = json.loads(result.output[result.output.index("{"):])
        self.assertEqual("(environment)", data["name"])
        self.assertEqual("env", data["source"])

    def test_config_details_decomposes_account_url(self):
        from cloudinary_cli.utils.config_utils import cloudinary_config_details
        config = cloudinary.Config()
        config.update(cloud_name="c", account_url="account://pk:SUPERSECRETxyz@acc_id")
        details = cloudinary_config_details(config)
        self.assertEqual("acc_id", details["account"]["account_id"])
        self.assertEqual("pk", details["account"]["provisioning_api_key"])
        self.assertNotIn("SUPERSECRETxyz", json.dumps(details))
        self.assertTrue(details["account"]["provisioning_api_secret"].endswith("txyz")
                        or details["account"]["provisioning_api_secret"].startswith("****"))
        self.assertNotIn("account_url", details)  # decomposed, not raw


class TestDefaultConfigResolution(_RestoresSdkConfig):
    """Resolution precedence: -c > -C > stored default > environment > unconfigured."""

    runner = CliRunner()

    def _invoke(self, args, saved, env=None):
        env = dict(env or {})
        with patch("cloudinary_cli.utils.config_resolver.load_config", return_value=dict(saved)), \
                patch.dict("os.environ", env, clear=False):
            for key in ("CLOUDINARY_URL", "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY",
                        "CLOUDINARY_API_SECRET"):
                if key not in env:
                    os.environ.pop(key, None)
            cloudinary.reset_config()
            return self.runner.invoke(cli, args)

    def test_stored_default_applies_when_no_explicit_config(self):
        saved = {"__default__": "eu-cloud", "eu-cloud": _oauth_url()}
        result = self._invoke(['url', 'sample'], saved=saved)
        self.assertEqual(0, result.exit_code, result.output)
        self.assertEqual("eu-cloud", cloudinary.config().cloud_name)

    def test_no_implicit_sole_login_without_default(self):
        # A single saved login with no stored default no longer auto-applies.
        saved = {"eu-cloud": _oauth_url()}
        result = self._invoke(['url', 'sample'], saved=saved)
        self.assertIn("No Cloudinary configuration found.", result.output)
        self.assertIsNone(cloudinary.config().cloud_name)

    def test_stored_default_beats_env(self):
        saved = {"__default__": "eu-cloud", "eu-cloud": _oauth_url()}
        self._invoke(['url', 'sample'], saved=saved,
                     env={"CLOUDINARY_URL": "cloudinary://key:secret@env_cloud"})
        self.assertEqual("eu-cloud", cloudinary.config().cloud_name)

    def test_env_applies_when_no_stored_default(self):
        saved = {"eu-cloud": _oauth_url()}
        self._invoke(['url', 'sample'], saved=saved,
                     env={"CLOUDINARY_URL": "cloudinary://key:secret@env_cloud"})
        self.assertEqual("env_cloud", cloudinary.config().cloud_name)
        self.assertIsNone(cloudinary.config().oauth_token)

    def test_explicit_minus_C_overrides_default(self):
        saved = {"__default__": "eu-cloud", "eu-cloud": _oauth_url(),
                 "other": "cloudinary://key:secret@other_cloud"}
        result = self._invoke(['-C', 'other', 'url', 'sample'], saved=saved)
        self.assertEqual(0, result.exit_code, result.output)
        self.assertEqual("other_cloud", cloudinary.config().cloud_name)
        self.assertIsNone(cloudinary.config().oauth_token)

    def test_default_pointing_at_deleted_config_is_ignored(self):
        saved = {"__default__": "gone"}
        result = self._invoke(['url', 'sample'], saved=saved)
        self.assertIn("No Cloudinary configuration found.", result.output)

    def test_inline_url_and_saved_together_errors(self):
        # A1: -c and -C are mutually exclusive; passing both must error, not silently drop one.
        saved = {"eu-cloud": _oauth_url()}
        result = self._invoke(
            ['-c', 'cloudinary://a:b@inline', '-C', 'eu-cloud', 'url', 'sample'], saved=saved)
        self.assertEqual(2, result.exit_code)
        self.assertIn("mutually exclusive", result.output)


class TestResolverNoNetworkIO(_RestoresSdkConfig):
    """Finding 1 regression: resolution never refreshes a stale OAuth token (no network I/O)."""

    runner = CliRunner()

    def _stale_url(self):
        return to_cloudinary_url(Session(
            cloud_name="eu-cloud", access_token="eyJ.old.tok", refresh_token="rt_old",
            expires_at=int(time.time()) - 10, region="api-eu",
            issuer="https://oauth.cloudinary.com/"))

    def test_resolve_does_not_call_flow_refresh(self):
        saved = {"__default__": "eu-cloud", "eu-cloud": self._stale_url()}
        with patch("cloudinary_cli.utils.config_resolver.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.auth.flow.refresh") as refresh, \
                patch.dict("os.environ", {}, clear=False):
            for key in ("CLOUDINARY_URL", "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY",
                        "CLOUDINARY_API_SECRET"):
                os.environ.pop(key, None)
            cloudinary.reset_config()
            from cloudinary_cli.utils.config_resolver import resolve_cli_config
            resolve_cli_config()
        refresh.assert_not_called()
        # The stale token is loaded as-is (presence check is refresh-free), awaiting a lazy refresh
        # only when the SDK reads oauth_token at request time.
        self.assertTrue(cloudinary.config().has_oauth)
        self.assertEqual("eyJ.old.tok", cloudinary.config().__dict__.get("oauth_token"))

    def test_help_does_not_reach_phase_b(self):
        with patch("cloudinary_cli.auth.flow.refresh") as refresh:
            self.runner.invoke(cli, ['--help'])
        refresh.assert_not_called()


class TestSelfRefreshingOAuthToken(_RestoresSdkConfig):
    """The active OAuth config refreshes its token lazily when the SDK reads oauth_token at request
    time; presence/type checks (has_oauth) never trigger a refresh."""

    def _stale_url(self):
        return to_cloudinary_url(Session(
            cloud_name="eu-cloud", access_token="eyJ.old.tok", refresh_token="rt_old",
            expires_at=int(time.time()) - 10, region="api-eu",
            issuer="https://oauth.cloudinary.com/"))

    def test_reading_oauth_token_refreshes_stale_active_login(self):
        import cloudinary_cli.utils.config_resolver as resolver
        saved = {"eu-cloud": self._stale_url()}
        new_token = jwt_access_token(cloud_name="eu-cloud", tag="resolver-new")
        token_response = {"access_token": new_token, "refresh_token": "rt_new", "expires_in": 300}
        with patch("cloudinary_cli.utils.config_resolver.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.auth.refresh.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.utils.config_utils.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.auth.flow.refresh", return_value=token_response), \
                patch("cloudinary_cli.auth.refresh.update_config"):
            resolver.resolve_cli_config(config_saved="eu-cloud")
            # The read of oauth_token is what triggers the refresh (as the SDK does per request).
            self.assertEqual(new_token, cloudinary.config().oauth_token)

    def test_presence_check_does_not_refresh(self):
        """has_oauth (used by type/validity/-ls) must NOT touch the network on a stale token."""
        import cloudinary_cli.utils.config_resolver as resolver
        saved = {"eu-cloud": self._stale_url()}
        with patch("cloudinary_cli.utils.config_resolver.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.auth.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.utils.config_utils.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.auth.flow.refresh") as refresh:
            resolver.resolve_cli_config(config_saved="eu-cloud")
            self.assertTrue(cloudinary.config().has_oauth)
        refresh.assert_not_called()

    def test_noop_for_inline_url(self):
        import cloudinary_cli.utils.config_resolver as resolver
        with patch("cloudinary_cli.auth.flow.refresh") as refresh:
            resolver.resolve_cli_config(config="cloudinary://key:secret@cloud")
            _ = cloudinary.config().oauth_token
        refresh.assert_not_called()

    def test_noop_for_api_key_config(self):
        import cloudinary_cli.utils.config_resolver as resolver
        saved = {"mykey": "cloudinary://key:secret@cloud"}
        with patch("cloudinary_cli.utils.config_resolver.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.utils.config_utils.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.auth.flow.refresh") as refresh:
            resolver.resolve_cli_config(config_saved="mykey")
            _ = cloudinary.config().oauth_token
        refresh.assert_not_called()


class TestConfigDefaultCommands(_RestoresSdkConfig):
    """`cld config` default management: -d, --set-default, --unset-default, -ls marker, -rm cleanup."""

    runner = CliRunner()

    def test_d_marks_existing(self):
        saved = {"prod": "cloudinary://k:s@prod", "eu-cloud": _oauth_url()}
        with patch("cloudinary_cli.core.config.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.core.config.set_default_config") as set_default:
            result = self.runner.invoke(cli, ['config', '-d', 'prod'])
        self.assertEqual(0, result.exit_code, result.output)
        set_default.assert_called_once_with("prod")
        self.assertIn("Default set to 'prod'", result.output)

    def test_d_nonexistent_errors(self):
        with patch("cloudinary_cli.core.config.load_config", return_value={"prod": "cloudinary://k:s@prod"}):
            result = self.runner.invoke(cli, ['config', '-d', 'nope'])
        self.assertEqual(2, result.exit_code)
        self.assertIn("does not exist", result.output)

    def test_set_default_without_create_flag_errors(self):
        result = self.runner.invoke(cli, ['config', '--set-default'])
        self.assertEqual(2, result.exit_code)
        self.assertIn("requires -n or --from_url", result.output)

    def test_new_with_set_default(self):
        with patch("cloudinary_cli.core.config.verify_cloudinary_url", return_value=True), \
                patch("cloudinary_cli.core.config.update_config"), \
                patch("cloudinary_cli.core.config.set_default_config") as set_default:
            result = self.runner.invoke(
                cli, ['config', '-n', 'prod', 'cloudinary://k:s@prod', '--set-default'])
        self.assertEqual(0, result.exit_code, result.output)
        set_default.assert_called_once_with("prod")
        self.assertIn("Default set to 'prod'", result.output)

    def test_set_default_on_failing_url_neither_saves_nor_defaults(self):
        with patch("cloudinary_cli.core.config.verify_cloudinary_url", return_value=False), \
                patch("cloudinary_cli.core.config.update_config") as update, \
                patch("cloudinary_cli.core.config.set_default_config") as set_default:
            self.runner.invoke(
                cli, ['config', '-n', 'prod', 'cloudinary://bad', '--set-default'])
        update.assert_not_called()
        set_default.assert_not_called()

    def test_unset_default(self):
        with patch("cloudinary_cli.core.config.load_config", return_value={}), \
                patch("cloudinary_cli.core.config.clear_default_config") as clear:
            result = self.runner.invoke(cli, ['config', '--unset-default'])
        self.assertEqual(0, result.exit_code, result.output)
        clear.assert_called_once()
        self.assertIn("cleared", result.output)

    def _run_ls(self, args, saved, env=None):
        # Both the resolver (Phase A, which records the active config) and the config command read
        # the same saved dict; env is controlled via os.environ so is_env_configured() is genuine.
        env = dict(env or {})
        with patch("cloudinary_cli.core.config.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.utils.config_listing.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.utils.config_resolver.load_config", return_value=dict(saved)), \
                patch.dict("os.environ", env, clear=False):
            for key in ("CLOUDINARY_URL", "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY",
                        "CLOUDINARY_API_SECRET"):
                if key not in env:
                    os.environ.pop(key, None)
            cloudinary.reset_config()
            return self.runner.invoke(cli, args)

    def _ls_json(self, saved, env=None):
        result = self._run_ls(['config', '-ls', '--json'], saved, env)
        self.assertEqual(0, result.exit_code, result.output)
        return {r["name"]: r for r in json.loads(result.output[result.output.index("["):])}

    def test_ls_table_marks_default(self):
        saved = {"__default__": "eu-cloud", "prod": "cloudinary://k:s@prod", "eu-cloud": _oauth_url()}
        result = self._run_ls(['config', '-ls'], saved)
        self.assertEqual(0, result.exit_code, result.output)
        for header in ("NAME", "CLOUD", "TYPE", "DEFAULT", "ACTIVE"):
            self.assertIn(header, result.output)
        self.assertIn("prod", result.output)
        self.assertIn("oauth", result.output)
        self.assertIn("api_key", result.output)
        # with no env, the stored default is both default and active (two markers)
        rows = {line.split()[0]: line for line in result.output.splitlines() if line.startswith(("prod", "eu-cloud"))}
        self.assertEqual(2, rows["eu-cloud"].count("*"))
        self.assertEqual(0, rows["prod"].count("*"))
        self.assertNotIn("__default__", result.output)

    def test_ls_json(self):
        saved = {"__default__": "eu-cloud", "prod": "cloudinary://k:s@prodcloud", "eu-cloud": _oauth_url()}
        by_name = self._ls_json(saved)
        self.assertNotIn("__default__", by_name)
        self.assertEqual("oauth", by_name["eu-cloud"]["type"])
        self.assertEqual("saved", by_name["eu-cloud"]["source"])
        self.assertTrue(by_name["eu-cloud"]["default"])
        self.assertTrue(by_name["eu-cloud"]["active"])  # no env -> stored default is active
        self.assertEqual("api_key", by_name["prod"]["type"])
        self.assertEqual("prodcloud", by_name["prod"]["cloud_name"])
        self.assertFalse(by_name["prod"]["default"])
        self.assertFalse(by_name["prod"]["active"])

    def test_ls_minus_C_marks_selected_active(self):
        saved = {"__default__": "eu-cloud", "eu-cloud": _oauth_url(),
                 "test": "cloudinary://k:s@test_cloud"}
        # an explicit -C selects the active config for this invocation, overriding the default
        result = self._run_ls(['-C', 'test', 'config', '-ls', '--json'], saved)
        self.assertEqual(0, result.exit_code, result.output)
        by_name = {r["name"]: r for r in json.loads(result.output[result.output.index("["):])}
        self.assertTrue(by_name["test"]["active"])
        self.assertFalse(by_name["eu-cloud"]["active"])  # not active, but still the stored default
        self.assertTrue(by_name["eu-cloud"]["default"])

    def test_ls_inline_url_shown_as_active_command_line_row(self):
        saved = {"__default__": "eu-cloud", "eu-cloud": _oauth_url()}
        # an inline -c URL is not a saved config, but it is what's active for this invocation
        result = self._run_ls(['-c', 'cloudinary://a:b@inline_cloud', 'config', '-ls', '--json'], saved)
        self.assertEqual(0, result.exit_code, result.output)
        by_name = {r["name"]: r for r in json.loads(result.output[result.output.index("["):])}
        cmd = by_name["(command-line)"]  # synthetic source: parenthesized in both table and JSON
        self.assertEqual("url", cmd["source"])
        self.assertEqual("inline_cloud", cmd["cloud_name"])
        self.assertTrue(cmd["active"])
        self.assertFalse(cmd["default"])
        # the stored default is still recorded, but it is not active while -c wins
        self.assertTrue(by_name["eu-cloud"]["default"])
        self.assertFalse(by_name["eu-cloud"]["active"])

    _ENV = {"CLOUDINARY_URL": "cloudinary://k:s@env_cloud"}

    def test_ls_env_row_active_when_no_default(self):
        by_name = self._ls_json({"eu-cloud": _oauth_url()}, env=self._ENV)
        env = by_name["(environment)"]
        self.assertEqual("env", env["source"])
        self.assertEqual("env_cloud", env["cloud_name"])
        self.assertFalse(env["default"])  # the environment is never the *stored* default
        self.assertTrue(env["active"])    # active because nothing outranks it
        self.assertFalse(by_name["eu-cloud"]["active"])

    def test_ls_stored_default_outranks_env_row(self):
        by_name = self._ls_json({"__default__": "eu-cloud", "eu-cloud": _oauth_url()}, env=self._ENV)
        env = by_name["(environment)"]
        self.assertFalse(env["active"])  # stored default outranks the environment
        # the stored default is both recorded and active
        self.assertTrue(by_name["eu-cloud"]["default"])
        self.assertTrue(by_name["eu-cloud"]["active"])

    def test_synthetic_row_name_parenthesized_in_table_and_json(self):
        # synthetic (environment / command-line) configs read as parenthesized in both views
        result = self._run_ls(['config', '-ls'], {"eu-cloud": _oauth_url()}, env=dict(self._ENV))
        self.assertIn("(environment)", result.output)
        by_name = self._ls_json({"eu-cloud": _oauth_url()}, env=dict(self._ENV))
        self.assertIn("(environment)", by_name)

    def test_rm_of_default_clears_it(self):
        with patch("cloudinary_cli.core.config.remove_config_keys", return_value=[]), \
                patch("cloudinary_cli.core.config.get_default_config_name", return_value="prod"), \
                patch("cloudinary_cli.core.config.clear_default_config") as clear:
            result = self.runner.invoke(cli, ['config', '-rm', 'prod'])
        self.assertEqual(0, result.exit_code, result.output)
        clear.assert_called_once()

    def test_reserved_name_rejected_on_new(self):
        result = self.runner.invoke(
            cli, ['config', '-n', '__default__', 'cloudinary://k:s@c'])
        self.assertEqual(2, result.exit_code)
        self.assertIn("reserved", result.output)

    def test_refresh_named_delegates_to_refresh_config(self):
        with patch("cloudinary_cli.core.config.refresh_config", return_value="refreshed") as rc:
            result = self.runner.invoke(cli, ['config', '--refresh', 'eu-cloud'])
        self.assertEqual(0, result.exit_code, result.output)
        rc.assert_called_once_with("eu-cloud", force=False)
        self.assertIn("Refreshed 'eu-cloud'", result.output)

    def test_refresh_force_passes_flag(self):
        with patch("cloudinary_cli.core.config.refresh_config", return_value="refreshed") as rc:
            self.runner.invoke(cli, ['config', '--refresh', 'eu-cloud', '--force'])
        rc.assert_called_once_with("eu-cloud", force=True)

    def test_refresh_no_name_uses_active_config(self):
        with patch("cloudinary_cli.core.config.active_config_name", return_value="active-one"), \
                patch("cloudinary_cli.core.config.refresh_config", return_value="refreshed") as rc:
            self.runner.invoke(cli, ['config', '--refresh'])
        rc.assert_called_once_with("active-one", force=False)

    def test_refresh_unknown_name_errors(self):
        with patch("cloudinary_cli.core.config.refresh_config", return_value="not_found"):
            result = self.runner.invoke(cli, ['config', '--refresh', 'ghost'])
        self.assertEqual(2, result.exit_code)
        self.assertIn("does not exist", result.output)

    def test_refresh_failed_reports_relogin_with_region(self):
        with patch("cloudinary_cli.core.config.refresh_config", return_value="failed"), \
                patch("cloudinary_cli.core.config.relogin_command",
                      return_value="cld login eu-cloud --region api-eu") as relogin:
            result = self.runner.invoke(cli, ['config', '--refresh', 'eu-cloud'], standalone_mode=False)
        self.assertFalse(result.return_value)  # main() maps falsy -> exit 1
        relogin.assert_called_once_with("eu-cloud")
        self.assertIn("cld login eu-cloud --region api-eu", result.output)

    def test_refresh_all_reports_each(self):
        with patch("cloudinary_cli.core.config.refresh_configs",
                   return_value={"a": "refreshed", "b": "fresh"}) as rc:
            result = self.runner.invoke(cli, ['config', '--refresh-all'])
        self.assertEqual(0, result.exit_code, result.output)
        rc.assert_called_once_with(force=False)
        self.assertIn("Refreshed 'a'", result.output)
        self.assertIn("'b' token is still fresh", result.output)

    def test_force_without_refresh_errors(self):
        result = self.runner.invoke(cli, ['config', '--force'])
        self.assertEqual(2, result.exit_code)
        self.assertIn("--force only applies", result.output)


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
        new_token = jwt_access_token(cloud_name="eu-cloud", tag="target-new")
        token_response = {"access_token": new_token, "refresh_token": "rt_new", "expires_in": 300}
        with patch("cloudinary_cli.utils.config_resolver.load_config", return_value=config), \
                patch("cloudinary_cli.auth.refresh.load_config", return_value=config), \
                patch("cloudinary_cli.auth.flow.refresh", return_value=token_response), \
                patch("cloudinary_cli.auth.refresh.update_config"), \
                patch("cloudinary_cli.utils.config_resolver.ping_cloudinary", return_value=True):
            target_config = get_cloudinary_config("eu-cloud")
        self.assertTrue(target_config)
        self.assertEqual(new_token, target_config.oauth_token)

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
