import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Each worker refreshes config under the cross-process lock; with the lock the read-modify-write
# is serialized, so disjoint keys from concurrent writers must all survive (no last-writer-wins).
_WORKER = """
import os, sys, time
sys.path.insert(0, {repo!r})
import cloudinary, cloudinary.api  # noqa
from cloudinary_cli.utils.config_utils import update_config
key = sys.argv[1]
update_config({{key: "cloudinary://k:s@" + key}})
"""


class TestConfigConcurrency(unittest.TestCase):
    def test_concurrent_writers_lose_no_keys(self):
        tmp = tempfile.mkdtemp()
        env = dict(os.environ, CLOUDINARY_HOME=tmp)
        worker = _WORKER.format(repo=REPO_ROOT)

        n = 12
        procs = [
            subprocess.Popen([sys.executable, "-c", worker, f"cloud{i}"],
                             env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            for i in range(n)
        ]
        for p in procs:
            _, err = p.communicate(timeout=60)
            self.assertEqual(0, p.returncode, err.decode())

        with open(os.path.join(tmp, "config.json")) as f:
            config = json.load(f)  # must be valid JSON (never half-written)

        for i in range(n):
            self.assertIn(f"cloud{i}", config)  # every concurrent write survived


if __name__ == "__main__":
    unittest.main()
