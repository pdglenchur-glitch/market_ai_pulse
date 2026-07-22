"""Throwaway probe: prove a real Databricks Job can be created via the SDK,
pulling code straight from our public GitHub repo (git_source), run on
serverless compute, triggered via run-now, and polled to completion.
"""
import os
import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import jobs

REPO_URL = "https://github.com/pdglenchur-glitch/market_ai_pulse"


def main() -> None:
    client = WorkspaceClient(host=os.environ["DATABRICKS_HOST"], token=os.environ["DATABRICKS_TOKEN"])

    created = client.jobs.create(
        name="market-ai-pulse-probe",
        git_source=jobs.GitSource(
            git_url=REPO_URL,
            git_provider=jobs.GitProvider.GIT_HUB,
            git_branch="main",
        ),
        tasks=[
            jobs.Task(
                task_key="probe",
                spark_python_task=jobs.SparkPythonTask(
                    python_file="databricks/_lakeflow_probe.py",
                    source=jobs.Source.GIT,
                ),
            )
        ],
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
        raise RuntimeError(f"Probe job failed: {state.state_message}")

    print("PASS: probe job ran successfully via git_source on serverless compute")

    client.jobs.delete(created.job_id)
    print("Cleaned up probe job")


if __name__ == "__main__":
    main()
