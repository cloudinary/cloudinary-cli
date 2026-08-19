import json
import os
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote

from click.testing import CliRunner
from cloudinary.exceptions import BadRequest, NotAllowed, RateLimited
from filelock import FileLock

from cloudinary_cli.cli import cli
from cloudinary_cli.utils import config_utils
from cloudinary_cli.utils.config_utils import claim_url_from_url, expires_at_from_url, validate_config_url

# Shaped like a real `POST /v1_1/provisioning/clouds` response, with every value obviously fake:
# the claim_url keeps its own ?token= query (and the -._ characters in it) because that is what the
# saved-URL encoding has to survive, and the delivery IP is from the TEST-NET-3 documentation range.
FAKE_CLOUD = "fakecloud"
FAKE_API_KEY = "100000000000001"
FAKE_API_SECRET = "fake-api-secret_NOT-REAL-000"
FAKE_CLAIM_TOKEN = "fake-claim-token.NOT-REAL_000"
FAKE_DELIVERY_IP = "203.0.113.10"
FAKE_CLOUDINARY_URL = f"cloudinary://{FAKE_API_KEY}:{FAKE_API_SECRET}@{FAKE_CLOUD}"

CLOUD_RESPONSE = {
    "account_id": "00000000-0000-4000-8000-000000000001",
    "email": "cloud-fake0000000000@cloud.cloudinary.invalid",
    "cloud_name": FAKE_CLOUD,
    "api_key": FAKE_API_KEY,
    "api_secret": FAKE_API_SECRET,
    "api_environment_variable": f"CLOUDINARY_URL={FAKE_CLOUDINARY_URL}",
    "claimed": False,
    "expires_at": "2026-08-19T16:13:09Z",
    "delivery_ips": [FAKE_DELIVERY_IP],
    "claim_url": "https://console.example.invalid/users/agent_email_confirmation"
                 f"?token={FAKE_CLAIM_TOKEN}",
    "guidance": "A Claimable Cloud is ready and the API key and secret below work immediately.",
}

CREATE_ARGS = ["agent", "cloud", "create"]


class CloudTestCase(unittest.TestCase):
    """Each test runs against a temporary config file, so nothing touches the developer's real one."""

    runner = CliRunner()

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.config_file = os.path.join(self._dir.name, "config.json")
        for ctx in (patch.object(config_utils, "CLOUDINARY_CLI_CONFIG_FILE", self.config_file),
                    patch.object(config_utils, "_config_lock", FileLock(self.config_file + ".lock")),
                    patch.object(config_utils, "_config_cache", None),
                    patch.object(config_utils, "_config_cache_stat", None)):
            ctx.start()
            self.addCleanup(ctx.stop)

    def write_config(self, config):
        with open(self.config_file, "w") as f:
            json.dump(config, f)

    def read_config(self):
        with open(self.config_file) as f:
            return json.load(f)


