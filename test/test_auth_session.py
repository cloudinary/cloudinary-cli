import time
import unittest
from unittest import mock
from unittest.mock import patch

import cloudinary

from cloudinary_cli.auth import (
    login,
    refresh_url_if_stale,
    refresh_config,
    refresh_configs,
    _derive_config_name,
)
from cloudinary_cli.auth.session import (
    Session,
    to_cloudinary_url,
    from_cloudinary_url,
    is_oauth_url,
    strip_oauth_internal_keys,
)


def _session(**overrides):
    base = dict(cloud_name="eu-cloud", access_token="eyJ.aaa.bbb", refresh_token="rt_123",
                expires_at=int(time.time()) + 300, region="api-eu",
                issuer="https://oauth.cloudinary.com/")
    base.update(overrides)
    return Session(**base)


class TestSessionCodec(unittest.TestCase):
    def test_round_trip(self):
        s = _session()
        parsed = from_cloudinary_url(to_cloudinary_url(s))
        self.assertEqual(s.cloud_name, parsed.cloud_name)
        self.assertEqual(s.access_token, parsed.access_token)
        self.assertEqual(s.refresh_token, parsed.refresh_token)
        self.assertEqual(s.region, parsed.region)
        self.assertEqual(s.issuer, parsed.issuer)
        self.assertEqual(s.expires_at, parsed.expires_at)
        self.assertIsInstance(parsed.expires_at, int)

    def test_parses_through_sdk_as_bearer(self):
        url = to_cloudinary_url(_session())
        config = cloudinary.Config()
        config._setup_from_parsed_url(config._parse_cloudinary_url(url))
        self.assertEqual("eu-cloud", config.cloud_name)
        self.assertEqual("eyJ.aaa.bbb", config.oauth_token)
        self.assertIsNone(config.api_key)
        self.assertIsNone(config.api_secret)
        self.assertEqual("https://api-eu.cloudinary.com", config.upload_prefix)

    def test_is_oauth_url(self):
        self.assertTrue(is_oauth_url(to_cloudinary_url(_session())))
        self.assertFalse(is_oauth_url("cloudinary://key:secret@cloud"))
        self.assertFalse(is_oauth_url(None))
        # substring 'oauth_token' outside the query key must not match
        self.assertFalse(is_oauth_url("cloudinary://key:secret@oauth_token.example.com"))
        self.assertFalse(is_oauth_url("cloudinary://key:secret@cloud?cname=oauth_token.io"))

    def test_is_fresh(self):
        self.assertTrue(_session().is_fresh())
        self.assertFalse(_session(expires_at=int(time.time()) - 10).is_fresh())

    def test_missing_expires_in_falls_back_to_fresh(self):
        s = Session.from_token_response({"access_token": "eyJ.aaa.bbb"}, cloud_name="c")
        self.assertGreater(s.expires_at, int(time.time()))
        self.assertTrue(s.is_fresh())

    def test_zero_expires_in_falls_back_to_fresh(self):
        s = Session.from_token_response(
            {"access_token": "eyJ.aaa.bbb", "expires_in": 0}, cloud_name="c")
        self.assertTrue(s.is_fresh())


class TestStripOAuthInternalKeys(unittest.TestCase):
    def test_drops_bookkeeping_keeps_auth_and_host(self):
        url = to_cloudinary_url(_session())
        config = cloudinary.Config()
        config._setup_from_parsed_url(config._parse_cloudinary_url(url))
        full = {k: v for k, v in config.__dict__.items() if not k.startswith("_")}
        self.assertEqual({"refresh_token", "expires_at", "region", "issuer"}, full.keys() &
                         {"refresh_token", "expires_at", "region", "issuer"})

        sanitized = strip_oauth_internal_keys(full)
        for leaked in ("refresh_token", "expires_at", "region", "issuer"):
            self.assertNotIn(leaked, sanitized)
        self.assertEqual("eyJ.aaa.bbb", sanitized["oauth_token"])
        self.assertEqual("https://api-eu.cloudinary.com", sanitized["upload_prefix"])
        self.assertEqual("eu-cloud", sanitized["cloud_name"])

    def test_noop_on_api_key_config(self):
        full = {"cloud_name": "c", "api_key": "k", "api_secret": "s"}
        self.assertEqual(full, strip_oauth_internal_keys(full))


