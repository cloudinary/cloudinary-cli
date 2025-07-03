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

    @patch('cloudinary.api.metadata_fields')
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
        self.assertEqual(result, mock_metadata_fields.return_value['metadata_fields'])

    @patch('cloudinary.api.metadata_rules')
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
        self.assertEqual(result, mock_metadata_rules.return_value['metadata_rules'])

    @patch('cloudinary.api.add_metadata_field')
    def test_create_metadata_item_field(self, mock_add_metadata_field):
        """Test creating a single metadata field"""
        mock_metadata_fields = {
            'metadata_fields': [
                {
                    'external_id': 'test_field',
                    'type': 'string',
                    'label': 'Test Field',
                    'mandatory': False
                }
            ]
        }
        
        clone_module.create_metadata_item('add_metadata_field', mock_metadata_fields, self.mock_target_config)

        mock_add_metadata_field.assert_called_once_with(mock_metadata_fields)

    @patch('cloudinary.api.add_metadata_rule')
    def test_create_metadata_item_rule(self, mock_add_metadata_rule):
        """Test creating a single metadata rule"""
        mock_metadata_rules = {
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

        clone_module.create_metadata_item('add_metadata_rule', mock_metadata_rules, self.mock_target_config)

        mock_add_metadata_rule.assert_called_once_with(mock_metadata_rules)

    @patch('cloudinary.api.add_metadata_field')
    def test_create_metadata_item_field_with_error(self, mock_add_metadata_field):
        """Test creating metadata field with API error"""
        mock_metadata_fields = {
            'metadata_fields': [
                {
                    'external_id': 'test_field',
                    'type': 'string',
                    'label': 'Test Field',
                    'mandatory': False
                }
            ]
        }
        
        mock_add_metadata_field.side_effect = Exception("API Error")
        
        with self.assertLogs(logger, level='ERROR') as log:
            clone_module.create_metadata_item('add_metadata_field', mock_metadata_fields, self.mock_target_config)
            self.assertIn('Error creating metadata field', log.output[0])

    @patch('cloudinary.api.add_metadata_rule')
    def test_create_metadata_item_rule_with_error(self, mock_add_metadata_rule):
        """Test creating metadata rule with API error"""
        mock_metadata_rules = {
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
        
        mock_add_metadata_rule.side_effect = Exception("API Error")
        
        with self.assertLogs(logger, level='ERROR') as log:
            clone_module.create_metadata_item('add_metadata_rule', mock_metadata_rules, self.mock_target_config)
            self.assertIn('Error creating metadata field', log.output[0])

    @patch.object(clone_module, 'create_metadata_item')
    @patch.object(clone_module, 'list_metadata_items')
    def test_compare_create_metadata_items_new_fields(self, mock_list, mock_create):
        """Test comparing and creating new metadata fields"""
        mock_source_fields = {
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

        mock_destination_fields = []
        
        clone_module.compare_create_metadata_items(mock_source_fields, mock_destination_fields, self.mock_target_config, key="metadata_fields")
        
        # Both fields should be created
        self.assertEqual(mock_create.call_count, 2)
        mock_create.assert_any_call(mock_source_fields[0])
        mock_create.assert_any_call(mock_source_fields[1])

    @patch.object(clone_module, 'create_metadata_item')
    @patch.object(clone_module, 'list_metadata_items')
    def test_compare_create_metadata_items_new_rules(self, mock_list, mock_create):
        """Test comparing and creating new metadata rules"""
        mock_source_metadata_rules = [
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

        mock_destination_metadata_rules = []
        
        clone_module.compare_create_metadata_items(mock_source_metadata_rules, mock_destination_metadata_rules, self.mock_target_config, key="metadata_rules")
        
        # Both rules should be created
        self.assertEqual(mock_create.call_count, 2)
        mock_create.assert_any_call('add_metadata_rule', mock_source_metadata_rules[0])
        mock_create.assert_any_call('add_metadata_rule', mock_source_metadata_rules[1])
    
    @patch.object(clone_module, 'create_metadata_item')
    @patch.object(clone_module, 'list_metadata_items')
    def test_compare_create_metadata_items_existing_fields(self, mock_list, mock_create):
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
        mock_destination_fields = [
            {
                'external_id': 'field1',
                'type': 'string',
                'label': 'Field 1'
            }
        ]
        
        clone_module.compare_create_metadata_items(mock_source_fields, mock_destination_fields, self.mock_target_config, key="metadata_fields")
        
        # No fields should be created
        mock_create.assert_not_called()

    @patch.object(clone_module, 'create_metadata_item')
    @patch.object(clone_module, 'list_metadata_items')
    def test_compare_create_metadata_items_existing_rules(self, mock_list, mock_create):
        """Test comparing when rules already exist"""

        mock_source_metadata_rules = [
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
        
        # Simulate destination already having the rule
        mock_destination_metadata_rules = [
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
        
        clone_module.compare_create_metadata_items(mock_source_metadata_rules, mock_destination_metadata_rules, self.mock_target_config, key="metadata_rules")
        
        # No rules should be created
        mock_create.assert_not_called()
    
    @patch.object(clone_module, 'create_metadata_item')
    @patch.object(clone_module, 'list_metadata_items')
    def test_compare_create_metadata_items_mixed_scenario(self, mock_list, mock_create):
        """Test comparing with mix of new and existing fields"""
        mock_source_fields = {
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
        mock_destination_fields = [
            {
                'external_id': 'existing_field',
                'type': 'string',
                'label': 'Existing Field'
            }
        ]
        
        clone_module.compare_create_metadata_items(mock_source_fields, mock_destination_fields, self.mock_target_config, key="metadata_fields")
        
        # Only new_field should be created
        mock_create.assert_called_once_with(mock_source_fields[1])

    @patch.object(clone_module, 'create_metadata_item')
    @patch.object(clone_module, 'list_metadata_items')
    def test_compare_create_metadata_items_mixed_rules_scenario(self, mock_list, mock_create):
        """Test comparing with mix of new and existing rules"""
        mock_source_metadata_rules = [
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
        
        # Simulate destination having only one rule
        mock_destination_metadata_rules = [
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
        
        clone_module.compare_create_metadata_items(mock_source_metadata_rules, mock_destination_metadata_rules, self.mock_target_config, key="metadata_rules")
        
        # Only new_rule should be created
        mock_create.assert_called_once_with('add_metadata_rule', mock_source_metadata_rules[1])

if __name__ == '__main__':
    unittest.main()