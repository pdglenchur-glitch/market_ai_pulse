"""One-off: register a GitHub PAT with Databricks as a Git credential, so
git_source can still clone this repo once it goes private. Removes any
existing gitHub credential first (idempotent, safe to rerun).
"""
import os

from databricks.sdk import WorkspaceClient

GIT_USERNAME = "pdglenchur-glitch"


def main() -> None:
    client = WorkspaceClient(host=os.environ["DATABRICKS_HOST"], token=os.environ["DATABRICKS_TOKEN"])
    pat = os.environ["DATABRICKS_GIT_PAT"]

    existing = [c for c in client.git_credentials.list() if c.git_provider == "gitHub"]
    for cred in existing:
        print(f"Deleting existing gitHub credential id={cred.credential_id}")
        client.git_credentials.delete(cred.credential_id)

    created = client.git_credentials.create(
        git_provider="gitHub",
        personal_access_token=pat,
        git_username=GIT_USERNAME,
    )
    print(f"Created git credential id={created.credential_id} for {created.git_username}")

    print("Current gitHub credentials:")
    for cred in client.git_credentials.list():
        if cred.git_provider == "gitHub":
            print(f"  id={cred.credential_id} username={cred.git_username}")


if __name__ == "__main__":
    main()
