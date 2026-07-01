import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from click.testing import CliRunner
from cloudinary.exceptions import BadRequest, RateLimited, AlreadyExists, GeneralError
from filelock import FileLock

from cloudinary_cli.cli import cli
from cloudinary_cli.utils import config_utils

AGENT_RESPONSE = {
    "external_id": "acct-123",
    "email": "you@example.com",
    "plan_name": "free",
    "product_environments": [
        {
            "external_id": "env-456",
            "cloud_name": "testcloud",
            "api_key": "111",
            "api_secret": "secret",
            "api_environment_variable": "CLOUDINARY_URL=cloudinary://111:secret@testcloud",
        }
    ],
    "guidance": "A verification email has been sent.",
}

SIGNUP_ARGS = [
    "agent", "signup",
    "you@example.com", "claude-code", "claude-opus-4-8", "test the agent account flow",
]


class TestCLIAgentSignup(unittest.TestCase):
    runner = CliRunner()

    def _invoke(self, extra_args=None, default_status="no", existing=None, save_side_effect=None):
        with patch("cloudinary_cli.core.agent.cloudinary.provisioning.create_agent_account",
                   return_value=AGENT_RESPONSE) as create, \
                patch("cloudinary_cli.core.agent.config_name_for_email",
                      return_value=existing) as lookup, \
                patch("cloudinary_cli.core.agent.user_config_names", return_value=[]), \
                patch("cloudinary_cli.core.agent.save_named_config",
                      return_value=default_status, side_effect=save_side_effect) as save:
            result = self.runner.invoke(cli, SIGNUP_ARGS + (extra_args or []))
        return result, create, save, lookup

    def test_signup_pretty_output_default(self):
        result, create, save, _ = self._invoke()

        self.assertEqual(0, result.exit_code)
        create.assert_called_once_with(
            "you@example.com", "claude-code", "claude-opus-4-8", "test the agent account flow",
            sdk_framework=None)
        self.assertIn("Cloudinary account created.", result.output)
        self.assertIn("Cloud name:", result.output)
        self.assertIn("testcloud", result.output)
        self.assertIn("CLOUDINARY_URL:", result.output)
        self.assertIn("cloudinary://111:secret@testcloud", result.output)
        self.assertIn("Config 'testcloud' saved!", result.output)
        self.assertIn("inert until the emailed verification", result.output)
        # guidance from the response is shown in the human path too
        self.assertIn("A verification email has been sent.", result.output)
        # the saved URL carries the account email
        name_arg, url_arg = save.call_args.args
        self.assertEqual("testcloud", name_arg)
        self.assertIn("cloudinary://111:secret@testcloud", url_arg)
        self.assertIn("account_email=you%40example.com", url_arg)
        self.assertEqual({"set_default": False}, save.call_args.kwargs)

    def test_signup_no_save_persists_nothing(self):
        result, _, save, lookup = self._invoke(["--no-save"])

        self.assertEqual(0, result.exit_code)
        save.assert_not_called()
        lookup.assert_called_once()  # pre-flight still runs
        self.assertIn("Cloudinary account created.", result.output)
        self.assertNotIn("Config 'testcloud' saved!", result.output)

    def test_signup_name_overrides_config_name(self):
        result, _, save, _ = self._invoke(["--name", "myagent"])

        self.assertEqual(0, result.exit_code)
        self.assertEqual("myagent", save.call_args.args[0])

    def test_signup_set_default_forwarded(self):
        result, _, save, _ = self._invoke(["--set-default"], default_status="made")

        self.assertEqual(0, result.exit_code)
        self.assertEqual({"set_default": True}, save.call_args.kwargs)
        self.assertIn("Default set to 'testcloud'", result.output)

    def test_signup_auto_defaulted_message(self):
        result, _, _, _ = self._invoke(default_status="made")

        self.assertEqual(0, result.exit_code)
        self.assertIn("Default set to 'testcloud'", result.output)

    def test_signup_passes_sdk_framework(self):
        result, create, _, _ = self._invoke(["--sdk-framework", "python"])

        self.assertEqual(0, result.exit_code)
        create.assert_called_once_with(
            "you@example.com", "claude-code", "claude-opus-4-8", "test the agent account flow",
            sdk_framework="python")

    def test_signup_surfaces_unknown_future_keys(self):
        response = dict(
            AGENT_RESPONSE,
            trial_days=14,  # novel top-level scalar
            docs_url="https://example.com/start",  # novel top-level scalar
            metadata={"ignored": True},  # nested -> not dumped into the summary
        )
        response["product_environments"] = [
            dict(AGENT_RESPONSE["product_environments"][0], region="us-east")  # novel env scalar
        ]
        with patch("cloudinary_cli.core.agent.cloudinary.provisioning.create_agent_account",
                   return_value=response), \
                patch("cloudinary_cli.core.agent.config_name_for_email", return_value=None), \
                patch("cloudinary_cli.core.agent.user_config_names", return_value=[]), \
                patch("cloudinary_cli.core.agent.save_named_config", return_value="no"):
            result = self.runner.invoke(cli, SIGNUP_ARGS)

        self.assertEqual(0, result.exit_code)
        self.assertIn("Trial days:", result.output)
        self.assertIn("14", result.output)
        self.assertIn("Docs url:", result.output)
        self.assertIn("https://example.com/start", result.output)
        self.assertIn("Region:", result.output)  # novel env key surfaced too
        self.assertIn("us-east", result.output)
        self.assertNotIn("ignored", result.output)  # nested values not dumped

    def test_signup_json_flag_emits_raw_json(self):
        result, _, save, _ = self._invoke(["--json"])

        self.assertEqual(0, result.exit_code)
        self.assertIn('"external_id": "acct-123"', result.output)
        self.assertIn("A verification email has been sent.", result.output)  # guidance present
        self.assertNotIn("CLOUDINARY_URL:", result.output)  # no pretty labels
        save.assert_called_once()  # saving is independent of output format

    def test_signup_json_no_save(self):
        result, _, save, _ = self._invoke(["--json", "--no-save"])

        self.assertEqual(0, result.exit_code)
        self.assertIn('"external_id": "acct-123"', result.output)
        save.assert_not_called()

    def test_signup_reserved_name_rejected(self):
        result, create, save, _ = self._invoke(["--name", "__default__"])

        self.assertEqual(2, result.exit_code)
        self.assertIn("reserved configuration name", result.output)
        create.assert_not_called()
        save.assert_not_called()

    def test_signup_empty_email_rejected(self):
        with patch("cloudinary_cli.core.agent.cloudinary.provisioning.create_agent_account") as create:
            result = self.runner.invoke(
                cli, ["agent", "signup", "  ", "claude-code", "claude-opus-4-8", "goal"])

        self.assertEqual(2, result.exit_code)
        self.assertIn("email must not be empty", result.output)
        create.assert_not_called()

    def test_signup_preflight_local_hit_skips_api(self):
        result, create, save, _ = self._invoke(existing="testcloud")

        self.assertNotEqual(0, result.exit_code)
        create.assert_not_called()
        save.assert_not_called()
        self.assertIn("you@example.com", result.output)
        self.assertIn("saved as 'testcloud'", result.output)
        self.assertIn("cld -C testcloud", result.output)

    def test_signup_preflight_blocks_even_with_no_save(self):
        result, create, save, _ = self._invoke(["--no-save"], existing="testcloud")

        self.assertNotEqual(0, result.exit_code)
        create.assert_not_called()
        save.assert_not_called()

    def test_signup_name_collision_warns(self):
        with patch("cloudinary_cli.core.agent.cloudinary.provisioning.create_agent_account",
                   return_value=AGENT_RESPONSE), \
                patch("cloudinary_cli.core.agent.config_name_for_email", return_value=None), \
                patch("cloudinary_cli.core.agent.user_config_names", return_value=["foo"]), \
                patch("cloudinary_cli.core.agent.save_named_config", return_value="no"):
            result = self.runner.invoke(cli, SIGNUP_ARGS + ["--name", "foo"])

        self.assertEqual(0, result.exit_code)
        self.assertIn("Overwriting existing config 'foo'", result.output)

    def test_signup_save_failure_still_shows_credentials(self):
        result, _, _, _ = self._invoke(save_side_effect=OSError("disk full"))

        self.assertIn("cloudinary://111:secret@testcloud", result.output)  # creds shown first
        self.assertIn("Could not save the configuration", result.output)
        self.assertIn("cld config -n testcloud", result.output)  # manual-add hint

    def test_signup_missing_product_env_surfaces_creds(self):
        response = dict(AGENT_RESPONSE, product_environments=[])
        with patch("cloudinary_cli.core.agent.cloudinary.provisioning.create_agent_account",
                   return_value=response), \
                patch("cloudinary_cli.core.agent.config_name_for_email", return_value=None), \
                patch("cloudinary_cli.core.agent.user_config_names", return_value=[]), \
                patch("cloudinary_cli.core.agent.save_named_config") as save:
            result = self.runner.invoke(cli, SIGNUP_ARGS)

        self.assertEqual(0, result.exit_code)
        self.assertIn("Cloudinary account created.", result.output)
        self.assertIn("you@example.com", result.output)  # raw creds still surfaced
        self.assertIn("Could not save the configuration automatically", result.output)
        save.assert_not_called()

    def _invoke_failing(self, error, existing=None):
        with patch("cloudinary_cli.core.agent.cloudinary.provisioning.create_agent_account",
                   side_effect=error) as create, \
                patch("cloudinary_cli.core.agent.config_name_for_email", return_value=existing), \
                patch("cloudinary_cli.core.agent.save_named_config") as save:
            create.__name__ = "create_agent_account"  # call_api reads func.__name__ when logging
            result = self.runner.invoke(cli, SIGNUP_ARGS)
        return result, save

    def test_signup_server_email_taken_no_local_config(self):
        result, save = self._invoke_failing(
            BadRequest('Error 400 - {"email":["has already been taken"]}'))

        self.assertNotEqual(0, result.exit_code)
        self.assertIn("An account already exists for you@example.com", result.output)
        self.assertIn("no configuration is saved on this machine", result.output)
        self.assertIn("cld config -n", result.output)
        self.assertIn("verification email", result.output)
        self.assertNotIn("cld config -ls", result.output)
        save.assert_not_called()

    def test_signup_already_exists_409(self):
        result, save = self._invoke_failing(AlreadyExists("Error 409 - account exists"))

        self.assertNotEqual(0, result.exit_code)
        self.assertIn("An account already exists for you@example.com", result.output)
        save.assert_not_called()

    def test_signup_generic_500_clean_message(self):
        result, save = self._invoke_failing(
            GeneralError('Error 500 - {"error":{"message":"boom"}}'))

        self.assertNotEqual(0, result.exit_code)
        self.assertIn("Signup failed: boom.", result.output)
        save.assert_not_called()

    def test_signup_other_bad_request_surfaces_message(self):
        result, save = self._invoke_failing(
            BadRequest('Error 400 - {"email":["is invalid"]}'))

        self.assertNotEqual(0, result.exit_code)
        self.assertIn("Signup failed: email is invalid.", result.output)
        save.assert_not_called()

    def test_signup_bad_request_str_not_list(self):
        result, _ = self._invoke_failing(BadRequest('Error 400 - {"email":"is invalid"}'))

        self.assertIn("Signup failed: email is invalid.", result.output)

    def test_signup_bad_request_empty_body(self):
        result, _ = self._invoke_failing(BadRequest("Error 400 - {}"))

        self.assertNotEqual(0, result.exit_code)
        self.assertNotIn("Signup failed: .", result.output)  # no dangling empty detail

    def test_signup_bad_request_non_json(self):
        result, _ = self._invoke_failing(BadRequest("Error 400 - service unavailable"))

        self.assertIn("Signup failed: Error 400 - service unavailable.", result.output)

    def test_signup_rate_limited_guides_to_retry(self):
        result, save = self._invoke_failing(RateLimited("Error 420 - too many requests"))

        self.assertNotEqual(0, result.exit_code)
        self.assertIn("Rate limited", result.output)
        self.assertIn("per IP address", result.output)
        save.assert_not_called()


