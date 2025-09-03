#!/usr/bin/env python3
"""
Debug the upload process with metadata
"""
import os
from dotenv import load_dotenv
import cloudinary
from cloudinary import uploader

# Load environment variables
load_dotenv()

def debug_upload_with_metadata():
    """Debug the upload process to see if metadata is being applied"""
    print("=== DEBUGGING UPLOAD WITH METADATA ===")

    # Configure target cloud
    cloudinary.config(cloud_name='rancloud4-clone',
                     api_key='261979336168998',
                     api_secret='vWhrENVGAw51yxcYJMuk3wyes20')

    print("✅ Configured target cloud")

    # Test uploading from a source URL with metadata
    source_url = "https://rancloud4-res.cloudinary.com/image/upload/v1749454332/CMB01_WHT01_A_bl7xze.tiff"

    metadata_to_add = {
        'sku': 'WB1022',
        'smd_alt': 'A white, perforated plastic container with a handle on the top.'
    }

    print(f"Source URL: {source_url}")
    print(f"Metadata to add: {metadata_to_add}")

    try:
        print("Uploading with metadata...")
        result = uploader.upload(source_url,
                               public_id='debug_test_asset',
                               metadata=metadata_to_add,
                               overwrite=True)

        print("✅ Upload successful!")
        print(f"Public ID: {result.get('public_id')}")

        # Check if metadata was applied
        from cloudinary import api
        uploaded_asset = api.resource('debug_test_asset', resource_type='image')
        uploaded_metadata = uploaded_asset.get('metadata', {})

        print(f"Uploaded asset metadata: {uploaded_metadata}")

        if uploaded_metadata:
            print("✅ Metadata successfully applied during upload!")
        else:
            print("❌ Metadata was not applied during upload")

    except Exception as e:
        print(f"❌ Upload failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_upload_with_metadata()
