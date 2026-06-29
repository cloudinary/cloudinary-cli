"""In-process single-flight refresh and 401 retry/adopt behavior for the OAuth token seam."""
import threading
import time
import unittest
from unittest.mock import patch, MagicMock

import cloudinary
from cloudinary.exceptions import AuthorizationRequired

from cloudinary_cli.auth.oauth_config import OAuthConfig, install_oauth_config, install_env_config
from cloudinary_cli.auth.session import Session, to_cloudinary_url, from_cloudinary_url
from cloudinary_cli.utils.api_utils import call_api

from test.oauth_helpers import jwt_access_token


def _url(cloud="eu-cloud", token="eyJ.tok", refresh="rt", region="api-eu", expires_delta=300):
    return to_cloudinary_url(Session(
        cloud_name=cloud, access_token=token, refresh_token=refresh,
        expires_at=int(time.time()) + expires_delta, region=region,
        issuer="https://oauth.cloudinary.com/"))


class _RestoresSdkConfig(unittest.TestCase):
    def setUp(self):
        import os
        self._env_snapshot = dict(os.environ)
        for key in [k for k in os.environ if k.startswith("CLOUDINARY_")]:
            del os.environ[key]
        cloudinary.reset_config()
        self.addCleanup(self._restore)

    def _restore(self):
        import os
        os.environ.clear()
        os.environ.update(self._env_snapshot)
        cloudinary.reset_config()


