"""Local connectivity check (Phase 0, step 0.8) — not part of the pipeline.

Confirms the four R2_* secrets can authenticate via boto3 and list bucket contents
(expected to be empty at this point).
"""
import os

import boto3
from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    client = boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY"],
        aws_secret_access_key=os.environ["R2_SECRET_KEY"],
        region_name="auto",
    )
    bucket = os.environ["R2_BUCKET"]

    response = client.list_objects_v2(Bucket=bucket)
    contents = response.get("Contents", [])
    print(f"Bucket '{bucket}' object count: {len(contents)}")
    for obj in contents:
        print(f"  {obj['Key']}")
    print("PASS: authenticated and listed bucket contents")


if __name__ == "__main__":
    main()
