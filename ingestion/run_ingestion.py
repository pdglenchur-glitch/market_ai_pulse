"""Single ingestion entrypoint (step 2.1).

Runs every pull_*.py source and lands each resulting file in both R2 and
the Databricks volume. This is the one command pipeline.yml calls for the
"ingest" + "stage" steps of the weekly run (Section 2 of PROJECT_PLAN.md).

Sources are added here incrementally as Phase 2 builds each one out.

One source failing doesn't abort the rest: confirmed for real on
2026-08-07 that arXiv (pull_research_pace, last in SOURCES) can be
unavailable for an extended stretch, well beyond what retry-with-backoff
inside a single run can ride out. Before this fix, that one flaky source
aborted the whole script with a non-zero exit code even after
market/macro/attention/dev_momentum had already succeeded and uploaded,
which in turn made pipeline.yml skip transform/export/publish entirely -
every dashboard panel went stale for the day over one non-critical
source, not just Research Pace. Now each source is isolated: a failure
is logged and skipped, and the run only fails loudly (non-zero exit, so
the existing GitHub Issue alert fires) if every single source failed,
which is the real "something's fundamentally broken" signal. A single
missing source shows up instead in monitoring/daily_report.ipynb's
per-source freshness check, which exists specifically for this.
"""
import land_to_databricks_volume
import land_to_r2
import pull_attention_data
import pull_dev_momentum
import pull_macro_data
import pull_market_data
import pull_research_pace

SOURCES = [
    pull_market_data,
    pull_macro_data,
    pull_attention_data,
    pull_dev_momentum,
    pull_research_pace,
]


def main() -> None:
    failed = []
    for source in SOURCES:
        name = source.__name__
        try:
            path = source.run()
            land_to_r2.upload(path, f"raw/{path.name}")
            land_to_databricks_volume.upload(path)
        except Exception as exc:  # noqa: BLE001
            print(f"  {name} failed, continuing with remaining sources: {exc!r}")
            failed.append(name)

    if failed:
        print(f"Ingestion finished with {len(failed)} of {len(SOURCES)} source(s) failing: {', '.join(failed)}")
        if len(failed) == len(SOURCES):
            raise RuntimeError("every ingestion source failed, nothing was landed this run")


if __name__ == "__main__":
    main()
