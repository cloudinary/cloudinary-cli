#!/usr/bin/env python3
"""
Debug metadata copying issue
"""
import os
from dotenv import load_dotenv
import cloudinary
from cloudinary_cli.modules.clone import search_assets, _prepare_upload_list, get_metadata_schema

# Load environment variables
load_dotenv()

def debug_metadata_copy():
    """Debug the metadata copying process step by step"""
    print("=== DEBUGGING METADATA COPY ISSUE ===\n")

    # Step 1: Check if source assets have metadata
    print("1. Checking source assets for metadata...")
    cloudinary.config(cloud_name='rancloud4', api_key='368291634223844', api_secret='asZdYkxUC64cMr66hVlA_bm_o5o')

    # Search for assets with metadata
    search_results = search_assets('resource_type:image', force=False, include_metadata=True)
    assets = search_results.get('resources', [])

    print(f"   Found {len(assets)} assets")

    assets_with_metadata = []
    for asset in assets[:10]:  # Check first 10 assets
        if asset.get('metadata') and len(asset.get('metadata', {})) > 0:
            assets_with_metadata.append(asset)
            metadata = asset.get('metadata', {})
            print(f"   ✅ Asset {asset['public_id']} has metadata: {list(metadata.keys())}")

    if not assets_with_metadata:
        print("   ❌ No assets with metadata found in first 10 assets")
        print("   💡 Make sure your source assets actually have metadata!")
        return False

    # Use the first asset with metadata for testing
    test_asset = assets_with_metadata[0]
    print(f"\n2. Testing with asset: {test_asset['public_id']}")
    print(f"   Source metadata: {test_asset.get('metadata', {})}")

    # Step 2: Check target schema
    print("\n3. Checking target schema...")
    cloudinary.config(cloud_name='rancloud4-clone', api_key='261979336168998', api_secret='vWhrENVGAw51yxcYJMuk3wyes20')
    target_schema = get_metadata_schema()
    print(f"   Target schema fields: {list(target_schema.keys())}")

    # Step 3: Test metadata filtering
    print("\n4. Testing metadata filtering...")
    from cloudinary_cli.modules.clone import filter_metadata_for_asset
    source_metadata = test_asset.get('metadata', {})
    filtered_metadata = filter_metadata_for_asset(source_metadata, target_schema)
    print(f"   Filtered metadata: {filtered_metadata}")

    # Step 4: Test upload preparation
    print("\n5. Testing upload preparation...")
    target_config = {'cloud_name': 'rancloud4-clone', 'api_key': '261979336168998', 'api_secret': 'vWhrENVGAw51yxcYJMuk3wyes20'}

    upload_list = _prepare_upload_list(
        {'resources': [test_asset]},
        target_config,
        False, False, None, None, 3600, [], True  # copy_metadata=True
    )

    if upload_list:
        asset_url, options = upload_list[0]
        print(f"   Asset URL: {asset_url}")
        print(f"   Options keys: {list(options.keys())}")
        if 'metadata' in options:
            print(f"   ✅ Metadata in options: {options['metadata']}")
        else:
            print("   ❌ No metadata in options!")
    else:
        print("   ❌ No upload items prepared!")

    # Step 5: Test actual upload
    print("\n6. Testing actual upload...")
    if upload_list:
        from cloudinary_cli.utils.api_utils import upload_file
        asset_url, options = upload_list[0]

        print(f"   Uploading from: {asset_url}")
        print(f"   With metadata: {'metadata' in options}")

        try:
            result = upload_file(asset_url, options)
            print("   ✅ Upload completed")

            # Check if uploaded asset has metadata
            from cloudinary import api
            uploaded_asset = api.resource(options['public_id'], resource_type='image')
            uploaded_metadata = uploaded_asset.get('metadata', {})
            print(f"   Uploaded asset metadata: {uploaded_metadata}")

            if uploaded_metadata:
                print("   ✅ SUCCESS: Metadata copied successfully!")
                return True
            else:
                print("   ❌ FAILURE: Metadata not copied!")
                return False

        except Exception as e:
            print(f"   ❌ Upload failed: {e}")
            return False

if __name__ == "__main__":
    success = debug_metadata_copy()
    if not success:
        print("\n🔍 DEBUGGING RESULTS:")
        print("   • Check if source assets actually have metadata")
        print("   • Verify target cloud has the required metadata fields")
        print("   • Make sure --copy_metadata flag is used in clone command")
        print("   • Check if upload_file function is properly handling metadata")
