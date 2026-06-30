import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# save_config resolves CLOUDINARY_CLI_CONFIG_FILE from CLOUDINARY_HOME at import time, so the
# write must happen in a subprocess with CLOUDINARY_HOME pointed at a temp dir.
_WRITER = """
import sys
sys.path.insert(0, {repo!r})
import cloudinary, cloudinary.api  # noqa
from cloudinary_cli.utils.config_utils import save_config
save_config({{"cloud": "cloudinary://key:secret@cloud?oauth_token=tok&refresh_token=r"}})
"""


@unittest.skipIf(sys.platform == "win32", "POSIX file modes not applicable on Windows")
class TestConfigPermissions(unittest.TestCase):
    def test_saved_config_is_owner_only(self):
        tmp = tempfile.mkdtemp()
        env = dict(os.environ, CLOUDINARY_HOME=tmp)

        proc = subprocess.run(
            [sys.executable, "-c", _WRITER.format(repo=REPO_ROOT)],
            env=env, capture_output=True,
        )
        self.assertEqual(0, proc.returncode, proc.stderr.decode())

        config_file = os.path.join(tmp, "config.json")
        # The file holds api_secret + OAuth tokens, so it must not be group/world readable.
        mode = stat.S_IMODE(os.stat(config_file).st_mode)
        self.assertEqual(0o600, mode, f"expected 0600, got {oct(mode)}")

        # Sanity: it's still valid JSON carrying the secret-bearing value.
        with open(config_file) as f:
            self.assertIn("oauth_token", json.load(f)["cloud"])


if __name__ == "__main__":
    unittest.main()
