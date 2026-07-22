"""Throwaway probe: run the full bronze -> silver -> gold chain as a 3-task
Databricks Job, to validate steps 3.6-3.13 before finalizing the real job
definition and trigger_and_poll_job.py.
"""
import os
import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import compute, jobs

REPO_URL = "https://github.com/pdglenchur-glitch/market_ai_pulse"


def main() -> None:
    client = WorkspaceClient(host=os.environ["DATABRICKS_HOST"], token=os.environ["DATABRICKS_TOKEN"])

    env_spec = compute.Environment(environment_version="3")

    def task(key, python_file, depends_on=None):
        return jobs.Task(
            task_key=key,
            depends_on=[jobs.TaskDependency(task_key=depends_on)] if depends_on else None,
            spark_python_task=jobs.SparkPythonTask(python_file=python_file, source=jobs.Source.GIT),
            environment_key="default",
        )

    created = client.jobs.create(
        name="market-ai-pulse-probe-full-transform",
        git_source=jobs.GitSource(git_url=REPO_URL, git_provider=jobs.GitProvider.GIT_HUB, git_branch="main"),
        tasks=[
            task("bronze_read", "databricks/land_volume_to_bronze.py"),
            task("bronze_to_silver", "databricks/bronze_to_silver.py", depends_on="bronze_read"),
            task("silver_to_gold", "databricks/silver_to_gold.py", depends_on="bronze_to_silver"),
        ],
        environments=[jobs.JobEnvironment(environment_key="default", spec=env_spec)],
    )
    print(f"Created job_id={created.job_id}")

    run = client.jobs.run_now(job_id=created.job_id)
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
        time.sleep(15)

    if state.result_state != jobs.RunResultState.SUCCESS:
        for task_run in run_status.tasks:
            print(f"Task {task_run.task_key}: {task_run.state.result_state}")
            output = client.jobs.get_run_output(task_run.run_id)
            if output.error:
                print(f"  error: {output.error}")
            if output.error_trace:
                print(f"  trace:\n{output.error_trace}")
        raise RuntimeError(f"Job failed: {state.state_message}")

    print("PASS: full bronze -> silver -> gold job ran successfully")
    client.jobs.delete(created.job_id)
    print("Cleaned up probe job")


if __name__ == "__main__":
    main()