class TestSingleFlightRefresh(_RestoresSdkConfig):
    """Concurrent stale reads refresh once under the in-process lock; losers adopt the result."""

    def test_concurrent_stale_reads_refresh_once(self):
        saved = {"eu-cloud": _url(token="eyJ.old", refresh="rt_old", expires_delta=-10)}
        new_token = jwt_access_token(cloud_name="eu-cloud", tag="single-flight-new")
        token_response = {"access_token": new_token, "refresh_token": "rt_new", "expires_in": 300}

        def slow_refresh(refresh_token, region):
            time.sleep(0.02)  # widen the window so threads pile on the lock
            return dict(token_response)

        with patch("cloudinary_cli.utils.config_utils.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.auth.refresh.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.auth.flow.refresh", side_effect=slow_refresh) as refresh, \
                patch("cloudinary_cli.auth.refresh.update_config"):
            install_oauth_config(saved["eu-cloud"], saved_name="eu-cloud")
            config = cloudinary.config()

            results = []

            def read_token():
                results.append(config.oauth_token)

            threads = [threading.Thread(target=read_token) for _ in range(20)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        refresh.assert_called_once()  # one rotation, not 20
        self.assertEqual([new_token] * 20, results)


class TestRetryOn401(_RestoresSdkConfig):
    """call_api marks the token invalid on AuthorizationRequired and retries via the refresh seam."""

    def test_retries_after_peer_rotation_and_succeeds(self):
        # Config holds the rejected token but a peer wrote a new one: retry adopts it, no rotation.
        install_oauth_config(_url(token="eyJ.old", refresh="rt_old", expires_delta=300),
                             saved_name="eu-cloud")
        saved = {"eu-cloud": _url(token="eyJ.new", refresh="rt_new", expires_delta=300)}
        calls = {"n": 0}

        def func(*a, **k):
            calls["n"] += 1
            if calls["n"] == 1:
                raise AuthorizationRequired("Invalid token [expired]")
            return {"public_id": "ok"}

        with patch("cloudinary_cli.utils.config_utils.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.auth.refresh.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.auth.flow.refresh") as refresh, \
                patch("cloudinary_cli.auth.refresh.update_config"):
            result = call_api(func, "file.mp4")

        self.assertEqual({"public_id": "ok"}, result)
        self.assertEqual(2, calls["n"])               # original + one retry
        refresh.assert_not_called()                   # adopted peer's token, no rotation
        self.assertEqual("eyJ.new", cloudinary.config().oauth_token)

    def test_401_on_clock_fresh_token_forces_one_refresh_then_succeeds(self):
        # No peer rotated: the rejected token is still clock-fresh on disk, so the retry forces one rotation.
        install_oauth_config(_url(token="eyJ.old", refresh="rt_old", expires_delta=300),
                             saved_name="eu-cloud")
        saved = {"eu-cloud": _url(token="eyJ.old", refresh="rt_old", expires_delta=300)}
        new_token = jwt_access_token(cloud_name="eu-cloud", tag="clock-fresh-new")
        calls = {"n": 0}

        def func(*a, **k):
            calls["n"] += 1
            if calls["n"] == 1:
                raise AuthorizationRequired("Invalid token [expired]")
            return {"public_id": "ok"}

        with patch("cloudinary_cli.utils.config_utils.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.auth.refresh.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.auth.flow.refresh",
                      return_value={"access_token": new_token, "refresh_token": "rt_new",
                                    "expires_in": 300}) as refresh, \
                patch("cloudinary_cli.auth.refresh.update_config"):
            result = call_api(func, "file.mp4")

        self.assertEqual({"public_id": "ok"}, result)
        self.assertEqual(2, calls["n"])
        refresh.assert_called_once()                  # forced past the clock by the 401
        self.assertEqual(new_token, cloudinary.config().oauth_token)

    def test_revoked_token_fails_fast(self):
        # flow.refresh fails too: no new token to adopt, so propagate after the first attempt.
        import requests
        install_oauth_config(_url(token="eyJ.old", refresh="rt_old", expires_delta=300),
                             saved_name="eu-cloud")
        saved = {"eu-cloud": _url(token="eyJ.old", refresh="rt_old", expires_delta=300)}
        calls = {"n": 0}

        def func(*a, **k):
            calls["n"] += 1
            raise AuthorizationRequired("Invalid token [expired]")

        with patch("cloudinary_cli.utils.config_utils.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.auth.refresh.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.auth.flow.refresh",
                      side_effect=requests.RequestException("refresh token revoked")), \
                patch("cloudinary_cli.auth.refresh.update_config"):
            with self.assertRaises(AuthorizationRequired):
                call_api(func, "file.mp4")

        self.assertEqual(1, calls["n"])  # nothing to adopt -> fail fast

    def test_one_refresh_and_retry_then_propagates(self):
        # Refresh succeeds (new token) but the server rejects it too: one retry, then propagate.
        install_oauth_config(_url(token="eyJ.t0", refresh="rt0", expires_delta=300),
                             saved_name="eu-cloud")
        saved = {"eu-cloud": _url(token="eyJ.t0", refresh="rt0", expires_delta=300)}
        calls = {"n": 0}

        def func(*a, **k):
            calls["n"] += 1
            raise AuthorizationRequired("Invalid token [expired]")

        def ever_new_token(refresh_token, region):
            return {"access_token": jwt_access_token(cloud_name="eu-cloud", tag=f"t{calls['n']}"),
                    "refresh_token": f"rt{calls['n']}", "expires_in": 300}

        with patch("cloudinary_cli.utils.config_utils.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.auth.refresh.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.auth.flow.refresh", side_effect=ever_new_token), \
                patch("cloudinary_cli.auth.refresh.update_config"):
            with self.assertRaises(AuthorizationRequired):
                call_api(func, "file.mp4")

        self.assertEqual(2, calls["n"])  # original + one retry, no unbounded rotation

    def test_non_oauth_config_propagates_immediately(self):
        install_oauth_config("cloudinary://key:secret@cloud", saved_name=None)  # api-key: has_oauth False
        calls = {"n": 0}

        def func(*a, **k):
            calls["n"] += 1
            raise AuthorizationRequired("nope")

        with self.assertRaises(AuthorizationRequired):
            call_api(func, "x")
        self.assertEqual(1, calls["n"])  # no adopt attempt on a non-OAuth config

    def test_env_config_propagates_immediately(self):
        import os
        os.environ["CLOUDINARY_URL"] = (
            "cloudinary://env_cloud?oauth_token=eyJ.env&refresh_token=rt&"
            f"expires_at={int(time.time()) - 10}&region=api")
        cloudinary.reset_config()
        install_env_config()  # static: _saved_name is None -> invalidate_token returns False
        calls = {"n": 0}

        def func(*a, **k):
            calls["n"] += 1
            raise AuthorizationRequired("expired")

        with self.assertRaises(AuthorizationRequired):
            call_api(func, "x")
        self.assertEqual(1, calls["n"])

    def test_success_passes_through_without_refresh(self):
        install_oauth_config(_url(), saved_name="eu-cloud")
        sentinel = MagicMock(return_value={"public_id": "p"})
        result = call_api(sentinel, "file", folder="f")
        self.assertEqual({"public_id": "p"}, result)
        # no retry; args forwarded verbatim with the active token pinned so the wire token == rejected
        sentinel.assert_called_once_with("file", folder="f", oauth_token="eyJ.tok")

    def test_token_pinned_so_wire_token_equals_invalidate_arg(self):
        # The token sent to the SDK and the token handed to invalidate_token must be identical, even if
        # a peer rotates the config between our read and the SDK's own read. Pinning closes that gap.
        config = install_oauth_config(_url(token="eyJ.pin", refresh="rt", expires_delta=300),
                                      saved_name="eu-cloud")
        sent = {}

        def func(*a, **k):
            sent["oauth_token"] = k.get("oauth_token")
            raise AuthorizationRequired("Invalid token [expired]")

        seen = {}

        def spy(rejected):
            seen["rejected"] = rejected
            return False  # stop after one attempt; we only care about the pinned value

        with patch.object(config, "invalidate_token", side_effect=spy):
            with self.assertRaises(AuthorizationRequired):
                call_api(func, "file.mp4")

        self.assertEqual("eyJ.pin", sent["oauth_token"])          # the value the SDK would send
        self.assertEqual(sent["oauth_token"], seen["rejected"])   # == what invalidate_token is told


class TestRefreshDecision(_RestoresSdkConfig):
    """refresh_url_if_stale's rotate-vs-adopt rule for `force`, `expected`, and the proactive sweep."""

    def _refresh(self, **kwargs):
        from cloudinary_cli.auth import refresh_url_if_stale
        return refresh_url_if_stale("eu-cloud", self.url, **kwargs)

    def test_expected_matches_disk_rotates_even_when_clock_fresh(self):
        # 401 path: token clock-fresh but rejected; disk still holds it -> rotate once.
        self.url = _url(token="eyJ.cur", refresh="rt", expires_delta=300)
        saved = {"eu-cloud": self.url}
        new_token = jwt_access_token(cloud_name="eu-cloud", tag="expected-matches-new")
        with patch("cloudinary_cli.auth.refresh.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.auth.flow.refresh",
                      return_value={"access_token": new_token, "refresh_token": "rt2",
                                    "expires_in": 300}) as refresh, \
                patch("cloudinary_cli.auth.refresh.update_config"):
            new_url = self._refresh(expected="eyJ.cur")
        refresh.assert_called_once()
        self.assertEqual(new_token, from_cloudinary_url(new_url).access_token)

    def test_expected_differs_from_disk_adopts_without_refresh(self):
        # Peer already rotated: disk token != expected -> adopt, no network.
        self.url = _url(token="eyJ.new", refresh="rt2", expires_delta=300)  # what disk now holds
        saved = {"eu-cloud": self.url}
        with patch("cloudinary_cli.auth.refresh.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.auth.flow.refresh") as refresh, \
                patch("cloudinary_cli.auth.refresh.update_config"):
            new_url = self._refresh(expected="eyJ.old")  # we were sent the OLD token
        refresh.assert_not_called()
        self.assertEqual(self.url, new_url)

    def test_force_refreshes_a_clock_fresh_token_user_path(self):
        # `config --refresh --force`: rotate even a perfectly fresh token.
        self.url = _url(token="eyJ.cur", refresh="rt", expires_delta=300)
        saved = {"eu-cloud": self.url}
        forced_token = jwt_access_token(cloud_name="eu-cloud", tag="forced-new")
        with patch("cloudinary_cli.auth.refresh.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.auth.flow.refresh",
                      return_value={"access_token": forced_token, "refresh_token": "rt2",
                                    "expires_in": 300}) as refresh, \
                patch("cloudinary_cli.auth.refresh.update_config"):
            new_url = self._refresh(force=True)
        refresh.assert_called_once()
        self.assertEqual(forced_token, from_cloudinary_url(new_url).access_token)

    def test_no_expected_no_force_uses_clock_freshness(self):
        # The proactive sweep with no specific token: a fresh token is left untouched.
        self.url = _url(token="eyJ.cur", refresh="rt", expires_delta=300)
        saved = {"eu-cloud": self.url}
        with patch("cloudinary_cli.auth.refresh.load_config", return_value=dict(saved)), \
                patch("cloudinary_cli.auth.flow.refresh") as refresh, \
                patch("cloudinary_cli.auth.refresh.update_config"):
            new_url = self._refresh()
        refresh.assert_not_called()
        self.assertEqual(self.url, new_url)


if __name__ == "__main__":
    unittest.main()
