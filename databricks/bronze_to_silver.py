"""Lakeflow job task: bronze -> silver (steps 3.1-3.5).

Types, deduplicates, and historizes each source into an accumulating
silver table keyed by its natural key, via MERGE — so a rerun on the same
date/key updates that row in place instead of duplicating it. This is how
history builds up over successive weekly runs (Section 11's open question).

Runs inside the job via git_source; `spark` is provided by the runtime.
"""
from delta.tables import DeltaTable
from pyspark.sql import functions as F

spark.sql("CREATE SCHEMA IF NOT EXISTS workspace.silver")


def merge_into(table_name: str, updates_df, key_cols: list[str]) -> None:
    full_name = f"workspace.silver.{table_name}"
    if not spark.catalog.tableExists(full_name):
        updates_df.write.format("delta").saveAsTable(full_name)
        print(f"Created {full_name}")
        return

    condition = " AND ".join(f"t.{c} = s.{c}" for c in key_cols)
    (
        DeltaTable.forName(spark, full_name)
        .alias("t")
        .merge(updates_df.alias("s"), condition)
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute()
    )
    print(f"Merged into {full_name}")


# --- market_data: explode the records array, keyed by (symbol, date) ---
bronze_market = spark.table("workspace.bronze.market_data")
market_silver = bronze_market.select(F.explode("records").alias("r"), "fetched_at").select(
    F.col("r.symbol").alias("symbol"),
    F.col("r.category").alias("category"),
    F.to_date("r.date").alias("date"),
    F.col("r.open").cast("double").alias("open"),
    F.col("r.high").cast("double").alias("high"),
    F.col("r.low").cast("double").alias("low"),
    F.col("r.close").cast("double").alias("close"),
    F.col("r.volume").cast("long").alias("volume"),
    F.to_timestamp("fetched_at").alias("fetched_at"),
)
merge_into("market_data", market_silver, ["symbol", "date"])

# --- macro_data: melt named series {date, value} into (series, date, value) ---
bronze_macro = spark.table("workspace.bronze.macro_data")
series_names = [c for c in bronze_macro.columns if c != "fetched_at"]
macro_pieces = [
    bronze_macro.select(
        F.lit(series).alias("series"),
        F.to_date(F.col(f"`{series}`.date")).alias("date"),
        F.col(f"`{series}`.value").cast("double").alias("value"),
        F.to_timestamp("fetched_at").alias("fetched_at"),
    )
    for series in series_names
]
macro_silver = macro_pieces[0]
for piece in macro_pieces[1:]:
    macro_silver = macro_silver.unionByName(piece)
merge_into("macro_data", macro_silver, ["series", "date"])

# --- attention_data: melt named articles {date, views} into (article, date, views) ---
bronze_attention = spark.table("workspace.bronze.attention_data")
article_names = [c for c in bronze_attention.columns if c != "fetched_at"]
attention_pieces = [
    bronze_attention.select(
        F.lit(article).alias("article"),
        F.to_date(F.col(f"`{article}`.date")).alias("date"),
        F.col(f"`{article}`.views").cast("long").alias("views"),
        F.to_timestamp("fetched_at").alias("fetched_at"),
    )
    for article in article_names
]
attention_silver = attention_pieces[0]
for piece in attention_pieces[1:]:
    attention_silver = attention_silver.unionByName(piece)
merge_into("attention_data", attention_silver, ["article", "date"])

# --- dev_momentum: melt named repos {stars} into (repo, snapshot_date, stars).
# No per-repo date in the source, so the run's own fetched_at date is the key's date part ---
bronze_dev = spark.table("workspace.bronze.dev_momentum")
repo_names = [c for c in bronze_dev.columns if c != "fetched_at"]
dev_pieces = [
    bronze_dev.select(
        F.lit(repo).alias("repo"),
        F.to_date("fetched_at").alias("snapshot_date"),
        F.col(f"`{repo}`.stars").cast("long").alias("stars"),
        F.to_timestamp("fetched_at").alias("fetched_at"),
    )
    for repo in repo_names
]
dev_silver = dev_pieces[0]
for piece in dev_pieces[1:]:
    dev_silver = dev_silver.unionByName(piece)
merge_into("dev_momentum", dev_silver, ["repo", "snapshot_date"])

# --- research_pace: melt named categories {count} into (category, snapshot_date, count) ---
bronze_research = spark.table("workspace.bronze.research_pace")
category_names = [c for c in bronze_research.columns if c != "fetched_at"]
research_pieces = [
    bronze_research.select(
        F.lit(category).alias("category"),
        F.to_date("fetched_at").alias("snapshot_date"),
        F.col(f"`{category}`.count").cast("long").alias("count"),
        F.to_timestamp("fetched_at").alias("fetched_at"),
    )
    for category in category_names
]
research_silver = research_pieces[0]
for piece in research_pieces[1:]:
    research_silver = research_silver.unionByName(piece)
merge_into("research_pace", research_silver, ["category", "snapshot_date"])

print("bronze_to_silver complete")
