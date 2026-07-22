"""Phase 1 thin vertical slice: push a local JSON file into the Unity Catalog volume.

Uses the Databricks Files API (via the SDK) to land the same file that
land_to_r2.py uploads to R2, at /Volumes/workspace/default/raw_landing/.
"""
import argparse
import os
from pathlib import Path

from databricks.sdk import WorkspaceClient
from dotenv import load_dotenv

load_dotenv()

VOLUME_DIR = "/Volumes/workspace/default/raw_landing"


def upload(local_path: Path, dest_dir: str = VOLUME_DIR) -> None:
    client = WorkspaceClient(host=os.environ["DATABRICKS_HOST"], token=os.environ["DATABRICKS_TOKEN"])
    dest_path = f"{dest_dir}/{local_path.name}"
    with open(local_path, "rb") as f:
        client.files.upload(dest_path, f, overwrite=True)
    print(f"Uploaded {local_path} to {dest_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/raw/market_data.json"))
    args = parser.parse_args()

    upload(args.input)


if __name__ == "__main__":
    main()