class TestCloudCreate(CloudTestCase):
    def _invoke(self, extra_args=None, response=None, error=None):
        with patch("cloudinary.provisioning.create_cloud",
                   return_value=response or CLOUD_RESPONSE, side_effect=error) as create:
            create.__name__ = "create_cloud"  # call_api reads func.__name__ when logging
            result = self.runner.invoke(cli, CREATE_ARGS + (extra_args or []))
        return result, create

    def test_create_prints_credentials_and_saves_config(self):
        result, create = self._invoke()

        self.assertEqual(0, result.exit_code)
        self.assertIn("Claimable Cloud created.", result.output)
        self.assertIn(FAKE_CLOUD, result.output)
        self.assertIn(FAKE_CLOUDINARY_URL, result.output)
        self.assertIn(FAKE_DELIVERY_IP, result.output)
        self.assertIn(CLOUD_RESPONSE["claim_url"], result.output)
        self.assertIn("2026-08-19T16:13:09Z", result.output)
        self.assertIn(CLOUD_RESPONSE["guidance"], result.output)  # server guidance passed through verbatim
        self.assertIn(f"Config '{FAKE_CLOUD}' saved!", result.output)

    def test_create_without_ip_omits_delivery_ips_entirely(self):
        result, create = self._invoke()

        self.assertEqual(0, result.exit_code)
        self.assertIsNone(create.call_args.kwargs["delivery_ips"])

    def test_create_forwards_ips_and_attribution(self):
        result, create = self._invoke([
            "you@cloudinary.com",
            "--ip", "8.8.8.8", "--ip", "requester_ip",
            "--agent-framework", "claude-code", "--agent-llm-model", "claude-opus-5",
            "--agent-goal", "test", "--sdk-framework", "python",
        ])

        self.assertEqual(0, result.exit_code)
        self.assertEqual({
            "delivery_ips": ["8.8.8.8", "requester_ip"],
            "email": "you@cloudinary.com",
            "agent_framework": "claude-code",
            "agent_llm_model": "claude-opus-5",
            "agent_goal": "test",
            "sdk_framework": "python",
        }, create.call_args.kwargs)

    def test_create_forwards_ips_verbatim_without_client_side_validation(self):
        # the server owns the delivery-IP rules (count, routability, CIDR); the CLI must not
        # duplicate them and reject something the server would have accepted
        result, create = self._invoke(
            ["--ip", "1.1.1.1", "--ip", "2.2.2.2", "--ip", "3.3.3.3", "--ip", "10.0.0.0/8"])

        self.assertEqual(0, result.exit_code)
        self.assertEqual(["1.1.1.1", "2.2.2.2", "3.3.3.3", "10.0.0.0/8"],
                         create.call_args.kwargs["delivery_ips"])

    def test_create_accepts_ipv6(self):
        result, create = self._invoke(["--ip", "2001:4860:4860::8888"])

        self.assertEqual(0, result.exit_code)
        self.assertEqual(["2001:4860:4860::8888"], create.call_args.kwargs["delivery_ips"])

    def test_create_reserved_name_rejected(self):
        result, create = self._invoke(["--name", "__default__"])

        self.assertEqual(2, result.exit_code)
        self.assertIn("reserved configuration name", result.output)
        create.assert_not_called()

    def test_create_name_collision_makes_no_api_call(self):
        self.write_config({"taken": "cloudinary://k:s@somecloud"})
        result, create = self._invoke(["--name", "taken"])

        self.assertNotEqual(0, result.exit_code)
        self.assertIn("already exists", result.output)
        create.assert_not_called()  # never burn a rate-limited cloud we would refuse to store

    def test_create_name_collision_allowed_with_no_save(self):
        self.write_config({"taken": "cloudinary://k:s@somecloud"})
        result, create = self._invoke(["--name", "taken", "--no-save"])

        self.assertEqual(0, result.exit_code)
        create.assert_called_once()

    def test_create_persists_claim_url_and_expiry_on_saved_config(self):
        result, _ = self._invoke()

        self.assertEqual(0, result.exit_code)
        stored = self.read_config()[FAKE_CLOUD]
        validate_config_url(stored)
        self.assertEqual(CLOUD_RESPONSE["claim_url"], claim_url_from_url(stored))
        self.assertEqual(CLOUD_RESPONSE["expires_at"], expires_at_from_url(stored))

    def test_create_persists_delivery_ips_and_account_id(self):
        result, _ = self._invoke()

        self.assertEqual(0, result.exit_code)
        stored = self.read_config()[FAKE_CLOUD]
        from cloudinary_cli.utils.config_utils import delivery_ips_from_url, account_id_from_url
        # the server rewrites the list it was sent, and there is no endpoint to read it back
        self.assertEqual(CLOUD_RESPONSE["delivery_ips"], delivery_ips_from_url(stored))
        self.assertEqual(CLOUD_RESPONSE["account_id"], account_id_from_url(stored))

    def test_persisted_delivery_ips_survive_ipv6(self):
        response = dict(CLOUD_RESPONSE, delivery_ips=["8.8.8.8", "2001:4860:4860::8888"])
        result, _ = self._invoke(response=response)

        from cloudinary_cli.utils.config_utils import delivery_ips_from_url
        self.assertEqual(response["delivery_ips"], delivery_ips_from_url(self.read_config()[FAKE_CLOUD]))

    def test_create_stores_a_real_email_but_not_the_placeholder(self):
        from cloudinary_cli.utils.config_utils import cloud_email_from_url

        result, _ = self._invoke()  # response carries the synthetic @cloud.cloudinary.invalid
        self.assertIsNone(cloud_email_from_url(self.read_config()[FAKE_CLOUD]))

        self.setUp()  # fresh config file
        result, _ = self._invoke(response=dict(CLOUD_RESPONSE, email="you@cloudinary.com"))
        self.assertEqual("you@cloudinary.com", cloud_email_from_url(self.read_config()[FAKE_CLOUD]))

    def test_stored_cloud_email_is_not_the_signup_account_email(self):
        # a real claim-page email must still not make config_name_for_email match this cloud
        self._invoke(response=dict(CLOUD_RESPONSE, email="you@cloudinary.com"))

        stored = self.read_config()[FAKE_CLOUD]
        self.assertNotIn("account_email", stored)
        self.assertIsNone(config_utils.email_from_url(stored))
        self.assertIsNone(config_utils.config_name_for_email("you@cloudinary.com"))

    def test_noisy_response_fields_are_not_persisted(self):
        result, _ = self._invoke()

        stored = self.read_config()[FAKE_CLOUD]
        self.assertNotIn("guidance", stored)  # paragraphs of prose
        self.assertNotIn("claimed", stored)  # always false, never updated
        self.assertNotIn("api_environment_variable", stored)  # duplicates the URL itself

    def test_create_does_not_write_account_email_param(self):
        result, _ = self._invoke(["you@cloudinary.com"])

        self.assertEqual(0, result.exit_code)
        stored = self.read_config()[FAKE_CLOUD]
        self.assertNotIn("account_email", stored)
        # so a Claimable Cloud never masquerades as a signup account
        self.assertIsNone(config_utils.config_name_for_email("you@cloudinary.com"))

    def test_create_no_save_persists_nothing_and_warns(self):
        result, _ = self._invoke(["--no-save"])

        self.assertEqual(0, result.exit_code)
        self.assertFalse(os.path.exists(self.config_file))
        self.assertIn("Nothing was saved", result.output)
        self.assertIn("claim", result.output)
        self.assertIn(CLOUD_RESPONSE["claim_url"], result.output)

    def test_create_set_default(self):
        result, _ = self._invoke(["--set-default"])

        self.assertEqual(0, result.exit_code)
        self.assertEqual(FAKE_CLOUD, self.read_config()["__default__"])

    def test_create_custom_name(self):
        result, _ = self._invoke(["--name", "mycloud"])

        self.assertEqual(0, result.exit_code)
        self.assertIn("mycloud", self.read_config())

    def test_create_json_emits_raw_response(self):
        result, _ = self._invoke(["--json"])

        self.assertEqual(0, result.exit_code)
        payload = json.loads(result.output[:result.output.rindex("}") + 1])
        self.assertEqual(CLOUD_RESPONSE, payload)  # unmodified
        self.assertNotIn("CLOUDINARY_URL:", result.output)  # no pretty labels

    def test_create_shows_credentials_even_when_save_fails(self):
        with patch("cloudinary.provisioning.create_cloud", return_value=CLOUD_RESPONSE), \
                patch("cloudinary_cli.core.agent.save_named_config", side_effect=OSError("disk full")):
            result = self.runner.invoke(cli, CREATE_ARGS)

        self.assertEqual(0, result.exit_code)
        self.assertIn(FAKE_CLOUDINARY_URL, result.output)
        self.assertIn("Could not save the configuration", result.output)
        self.assertIn(f"cld config -n {FAKE_CLOUD}", result.output)  # manual-add hint keeps the claim URL
        self.assertIn("claim_url", result.output)

    def test_create_surfaces_unknown_future_keys(self):
        response = dict(CLOUD_RESPONSE, region="us-east", nested={"ignored": True})
        result, _ = self._invoke(response=response)

        self.assertEqual(0, result.exit_code)
        self.assertIn("Region:", result.output)
        self.assertIn("us-east", result.output)
        self.assertNotIn("ignored", result.output)

    def test_create_makes_no_outbound_ip_lookup(self):
        # the server derives the allow-list from the request's own source address; the CLI must not
        # probe an echo service to second-guess it
        with patch("cloudinary_cli.core.agent.call_api", return_value=CLOUD_RESPONSE), \
                patch("requests.get", side_effect=AssertionError("no echo-service call")):
            result = self.runner.invoke(cli, CREATE_ARGS)

        self.assertEqual(0, result.exit_code)