class TestRefreshUrlIfStale(unittest.TestCase):
    def test_non_oauth_passthrough(self):
        url = "cloudinary://key:secret@cloud"
        self.assertEqual(url, refresh_url_if_stale("c", url))

    def test_fresh_unchanged(self):
        url = to_cloudinary_url(_session())
        with patch("cloudinary_cli.auth.flow.refresh") as refresh:
            self.assertEqual(url, refresh_url_if_stale("eu-cloud", url))
            refresh.assert_not_called()

    def test_force_refreshes_fresh_token(self):
        url = to_cloudinary_url(_session())  # fresh
        token_response = {"access_token": "eyJ.new.tok", "refresh_token": "rt_new", "expires_in": 300}
        with patch("cloudinary_cli.auth.load_config", return_value={"eu-cloud": url}), \
                patch("cloudinary_cli.auth.flow.refresh", return_value=token_response) as refresh, \
                patch("cloudinary_cli.auth.update_config"):
            new_url = refresh_url_if_stale("eu-cloud", url, force=True)
        refresh.assert_called_once()
        self.assertIn("oauth_token=eyJ.new.tok", new_url)

    def test_stale_refreshes_and_rewrites(self):
        stale_url = to_cloudinary_url(_session(expires_at=int(time.time()) - 10))
        token_response = {"access_token": "eyJ.new.tok", "refresh_token": "rt_new", "expires_in": 300}
        with patch("cloudinary_cli.auth.load_config", return_value={"eu-cloud": stale_url}), \
                patch("cloudinary_cli.auth.flow.refresh", return_value=token_response), \
                patch("cloudinary_cli.auth.update_config") as update_config:
            new_url = refresh_url_if_stale("eu-cloud", stale_url)
        self.assertIn("oauth_token=eyJ.new.tok", new_url)
        self.assertIn("refresh_token=rt_new", new_url)
        update_config.assert_called_once()

    def test_no_refresh_token_returns_unchanged(self):
        url = to_cloudinary_url(_session(expires_at=int(time.time()) - 10, refresh_token=None))
        self.assertEqual(url, refresh_url_if_stale("eu-cloud", url))

    def test_refresh_timeout_returns_stale_url(self):
        import requests
        stale_url = to_cloudinary_url(_session(expires_at=int(time.time()) - 10))
        with patch("cloudinary_cli.auth.load_config", return_value={"eu-cloud": stale_url}), \
                patch("cloudinary_cli.auth.flow.refresh", side_effect=requests.Timeout()), \
                patch("cloudinary_cli.auth.update_config") as update_config:
            self.assertEqual(stale_url, refresh_url_if_stale("eu-cloud", stale_url))
            update_config.assert_not_called()

    def test_refresh_failure_warns_once_per_config(self):
        # A3a: a failed background refresh must surface a re-login hint (not just a debug line), but
        # only once per config so a bulk run does not log it per asset.
        import requests
        import cloudinary_cli.auth as auth
        auth._refresh_warned.discard("eu-cloud")
        self.addCleanup(auth._refresh_warned.discard, "eu-cloud")
        stale_url = to_cloudinary_url(_session(expires_at=int(time.time()) - 10))
        with patch("cloudinary_cli.auth.load_config", return_value={"eu-cloud": stale_url}), \
                patch("cloudinary_cli.auth.flow.refresh", side_effect=requests.ConnectionError()), \
                patch("cloudinary_cli.auth.update_config"), \
                patch("cloudinary_cli.auth.logger.warning") as warn:
            refresh_url_if_stale("eu-cloud", stale_url)
            refresh_url_if_stale("eu-cloud", stale_url)  # second stale read in the same run
        warn.assert_called_once()
        self.assertIn("cld login eu-cloud", warn.call_args[0][0])

    def test_refresh_success_rearms_the_warning(self):
        # After a successful refresh the warning is re-armed, so a later failure warns again.
        import cloudinary_cli.auth as auth
        auth._refresh_warned.add("eu-cloud")
        self.addCleanup(auth._refresh_warned.discard, "eu-cloud")
        stale_url = to_cloudinary_url(_session(expires_at=int(time.time()) - 10))
        token_response = {"access_token": "eyJ.new.tok", "refresh_token": "rt_new", "expires_in": 300}
        with patch("cloudinary_cli.auth.load_config", return_value={"eu-cloud": stale_url}), \
                patch("cloudinary_cli.auth.flow.refresh", return_value=token_response), \
                patch("cloudinary_cli.auth.update_config"):
            refresh_url_if_stale("eu-cloud", stale_url)
        self.assertNotIn("eu-cloud", auth._refresh_warned)

    def test_adopts_peer_refresh_without_calling_refresh(self):
        # Peer already rewrote the saved URL to a fresh token while we waited for the lock.
        stale_url = to_cloudinary_url(_session(expires_at=int(time.time()) - 10))
        peer_fresh_url = to_cloudinary_url(_session(
            access_token="eyJ.peer.tok", expires_at=int(time.time()) + 300))
        with patch("cloudinary_cli.auth.load_config", return_value={"eu-cloud": peer_fresh_url}), \
                patch("cloudinary_cli.auth.flow.refresh") as refresh, \
                patch("cloudinary_cli.auth.update_config") as update_config:
            result = refresh_url_if_stale("eu-cloud", stale_url)
        self.assertEqual(peer_fresh_url, result)
        refresh.assert_not_called()      # we did not burn the (already-rotated) refresh token
        update_config.assert_not_called()

    def test_refreshes_when_peer_value_still_stale(self):
        stale_url = to_cloudinary_url(_session(expires_at=int(time.time()) - 10))
        token_response = {"access_token": "eyJ.new.tok", "refresh_token": "rt_new", "expires_in": 300}
        with patch("cloudinary_cli.auth.load_config", return_value={"eu-cloud": stale_url}), \
                patch("cloudinary_cli.auth.flow.refresh", return_value=token_response) as refresh, \
                patch("cloudinary_cli.auth.update_config") as update_config:
            result = refresh_url_if_stale("eu-cloud", stale_url)
        self.assertIn("oauth_token=eyJ.new.tok", result)
        refresh.assert_called_once()
        update_config.assert_called_once()


