"""Single ingestion entrypoint (step 2.1).

Runs every pull_*.py source and lands each resulting file in both R2 and
the Databricks volume. This is the one command pipeline.yml calls for the
"ingest" + "stage" steps of the weekly run (Section 2 of PROJECT_PLAN.md).

Sources are added here incrementally as Phase 2 builds each one out.
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
    for source in SOURCES:
        path = source.run()
        land_to_r2.upload(path, f"raw/{path.name}")
        land_to_databricks_volume.upload(path)


if __name__ == "__main__":
    main()