_BANNER = "No Cloudinary configuration found"


class TestUnconfiguredBanner(unittest.TestCase):
    """The top-level group prints the 'No configuration found' banner only for commands that
    consume the resolved account; config-optional commands (login/logout/config/agent) stay silent."""

    runner = CliRunner()

    @contextmanager
    def _unconfigured(self, saved=None):
        import cloudinary
        with tempfile.TemporaryDirectory() as d:
            config_file = os.path.join(d, "config.json")
            if saved:  # saved configs on disk but (deliberately) no __default__ set
                with open(config_file, "w") as f:
                    json.dump(saved, f)
            env = {k: v for k, v in os.environ.items() if k != "CLOUDINARY_URL"}
            with patch.dict(os.environ, env, clear=True), \
                    patch.object(cloudinary, "_config", cloudinary.Config()), \
                    patch.object(config_utils, "CLOUDINARY_CLI_CONFIG_FILE", config_file), \
                    patch.object(config_utils, "_config_lock", FileLock(config_file + ".lock")):
                yield

    def _invoke(self, args, saved=None):
        with self._unconfigured(saved=saved):
            return self.runner.invoke(cli, args)

    def test_config_optional_commands_do_not_warn(self):
        for args in (["login", "--help"], ["logout"], ["config", "-ls"],
                     ["config", "-n", "foo", "cloudinary://k:s@c"], ["agent", "--help"]):
            result = self._invoke(args)
            self.assertNotIn(_BANNER, result.stderr, args)

    def test_account_commands_still_warn(self):
        for args in (["url", "sample"], ["utils"], ["admin"], ["uploader"]):
            result = self._invoke(args)
            self.assertIn(_BANNER, result.stderr, args)

    def test_banner_has_no_warning_prefix(self):
        result = self._invoke(["url", "sample"])
        self.assertIn(_BANNER, result.stderr)
        self.assertNotIn("warning:", result.stderr)  # printed clean, not via logger.warning
        self.assertIn("cld login", result.stderr)  # guidance lines carry no prefix either

    def test_saved_configs_but_no_default_gives_distinct_banner(self):
        saved = {"prod": "cloudinary://k:s@prodcloud"}  # no __default__
        result = self._invoke(["admin", "usage"], saved=saved)
        self.assertNotIn(_BANNER, result.stderr)  # not the "found nothing" message
        self.assertIn("No default Cloudinary configuration is set", result.stderr)
        self.assertIn("-C <name>", result.stderr)
        self.assertIn("cld config -d <name>", result.stderr)

    def test_no_default_api_error_is_accurate(self):
        saved = {"prod": "cloudinary://k:s@prodcloud"}
        result = self._invoke(["admin", "usage"], saved=saved)
        self.assertNotEqual(0, result.exit_code)
        self.assertIn("No default Cloudinary configuration is set", str(result.exception))

    def test_inline_c_rejects_non_url(self):
        result = self._invoke(["-c", "dummy", "url", "sample"])
        self.assertEqual(2, result.exit_code)
        self.assertIn("-c/--config expects a CLOUDINARY_URL", result.output)

    def test_inline_c_with_saved_name_points_to_capital_c(self):
        saved = {"prod": "cloudinary://k:s@prodcloud"}
        result = self._invoke(["-c", "prod", "url", "sample"], saved=saved)
        self.assertEqual(2, result.exit_code)
        self.assertIn("'prod' is a saved configuration name", result.output)
        self.assertIn("cld -C prod", result.output)

    def test_inline_c_accepts_valid_url(self):
        result = self._invoke(["-c", "cloudinary://k:s@realcloud", "url", "sample"])
        self.assertEqual(0, result.exit_code)
        self.assertIn("realcloud", result.output)

    def test_inline_c_keyless_url_reports_incomplete_not_missing(self):
        # cloudinary://<cloud> is a valid config URL but has no credentials: URL building still
        # works, so the banner must say "incomplete", not "no configuration found".
        result = self._invoke(["-c", "cloudinary://dummy", "url", "sample"])
        self.assertEqual(0, result.exit_code)
        self.assertNotIn(_BANNER, result.stderr)
        self.assertIn("has a cloud name but no credentials", result.stderr)
        self.assertIn("dummy", result.output)  # URL still built

    def test_saved_keyless_config_reports_incomplete(self):
        saved = {"keyless": "cloudinary://keylesscloud"}
        result = self._invoke(["-C", "keyless", "admin", "usage"], saved=saved)
        self.assertNotIn(_BANNER, result.stderr)
        self.assertIn("has a cloud name but no credentials", result.stderr)

    def test_empty_config_ls_shows_guidance(self):
        result = self._invoke(["config", "-ls"])
        self.assertEqual(0, result.exit_code)
        self.assertIn(_BANNER, result.output)  # printed to stdout, not the stderr banner
        self.assertIn("cld login", result.output)
        self.assertNotIn("NAME", result.output)  # no empty header-only table

    def test_empty_config_ls_json_stays_empty_array(self):
        result = self._invoke(["config", "-ls", "-j"])
        self.assertEqual(0, result.exit_code)
        self.assertNotIn(_BANNER, result.output)
        self.assertIn("[]", result.output)

    def test_bare_config_reports_no_config_via_own_error(self):
        result = self._invoke(["config"])
        self.assertNotEqual(0, result.exit_code)
        self.assertNotIn(_BANNER, result.stderr)  # not the group banner
        self.assertEqual("No Cloudinary configuration found.", str(result.exception))


if __name__ == "__main__":
    unittest.main()