class TestRefreshConfig(unittest.TestCase):
    def _cfg(self, **extra):
        cfg = {
            "stale": to_cloudinary_url(_session(cloud_name="stale", expires_at=int(time.time()) - 10)),
            "fresh": to_cloudinary_url(_session(cloud_name="fresh")),
            "key": "cloudinary://k:s@kc",
        }
        cfg.update(extra)
        return cfg

    def test_not_found(self):
        with patch("cloudinary_cli.auth.load_config", return_value=self._cfg()):
            self.assertEqual("not_found", refresh_config("ghost"))

    def test_not_oauth(self):
        with patch("cloudinary_cli.auth.load_config", return_value=self._cfg()):
            self.assertEqual("not_oauth", refresh_config("key"))

    def test_fresh_skipped(self):
        with patch("cloudinary_cli.auth.load_config", return_value=self._cfg()), \
                patch("cloudinary_cli.auth.flow.refresh") as refresh:
            self.assertEqual("fresh", refresh_config("fresh"))
            refresh.assert_not_called()

    def test_stale_refreshed(self):
        token_response = {"access_token": "new", "refresh_token": "rt_new", "expires_in": 300}
        with patch("cloudinary_cli.auth.load_config", return_value=self._cfg()), \
                patch("cloudinary_cli.auth.flow.refresh", return_value=token_response), \
                patch("cloudinary_cli.auth.update_config"):
            self.assertEqual("refreshed", refresh_config("stale"))

    def test_force_refreshes_fresh(self):
        token_response = {"access_token": "new", "refresh_token": "rt_new", "expires_in": 300}
        with patch("cloudinary_cli.auth.load_config", return_value=self._cfg()), \
                patch("cloudinary_cli.auth.flow.refresh", return_value=token_response) as refresh, \
                patch("cloudinary_cli.auth.update_config"):
            self.assertEqual("refreshed", refresh_config("fresh", force=True))
            refresh.assert_called_once()

    def test_failed_when_no_refresh_token(self):
        cfg = self._cfg(stale=to_cloudinary_url(_session(
            cloud_name="stale", expires_at=int(time.time()) - 10, refresh_token=None)))
        with patch("cloudinary_cli.auth.load_config", return_value=cfg):
            self.assertEqual("failed", refresh_config("stale"))

    def test_relogin_command_includes_non_default_region(self):
        from cloudinary_cli.auth import relogin_command
        cfg = {
            "global": to_cloudinary_url(_session(cloud_name="global", region="api")),
            "stg": to_cloudinary_url(_session(cloud_name="stg", region="api-staging")),
            "key": "cloudinary://k:s@kc",
        }
        with patch("cloudinary_cli.auth.load_config", return_value=cfg):
            self.assertEqual("cld login global", relogin_command("global"))
            self.assertEqual("cld login stg --region api-staging", relogin_command("stg"))
            self.assertEqual("cld login key", relogin_command("key"))  # non-oauth: no region

    def test_refresh_configs_sweeps_oauth_only(self):
        token_response = {"access_token": "new", "refresh_token": "rt_new", "expires_in": 300}
        with patch("cloudinary_cli.auth.load_config", return_value=self._cfg()), \
                patch("cloudinary_cli.auth.flow.refresh", return_value=token_response), \
                patch("cloudinary_cli.auth.update_config"):
            results = refresh_configs()
        self.assertEqual({"stale": "refreshed", "fresh": "fresh"}, results)  # "key" not swept


