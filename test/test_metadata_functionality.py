#!/usr/bin/env python3
"""
Test suite for metadata functionality in Cloudinary CLI
"""
import os
import unittest
from unittest.mock import patch, MagicMock
from dotenv import load_dotenv
import cloudinary
from cloudinary import api

# Load test environment
load_dotenv()

class TestMetadataFunctionality(unittest.TestCase):
    """Test cases for metadata schema replication and copying"""

    def setUp(self):
        """Set up test environment"""
        # Configure cloudinary with test credentials
        cloudinary.config(cloud_name='rancloud4',
                         api_key='368291634223844',
                         api_secret='asZdYkxUC64cMr66hVlA_bm_o5o')

    def test_cloudinary_configuration(self):
        """Test that Cloudinary is properly configured"""
        config = cloudinary.config()
        self.assertEqual(config.cloud_name, 'rancloud4')
        self.assertEqual(config.api_key, '368291634223844')
        self.assertIsNotNone(config.api_secret)

    def test_list_metadata_fields_api(self):
        """Test the list_metadata_fields API call"""
        try:
            response = api.list_metadata_fields()
            self.assertIsNotNone(response)

            # Check that we can access metadata_fields
            if hasattr(response, 'get'):
                fields = response.get('metadata_fields')
            else:
                fields = response['metadata_fields']

            self.assertIsInstance(fields, list)

            # Check that sku field exists (as mentioned by user)
            field_ids = [field['external_id'] for field in fields if 'external_id' in field]
            self.assertIn('sku', field_ids, "SKU field should exist in metadata fields")

        except Exception as e:
            self.fail(f"list_metadata_fields API call failed: {e}")

    def test_get_specific_metadata_field(self):
        """Test getting a specific metadata field by ID"""
        try:
            sku_field = api.metadata_field_by_field_id('sku')
            self.assertIsNotNone(sku_field)
            self.assertEqual(sku_field['external_id'], 'sku')
            self.assertIn('label', sku_field)
            self.assertIn('type', sku_field)
        except Exception as e:
            self.fail(f"Failed to get SKU field: {e}")

    def test_metadata_schema_parsing(self):
        """Test parsing metadata schema from API response"""
        from cloudinary_cli.modules.clone import get_metadata_schema

        schema = get_metadata_schema()
        self.assertIsInstance(schema, dict)

        # Check that sku field is in schema
        self.assertIn('sku', schema, "SKU field should be in parsed schema")

        # Check field structure
        sku_field = schema['sku']
        self.assertIn('external_id', sku_field)
        self.assertIn('label', sku_field)
        self.assertIn('type', sku_field)

    @patch('cloudinary.api.list_metadata_fields')
    def test_get_metadata_schema_with_mock(self, mock_list_fields):
        """Test get_metadata_schema with mocked API response"""
        from cloudinary_cli.modules.clone import get_metadata_schema

        # Mock response
        mock_response = {
            'metadata_fields': [
                {
                    'external_id': 'test_field',
                    'label': 'Test Field',
                    'type': 'string'
                },
                {
                    'external_id': 'sku',
                    'label': 'SKU',
                    'type': 'string',
                    'mandatory': False
                }
            ]
        }
        mock_list_fields.return_value = mock_response

        schema = get_metadata_schema()
        self.assertIn('test_field', schema)
        self.assertIn('sku', schema)
        self.assertEqual(schema['sku']['label'], 'SKU')

    def test_validate_metadata_compatibility(self):
        """Test metadata compatibility validation"""
        from cloudinary_cli.modules.clone import validate_metadata_compatibility

        # Mock source assets with metadata
        source_assets = {
            'resources': [
                {
                    'public_id': 'test_asset_1',
                    'metadata': {
                        'sku': 'TEST123',
                        'position': '1',
                        'deleted--41e3d590820d2eff--group_name': 'deleted_value1',
                        'deleted--49bada32aabed19b--color': 'deleted_value2'
                    }
                },
                {
                    'public_id': 'test_asset_2',
                    'metadata': {
                        'sku': 'TEST456',
                        'deleted--f788e23081ca6dea--group': 'deleted_value3'
                    }
                }
            ]
        }

        # Mock target schema
        target_schema = {
            'sku': {'external_id': 'sku', 'type': 'string'},
            'position': {'external_id': 'position', 'type': 'integer'}
        }

        # Test with copy_metadata enabled
        result = validate_metadata_compatibility(source_assets, target_schema, copy_metadata=True)
        self.assertTrue(result['valid'], "Validation should pass for compatible metadata")
        self.assertEqual(len(result['warnings']), 0, "No warnings expected")
        self.assertEqual(len(result['errors']), 0, "No errors expected")

        # Test with missing field in target schema
        incomplete_schema = {'sku': {'external_id': 'sku', 'type': 'string'}}
        result = validate_metadata_compatibility(source_assets, incomplete_schema, copy_metadata=True)
        self.assertFalse(result['valid'], "Validation should fail for missing fields")
        self.assertIn('position', result['errors'][0], "Error should mention missing position field")

    def test_filter_metadata_for_asset(self):
        """Test filtering metadata for target schema compatibility"""
        from cloudinary_cli.modules.clone import filter_metadata_for_asset

        asset_metadata = {
            'sku': 'TEST123',
            'position': '1',
            'nonexistent_field': 'value',
            'deleted--41e3d590820d2eff--group_name': 'deleted_value1',
            'deleted--49bada32aabed19b--color': 'deleted_value2',
            'deleted--f788e23081ca6dea--group': 'deleted_value3'
        }

        target_schema = {
            'sku': {'external_id': 'sku', 'type': 'string'},
            'position': {'external_id': 'position', 'type': 'integer'}
        }

        filtered = filter_metadata_for_asset(asset_metadata, target_schema)
        self.assertIn('sku', filtered)
        self.assertIn('position', filtered)
        self.assertNotIn('nonexistent_field', filtered)
        self.assertNotIn('deleted--41e3d590820d2eff--group_name', filtered)
        self.assertNotIn('deleted--49bada32aabed19b--color', filtered)
        self.assertNotIn('deleted--f788e23081ca6dea--group', filtered)
        self.assertEqual(filtered['sku'], 'TEST123')
        self.assertEqual(len(filtered), 2)  # Only sku and position should remain


