"""Cross-process OAuth refresh safety: N processes sharing one config.json rotate a single-use
refresh token at most once, mediated by the FileLock and adopt-on-disk check in refresh_url_if_stale.
Workers read oauth_token against a shared token server that counts refresh-token consumption."""
import json
import multiprocessing
import os
import tempfile
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from urllib.parse import parse_qs

from test.oauth_helpers import jwt_access_token


def _make_token(tag):
    # Pinned iat/exp so the same tag yields a byte-identical token for cross-process comparison.
    return jwt_access_token(cloud_name="proc-cloud", iat=1_700_000_000, exp=2_000_000_000, tag=tag)


class _RotatingTokenServer(BaseHTTPRequestHandler):
    """Stand-in auth server: each refresh consumes the presented (single-use) token and mints a new
    pair; an already-consumed token yields 400. State in class attrs (one server, one process)."""

    valid_refresh = None
    generation = 0
    refresh_calls = 0
    rejected_calls = 0

    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode()
        params = {k: v[0] for k, v in parse_qs(body).items()}
        cls = type(self)
        presented = params.get("refresh_token")
        cls.refresh_calls += 1
        if presented != cls.valid_refresh:
            cls.rejected_calls += 1
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error":"invalid_grant"}')
            return
        cls.generation += 1
        cls.valid_refresh = f"rt_gen{cls.generation}"
        resp = {
            "access_token": _make_token(f"gen{cls.generation}"),
            "refresh_token": cls.valid_refresh,
            "expires_in": 300,
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(resp).encode())


def _worker(home, token_url, barrier_path, idx, out):
    # Point the CLI at the shared config + fake token endpoint, wait at the barrier, then read oauth_token.
    os.environ["CLOUDINARY_HOME"] = home
    for k in list(os.environ):
        if k.startswith("CLOUDINARY_") and k != "CLOUDINARY_HOME":
            del os.environ[k]

    import cloudinary
    from cloudinary_cli.utils.config_utils import load_config
    from cloudinary_cli.auth.oauth_config import install_oauth_config
    import cloudinary_cli.auth.flow as flow_mod

    # flow.py imported the URL helper into its own namespace; redirect that binding to the fake server.
    flow_mod.oauth_token_url_for_region = lambda region: token_url

    url = load_config()["proc-cloud"]
    install_oauth_config(url, saved_name="proc-cloud")

    # cross-process barrier: drop a file, then spin until all are present
    open(os.path.join(barrier_path, f"ready-{idx}"), "w").close()
    deadline = time.time() + 10
    while len(os.listdir(barrier_path)) < out["n"] and time.time() < deadline:
        time.sleep(0.005)

    try:
        token = cloudinary.config().oauth_token
        out[idx] = token
    except Exception as e:  # noqa: BLE001
        out[idx] = f"ERROR:{e}"


def _worker_401(home, token_url, barrier_path, idx, out):
    # Like _worker, but starts clock-fresh and gets one 401: call_api's retry must converge on one rotation.
    os.environ["CLOUDINARY_HOME"] = home
    for k in list(os.environ):
        if k.startswith("CLOUDINARY_") and k != "CLOUDINARY_HOME":
            del os.environ[k]

    import cloudinary
    from cloudinary.exceptions import AuthorizationRequired
    from cloudinary_cli.utils.config_utils import load_config
    from cloudinary_cli.utils.api_utils import call_api
    from cloudinary_cli.auth.oauth_config import install_oauth_config
    import cloudinary_cli.auth.flow as flow_mod

    flow_mod.oauth_token_url_for_region = lambda region: token_url

    url = load_config()["proc-cloud"]
    install_oauth_config(url, saved_name="proc-cloud")

    open(os.path.join(barrier_path, f"ready-{idx}"), "w").close()
    deadline = time.time() + 10
    while len(os.listdir(barrier_path)) < out["n"] and time.time() < deadline:
        time.sleep(0.005)

    state = {"n": 0}

    def api_call(*a, **k):
        # Reject the original token once, accept any other.
        state["n"] += 1
        token = cloudinary.config().oauth_token
        if state["n"] == 1 and token == _make_token("gen0"):
            raise AuthorizationRequired("Invalid token [expired]")
        return {"ok": token}

    try:
        out[idx] = call_api(api_call, (), {})["ok"]
    except Exception as e:  # noqa: BLE001
        out[idx] = f"ERROR:{e}"


