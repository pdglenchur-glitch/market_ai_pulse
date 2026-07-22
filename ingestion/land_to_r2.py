"""Phase 1 thin vertical slice: upload a local JSON file to the R2 bucket.

Uploads under a raw/ prefix, keyed by filename, so each source's landed
file is easy to find alongside the others.
"""
import argparse
import os
from pathlib import Path

import boto3
from dotenv import load_dotenv

load_dotenv()


def upload(local_path: Path, key: str) -> None:
    client = boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY"],
        aws_secret_access_key=os.environ["R2_SECRET_KEY"],
        region_name="auto",
    )
    bucket = os.environ["R2_BUCKET"]
    client.upload_file(str(local_path), bucket, key)
    print(f"Uploaded {local_path} to s3://{bucket}/{key}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/raw/market_data.json"))
    parser.add_argument("--key", default=None, help="Defaults to raw/<input filename>")
    args = parser.parse_args()

    key = args.key or f"raw/{args.input.name}"
    upload(args.input, key)


if __name__ == "__main__":
    main()
