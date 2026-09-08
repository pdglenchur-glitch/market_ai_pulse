"""Push a raw source JSON into the Unity Catalog volume via the Databricks
Files API.

Files land under a per-run timestamped subdirectory,
/Volumes/workspace/default/raw_landing/<UTC timestamp>/<name>.json, rather
than being overwritten in place. Two reasons:

1. It gives the transform job a reliable **file-arrival trigger**. Databricks
   Free Edition disabled the Jobs API `run-now` call this pipeline used to
   kick off the transform (2026-09-07, bug #24), so the job now fires itself
   when new files appear in raw_landing/. A genuinely new path triggers that
   reliably; an in-place overwrite of an existing path does not.
2. It keeps a short history of exactly what each run landed, which makes a
   bad run easy to inspect after the fact.

RUN_STAMP is module-level so every source landed by one `python
run_ingestion.py` process shares the same subdirectory.
"""
import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

from databricks.sdk import WorkspaceClient
from dotenv import load_dotenv

load_dotenv()

VOLUME_ROOT = "/Volumes/workspace/default/raw_landing"
RUN_STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def upload(local_path: Path, root: str = VOLUME_ROOT, stamp: str = RUN_STAMP) -> None:
    client = WorkspaceClient(host=os.environ["DATABRICKS_HOST"], token=os.environ["DATABRICKS_TOKEN"])
    dest_path = f"{root}/{stamp}/{local_path.name}"
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
