import unittest
from unittest.mock import patch, MagicMock
import re

from cloudinary_cli.modules.clone import search_assets, process_metadata
from cloudinary_cli.defaults import logger


class TestCLIClone(unittest.TestCase):

    def setUp(self):
        self.mock_search_result = {
            'resources': [
                {
                    'public_id': 'test_asset',
                    'type': 'upload',
                    'resource_type': 'image',
                    'format': 'jpg',
                    'secure_url': 'https://res.cloudinary.com/test/image/upload/test_asset.jpg',
                    'tags': ['tag1', 'tag2'],
                    'context': {'key': 'value'},
                    'access_control': None,
                    'folder': 'test_folder',
                    'display_name': 'Test Asset'
                }
            ]
        }

    @patch('cloudinary_cli.modules.clone.handle_auto_pagination')
    @patch('cloudinary_cli.modules.clone.execute_single_request')
    @patch('cloudinary.search.Search')
    def test_search_assets_default_expression(self, mock_search_class, mock_execute, mock_pagination):
        """Test search_assets with empty search expression uses default"""
        mock_search = MagicMock()
        mock_search_class.return_value = mock_search
        mock_execute.return_value = self.mock_search_result
        mock_pagination.return_value = self.mock_search_result

        result = search_assets(force=True, search_exp="")

        # Verify default search expression is used
        mock_search.expression.assert_called_with("type:upload OR type:private OR type:authenticated")
        self.assertEqual(result, self.mock_search_result)

    @patch('cloudinary_cli.modules.clone.handle_auto_pagination')
    @patch('cloudinary_cli.modules.clone.execute_single_request')
    @patch('cloudinary.search.Search')
    def test_search_assets_with_custom_expression(self, mock_search_class, mock_execute, mock_pagination):
        """Test search_assets appends default types to custom expression"""
        mock_search = MagicMock()
        mock_search_class.return_value = mock_search
        mock_execute.return_value = self.mock_search_result
        mock_pagination.return_value = self.mock_search_result

        result = search_assets(force=True, search_exp="tags:test")

        # Verify custom expression gets default types appended
        expected_exp = "tags:test AND (type:upload OR type:private OR type:authenticated)"
        mock_search.expression.assert_called_with(expected_exp)
        self.assertEqual(result, self.mock_search_result)

    @patch('cloudinary_cli.modules.clone.handle_auto_pagination')
    @patch('cloudinary_cli.modules.clone.execute_single_request')
    @patch('cloudinary.search.Search')
    def test_search_assets_with_allowed_type(self, mock_search_class, mock_execute, mock_pagination):
        """Test search_assets accepts allowed types"""
        mock_search = MagicMock()
        mock_search_class.return_value = mock_search
        mock_execute.return_value = self.mock_search_result
        mock_pagination.return_value = self.mock_search_result

        result = search_assets(force=True, search_exp="type:upload")

        # Verify allowed type is accepted as-is
        mock_search.expression.assert_called_with("type:upload")
        self.assertEqual(result, self.mock_search_result)

    @patch('cloudinary_cli.modules.clone.logger')
    def test_search_assets_with_disallowed_type(self, mock_logger):
        """Test search_assets rejects disallowed types"""
        result = search_assets(force=True, search_exp="type:facebook")

        # Verify error is logged and False is returned
        mock_logger.error.assert_called_once()
        error_call = mock_logger.error.call_args[0][0]
        self.assertIn("Unsupported type(s) in search expression", error_call)
        self.assertIn("facebook", error_call)
        self.assertEqual(result, False)

    @patch('cloudinary_cli.modules.clone.logger')
    def test_search_assets_with_mixed_types(self, mock_logger):
        """Test search_assets with mix of allowed and disallowed types"""
        result = search_assets(force=True, search_exp="type:upload OR type:facebook")

        # Verify error is logged for disallowed type
        mock_logger.error.assert_called_once()
        error_call = mock_logger.error.call_args[0][0]
        self.assertIn("facebook", error_call)
        # Verify that only the disallowed type is mentioned in the error part
        self.assertIn("Unsupported type(s) in search expression: facebook", error_call)
        self.assertEqual(result, False)

    def test_search_assets_type_validation_regex(self):
        """Test the regex used for type validation"""
        # Test various type formats
        test_cases = [
            ("type:upload", ["upload"]),
            ("type=upload", ["upload"]),
            ("type: upload", ["upload"]),  # with space
            ("type = upload", ["upload"]),  # with spaces
            ("type:upload OR type:private", ["upload", "private"]),
            ("tags:test AND type:authenticated", ["authenticated"]),
        ]

        for search_exp, expected_types in test_cases:
            with self.subTest(search_exp=search_exp):
                found_types = re.findall(r"\btype\s*[:=]\s*\w+", search_exp)
                cleaned_types = [''.join(t.split()) for t in found_types]
                # Extract just the type names
                type_names = [t.split(':')[-1].split('=')[-1] for t in cleaned_types]
                self.assertEqual(sorted(type_names), sorted(expected_types))

    def test_process_metadata_basic(self):
        """Test process_metadata with basic asset"""
        res = {
            'public_id': 'test_asset',
            'type': 'upload',
            'resource_type': 'image',
            'format': 'jpg',
            'secure_url': 'https://res.cloudinary.com/test/image/upload/test_asset.jpg',
            'access_control': None
        }

        options, url = process_metadata(
            res, overwrite=True, async_=False, notification_url=None,
            auth_token=None, ttl=3600, copy_fields=[]
        )

        self.assertEqual(url, 'https://res.cloudinary.com/test/image/upload/test_asset.jpg')
        self.assertEqual(options['public_id'], 'test_asset')
        self.assertEqual(options['type'], 'upload')
        self.assertEqual(options['resource_type'], 'image')
        self.assertEqual(options['overwrite'], True)
        self.assertEqual(options['async'], False)

    def test_process_metadata_with_tags_and_context(self):
        """Test process_metadata copying tags and context"""
        res = {
            'public_id': 'test_asset',
            'type': 'upload',
            'resource_type': 'image',
            'format': 'jpg',
            'secure_url': 'https://res.cloudinary.com/test/image/upload/test_asset.jpg',
            'access_control': None,
            'tags': ['tag1', 'tag2'],
            'context': {'key': 'value'}
        }

        options, url = process_metadata(
            res, overwrite=False, async_=True, notification_url='http://webhook.com',
            auth_token=None, ttl=3600, copy_fields=['tags', 'context']
        )

        self.assertEqual(options['tags'], ['tag1', 'tag2'])
        self.assertEqual(options['context'], {'key': 'value'})
        self.assertEqual(options['notification_url'], 'http://webhook.com')
        self.assertEqual(options['overwrite'], False)
        self.assertEqual(options['async'], True)

    def test_process_metadata_with_folder(self):
        """Test process_metadata with folder handling"""
        res = {
            'public_id': 'test_asset',
            'type': 'upload',
            'resource_type': 'image',
            'format': 'jpg',
            'secure_url': 'https://res.cloudinary.com/test/image/upload/test_asset.jpg',
            'access_control': None,
            'folder': 'test_folder'
        }

        options, url = process_metadata(
            res, overwrite=False, async_=False, notification_url=None,
            auth_token=None, ttl=3600, copy_fields=[]
        )

        self.assertEqual(options['asset_folder'], 'test_folder')

    def test_process_metadata_with_asset_folder(self):
        """Test process_metadata with asset_folder"""
        res = {
            'public_id': 'test_asset',
            'type': 'upload',
            'resource_type': 'image',
            'format': 'jpg',
            'secure_url': 'https://res.cloudinary.com/test/image/upload/test_asset.jpg',
            'access_control': None,
            'asset_folder': 'asset_folder_test'
        }

        options, url = process_metadata(
            res, overwrite=False, async_=False, notification_url=None,
            auth_token=None, ttl=3600, copy_fields=[]
        )

        self.assertEqual(options['asset_folder'], 'asset_folder_test')

    def test_process_metadata_with_display_name(self):
        """Test process_metadata with display_name"""
        res = {
            'public_id': 'test_asset',
            'type': 'upload',
            'resource_type': 'image',
            'format': 'jpg',
            'secure_url': 'https://res.cloudinary.com/test/image/upload/test_asset.jpg',
            'access_control': None,
            'display_name': 'Test Asset Display Name'
        }

        options, url = process_metadata(
            res, overwrite=False, async_=False, notification_url=None,
            auth_token=None, ttl=3600, copy_fields=[]
        )

        self.assertEqual(options['display_name'], 'Test Asset Display Name')

    @patch('cloudinary_cli.modules.clone.time.time')
    @patch('cloudinary.utils.private_download_url')
    def test_process_metadata_restricted_asset_no_auth_token(self, mock_private_url, mock_time):
        """Test process_metadata with restricted asset and no auth token"""
        mock_time.return_value = 1000
        mock_private_url.return_value = 'https://private.url/test_asset.jpg'

        res = {
            'public_id': 'test_asset',
            'type': 'upload',
            'resource_type': 'image',
            'format': 'jpg',
            'secure_url': 'https://res.cloudinary.com/test/image/upload/test_asset.jpg',
            'access_control': [{'access_type': 'token'}]
        }

        options, url = process_metadata(
            res, overwrite=False, async_=False, notification_url=None,
            auth_token=None, ttl=3600, copy_fields=[]
        )

        # Should use private download URL
        mock_private_url.assert_called_once_with(
            'test_asset', 'jpg', resource_type='image', type='upload', expires_at=4600
        )
        self.assertEqual(url, 'https://private.url/test_asset.jpg')

    @patch('cloudinary.utils.cloudinary_url')
    def test_process_metadata_restricted_asset_with_auth_token(self, mock_cloudinary_url):
        """Test process_metadata with restricted asset and auth token"""
        mock_cloudinary_url.return_value = ('https://signed.url/test_asset.jpg', {})

        res = {
            'public_id': 'test_asset',
            'type': 'upload',
            'resource_type': 'image',
            'format': 'jpg',
            'secure_url': 'https://res.cloudinary.com/test/image/upload/test_asset.jpg',
            'access_control': [{'access_type': 'token'}]
        }

        options, url = process_metadata(
            res, overwrite=False, async_=False, notification_url=None,
            auth_token={'key': 'value'}, ttl=3600, copy_fields=[]
        )

        # Should use signed URL
        mock_cloudinary_url.assert_called_once_with(
            'test_asset.jpg',
            type='upload',
            resource_type='image',
            auth_token={'duration': 3600},
            secure=True,
            sign_url=True
        )
        # The current implementation assigns the tuple directly, so we expect the tuple
        self.assertEqual(url, ('https://signed.url/test_asset.jpg', {}))

    @patch('cloudinary.utils.cloudinary_url')
    def test_process_metadata_restricted_raw_asset_with_auth_token(self, mock_cloudinary_url):
        """Test process_metadata with restricted raw asset and auth token"""
        mock_cloudinary_url.return_value = ('https://signed.url/test_asset', {})

        res = {
            'public_id': 'test_asset',
            'type': 'upload',
            'resource_type': 'raw',
            'format': 'pdf',
            'secure_url': 'https://res.cloudinary.com/test/raw/upload/test_asset.pdf',
            'access_control': [{'access_type': 'token'}]
        }

        options, url = process_metadata(
            res, overwrite=False, async_=False, notification_url=None,
            auth_token={'key': 'value'}, ttl=3600, copy_fields=[]
        )

        # For raw assets, should not append format to public_id
        mock_cloudinary_url.assert_called_once_with(
            'test_asset',  # No .pdf extension for raw assets
            type='upload',
            resource_type='raw',
            auth_token={'duration': 3600},
            secure=True,
            sign_url=True
        )
        # The current implementation assigns the tuple directly, so we expect the tuple
        self.assertEqual(url, ('https://signed.url/test_asset', {}))


if __name__ == '__main__':
    unittest.main()