class TestLoginGuards(unittest.TestCase):
    def test_missing_cloud_name_raises_and_saves_nothing(self):
        session = _session(cloud_name=None)
        with patch("cloudinary_cli.auth._run_browser_flow", return_value=session), \
                patch("cloudinary_cli.auth.update_config") as update_config:
            with self.assertRaises(RuntimeError):
                login(region="api-eu")
            update_config.assert_not_called()


class TestBrowserFlowNonInteractive(unittest.TestCase):
    """No browser + no TTY: _run_browser_flow must fail fast with a headless-usage hint, never block
    in wait_for_callback until the callback times out."""

    def test_no_browser_no_tty_fails_fast_without_waiting(self):
        from cloudinary_cli.auth import _run_browser_flow
        fake_httpd = mock.Mock()
        with patch("cloudinary_cli.auth.start_callback_server",
                   return_value=(fake_httpd, "http://127.0.0.1:49421/callback")), \
                patch("cloudinary_cli.auth.webbrowser.open", return_value=False), \
                patch("cloudinary_cli.auth.is_interactive", return_value=False), \
                patch("cloudinary_cli.auth.wait_for_callback") as wait:
            with self.assertRaises(RuntimeError) as ctx:
                _run_browser_flow("api-eu")
        wait.assert_not_called()                 # fails fast: no 5-minute callback wait
        fake_httpd.server_close.assert_called_once()  # releases the bound port
        self.assertIn("-c", str(ctx.exception))  # points at the headless API-key alternative

    def test_no_browser_but_tty_still_waits(self):
        # A human at a TTY can paste the printed URL, so we must NOT fail fast here.
        from cloudinary_cli.auth import _run_browser_flow
        with patch("cloudinary_cli.auth.start_callback_server",
                   return_value=(mock.Mock(), "http://127.0.0.1:49421/callback")), \
                patch("cloudinary_cli.auth.webbrowser.open", return_value=False), \
                patch("cloudinary_cli.auth.is_interactive", return_value=True), \
                patch("cloudinary_cli.auth.wait_for_callback", return_value=("code", "st")) as wait, \
                patch("cloudinary_cli.auth.flow.exchange_code", return_value={"access_token": "x"}):
            # state mismatch is irrelevant here; we only assert it reached the wait (did not fast-fail)
            with patch("cloudinary_cli.auth.secrets.token_urlsafe", return_value="st"):
                _run_browser_flow("api-eu")
        wait.assert_called_once()


class TestDeriveConfigName(unittest.TestCase):
    def _derive(self, cloud, region, config):
        with patch("cloudinary_cli.auth.load_config", return_value=config):
            return _derive_config_name(cloud, region)

    def test_default_region_bare(self):
        self.assertEqual("my_cloud", self._derive("my_cloud", "api", {}))

    def test_region_suffix(self):
        self.assertEqual("my_cloud-eu", self._derive("my_cloud", "api-eu", {}))

    def test_relogin_overwrites_same_type(self):
        existing = {"my_cloud-eu": "cloudinary://my_cloud-eu?oauth_token=x"}
        self.assertEqual("my_cloud-eu", self._derive("my_cloud", "api-eu", existing))

    def test_cross_type_collision_gets_oauth_suffix(self):
        existing = {"my_cloud": "cloudinary://key:secret@my_cloud"}
        self.assertEqual("my_cloud-oauth", self._derive("my_cloud", "api", existing))

    def test_cross_type_collision_with_region(self):
        existing = {"my_cloud-eu": "cloudinary://key:secret@my_cloud"}
        self.assertEqual("my_cloud-eu-oauth", self._derive("my_cloud", "api-eu", existing))
