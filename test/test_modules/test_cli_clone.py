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

        result = clone_module.list_metadata_items()

        mock_metadata_fields.assert_called_once()
        self.assertEqual(result, mock_metadata_fields.return_value['metadata_fields'])

    @patch('cloudinary.api.add_metadata_field')
    def test_create_metadata_item(self, mock_add_metadata_field):
        """Test creating a single metadata field"""
        metadata_field = {
            'external_id': 'test_field',
            'type': 'string',
            'label': 'Test Field',
            'mandatory': False
        }
        
        clone_module.create_metadata_item(metadata_field)

        mock_add_metadata_field.assert_called_once_with(metadata_field)

    @patch('cloudinary.api.add_metadata_field')
    def test_create_metadata_item_with_error(self, mock_add_metadata_field):
        """Test creating metadata field with API error"""
        metadata_field = {
            'external_id': 'test_field',
            'type': 'string',
            'label': 'Test Field',
            'mandatory': False
        }
        
        mock_add_metadata_field.side_effect = Exception("API Error")
        
        with self.assertLogs(logger, level='ERROR') as log:
            clone_module.create_metadata_item(metadata_field)
            self.assertIn('Error creating metadata field', log.output[0])

    @patch.object(clone_module, 'create_metadata_item')
    @patch.object(clone_module, 'list_metadata_items')
    def test_compare_create_metadata_items_new_fields(self, mock_list, mock_create):
        """Test comparing and creating new metadata fields"""
        source_fields = [
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
        
        # Simulate destination having no fields
        mock_list.return_value = []
        
        clone_module.compare_create_metadata_items(source_fields)
        
        # Both fields should be created
        self.assertEqual(mock_create.call_count, 2)
        mock_create.assert_any_call(source_fields[0])
        mock_create.assert_any_call(source_fields[1])

    @patch.object(clone_module, 'create_metadata_item')
    @patch.object(clone_module, 'list_metadata_items')
    def test_compare_create_metadata_items_existing_fields(self, mock_list, mock_create):
        """Test comparing when fields already exist"""
        source_fields = [
            {
                'external_id': 'field1',
                'type': 'string',
                'label': 'Field 1'
            }
        ]
        
        # Simulate destination already having the field
        mock_list.return_value = [
            {
                'external_id': 'field1',
                'type': 'string',
                'label': 'Field 1'
            }
        ]
        
        clone_module.compare_create_metadata_items(source_fields)
        
        # No fields should be created
        mock_create.assert_not_called()

    @patch.object(clone_module, 'create_metadata_item')
    @patch.object(clone_module, 'list_metadata_items')
    def test_compare_create_metadata_items_mixed_scenario(self, mock_list, mock_create):
        """Test comparing with mix of new and existing fields"""
        source_fields = [
            {
                'external_id': 'existing_field',
                'type': 'string',
                'label': 'Existing Field'
            },
            {
                'external_id': 'new_field',
                'type': 'integer',
                'label': 'New Field'
            }
        ]
        
        # Simulate destination having only one field
        mock_list.return_value = [
            {
                'external_id': 'existing_field',
                'type': 'string',
                'label': 'Existing Field'
            }
        ]
        
        clone_module.compare_create_metadata_items(source_fields)
        
        # Only new_field should be created
        mock_create.assert_called_once_with(source_fields[1])


if __name__ == '__main__':
    unittest.main()