class TestCloudCreateErrors(CloudTestCase):
    """Server messages captured verbatim from staging — the SDK surfaces the message only, not the
    error envelope's `code`, so the guidance is keyed on these strings."""

    def _invoke_failing(self, error, extra_args=None):
        with patch("cloudinary.provisioning.create_cloud", side_effect=error) as create:
            create.__name__ = "create_cloud"
            return self.runner.invoke(cli, CREATE_ARGS + (extra_args or []))

    def test_public_ip_rejection_surfaces_the_server_message(self):
        # the server explains the rejection; the CLI passes it through rather than guessing
        # whether the private address came from --ip or from the request's own source
        result = self._invoke_failing(
            BadRequest("Error 400 - delivery_ips must contain at least one public IP address"))

        self.assertNotEqual(0, result.exit_code)
        self.assertIn("delivery_ips must contain at least one public IP address", result.output)

    def test_too_many_ips_server_message_surfaced(self):
        result = self._invoke_failing(BadRequest("Error 400 - At most 3 delivery_ips are allowed"))

        self.assertNotEqual(0, result.exit_code)
        self.assertIn("At most 3 delivery_ips are allowed", result.output)

    def test_invalid_ip_server_message_surfaced(self):
        result = self._invoke_failing(BadRequest("Error 400 - Invalid delivery IP: not-an-ip"))

        self.assertNotEqual(0, result.exit_code)
        self.assertIn("Invalid delivery IP: not-an-ip", result.output)

    def test_rate_limited(self):
        result = self._invoke_failing(RateLimited("Error 429 - Rate limit exceeded"))

        self.assertNotEqual(0, result.exit_code)
        self.assertIn("Rate limited", result.output)
        self.assertIn("10 clouds per 24 hours", result.output)

    def test_registration_disabled(self):
        result = self._invoke_failing(
            NotAllowed("Error 403 - Agent account registration is currently unavailable"))

        self.assertNotEqual(0, result.exit_code)
        self.assertIn("currently disabled by Cloudinary", result.output)

    def test_geo_location_not_permitted_mentions_supplied_ips(self):
        result = self._invoke_failing(NotAllowed("Error 403 - Location not permitted"))

        self.assertNotEqual(0, result.exit_code)
        self.assertIn("Location not permitted", result.output)
        self.assertIn("every --ip supplied", result.output)


