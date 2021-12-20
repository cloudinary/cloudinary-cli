import unittest

import cloudinary
from click.testing import CliRunner

from cloudinary_cli.cli import cli


class TestCLISamples(unittest.TestCase):
    runner = CliRunner()

    @classmethod
    def tearDownClass(cls) -> None:
        cloudinary.reset_config()

    def test_sample(self):
        result = self.runner.invoke(cli, 'sample')

        self.assertEqual(0, result.exit_code)
        self.assertIn('image/upload/sample', result.output)

    def test_couple(self):
        result = self.runner.invoke(cli, 'couple')

        self.assertEqual(0, result.exit_code)
        self.assertIn('image/upload/couple', result.output)

    def test_dog(self):
        result = self.runner.invoke(cli, 'dog')

        self.assertEqual(0, result.exit_code)
        self.assertIn('video/upload/dog', result.output)
