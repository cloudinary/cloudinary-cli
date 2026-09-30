import json
import os
import subprocess
import sys
import tempfile
import unittest

from click.testing import CliRunner

from cloudinary_cli.cli import cli


class TestCLI(unittest.TestCase):
    runner = CliRunner()

    COMMANDS = [
        'admin',
        'agent',
        'config',
        'login',
        'logout',
        'make',
        'migrate',
        'provisioning',
        'search',
        'sync',
        'upload_dir',
        'uploader',
        'url',
        'utils',
    ]

    def test_cli(self):
        result = self.runner.invoke(cli)

        self.assertEqual(0, result.exit_code)
        self.assertIn('Usage:', result.output)

        for command in self.COMMANDS:
            self.assertIn(command, result.output)

    def test_cli_help(self):
        result = self.runner.invoke(cli, ['--help'])

        self.assertEqual(0, result.exit_code)
        self.assertIn('Usage:', result.output)

    def test_cli_version(self):
        result = self.runner.invoke(cli, ['--version'])

        self.assertEqual(0, result.exit_code)
        self.assertIn('Cloudinary CLI', result.output)
        self.assertIn('Cloudinary SDK', result.output)
        self.assertIn('Python', result.output)

    def _run_cli(self, *args, saved=None, **env_vars):
        """Run the CLI in a subprocess with only env_vars set, and a temp CLOUDINARY_HOME with the saved configs."""
        with tempfile.TemporaryDirectory() as home:
            if saved:
                with open(os.path.join(home, "config.json"), "w") as f:
                    json.dump(saved, f)
            env = {k: v for k, v in os.environ.items() if not k.startswith("CLOUDINARY_")}
            env.update(CLOUDINARY_HOME=home, **env_vars)
            return subprocess.run([sys.executable, "-m", "cloudinary_cli.cli", *args],
                                  env=env, capture_output=True, text=True)

    def assertUrlOutput(self, result):
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("res.cloudinary.com/demo/image/upload/sample", result.stdout)

    def assertEnvError(self, result, name):
        self.assertEqual(1, result.returncode)
        self.assertEqual(1, len(result.stderr.strip().splitlines()), result.stderr)
        self.assertTrue(result.stderr.strip().endswith(f"Fix or unset the {name} environment variable."),
                        result.stderr)

    def test_invalid_cloudinary_url_env(self):
        self.assertEnvError(self._run_cli("url", "sample", CLOUDINARY_URL="garbage"), "CLOUDINARY_URL")

    def test_invalid_cloudinary_url_env_query_keys(self):
        # The SDK raises TypeError, not ValueError, on this URL.
        result = self._run_cli("url", "sample", CLOUDINARY_URL="cloudinary://1:s@demo?a=1&a[b]=2")
        self.assertEnvError(result, "CLOUDINARY_URL")

    def test_invalid_cloudinary_url_env_with_config_override(self):
        self.assertUrlOutput(self._run_cli("-c", "cloudinary://123:abc@demo", "url", "sample",
                                           CLOUDINARY_URL="garbage"))

    def test_invalid_cloudinary_url_env_with_config_saved(self):
        self.assertUrlOutput(self._run_cli("-C", "demo", "url", "sample", saved={"demo": "cloudinary://123:abc@demo"},
                                           CLOUDINARY_URL="garbage"))

    def test_invalid_cloudinary_url_env_with_saved_default(self):
        saved = {"demo": "cloudinary://123:abc@demo", "__default__": "demo"}
        self.assertUrlOutput(self._run_cli("url", "sample", saved=saved, CLOUDINARY_URL="garbage"))

    def test_invalid_cloudinary_url_env_with_cloud_name(self):
        # With CLOUDINARY_CLOUD_NAME set, the SDK ignores CLOUDINARY_URL.
        self.assertUrlOutput(self._run_cli("url", "sample", CLOUDINARY_URL="garbage", CLOUDINARY_CLOUD_NAME="demo",
                                           CLOUDINARY_API_KEY="123", CLOUDINARY_API_SECRET="abc"))

    def test_invalid_cloudinary_url_env_config_new(self):
        # `config -n` works without a config, so the invalid variable does not block it.
        # The ping of the new config fails (fake credentials), which is not the error under test.
        result = self._run_cli("config", "-n", "demo", "cloudinary://123:abc@demo", CLOUDINARY_URL="garbage")
        self.assertNotIn("CLOUDINARY_URL", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_invalid_cloudinary_account_url_env(self):
        # Only `provisioning` uses CLOUDINARY_ACCOUNT_URL. Other commands continue to the API call,
        # which fails with the fake credentials.
        result = self._run_cli("admin", "ping", CLOUDINARY_URL="cloudinary://123:abc@demo",
                               CLOUDINARY_ACCOUNT_URL="garbage")
        self.assertNotIn("CLOUDINARY_ACCOUNT_URL", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_invalid_cloudinary_account_url_env_provisioning(self):
        # -c does not replace CLOUDINARY_ACCOUNT_URL.
        result = self._run_cli("-c", "cloudinary://123:abc@demo", "provisioning", "users",
                               CLOUDINARY_ACCOUNT_URL="garbage")
        self.assertEnvError(result, "CLOUDINARY_ACCOUNT_URL")

    def test_unknown_command_suggests_similar(self):
        result = self.runner.invoke(cli, ['serach', 'cat'])

        self.assertEqual(2, result.exit_code)
        self.assertIn("No such command", result.output)
        self.assertIn("Did you mean: search", result.output)

    def test_unknown_command_without_similar(self):
        result = self.runner.invoke(cli, ['xyzzy'])

        self.assertEqual(2, result.exit_code)
        self.assertNotIn("Did you mean", result.output)