class TestCrossProcessSingleFlight(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cld-mp-home-")
        self.barrier = tempfile.mkdtemp(prefix="cld-mp-barrier-")
        _RotatingTokenServer.valid_refresh = "rt_gen0"
        _RotatingTokenServer.generation = 0
        _RotatingTokenServer.refresh_calls = 0
        _RotatingTokenServer.rejected_calls = 0
        self.server = HTTPServer(("127.0.0.1", 0), _RotatingTokenServer)
        self.port = self.server.server_address[1]
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        import shutil
        shutil.rmtree(self.home, ignore_errors=True)
        shutil.rmtree(self.barrier, ignore_errors=True)

    def _write_config(self, expires_delta):
        from cloudinary_cli.auth.session import Session, to_cloudinary_url
        os.makedirs(self.home, exist_ok=True)
        sess = Session(
            cloud_name="proc-cloud", access_token=_make_token("gen0"),
            refresh_token="rt_gen0", expires_at=int(time.time()) + expires_delta, region="api",
            issuer="https://oauth.cloudinary.com/")
        with open(os.path.join(self.home, "config.json"), "w") as f:
            json.dump({"proc-cloud": to_cloudinary_url(sess)}, f)

    def _write_stale_config(self):
        self._write_config(expires_delta=-10)

    def _run_workers(self, worker, n=6):
        if multiprocessing.get_start_method(allow_none=True) is None:
            multiprocessing.set_start_method("spawn", force=True)
        token_url = f"http://127.0.0.1:{self.port}/oauth2/token"
        mgr = multiprocessing.Manager()
        out = mgr.dict()
        out["n"] = n
        procs = [multiprocessing.Process(target=worker,
                                         args=(self.home, token_url, self.barrier, i, out))
                 for i in range(n)]
        for p in procs:
            p.start()
        for p in procs:
            p.join(30)
        results = {i: out[i] for i in range(n)}
        errors = {i: v for i, v in results.items() if isinstance(v, str) and v.startswith("ERROR")}
        self.assertEqual({}, errors, f"workers errored: {errors}")
        return results

    def test_n_processes_consume_single_use_refresh_token_once(self):
        # Proactive path: all processes start on the same stale token and read oauth_token together.
        self._write_stale_config()
        results = self._run_workers(_worker)

        self.assertEqual(0, _RotatingTokenServer.rejected_calls,
                         "a process presented an already-consumed refresh token (rotation cascade)")
        self.assertEqual(1, _RotatingTokenServer.generation,
                         "the single-use refresh token rotated more than once across processes")
        distinct = set(results.values())
        self.assertEqual(1, len(distinct), f"workers disagreed on the token: {distinct}")
        self.assertEqual(_make_token("gen1"), next(iter(distinct)))

    def test_n_processes_recover_from_401_with_single_rotation(self):
        # Reactive path: all processes start clock-fresh, each gets one 401; retry converges on one rotation.
        self._write_config(expires_delta=300)
        results = self._run_workers(_worker_401)

        self.assertEqual(0, _RotatingTokenServer.rejected_calls,
                         "a process presented an already-consumed refresh token (rotation cascade)")
        self.assertEqual(1, _RotatingTokenServer.generation,
                         "a 401 on a clock-fresh token rotated more than once across processes")
        distinct = set(results.values())
        self.assertEqual({_make_token("gen1")}, distinct,
                         f"workers did not all recover onto the rotated token: {distinct}")


if __name__ == "__main__":
    unittest.main()
