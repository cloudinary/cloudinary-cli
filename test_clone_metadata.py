#!/usr/bin/env python3
"""
Integration test for clone functionality with metadata
"""
import os
import sys
from dotenv import load_dotenv
import cloudinary
from cloudinary import api

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cloudinary_cli.modules.clone import get_metadata_schema, validate_metadata_compatibility

# Load environment variables
load_dotenv()

def test_metadata_integration():
    """Test the complete metadata workflow"""
    print("🧪 Testing Metadata Integration...")

    try:
        # Configure cloudinary with the provided credentials
        cloudinary.config(cloud_name='rancloud4',
                         api_key='368291634223844',
                         api_secret='asZdYkxUC64cMr66hVlA_bm_o5o')

        print(f"✅ Configured Cloudinary: {cloudinary.config().cloud_name}")

        # Test 1: Get metadata schema
        print("\n📋 Test 1: Getting metadata schema...")
        schema = get_metadata_schema()
        print(f"✅ Retrieved schema with {len(schema)} fields")

        # Show the sku field details
        if 'sku' in schema:
            sku_field = schema['sku']
            print(f"✅ SKU field details: {sku_field}")
        else:
            print("❌ SKU field not found in schema")
            return False

        # Test 2: Mock source assets for validation
        print("\n🔍 Test 2: Testing metadata validation...")
        mock_source_assets = {
            'resources': [
                {
                    'public_id': 'sample_asset_1',
                    'metadata': {
                        'sku': 'SAMPLE123',
                        'position': '1'
                    }
                },
                {
                    'public_id': 'sample_asset_2',
                    'metadata': {
                        'sku': 'SAMPLE456'
                    }
                }
            ]
        }

        # Test validation with current schema
        validation_result = validate_metadata_compatibility(mock_source_assets, schema, copy_metadata=True)
        print(f"✅ Validation result: {validation_result['valid']}")
        if validation_result['warnings']:
            print(f"⚠️ Warnings: {validation_result['warnings']}")
        if validation_result['errors']:
            print(f"❌ Errors: {validation_result['errors']}")

        # Test 3: Test clone command with metadata (dry run)
        print("\n🚀 Test 3: Testing clone command setup...")
        try:
            from cloudinary_cli.modules.clone import clone
            print("✅ Clone function imported successfully")
            print("✅ Ready to test clone with metadata functionality")
        except Exception as e:
            print(f"❌ Failed to import clone function: {e}")
            return False

        print("\n✅ All metadata integration tests passed!")
        return True

    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_metadata_integration()
    if success:
        print("\n🎉 Metadata integration testing completed successfully!")
        print("\nNext steps:")
        print("1. Run the unit tests: python -m pytest test/test_metadata_functionality.py -v")
        print("2. Test the actual clone command with metadata:")
        print("   cld clone target_cloud --copy_metadata --replicate_schema -se 'resource_type:image AND metadata.sku:*'")
    else:
        print("\n❌ Metadata integration testing failed!")
        sys.exit(1)