def _hours_from_now(hours):
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


class TestCloudClaim(CloudTestCase):
    # Expiry is relative to now: the claim picker skips expired clouds, so a hardcoded timestamp
    # would silently change what these tests exercise once it passed.
    CLOUD_URL = (FAKE_CLOUDINARY_URL
                 + "?claim_url=" + quote(CLOUD_RESPONSE["claim_url"], safe="")
                 + "&expires_at=" + quote(_hours_from_now(8), safe=""))

    def _invoke(self, args, is_tty=True):
        # CliRunner swaps sys.stdout for a capture buffer, so the TTY check is steered by patching
        # isatty on whatever object is installed at call time, not on the original stream.
        with patch("cloudinary_cli.core.agent.launch") as launch, \
                patch("cloudinary_cli.core.agent.sys") as agent_sys:
            agent_sys.stdout.isatty.return_value = is_tty
            result = self.runner.invoke(cli, ["agent", "cloud", "claim"] + args)
        return result, launch

    def test_claim_opens_stored_url_on_a_tty(self):
        self.write_config({"mycloud": self.CLOUD_URL})
        result, launch = self._invoke(["mycloud"])

        self.assertEqual(0, result.exit_code)
        launch.assert_called_once_with(CLOUD_RESPONSE["claim_url"])
        self.assertIn("Opened the claim page", result.output)
        self.assertIn("must enter an email address", result.output)
        # printed as well as opened: launch() cannot confirm a browser came up, and the URL is
        # issued once and cannot be re-fetched
        self.assertIn(CLOUD_RESPONSE["claim_url"], result.output)
        self.assertNotIn("claimed", result.output.lower().replace("unclaimed", ""))

    def test_claim_print_flag_does_not_open_browser(self):
        self.write_config({"mycloud": self.CLOUD_URL})
        result, launch = self._invoke(["mycloud", "--print"])

        self.assertEqual(0, result.exit_code)
        launch.assert_not_called()
        # the bare URL and nothing else, so `--print` stays pipeable
        self.assertEqual(CLOUD_RESPONSE["claim_url"], result.output.strip())

    def test_claim_prints_instead_of_opening_when_not_a_tty(self):
        self.write_config({"mycloud": self.CLOUD_URL})
        result, launch = self._invoke(["mycloud"], is_tty=False)

        self.assertEqual(0, result.exit_code)
        launch.assert_not_called()  # an agent must hand the URL to its human, not spawn a browser
        self.assertIn(CLOUD_RESPONSE["claim_url"], result.output)

    def test_claim_selects_sole_saved_cloud_when_name_omitted(self):
        self.write_config({"mycloud": self.CLOUD_URL, "__default__": "mycloud"})
        result, launch = self._invoke(["--print"])

        self.assertEqual(0, result.exit_code)
        self.assertIn(CLOUD_RESPONSE["claim_url"], result.output)

    def test_claim_ignores_default_config_that_is_not_a_claimable_cloud(self):
        # The default is an ordinary account with no claim URL; the sole Claimable Cloud is chosen
        # instead of failing on the default the way a plain default-config lookup would.
        self.write_config({"ordinary": "cloudinary://k:s@somecloud",
                           "mycloud": self.CLOUD_URL,
                           "__default__": "ordinary"})
        result, _ = self._invoke(["--print"])

        self.assertEqual(0, result.exit_code)
        self.assertIn(CLOUD_RESPONSE["claim_url"], result.output)

    def test_claim_without_any_saved_cloud_reports_nothing_to_do(self):
        self.write_config({"ordinary": "cloudinary://k:s@somecloud", "__default__": "ordinary"})
        result, launch = self._invoke([])

        self.assertEqual(0, result.exit_code)  # nothing to do is not an error
        launch.assert_not_called()
        self.assertIn("No saved Claimable Clouds to claim", result.output)

    def test_claim_lists_choices_when_several_are_saved(self):
        second = self.CLOUD_URL.replace(FAKE_CLOUD, "second").replace("fake-claim-token", "other-token")
        self.write_config({"a": self.CLOUD_URL, "b": second})
        with patch("cloudinary_cli.core.agent.prompt_user", return_value="2"):
            result, launch = self._invoke([])

        self.assertEqual(0, result.exit_code)
        self.assertIn("1) a", result.output)
        self.assertIn("2) b", result.output)
        self.assertIn("other-token", launch.call_args.args[0])  # the selected one, not the first

    def test_claim_cancelled_selection_does_nothing(self):
        second = self.CLOUD_URL.replace(FAKE_CLOUD, "second")
        self.write_config({"a": self.CLOUD_URL, "b": second})
        with patch("cloudinary_cli.core.agent.prompt_user", return_value=""):
            result, launch = self._invoke([])

        self.assertEqual(0, result.exit_code)
        launch.assert_not_called()

    def test_claim_non_interactive_selection_errors_with_hint(self):
        second = self.CLOUD_URL.replace(FAKE_CLOUD, "second")
        self.write_config({"a": self.CLOUD_URL, "b": second})
        with patch("cloudinary_cli.core.agent.prompt_user", return_value=None):
            result, launch = self._invoke([])

        self.assertNotEqual(0, result.exit_code)
        launch.assert_not_called()

    def test_claim_json_output(self):
        self.write_config({"mycloud": self.CLOUD_URL})
        result, _ = self._invoke(["mycloud", "--json"])

        self.assertEqual(0, result.exit_code)
        payload = json.loads(result.output[:result.output.rindex("}") + 1])
        self.assertEqual({"cloud_name": FAKE_CLOUD,
                          "claim_url": CLOUD_RESPONSE["claim_url"],
                          "expires_at": expires_at_from_url(self.CLOUD_URL)}, payload)

    def test_claim_json_does_not_open_a_browser_even_on_a_tty(self):
        # --json is the machine-readable contract; the payload already carries the claim URL
        self.write_config({"mycloud": self.CLOUD_URL})
        result, launch = self._invoke(["mycloud", "--json"], is_tty=True)

        self.assertEqual(0, result.exit_code)
        launch.assert_not_called()

    def test_claim_without_stored_claim_url_explains_why(self):
        self.write_config({"plain": "cloudinary://k:s@somecloud"})
        result, launch = self._invoke(["plain"])

        self.assertNotEqual(0, result.exit_code)
        launch.assert_not_called()
        self.assertIn("No claim URL is stored", result.output)
        self.assertIn("cannot be re-fetched", result.output)

    def test_claim_unknown_config(self):
        self.write_config({"mycloud": self.CLOUD_URL})
        result, _ = self._invoke(["nosuch"])

        self.assertNotEqual(0, result.exit_code)
        self.assertIn("does not exist", result.output)

    EXPIRED_URL = CLOUD_URL.split("&expires_at=")[0] + "&expires_at=2020-01-01T00%3A00%3A00Z"

    def test_claim_warns_but_still_prints_when_expired(self):
        self.write_config({"old": self.EXPIRED_URL})
        result, _ = self._invoke(["old", "--print"])

        self.assertEqual(0, result.exit_code)
        self.assertIn("expired", result.output)
        self.assertIn(CLOUD_RESPONSE["claim_url"], result.output)  # printed anyway: local clock isn't authoritative

    def test_expired_cloud_is_not_offered_in_the_picker(self):
        self.write_config({"live": self.CLOUD_URL, "old": self.EXPIRED_URL})
        result, launch = self._invoke(["--print"])

        self.assertEqual(0, result.exit_code)
        self.assertNotIn("old", result.output)  # sole live cloud is chosen outright, no menu
        launch.assert_not_called()
        self.assertIn(CLOUD_RESPONSE["claim_url"], result.output)

    def test_picker_says_so_when_every_cloud_has_expired(self):
        self.write_config({"old": self.EXPIRED_URL})
        result, launch = self._invoke([])

        self.assertEqual(0, result.exit_code)  # nothing claimable is not an error
        launch.assert_not_called()
        self.assertIn("has expired", result.output)


