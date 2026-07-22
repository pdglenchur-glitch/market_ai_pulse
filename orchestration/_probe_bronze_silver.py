"""Throwaway probe: run bronze read + bronze_to_silver as a 2-task
Databricks Job (git_source, serverless), to validate steps 3.1-3.5 before
building the full silver_to_gold layer on top.
"""
import os
import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import compute, jobs

REPO_URL = "https://github.com/pdglenchur-glitch/market_ai_pulse"


def main() -> None:
    client = WorkspaceClient(host=os.environ["DATABRICKS_HOST"], token=os.environ["DATABRICKS_TOKEN"])

    env_spec = compute.Environment(environment_version="3")

    created = client.jobs.create(
        name="market-ai-pulse-probe-bronze-silver",
        git_source=jobs.GitSource(
            git_url=REPO_URL,
            git_provider=jobs.GitProvider.GIT_HUB,
            git_branch="main",
        ),
        tasks=[
            jobs.Task(
                task_key="bronze_read",
                spark_python_task=jobs.SparkPythonTask(
                    python_file="databricks/land_volume_to_bronze.py",
                    source=jobs.Source.GIT,
                ),
                environment_key="default",
            ),
            jobs.Task(
                task_key="bronze_to_silver",
                depends_on=[jobs.TaskDependency(task_key="bronze_read")],
                spark_python_task=jobs.SparkPythonTask(
                    python_file="databricks/bronze_to_silver.py",
                    source=jobs.Source.GIT,
                ),
                environment_key="default",
            ),
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

    print("PASS: bronze + silver job ran successfully")
    client.jobs.delete(created.job_id)
    print("Cleaned up probe job")


if __name__ == "__main__":
    main()
