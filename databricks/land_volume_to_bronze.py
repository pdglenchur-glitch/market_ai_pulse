"""Lakeflow job task (formalizes Phase 1 step 1.7 for all 5 sources): read
each source's raw JSON file from the raw_landing volume and overwrite its
bronze Delta table. Runs inside the job via git_source, so `spark` is
provided by the runtime — no explicit connection needed.

Bronze stays as close to the raw landed file as possible (untouched,
one row per run); typing/dedup/historization happens in bronze_to_silver.py.
"""
VOLUME_DIR = "/Volumes/workspace/default/raw_landing"
SOURCES = ["market_data", "macro_data", "attention_data", "dev_momentum", "research_pace"]

spark.sql("CREATE SCHEMA IF NOT EXISTS workspace.bronze")

for name in SOURCES:
    path = f"{VOLUME_DIR}/{name}.json"
    df = spark.read.option("multiline", "true").json(path)
    df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
        f"workspace.bronze.{name}"
    )
    print(f"Refreshed workspace.bronze.{name}")