class TestConfigListingStatus(CloudTestCase):
    """`config -ls` gains a STATUS column for saved Claimable Clouds, the same way EMAIL appears
    only when some config records one."""

    @staticmethod
    def _cloud_url(cloud, expires_at):
        from urllib.parse import quote
        return (f"cloudinary://k:s@{cloud}?claim_url={quote('https://console.cloudinary.com/x?token=ABC', safe='')}"
                f"&expires_at={quote(expires_at, safe='')}")

    @staticmethod
    def _in_hours(hours):
        from datetime import datetime, timedelta, timezone
        return (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def test_status_column_absent_without_any_claimable_cloud(self):
        self.write_config({"ordinary": "cloudinary://k:s@plaincloud"})
        result = self.runner.invoke(cli, ["config", "-ls"])

        self.assertEqual(0, result.exit_code)
        self.assertNotIn("STATUS", result.output)

    def test_status_column_shows_remaining_time(self):
        self.write_config({"ordinary": "cloudinary://k:s@plaincloud",
                           "mycloud": self._cloud_url(FAKE_CLOUD, self._in_hours(8))})
        result = self.runner.invoke(cli, ["config", "-ls"])

        self.assertEqual(0, result.exit_code)
        self.assertIn("STATUS", result.output)
        self.assertIn("unclaimed, expires in 8h", result.output)

    def test_status_column_marks_expired_cloud(self):
        self.write_config({"oldcloud": self._cloud_url("oldcloud", "2020-01-01T00:00:00Z")})
        result = self.runner.invoke(cli, ["config", "-ls"])

        self.assertEqual(0, result.exit_code)
        self.assertIn("unclaimed, expired", result.output)

    def test_status_never_claims_a_cloud_was_claimed(self):
        # Nothing reports claim status, so the column must never say "claimed".
        self.write_config({"mycloud": self._cloud_url(FAKE_CLOUD, self._in_hours(8))})
        result = self.runner.invoke(cli, ["config", "-ls"])

        self.assertNotIn("claimed", result.output.replace("unclaimed", ""))

    def test_claim_hint_shown_when_a_live_cloud_is_listed(self):
        self.write_config({"ordinary": "cloudinary://k:s@plaincloud",
                           "mycloud": self._cloud_url(FAKE_CLOUD, self._in_hours(8))})
        result = self.runner.invoke(cli, ["config", "-ls"])

        self.assertIn("1 unclaimed Claimable Cloud:", result.output)
        self.assertIn("uploaded to it.", result.output)  # singular count, singular pronoun
        self.assertIn("Claim with `cld agent cloud claim`", result.output)

    def test_claim_hint_counts_only_live_clouds(self):
        self.write_config({"live": self._cloud_url("livecloud", self._in_hours(8)),
                           "alsolive": self._cloud_url("second", self._in_hours(24)),
                           "dead": self._cloud_url("deadcloud", "2020-01-01T00:00:00Z")})
        result = self.runner.invoke(cli, ["config", "-ls"])

        self.assertIn("2 unclaimed Claimable Clouds:", result.output)  # the expired one is not counted
        self.assertIn("uploaded to them.", result.output)

    def test_no_claim_hint_when_every_cloud_has_expired(self):
        self.write_config({"dead": self._cloud_url("deadcloud", "2020-01-01T00:00:00Z")})
        result = self.runner.invoke(cli, ["config", "-ls"])

        self.assertIn("unclaimed, expired", result.output)  # still listed
        self.assertNotIn("cld agent cloud claim", result.output)  # but not advertised as claimable

    def test_no_claim_hint_without_any_cloud(self):
        self.write_config({"ordinary": "cloudinary://k:s@plaincloud"})
        result = self.runner.invoke(cli, ["config", "-ls"])

        self.assertNotIn("unclaimed", result.output)
        self.assertNotIn("cld agent cloud claim", result.output)

    def test_cloud_with_unreadable_expiry_still_gets_the_hint(self):
        # unknown expiry is not the same as expired, so it stays claimable
        self.write_config({"noexp": "cloudinary://k:s@noexp?claim_url=https%3A%2F%2Fc.io%2Fx%3Ftoken%3DD"})
        result = self.runner.invoke(cli, ["config", "-ls"])

        self.assertIn("Claim with `cld agent cloud claim`", result.output)

    def test_json_listing_has_no_hint_text(self):
        self.write_config({"mycloud": self._cloud_url(FAKE_CLOUD, self._in_hours(8))})
        result = self.runner.invoke(cli, ["config", "-ls", "-j"])

        json.loads(result.output)  # parses: no prose appended to the JSON payload

    def test_ordinary_config_row_has_no_status(self):
        self.write_config({"ordinary": "cloudinary://k:s@plaincloud",
                           "mycloud": self._cloud_url(FAKE_CLOUD, self._in_hours(8))})
        result = self.runner.invoke(cli, ["config", "-ls", "-j"])

        rows = {row["name"]: row for row in json.loads(result.output)}
        self.assertNotIn("status", rows["ordinary"])
        self.assertIn("status", rows["mycloud"])

    def test_json_carries_raw_expires_at_not_the_label(self):
        expires_at = self._in_hours(8)
        self.write_config({"mycloud": self._cloud_url(FAKE_CLOUD, expires_at)})
        result = self.runner.invoke(cli, ["config", "-ls", "-j"])

        # select by name, not position: an ambient CLOUDINARY_URL adds an "(environment)" row first
        row = {r["name"]: r for r in json.loads(result.output)}["mycloud"]
        self.assertEqual(expires_at, row["expires_at"])  # consumers get the timestamp, not "expires in 8h"

    def test_show_surfaces_claim_url_and_expiry(self):
        expires_at = self._in_hours(8)
        self.write_config({"mycloud": self._cloud_url(FAKE_CLOUD, expires_at)})
        result = self.runner.invoke(cli, ["config", "-s", "mycloud"])

        self.assertEqual(0, result.exit_code)
        self.assertIn("claim_url", result.output)
        self.assertIn("https://console.cloudinary.com/x?token=ABC", result.output)
        self.assertIn(expires_at, result.output)  # ISO expiry not mangled by the OAuth epoch formatter

    def test_show_header_flags_the_cloud_and_its_deadline(self):
        self.write_config({"mycloud": self._cloud_url(FAKE_CLOUD, self._in_hours(8))})
        result = self.runner.invoke(cli, ["config", "-s", "mycloud"])

        self.assertIn("[unclaimed, expires in 8h]", result.output)  # not just "(api_key)"
        self.assertIn("Claimable Cloud: disabled at expiry", result.output)
        self.assertIn("cld agent cloud claim mycloud", result.output)

    def test_show_annotates_the_iso_expiry_with_a_countdown(self):
        expires_at = self._in_hours(8)
        self.write_config({"mycloud": self._cloud_url(FAKE_CLOUD, expires_at)})
        result = self.runner.invoke(cli, ["config", "-s", "mycloud"])

        self.assertIn(f"{expires_at} (expires in 8h)", result.output)

    def test_show_of_expired_cloud_does_not_advise_claiming(self):
        self.write_config({"dead": self._cloud_url("deadcloud", "2020-01-01T00:00:00Z")})
        result = self.runner.invoke(cli, ["config", "-s", "dead"])

        self.assertIn("past its expiry", result.output)
        self.assertIn("cld agent cloud create", result.output)  # make a new one instead
        self.assertNotIn("cld agent cloud claim", result.output)

    def test_show_of_ordinary_config_is_unchanged(self):
        self.write_config({"plain": "cloudinary://k:s@plaincloud"})
        result = self.runner.invoke(cli, ["config", "-s", "plain"])

        self.assertIn("name: plain (api_key)", result.output)
        self.assertNotIn("Claimable Cloud", result.output)
        self.assertNotIn("unclaimed", result.output)

    def test_show_json_marks_the_config_as_a_claimable_cloud(self):
        self.write_config({"mycloud": self._cloud_url(FAKE_CLOUD, self._in_hours(8))})
        result = self.runner.invoke(cli, ["config", "-s", "mycloud", "-j"])

        payload = json.loads(result.output)
        # a consumer should not have to infer the kind from the presence of claim_url,
        # nor parse a countdown string to learn whether it is still live
        self.assertIs(True, payload["claimable_cloud"])
        self.assertIs(False, payload["expired"])

    def test_show_json_marks_an_expired_cloud(self):
        self.write_config({"dead": self._cloud_url("deadcloud", "2020-01-01T00:00:00Z")})
        result = self.runner.invoke(cli, ["config", "-s", "dead", "-j"])

        self.assertIs(True, json.loads(result.output)["expired"])

    def test_show_json_reports_unknown_expiry_as_null_not_false(self):
        self.write_config({"noexp": "cloudinary://k:s@noexp?claim_url=https%3A%2F%2Fc.io%2Fx%3Ftoken%3DD"})
        result = self.runner.invoke(cli, ["config", "-s", "noexp", "-j"])

        payload = json.loads(result.output)
        self.assertIs(True, payload["claimable_cloud"])
        self.assertIsNone(payload["expired"])  # unknown stays distinct from "still valid"

    def test_show_json_of_ordinary_config_omits_cloud_fields(self):
        self.write_config({"plain": "cloudinary://k:s@plaincloud"})
        result = self.runner.invoke(cli, ["config", "-s", "plain", "-j"])

        payload = json.loads(result.output)
        self.assertNotIn("claimable_cloud", payload)
        self.assertNotIn("expired", payload)

    def test_listing_json_carries_the_same_cloud_fields(self):
        self.write_config({"mycloud": self._cloud_url(FAKE_CLOUD, self._in_hours(8)),
                           "plain": "cloudinary://k:s@plaincloud"})
        result = self.runner.invoke(cli, ["config", "-ls", "-j"])

        rows = {row["name"]: row for row in json.loads(result.output)}
        self.assertIs(True, rows["mycloud"]["claimable_cloud"])
        self.assertIs(False, rows["mycloud"]["expired"])
        self.assertNotIn("claimable_cloud", rows["plain"])

    def test_show_json_keeps_the_raw_expiry(self):
        expires_at = self._in_hours(8)
        self.write_config({"mycloud": self._cloud_url(FAKE_CLOUD, expires_at)})
        result = self.runner.invoke(cli, ["config", "-s", "mycloud", "-j"])

        # the countdown is a display concern; JSON consumers get the timestamp alone
        self.assertEqual(expires_at, json.loads(result.output)["expires_at"])


class TestCloudExpiryStatus(unittest.TestCase):
    """The Claimable Cloud label layered over the generic countdown."""

    def _in(self, **delta):
        from datetime import datetime, timedelta, timezone
        from cloudinary_cli.utils.config_utils import cloud_expiry_status
        return cloud_expiry_status((datetime.now(timezone.utc) + timedelta(**delta)).strftime("%Y-%m-%dT%H:%M:%SZ"))

    def test_fresh_cloud_reads_in_hours_not_days(self):
        self.assertEqual("unclaimed, expires in 24h", self._in(hours=24))

    def test_past_expiry(self):
        self.assertEqual("unclaimed, expired", self._in(hours=-1))

    def test_always_leads_with_unclaimed(self):
        # the state the user must act on, not just a countdown that reads like a refreshable token
        self.assertTrue(self._in(hours=8).startswith("unclaimed"))

    def test_unreadable_expiry_still_reports_unclaimed(self):
        from cloudinary_cli.utils.config_utils import cloud_expiry_status
        self.assertEqual("unclaimed", cloud_expiry_status(None))
        self.assertEqual("unclaimed", cloud_expiry_status("not-a-date"))


class TestClaimUrlRoundTrip(unittest.TestCase):
    def test_realistic_claim_url_survives_write_then_read(self):
        from cloudinary_cli.core.agent import _cloud_params, _config_url_from_environment

        url = _config_url_from_environment(CLOUD_RESPONSE, params=_cloud_params(CLOUD_RESPONSE))

        validate_config_url(url)
        self.assertEqual(CLOUD_RESPONSE["claim_url"], claim_url_from_url(url))
        self.assertEqual(CLOUD_RESPONSE["expires_at"], expires_at_from_url(url))

    def test_saved_url_parses_cleanly_as_an_sdk_config(self):
        import cloudinary
        from cloudinary_cli.core.agent import _cloud_params, _config_url_from_environment

        url = _config_url_from_environment(CLOUD_RESPONSE, params=_cloud_params(CLOUD_RESPONSE))
        config = cloudinary.Config()
        config._setup_from_parsed_url(config._parse_cloudinary_url(url))

        self.assertEqual(FAKE_CLOUD, config.cloud_name)
        self.assertEqual(FAKE_API_KEY, config.api_key)
        self.assertEqual(FAKE_API_SECRET, config.api_secret)


if __name__ == "__main__":
    unittest.main()
