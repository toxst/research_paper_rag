########################################################
#             CODE TO TEST R2 CONNECTION               #
########################################################

# Run this file with the command: uv run python tests/test_r2.py

import os
import boto3
from dotenv import load_dotenv

load_dotenv()

s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["R2_ENDPOINT_URL"],
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    region_name="auto",
)

bucket = os.environ["R2_BUCKET_NAME"]
key = "test/hello.txt"

try:
    # Upload a small test object
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=b"Hello from Research Paper Assistant!",
    )
    print("Upload successful!")

    # Read it back
    response = s3.get_object(Bucket=bucket, Key=key)
    content = response["Body"].read().decode("utf-8")
    print("Retrieved content:", content)

    # Verify returned content
    assert content == "Hello from Research Paper Assistant!"

    # Remove the test object
    s3.delete_object(Bucket=bucket, Key=key)
    print("Test object cleaned up!")

except Exception as e:
    print(f"R2 test failed: {e}")
    raise