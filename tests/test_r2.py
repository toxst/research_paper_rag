########################################################
#             CODE TO TEST R2 CONNECTION               #
########################################################

# Run this file with the command: uv run python -m tests.test_r2

import sys
from pathlib import Path

# Add project root to path for config import
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from ingestion.r2_storage import R2Storage, R2StorageError


def test_r2_connection() -> None:
    """Test R2 connection using config.py settings."""
    # Get R2 config from config module (supports st.secrets or env vars)
    r2_config = config.R2_CONFIG

    # Validate required settings are present
    missing = [k for k, v in r2_config.items() if not v]
    if missing:
        print(f"Missing R2 configuration: {missing}")
        print("Set via Streamlit secrets (.streamlit/secrets.toml) or environment variables")
        sys.exit(1)

    print(f"Testing R2 connection to bucket: {r2_config['R2_BUCKET_NAME']}")
    print(f"Endpoint: {r2_config['R2_ENDPOINT_URL']}")

    try:
        # Create R2Storage client using the shared from_settings method
        storage = R2Storage.from_settings(r2_config)
        print("R2Storage client created successfully!")

        # Test with a small object
        test_key = "test/connection_check.txt"
        test_content = b"R2 connection test from Research Paper Assistant!"

        # Upload
        storage._client.put_object(
            Bucket=storage.bucket,
            Key=test_key,
            Body=test_content,
        )
        print("Upload successful!")

        # Read back and verify
        response = storage._client.get_object(Bucket=storage.bucket, Key=test_key)
        retrieved = response["Body"].read()
        assert retrieved == test_content, "Content mismatch!"
        print("Retrieved content verified!")

        # Clean up
        storage._client.delete_object(Bucket=storage.bucket, Key=test_key)
        print("Test object cleaned up!")

        print("\n[OK] R2 connection test PASSED")

    except R2StorageError as e:
        print(f"\n[ERROR] R2 configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] R2 connection test FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    test_r2_connection()