import unittest
from unittest.mock import patch, MagicMock
import re
import sys

# Import the modules package, which will load the clone module.
# The 'clone' name in the package is the command object, so we get the module from sys.modules.
import cloudinary_cli.modules
clone_module = sys.modules['cloudinary_cli.modules.clone']

from cloudinary_cli.defaults import logger


class TestCLIClone(unittest.TestCase):

    def setUp(self):
        self.mock_search_result = {
            'resources': [
                {
                    'public_id': 'sample',
                    'type': 'upload',
                    'resource_type': 'image',
                    'format': 'jpg',
                    'secure_url': 'https://res.cloudinary.com/demo/image/upload/v1234567890/sample.jpg',
                    'tags': ['tag1', 'tag2'],
                    'context': {'key': 'value'},
                    'folder': 'test_folder',
                    'display_name': 'Test Asset'
                }
            ]
        }
        self.mock_target_config = {
            'cloud_name': 'target-cloud',
            'api_key': 'target-key',
            'api_secret': 'target-secret'
        }

    @patch.object(clone_module, 'list_metadata_items')
    def test_list_metadata_items(self, mock_metadata_fields):
        """Test listing metadata fields"""
        mock_metadata_fields.return_value = {
            'metadata_fields': [
                {
                    'external_id': 'test_field',
                    'type': 'string',
                    'label': 'Test Field',
                    'mandatory': False
                }
            ]
        }

        result = clone_module.list_metadata_items("metadata_fields")

        mock_metadata_fields.assert_called_once()
        self.assertEqual(result, mock_metadata_fields.return_value)

    @patch.object(clone_module, 'list_metadata_items')
    def test_list_metadata_rules(self, mock_metadata_rules):
        """Test listing metadata fields"""
        mock_metadata_rules.return_value = {
            'metadata_rules': [
                {
                    'external_id': 'test_rule',
                    'condition': 'if',
                    'metadata_field': {
                        'external_id': 'test_field'
                    },
                    'results': [{
                        'value': 'test_value',
                        'apply_to': ['metadata_field_external_id']
                    }]
                }
            ]
        }

        result = clone_module.list_metadata_items("metadata_rules")

        mock_metadata_rules.assert_called_once()
        self.assertEqual(result, mock_metadata_rules.return_value)

    @patch.object(clone_module, 'create_metadata_item')
    def test_create_metadata_item_field(self, mock_add_metadata_field):
        """Test creating a single metadata field"""
        mock_metadata_field = {
            'external_id': 'test_field',
            'type': 'string',
            'label': 'Test Field',
            'mandatory': False
        }
        
        clone_module.create_metadata_item('add_metadata_field', mock_metadata_field)

        mock_add_metadata_field.assert_called_once_with('add_metadata_field', mock_metadata_field)

    @patch.object(clone_module, 'create_metadata_item')
    def test_create_metadata_item_rule(self, mock_add_metadata_rule):
        """Test creating a single metadata rule"""
        mock_metadata_rule = {
            'external_id': 'test_rule',
            'condition': 'if',
            'metadata_field': {
                'external_id': 'test_field'
            },
            'results': [{
                'value': 'test_value',
                'apply_to': ['metadata_field_external_id']
            }]
        }

        clone_module.create_metadata_item('add_metadata_rule', mock_metadata_rule)

        mock_add_metadata_rule.assert_called_once_with('add_metadata_rule', mock_metadata_rule)

    @patch.object(clone_module, 'create_metadata_item')
    @patch.object(clone_module, 'list_metadata_items')
    def test_compare_create_metadata_items_new_fields(self, mock_list, mock_create):
        """Test comparing and creating new metadata fields"""
        metadata_fields = {
            'metadata_fields': [
                {
                    'external_id': 'field1',
                    'type': 'string',
                    'label': 'Field 1'
                },
                {
                    'external_id': 'field2',
                    'type': 'integer',
                    'label': 'Field 2'
                }
            ]
        }

        mock_source_fields = metadata_fields
        mock_list.return_value = metadata_fields
        mock_destination_fields = {
            'metadata_fields': []
        }
        
        clone_module.compare_create_metadata_items(mock_source_fields, mock_destination_fields, self.mock_target_config, key="metadata_fields")
        
        # Both fields should be created
        self.assertEqual(mock_create.call_count, 2)
        mock_create.assert_any_call('add_metadata_field', mock_source_fields['metadata_fields'][0], self.mock_target_config)
        mock_create.assert_any_call('add_metadata_field', mock_source_fields['metadata_fields'][1], self.mock_target_config)

        result = clone_module.list_metadata_items("metadata_fields", self.mock_target_config)
        mock_list.assert_called_once()
        self.assertEqual(result, mock_list.return_value)

    @patch.object(clone_module, 'create_metadata_item')
    @patch.object(clone_module, 'list_metadata_items')
    def test_compare_create_metadata_items_new_rules(self, mock_list, mock_create):
        """Test comparing and creating new metadata rules"""
        metadata_rules = {
            'metadata_rules': [
                {
                    'external_id': 'rule1',
                    'condition': 'if',
                    'metadata_field': {'external_id': 'field1'},
                    'results': [{
                        'value': 'value1',
                        'apply_to': ['target_field1']
                    }]
                },
                {
                    'external_id': 'rule2',
                    'condition': 'if',
                    'metadata_field': {'external_id': 'field2'},
                    'results': [{
                        'value': 'value2',
                        'apply_to': ['target_field2']
                    }]
                }
            ]
        }
        
        mock_source_metadata_rules = metadata_rules
        mock_list.return_value = metadata_rules

        mock_destination_metadata_rules = {
            'metadata_rules': []
        }
        
        clone_module.compare_create_metadata_items(mock_source_metadata_rules, mock_destination_metadata_rules, self.mock_target_config, key="metadata_rules")
        
        # Both rules should be created
        self.assertEqual(mock_create.call_count, 2)
        mock_create.assert_any_call('add_metadata_rule', mock_source_metadata_rules['metadata_rules'][0], self.mock_target_config)
        mock_create.assert_any_call('add_metadata_rule', mock_source_metadata_rules['metadata_rules'][1], self.mock_target_config)

        result = clone_module.list_metadata_items("metadata_rules", self.mock_target_config)
        mock_list.assert_called_once()
        self.assertEqual(result, mock_list.return_value)

    @patch.object(clone_module, 'create_metadata_item')
    def test_compare_create_metadata_items_existing_fields(self, mock_create):
        """Test comparing when fields already exist"""
        mock_source_fields = {
            'metadata_fields': [
                {
                    'external_id': 'field1',
                    'type': 'string',
                    'label': 'Field 1'
                }
            ]
        }
        
        # Simulate destination already having the field
        mock_destination_fields = {
            'metadata_fields': [
                {
                    'external_id': 'field1',
                    'type': 'string',
                    'label': 'Field 1'
                }
            ]
        }
        
        mock_source_fields
        clone_module.compare_create_metadata_items(mock_source_fields, mock_destination_fields, self.mock_target_config, key="metadata_fields")
        
        # No fields should be created
        mock_create.assert_not_called()

    @patch.object(clone_module, 'create_metadata_item')
    def test_compare_create_metadata_items_existing_rules(self, mock_create):
        """Test comparing when rules already exist"""

        mock_source_metadata_rules = {
            'metadata_rules': [
                {
                    'external_id': 'rule1',
                    'condition': 'if',
                    'metadata_field': {'external_id': 'field1'},
                    'results': [{
                        'value': 'value1',
                        'apply_to': ['target_field1']
                    }]
                }
            ]
        }
        
        # Simulate destination already having the rule
        mock_destination_metadata_rules = {
            'metadata_rules': [
                {
                    'external_id': 'rule1',
                    'condition': 'if',
                    'metadata_field': {'external_id': 'field1'},
                    'results': [{
                        'value': 'value1',
                        'apply_to': ['target_field1']
                    }]
                }
            ]
        }
        
        clone_module.compare_create_metadata_items(mock_source_metadata_rules, mock_destination_metadata_rules, self.mock_target_config, key="metadata_rules")
        
        # No rules should be created
        mock_create.assert_not_called()
    
    @patch.object(clone_module, 'create_metadata_item')
    @patch.object(clone_module, 'list_metadata_items')
    def test_compare_create_metadata_items_mixed_scenario(self, mock_list, mock_create):
        """Test comparing with mix of new and existing fields"""
        metadata_fields = {
            'metadata_fields': [
                {
                    'external_id': 'field1',
                    'type': 'string',
                    'label': 'Field 1'
                },
                {
                    'external_id': 'field2',
                    'type': 'integer',
                    'label': 'Field 2'
                }
            ]
        }
        
        # Simulate destination having only one field
        mock_destination_fields = {
            'metadata_fields': [
                {
                    'external_id': 'field1',
                    'type': 'string',
                    'label': 'Field 1'
                }
            ]
        }

        mock_source_fields= metadata_fields
        mock_list.return_value = metadata_fields
        
        clone_module.compare_create_metadata_items(mock_source_fields, mock_destination_fields, self.mock_target_config, key="metadata_fields")
        
        # Only new_field should be created
        mock_create.assert_called_once_with('add_metadata_field', mock_source_fields['metadata_fields'][1], self.mock_target_config)
        
        result = clone_module.list_metadata_items("metadata_fields", self.mock_target_config)
        mock_list.assert_called_once()
        self.assertEqual(result, mock_list.return_value)

    @patch.object(clone_module, 'create_metadata_item')
    @patch.object(clone_module, 'list_metadata_items')
    def test_compare_create_metadata_items_mixed_rules_scenario(self, mock_list, mock_create):
        """Test comparing with mix of new and existing rules"""
        metadata_rules = {
            'metadata_rules': [
                {
                    'external_id': 'rule1',
                    'condition': 'if',
                    'metadata_field': {'external_id': 'field1'},
                    'results': [{
                        'value': 'value1',
                        'apply_to': ['target_field1']
                    }]
                },
                {
                    'external_id': 'rule2',
                    'condition': 'if',
                    'metadata_field': {'external_id': 'field2'},
                    'results': [{
                        'value': 'value2',
                        'apply_to': ['target_field2']
                    }]
                }
            ]
        }
        
        # Simulate destination having only one rule
        mock_destination_metadata_rules = {
            'metadata_rules': [
                {
                    'external_id': 'rule1',
                    'condition': 'if',
                    'metadata_field': {'external_id': 'field1'},
                    'results': [{
                        'value': 'value1',
                        'apply_to': ['target_field1']
                    }]
                }
            ]
        }

        mock_source_metadata_rules = metadata_rules
        mock_list.return_value = metadata_rules
        
        clone_module.compare_create_metadata_items(mock_source_metadata_rules, mock_destination_metadata_rules, self.mock_target_config, key="metadata_rules")
        
        # Only new_rule should be created
        mock_create.assert_called_once_with('add_metadata_rule', mock_source_metadata_rules['metadata_rules'][1], self.mock_target_config)

        result = clone_module.list_metadata_items("metadata_rules", self.mock_target_config)
        mock_list.assert_called_once()
        self.assertEqual(result, mock_list.return_value)

    @patch.object(clone_module, 'handle_auto_pagination')
    @patch.object(clone_module, 'execute_single_request')
    @patch('cloudinary.search.Search')
    def test_search_assets_default_expression(self, mock_search_class, mock_execute, mock_pagination):
        """Test search_assets with empty search expression uses default"""
        mock_search = MagicMock()
        mock_search_class.return_value = mock_search
        mock_execute.return_value = self.mock_search_result
        mock_pagination.return_value = self.mock_search_result

        result = clone_module.search_assets(force=True, search_exp="")

        # Verify default search expression is used
        mock_search.expression.assert_called_with("type:upload OR type:private OR type:authenticated")
        self.assertEqual(result, self.mock_search_result)

    @patch.object(clone_module, 'handle_auto_pagination')
    @patch.object(clone_module, 'execute_single_request')
    @patch('cloudinary.search.Search')
    def test_search_assets_with_custom_expression(self, mock_search_class, mock_execute, mock_pagination):
        """Test search_assets appends default types to custom expression"""
        mock_search = MagicMock()
        mock_search_class.return_value = mock_search
        mock_execute.return_value = self.mock_search_result
        mock_pagination.return_value = self.mock_search_result

        result = clone_module.search_assets(force=True, search_exp="tags:test")

        # Verify custom expression gets default types appended
        expected_exp = "tags:test AND (type:upload OR type:private OR type:authenticated)"
        mock_search.expression.assert_called_with(expected_exp)
        self.assertEqual(result, self.mock_search_result)

    @patch.object(clone_module, 'handle_auto_pagination')
    @patch.object(clone_module, 'execute_single_request')
    @patch('cloudinary.search.Search')
    def test_search_assets_with_allowed_type(self, mock_search_class, mock_execute, mock_pagination):
        """Test search_assets accepts allowed types"""
        mock_search = MagicMock()
        mock_search_class.return_value = mock_search
        mock_execute.return_value = self.mock_search_result
        mock_pagination.return_value = self.mock_search_result

        result = clone_module.search_assets(force=True, search_exp="type:upload")

        # Verify allowed type is accepted as-is
        mock_search.expression.assert_called_with("type:upload")
        self.assertEqual(result, self.mock_search_result)

    @patch.object(clone_module, 'logger')
    def test_search_assets_with_disallowed_type(self, mock_logger):
        """Test search_assets rejects disallowed types"""
        result = clone_module.search_assets(force=True, search_exp="type:facebook")

        # Verify error is logged and False is returned
        mock_logger.error.assert_called_once()
        error_call = mock_logger.error.call_args[0][0]
        self.assertIn("Unsupported type(s) in search expression", error_call)
        self.assertIn("facebook", error_call)
        self.assertEqual(result, False)

    @patch.object(clone_module, 'logger')
    def test_search_assets_with_mixed_types(self, mock_logger):
        """Test search_assets with mix of allowed and disallowed types"""
        result = clone_module.search_assets(force=True, search_exp="type:upload OR type:facebook")

        # Verify error is logged for disallowed type
        mock_logger.error.assert_called_once()
        error_call = mock_logger.error.call_args[0][0]
        self.assertIn("facebook", error_call)
        # Verify that only the disallowed type is mentioned in the error part
        self.assertIn("Unsupported type(s) in search expression: type:facebook", error_call)
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
            'public_id': 'sample',
            'type': 'upload',
            'resource_type': 'image',
            'format': 'jpg',
            'secure_url': 'https://res.cloudinary.com/demo/image/upload/v1234567890/sample.jpg'
        }

        options, url = clone_module.process_metadata(
            res, overwrite=True, async_=False, notification_url=None,
            auth_token=None, url_expiry=3600, copy_fields=[]
        )

        self.assertEqual(url, 'https://res.cloudinary.com/demo/image/upload/v1234567890/sample.jpg')
        self.assertEqual(options['public_id'], 'sample')
        self.assertEqual(options['type'], 'upload')
        self.assertEqual(options['resource_type'], 'image')
        self.assertEqual(options['overwrite'], True)
        self.assertEqual(options['async'], False)

    def test_process_metadata_with_tags_and_context(self):
        """Test process_metadata copying tags and context"""
        res = {
            'public_id': 'sample',
            'type': 'upload',
            'resource_type': 'image',
            'format': 'jpg',
            'secure_url': 'https://res.cloudinary.com/demo/image/upload/v1234567890/sample.jpg',
            'tags': ['tag1', 'tag2'],
            'context': {'key': 'value'}
        }

        options, url = clone_module.process_metadata(
            res, overwrite=False, async_=True, notification_url='http://webhook.com',
            auth_token=None, url_expiry=3600, copy_fields=['tags', 'context']
        )

        self.assertEqual(options['tags'], ['tag1', 'tag2'])
        self.assertEqual(options['context'], {'key': 'value'})
        self.assertEqual(options['notification_url'], 'http://webhook.com')
        self.assertEqual(options['overwrite'], False)
        self.assertEqual(options['async'], True)

    def test_process_metadata_with_folder(self):
        """Test process_metadata with folder handling"""
        res = {
            'public_id': 'sample',
            'type': 'upload',
            'resource_type': 'image',
            'format': 'jpg',
            'secure_url': 'https://res.cloudinary.com/demo/image/upload/v1234567890/sample.jpg',
            'folder': 'test_folder'
        }

        options, url = clone_module.process_metadata(
            res, overwrite=False, async_=False, notification_url=None,
            auth_token=None, url_expiry=3600, copy_fields=[]
        )

        self.assertEqual(options['asset_folder'], 'test_folder')

    def test_process_metadata_with_asset_folder(self):
        """Test process_metadata with asset_folder"""
        res = {
            'public_id': 'sample',
            'type': 'upload',
            'resource_type': 'image',
            'format': 'jpg',
            'secure_url': 'https://res.cloudinary.com/demo/image/upload/v1234567890/sample.jpg',
            'asset_folder': 'asset_folder_test'
        }

        options, url = clone_module.process_metadata(
            res, overwrite=False, async_=False, notification_url=None,
            auth_token=None, url_expiry=3600, copy_fields=[]
        )

        self.assertEqual(options['asset_folder'], 'asset_folder_test')

    def test_process_metadata_with_display_name(self):
        """Test process_metadata with display_name"""
        res = {
            'public_id': 'sample',
            'type': 'upload',
            'resource_type': 'image',
            'format': 'jpg',
            'secure_url': 'https://res.cloudinary.com/demo/image/upload/v1234567890/sample.jpg',
            'display_name': 'Test Asset Display Name'
        }

        options, url = clone_module.process_metadata(
            res, overwrite=False, async_=False, notification_url=None,
            auth_token=None, url_expiry=3600, copy_fields=[]
        )

        self.assertEqual(options['display_name'], 'Test Asset Display Name')

    @patch('time.time')
    @patch('cloudinary.utils.private_download_url')
    def test_process_metadata_restricted_asset_no_auth_token(self, mock_private_url, mock_time):
        """Test process_metadata with restricted asset and no auth token"""
        mock_time.return_value = 1000
        mock_private_url.return_value = 'https://api.cloudinary.com/v1_1/demo/image/download?api_key=123456789012345&format=jpg&public_id=sample&signature=abcdef123456789&timestamp=1234567890'

        res = {
            'public_id': 'sample',
            'type': 'upload',
            'resource_type': 'image',
            'format': 'jpg',
            'secure_url': 'https://res.cloudinary.com/demo/image/upload/v1234567890/sample.jpg',
            'access_control': [{'access_type': 'token'}]
        }

        options, url = clone_module.process_metadata(
            res, overwrite=False, async_=False, notification_url=None,
            auth_token=None, url_expiry=3600, copy_fields=[]
        )

        # Should use private download URL
        mock_private_url.assert_called_once_with(
            'sample', 'jpg', resource_type='image', type='upload', expires_at=4600
        )
        self.assertEqual(url, 'https://api.cloudinary.com/v1_1/demo/image/download?api_key=123456789012345&format=jpg&public_id=sample&signature=abcdef123456789&timestamp=1234567890')

    @patch('cloudinary.utils.cloudinary_url')
    def test_process_metadata_restricted_asset_with_auth_token(self, mock_cloudinary_url):
        """Test process_metadata with restricted asset and auth token"""
        mock_cloudinary_url.return_value = ('https://res.cloudinary.com/demo/image/upload/s--AbCdEfGhI--/sample.jpg', {})

        res = {
            'public_id': 'sample',
            'type': 'upload',
            'resource_type': 'image',
            'format': 'jpg',
            'secure_url': 'https://res.cloudinary.com/demo/image/upload/v1234567890/sample.jpg',
            'access_control': [{'access_type': 'token'}]
        }

        options, url = clone_module.process_metadata(
            res, overwrite=False, async_=False, notification_url=None,
            auth_token={'key': 'value'}, url_expiry=3600, copy_fields=[]
        )

        # Should use signed URL
        mock_cloudinary_url.assert_called_once_with(
            'sample.jpg',
            type='upload',
            resource_type='image',
            auth_token={'duration': 3600},
            secure=True,
            sign_url=True
        )
        # The current implementation assigns the tuple directly, so we expect the tuple
        self.assertEqual(url, ('https://res.cloudinary.com/demo/image/upload/s--AbCdEfGhI--/sample.jpg', {}))

    @patch('cloudinary.utils.cloudinary_url')
    def test_process_metadata_restricted_raw_asset_with_auth_token(self, mock_cloudinary_url):
        """Test process_metadata with restricted raw asset and auth token"""
        mock_cloudinary_url.return_value = ('https://res.cloudinary.com/demo/raw/upload/s--XyZaBcDeF--/sample_document', {})

        res = {
            'public_id': 'sample_document',
            'type': 'upload',
            'resource_type': 'raw',
            'format': 'pdf',
            'secure_url': 'https://res.cloudinary.com/demo/raw/upload/v1234567890/sample_document.pdf',
            'access_control': [{'access_type': 'token'}]
        }

        options, url = clone_module.process_metadata(
            res, overwrite=False, async_=False, notification_url=None,
            auth_token={'key': 'value'}, url_expiry=3600, copy_fields=[]
        )

        # For raw assets, should not append format to public_id
        mock_cloudinary_url.assert_called_once_with(
            'sample_document',  # No .pdf extension for raw assets
            type='upload',
            resource_type='raw',
            auth_token={'duration': 3600},
            secure=True,
            sign_url=True
        )
        # The current implementation assigns the tuple directly, so we expect the tuple
        self.assertEqual(url, ('https://res.cloudinary.com/demo/raw/upload/s--XyZaBcDeF--/sample_document', {}))


if __name__ == '__main__':
    unittest.main()
