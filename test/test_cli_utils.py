import unittest

from click.testing import CliRunner

from cloudinary_cli.cli import cli


class TestCLIUtils(unittest.TestCase):
    runner = CliRunner()
    UTILS = [
        'api_sign_request',
        'cloudinary_url',
        'private_download_url',
        'download_archive_url',
        'download_zip_url',
        'download_folder',
        'download_backedup_asset',
        'verify_api_response_signature',
        'verify_notification_signature',
    ]

    def test_list_utils(self):
        result = self.runner.invoke(cli, ['utils'])

        self.assertEqual(0, result.exit_code)
        for util in self.UTILS:
            self.assertIn(util, result.output)

    def test_utils_cloudinary_url(self):
        result = self.runner.invoke(cli, ['utils', 'cloudinary_url', 'sample'])

        self.assertEqual(0, result.exit_code)
        self.assertIn('image/upload/sample', result.output)
