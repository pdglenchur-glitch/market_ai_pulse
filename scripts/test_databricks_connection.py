"""Local connectivity check (Phase 0, steps 0.6-0.7) — not part of the pipeline.

Confirms DATABRICKS_HOST/DATABRICKS_TOKEN can list catalogs (expects `workspace`)
and that the raw_landing volume is visible at /Volumes/workspace/default/raw_landing/.
"""
import os
import sys

from databricks.sdk import WorkspaceClient
from dotenv import load_dotenv

load_dotenv()

VOLUME_PATH = "/Volumes/workspace/default/raw_landing/"


def main() -> None:
    host = os.environ["DATABRICKS_HOST"]
    token = os.environ["DATABRICKS_TOKEN"]
    client = WorkspaceClient(host=host, token=token)

    catalogs = [c.name for c in client.catalogs.list()]
    print(f"Catalogs: {catalogs}")
    if "workspace" not in catalogs:
        sys.exit("FAIL: 'workspace' catalog not found")
    print("PASS: 'workspace' catalog found")

    entries = client.files.list_directory_contents(VOLUME_PATH)
    names = [e.path for e in entries]
    print(f"Volume '{VOLUME_PATH}' contents: {names}")
    print("PASS: raw_landing volume is reachable")


if __name__ == "__main__":
    main()
