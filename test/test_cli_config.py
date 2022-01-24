import unittest

import cloudinary
from click.testing import CliRunner

from cloudinary_cli.cli import cli


def _get_real_cloudinary_url():
    cfg = cloudinary.config()

    return f"cloudinary://{cfg.api_key}:{cfg.api_secret}@{cfg.cloud_name}"


def _get_real_cloud_name():
    return cloudinary.config().cloud_name


class TestCLIConfig(unittest.TestCase):
    REAL_CLOUDINARY_URL = _get_real_cloudinary_url()
    REAL_CLOUD_NAME = _get_real_cloud_name()
    runner = CliRunner()
    TEST_CLOUD_NAME = 'test_cloud'
    TEST_CLOUDINARY_URL = 'cloudinary://key:secret@' + TEST_CLOUD_NAME
    INVALID_CLOUDINARY_URL = 'cloudinary://key:secret@'
    EMPTY_CLOUDINARY_URL = 'cloudinary://'

    @classmethod
    def tearDownClass(cls) -> None:
        cls._save_current_config(cls)

    def test_cli_config_no_config(self):
        result = self.runner.invoke(cli, ['--config'])

        self.assertEqual(2, result.exit_code)
        self.assertIn('requires an argument', result.output)

    def test_cli_config_valid_config(self):
        result = self.runner.invoke(cli, ['--config', self.TEST_CLOUDINARY_URL, 'url', 'sample'])

        self.assertEqual(0, result.exit_code)
        self.assertIn('res.cloudinary.com', result.output)
        self.assertIn(self.TEST_CLOUD_NAME, result.output)

    def test_cli_config_invalid_config(self):
        result = self.runner.invoke(cli, ['--config', 'invalid', 'url', 'sample'])

        self.assertEqual(1, result.exit_code)
        self.assertIn('Invalid CLOUDINARY_URL scheme', str(result.exc_info[1]))

    def test_cli_config_invalid_config_cloud_name(self):
        result = self.runner.invoke(cli, ['--config', self.INVALID_CLOUDINARY_URL, 'ping'])

        self.assertEqual(1, result.exit_code)
        self.assertIn('No Cloudinary configuration found.', str(result.exc_info[1]))

    def test_cli_show_config(self):
        result = self.runner.invoke(cli, ['--config', self.TEST_CLOUDINARY_URL, 'config'])

        self.assertEqual(0, result.exit_code)

        for value in ['cloud_name', 'api_key', 'api_secret', self.TEST_CLOUD_NAME]:
            self.assertIn(value, result.output)

    def test_cli_config_from_non_valid_url(self):
        result = self.runner.invoke(cli, ['config', '--from_url', self.TEST_CLOUDINARY_URL])

        self.assertEqual(0, result.exit_code)
        self.assertIn('unknown api_key', result.output)

    @unittest.skipUnless(cloudinary.config().api_secret, "Requires api_key/api_secret")
    def test_cli_config_from_a_valid_url(self):
        result = self._save_current_config()

        self.assertEqual(0, result.exit_code)
        self.assertIn('saved!', result.output)

    @unittest.skipUnless(cloudinary.config().api_secret, "Requires api_key/api_secret")
    def test_cli_config_show(self):
        self._save_current_config()

        result = self.runner.invoke(cli, ['config', '--show', self.REAL_CLOUD_NAME])

        self.assertEqual(0, result.exit_code)

        for value in ['cloud_name', 'api_key', 'api_secret', self.REAL_CLOUD_NAME]:
            self.assertIn(value, result.output)

    @unittest.skipUnless(cloudinary.config().api_secret, "Requires api_key/api_secret")
    def test_cli_config_show_default_no_config(self):
        self.runner.invoke(cli, ['config', '--from_url', self.EMPTY_CLOUDINARY_URL])

        result = self.runner.invoke(cli, ['config'])

        self.assertEqual(1, result.exit_code)

        self.assertIn("No Cloudinary configuration found", result.output)

    def test_cli_config_show_non_existent(self):
        result = self.runner.invoke(cli, ['config', '--show', self.TEST_CLOUD_NAME])

        self.assertEqual(2, result.exit_code)
        self.assertIn("does not exist", result.output)

    @unittest.skipUnless(cloudinary.config().api_secret, "Requires api_key/api_secret")
    def test_cli_config_list(self):
        self._save_current_config()

        result = self.runner.invoke(cli, ['config', '--ls'])

        self.assertEqual(0, result.exit_code)

        self.assertIn(self.REAL_CLOUD_NAME, result.output)

    @unittest.skipUnless(cloudinary.config().api_secret, "Requires api_key/api_secret")
    def test_cli_config_remove(self):
        self._save_current_config()

        result = self.runner.invoke(cli, ['config', '-rm', self.REAL_CLOUD_NAME])

        self.assertEqual(0, result.exit_code)

        self.assertIn(self.REAL_CLOUD_NAME, result.output)
        self.assertIn("deleted", result.output)

    def test_cli_config_remove_non_existent(self):
        result = self.runner.invoke(cli, ['config', '-rm', self.TEST_CLOUD_NAME])

        self.assertEqual(0, result.exit_code)
        self.assertIn("not found", result.output)

    def _save_current_config(self):
        return self.runner.invoke(cli, ['config', '--from_url', self.REAL_CLOUDINARY_URL])
