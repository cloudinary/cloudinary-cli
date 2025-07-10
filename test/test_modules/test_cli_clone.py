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

if __name__ == '__main__':
    unittest.main()