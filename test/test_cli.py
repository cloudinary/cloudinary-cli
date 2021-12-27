import unittest

from click.testing import CliRunner

from cloudinary_cli.cli import cli


class TestCLI(unittest.TestCase):
    runner = CliRunner()

    COMMANDS = [
        'admin',
        'config',
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
