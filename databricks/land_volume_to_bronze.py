"""Lakeflow job task (formalizes Phase 1 step 1.7 for all 5 sources): read
each source's raw JSON file from the raw_landing volume and overwrite its
bronze Delta table. Runs inside the job via git_source, so `spark` is
provided by the runtime - no explicit connection needed.

Ingestion lands each run's files under a timestamped subdirectory
(raw_landing/<stamp>/<name>.json - see ingestion/land_to_databricks_volume.py
for why). For each source, read from the newest subdirectory that actually
contains that source's file. Doing it per-source, not per-run, preserves the
partial-failure behaviour from bug #20: if one source failed to land this
run, bronze still refreshes from that source's last good file instead of
failing the whole job. A flat-layout path (raw_landing/<name>.json) is
accepted as a fallback for anything landed before the timestamped-subdir
change.

Bronze stays as close to the raw landed file as possible (untouched,
one row per run); typing/dedup/historization happens in bronze_to_silver.py.
"""
import os

VOLUME_ROOT = "/Volumes/workspace/default/raw_landing"
SOURCES = ["market_data", "macro_data", "attention_data", "dev_momentum", "research_pace"]

spark.sql("CREATE SCHEMA IF NOT EXISTS workspace.bronze")


def latest_path_for(name: str) -> str:
    fname = f"{name}.json"
    try:
        subdirs = sorted(
            (d for d in os.listdir(VOLUME_ROOT) if os.path.isdir(f"{VOLUME_ROOT}/{d}")),
            reverse=True,
        )
    except OSError:
        subdirs = []
    for d in subdirs:
        candidate = f"{VOLUME_ROOT}/{d}/{fname}"
        if os.path.exists(candidate):
            return candidate
    flat = f"{VOLUME_ROOT}/{fname}"
    if os.path.exists(flat):
        return flat
    raise FileNotFoundError(f"no landed file found for {name} under {VOLUME_ROOT}")


for name in SOURCES:
    path = latest_path_for(name)
    df = spark.read.option("multiline", "true").json(path)
    df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
        f"workspace.bronze.{name}"
    )
    print(f"Refreshed workspace.bronze.{name} from {path}")