class TestCloneWithMetadata(unittest.TestCase):
    """Test the clone command with metadata functionality"""

    def setUp(self):
        """Set up test environment for clone tests"""
        cloudinary.config(cloud_name='rancloud4',
                         api_key='368291634223844',
                         api_secret='asZdYkxUC64cMr66hVlA_bm_o5o')

    @patch('cloudinary_cli.modules.clone.search_assets')
    @patch('cloudinary_cli.modules.clone.get_metadata_schema')
    @patch('cloudinary_cli.modules.clone.validate_metadata_compatibility')
    def test_clone_with_metadata_enabled(self, mock_validate, mock_get_schema, mock_search):
        """Test clone command with metadata enabled"""
        from cloudinary_cli.modules.clone import _prepare_upload_list

        # Mock search results
        mock_search.return_value = {
            'resources': [
                {
                    'public_id': 'test_asset',
                    'type': 'upload',
                    'resource_type': 'image',
                    'metadata': {'sku': 'TEST123'}
                }
            ]
        }

        # Mock schema
        mock_get_schema.return_value = {
            'sku': {'external_id': 'sku', 'type': 'string'}
        }

        # Mock validation
        mock_validate.return_value = {'valid': True, 'warnings': [], 'errors': []}

        # Test prepare_upload_list with metadata enabled
        result = _prepare_upload_list(
            mock_search.return_value,
            {'cloud_name': 'target_cloud', 'api_key': 'test', 'api_secret': 'test'},
            False,  # overwrite
            False,  # async
            None,   # notification_url
            None,   # auth_token
            3600,   # url_expiry
            [],     # fields
            True    # copy_metadata
        )

        self.assertEqual(len(result), 1)
        asset_url, options = result[0]
        self.assertIn('metadata', options)
        self.assertEqual(options['metadata']['sku'], 'TEST123')


if __name__ == '__main__':
    # Set up test environment
    os.environ.setdefault('CLOUDINARY_URL', 'cloudinary://368291634223844:asZdYkxUC64cMr66hVlA_bm_o5o@rancloud4')

    # Run tests
    unittest.main(verbosity=2)
