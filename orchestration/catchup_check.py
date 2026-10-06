"""Decides whether the catch-up workflow needs to publish.

Databricks Free Edition sometimes withholds serverless compute from this
account for hours: the file-arrival trigger still fires, but 10-22h late, long
after pipeline.yml has given up waiting (PROJECT_MEMORY bug #27). The transform
then rebuilds gold inside Databricks with nothing left to export it.

This answers one question using only the Jobs API (control plane, no
serverless compute, no SQL warehouse): has a transform run succeeded since the
last time anything was published? It writes needed=true/false to
$GITHUB_OUTPUT, plus the run id and end time for the issue comment.
"""
import os
import subprocess
from datetime import datetime, timezone

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import jobs

JOB_NAME = "market-ai-pulse-transform"
PUBLISHED_PATHS = ["docs/data", "monitoring/pipeline_report.ipynb"]


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat(timespec="seconds")


def last_publish_ms() -> int:
    # Only the bot publishes; a human commit editing the report's code must not
    # count as a publish, or it would hide an unexported transform run.
    out = subprocess.run(
        ["git", "log", "-1", "--format=%ct", "-F", "--author=github-actions[bot]", "--", *PUBLISHED_PATHS],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return int(out) * 1000 if out else 0


def write_outputs(**values: str) -> None:
    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        for key, value in values.items():
            f.write(f"{key}={value}\n")


def main() -> None:
    client = WorkspaceClient(host=os.environ["DATABRICKS_HOST"], token=os.environ["DATABRICKS_TOKEN"])
    job = next(iter(client.jobs.list(name=JOB_NAME)))

    if list(client.jobs.list_runs(job_id=job.job_id, active_only=True)):
        print("A transform run is in progress; the next catch-up check will pick it up.")
        write_outputs(needed="false")
        return

    published_ms = last_publish_ms()
    print(f"Last publish commit: {iso(published_ms) if published_ms else 'none found'}")

    for run in client.jobs.list_runs(job_id=job.job_id, completed_only=True, limit=25):
        if run.state.result_state != jobs.RunResultState.SUCCESS or not run.end_time:
            continue
        print(f"Newest successful transform run: {run.run_id}, ended {iso(run.end_time)}")
        if run.end_time > published_ms:
            print("It finished after the last publish, so its gold tables were never exported.")
            write_outputs(needed="true", run_id=str(run.run_id), run_end=iso(run.end_time))
        else:
            print("Already published; nothing to do.")
            write_outputs(needed="false")
        return

    print("No successful transform run found.")
    write_outputs(needed="false")


if __name__ == "__main__":
    main()
