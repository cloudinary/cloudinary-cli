import unittest

import cloudinary
from click.testing import CliRunner

from cloudinary_cli.cli import cli


class TestCLIMake(unittest.TestCase):
    runner = CliRunner()

    def test_cli_make_no_params(self):
        result = self.runner.invoke(cli, ["make"])

        self.assertEqual(0, result.exit_code)
        self.assertIn('Usage:', result.output)

    def test_cli_make_list_languages(self):
        result = self.runner.invoke(cli, ["make", "-ll"])

        self.assertEqual(0, result.exit_code)
        self.assertIn('html', result.output)

    def test_cli_make_list_templates(self):
        result = self.runner.invoke(cli, ["make", "-lt"])

        self.assertEqual(0, result.exit_code)
        self.assertIn('html', result.output)
        self.assertIn('upload widget', result.output)

        result = self.runner.invoke(cli, ["make", "python", "-lt"])

        self.assertEqual(0, result.exit_code)
        self.assertIn('python', result.output)
        self.assertIn('upload', result.output)

    def test_cli_make_upload_widget(self):
        result = self.runner.invoke(cli, ["make", "upload_widget"])

        self.assertEqual(0, result.exit_code)
        self.assertIn('upload_widget', result.output)
        self.assertIn(f"cloudName: '{cloudinary.Config().cloud_name}'", result.output)

    def test_cli_make_base_python(self):
        result = self.runner.invoke(cli, ["make", "base", "python"])

        self.assertEqual(0, result.exit_code)
        self.assertIn('cloudinary.config', result.output)
        self.assertIn(f'"cloud_name": "{cloudinary.Config().cloud_name}"', result.output)

        result = self.runner.invoke(cli, ["make", "python", "base"])

        self.assertEqual(0, result.exit_code)
        self.assertIn('cloudinary.config', result.output)
        self.assertIn(f'"cloud_name": "{cloudinary.Config().cloud_name}"', result.output)

    def test_cli_make_python_find_all_empty_folders(self):
        result = self.runner.invoke(cli, ["make", "python", "find", "all", "empty", "folders"])

        self.assertEqual(0, result.exit_code)
        self.assertIn("cloudinary.config", result.output)
        self.assertIn(f'"cloud_name": "{cloudinary.Config().cloud_name}"', result.output)

        result = self.runner.invoke(cli, ["make", "python", "find_all_empty_folders"])

        self.assertEqual(0, result.exit_code)
        self.assertIn("cloudinary.config", result.output)
        self.assertIn(f'"cloud_name": "{cloudinary.Config().cloud_name}"', result.output)
