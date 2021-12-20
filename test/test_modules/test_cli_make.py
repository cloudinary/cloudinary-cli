import unittest

import cloudinary
from click.testing import CliRunner

from cloudinary_cli.cli import cli


class TestCLIMake(unittest.TestCase):
    runner = CliRunner()

    def test_cli_make_upload_widget(self):
        result = self.runner.invoke(cli, ['make', 'upload_widget'])

        self.assertEqual(0, result.exit_code)
        self.assertIn('upload_widget', result.output)
        self.assertIn(f"cloudName: '{cloudinary.Config().cloud_name}'", result.output)

    def test_cli_make_base_python(self):
        result = self.runner.invoke(cli, ['make', 'base', 'python'])

        self.assertEqual(0, result.exit_code)
        self.assertIn('cloudinary.config', result.output)
        self.assertIn(f'"cloud_name": "{cloudinary.Config().cloud_name}"', result.output)

    def test_cli_make_python_base(self):
        result = self.runner.invoke(cli, ['make', 'python', 'base'])

        self.assertEqual(0, result.exit_code)
        self.assertIn('cloudinary.config', result.output)
        self.assertIn(f'"cloud_name": "{cloudinary.Config().cloud_name}"', result.output)
