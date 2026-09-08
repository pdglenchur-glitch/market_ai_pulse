"""Keeps the Lakeflow transform job's definition in sync with
databricks/lakeflow_job_config.yml (create-or-update by name), then **waits**
for the run that Databricks starts on its own via the job's file-arrival
trigger - it no longer starts the run itself.

Why: on 2026-09-07 Databricks Free Edition disabled the Jobs API `run-now`
call for this org ("Triggering new runs ... is currently disabled
temporarily" - PROJECT_MEMORY bug #24), while manual runs and Databricks's
own triggers kept working. So the job now carries a file-arrival trigger on
the raw_landing volume: GitHub Actions lands the ingested files (a new
timestamped subdirectory each run), Databricks sees them and runs the job,
and this script polls jobs.list_runs for that run and fails loudly if it
doesn't finish successfully.

`ensure_job` still runs (it's jobs.reset / jobs.create, not run-now, so it's
allowed) so the job definition can never drift from git.
"""
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml
from databricks.sdk import WorkspaceClient
from databricks.sdk.service import compute, jobs

CONFIG_PATH = Path(__file__).parent.parent / "databricks" / "lakeflow_job_config.yml"
POLL_INTERVAL_SECONDS = 15
# The file-arrival trigger waits for the landing dir to go quiet (~60s by
# default) before firing, so a run should appear within a couple of minutes
# of ingestion finishing. Give it a wide margin for Databricks-side queueing.
RUN_APPEAR_TIMEOUT_SECONDS = 15 * 60
RUN_FINISH_TIMEOUT_SECONDS = 25 * 60
# Look back a few minutes for "our" run, in case the trigger fired while the
# previous ingestion step was still wrapping up.
SINCE_BUFFER_SECONDS = 4 * 60


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text())


def build_tasks(config: dict) -> list[jobs.Task]:
    tasks = []
    for t in config["tasks"]:
        depends_on = [jobs.TaskDependency(task_key=t["depends_on"])] if t.get("depends_on") else None
        tasks.append(
            jobs.Task(
                task_key=t["task_key"],
                depends_on=depends_on,
                spark_python_task=jobs.SparkPythonTask(python_file=t["python_file"], source=jobs.Source.GIT),
                environment_key="default",
            )
        )
    return tasks


def build_trigger(config: dict) -> jobs.TriggerSettings | None:
    fa = config.get("trigger", {}).get("file_arrival")
    if not fa:
        return None
    return jobs.TriggerSettings(
        file_arrival=jobs.FileArrivalTriggerConfiguration(url=fa["url"])
    )


def ensure_job(client: WorkspaceClient, config: dict) -> tuple[int, bool]:
    """Returns (job_id, had_trigger_before)."""
    name = config["name"]
    existing = list(client.jobs.list(name=name))

    settings = dict(
        name=name,
        git_source=jobs.GitSource(
            git_url=config["git"]["url"],
            git_provider=jobs.GitProvider.GIT_HUB,
            git_branch=config["git"]["branch"],
        ),
        tasks=build_tasks(config),
        trigger=build_trigger(config),
        environments=[
            jobs.JobEnvironment(
                environment_key="default",
                spec=compute.Environment(environment_version=str(config["environment_version"])),
            )
        ],
    )

    if existing:
        job_id = existing[0].job_id
        current = client.jobs.get(job_id=job_id)
        had_trigger_before = bool(getattr(current.settings, "trigger", None))
        client.jobs.reset(job_id=job_id, new_settings=jobs.JobSettings(**settings))
        print(f"Updated existing job_id={job_id} (had_trigger_before={had_trigger_before})")
        return job_id, had_trigger_before

    created = client.jobs.create(**settings)
    print(f"Created job_id={created.job_id}")
    return created.job_id, False


def wait_for_triggered_run(client: WorkspaceClient, job_id: int, since_ms: int, appear_timeout: int) -> None:
    print(f"Waiting for a file-arrival-triggered run started at/after {datetime.fromtimestamp(since_ms/1000, tz=timezone.utc).isoformat()}")

    appear_deadline = time.time() + appear_timeout
    run_id = None
    while time.time() < appear_deadline:
        runs = list(client.jobs.list_runs(job_id=job_id, start_time_from=since_ms, limit=25))
        if runs:
            newest = max(runs, key=lambda r: r.start_time or 0)
            run_id = newest.run_id
            print(f"Found run_id={run_id} (started {datetime.fromtimestamp((newest.start_time or 0)/1000, tz=timezone.utc).isoformat()})")
            break
        time.sleep(POLL_INTERVAL_SECONDS)

    if run_id is None:
        raise TimeoutError(
            "No transform run appeared - the file-arrival trigger did not fire within "
            f"{appear_timeout // 60} min of ingestion landing files."
        )

    finish_deadline = time.time() + RUN_FINISH_TIMEOUT_SECONDS
    while True:
        run_status = client.jobs.get_run(run_id)
        state = run_status.state
        print(f"Life cycle state: {state.life_cycle_state}, result: {state.result_state}")
        if state.life_cycle_state in (
            jobs.RunLifeCycleState.TERMINATED,
            jobs.RunLifeCycleState.SKIPPED,
            jobs.RunLifeCycleState.INTERNAL_ERROR,
        ):
            break
        if time.time() > finish_deadline:
            raise TimeoutError(f"Transform run {run_id} did not finish within {RUN_FINISH_TIMEOUT_SECONDS // 60} min.")
        time.sleep(POLL_INTERVAL_SECONDS)

    if state.result_state != jobs.RunResultState.SUCCESS:
        for task_run in run_status.tasks or []:
            print(f"Task {task_run.task_key}: {task_run.state.result_state}")
        raise RuntimeError(f"Lakeflow job run {run_id} failed: {state.state_message}")

    print(f"Lakeflow job run {run_id} succeeded")


def main() -> None:
    client = WorkspaceClient(host=os.environ["DATABRICKS_HOST"], token=os.environ["DATABRICKS_TOKEN"])
    config = load_config()

    since_ms = int(time.time() * 1000) - SINCE_BUFFER_SECONDS * 1000
    job_id, had_trigger_before = ensure_job(client, config)

    # On the run that first wires the trigger up, the files for THIS run landed
    # before the trigger existed, so Databricks establishes them as its
    # baseline and won't run the job. Expected exactly once - wait only briefly
    # for the off chance it fires on setup, then move on. Once the trigger is
    # in place, a no-show is a real failure and gets the full timeout.
    appear_timeout = 6 * 60 if not had_trigger_before else RUN_APPEAR_TIMEOUT_SECONDS

    try:
        wait_for_triggered_run(client, job_id, since_ms, appear_timeout)
    except TimeoutError as exc:
        if not had_trigger_before:
            print(f"{exc}\nThis is the first run with the file-arrival trigger configured; "
                  "the next pipeline run's files will trigger the job. Continuing so export "
                  "still publishes the current gold tables.")
            return
        raise


if __name__ == "__main__":
    main()
