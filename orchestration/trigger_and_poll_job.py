"""Triggers the Lakeflow transform job via the Databricks Jobs API and polls
until it finishes, failing loudly if the run doesn't succeed (step 3.15).

The job's definition lives in databricks/lakeflow_job_config.yml and is
kept in sync here on every run (create-or-update by name), so the job
never drifts from what's in git. No native schedule is ever attached —
it only runs when this script calls run-now.
"""
import os
import time
from pathlib import Path

import yaml
from databricks.sdk import WorkspaceClient
from databricks.sdk.service import compute, jobs

CONFIG_PATH = Path(__file__).parent.parent / "databricks" / "lakeflow_job_config.yml"
POLL_INTERVAL_SECONDS = 15


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


def ensure_job(client: WorkspaceClient, config: dict) -> int:
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
        environments=[
            jobs.JobEnvironment(
                environment_key="default",
                spec=compute.Environment(environment_version=str(config["environment_version"])),
            )
        ],
    )

    if existing:
        job_id = existing[0].job_id
        client.jobs.reset(job_id=job_id, new_settings=jobs.JobSettings(**settings))
        print(f"Updated existing job_id={job_id}")
        return job_id

    created = client.jobs.create(**settings)
    print(f"Created job_id={created.job_id}")
    return created.job_id


def run_and_poll(client: WorkspaceClient, job_id: int) -> None:
    run = client.jobs.run_now(job_id=job_id)
    print(f"Started run_id={run.run_id}")

    while True:
        run_status = client.jobs.get_run(run.run_id)
        state = run_status.state
        print(f"Life cycle state: {state.life_cycle_state}, result: {state.result_state}")
        if state.life_cycle_state in (
            jobs.RunLifeCycleState.TERMINATED,
            jobs.RunLifeCycleState.SKIPPED,
            jobs.RunLifeCycleState.INTERNAL_ERROR,
        ):
            break
        time.sleep(POLL_INTERVAL_SECONDS)

    if state.result_state != jobs.RunResultState.SUCCESS:
        for task_run in run_status.tasks:
            print(f"Task {task_run.task_key}: {task_run.state.result_state}")
        raise RuntimeError(f"Lakeflow job run failed: {state.state_message}")

    print(f"Lakeflow job run {run.run_id} succeeded")


def main() -> None:
    client = WorkspaceClient(host=os.environ["DATABRICKS_HOST"], token=os.environ["DATABRICKS_TOKEN"])
    config = load_config()
    job_id = ensure_job(client, config)
    run_and_poll(client, job_id)


if __name__ == "__main__":
    main()
