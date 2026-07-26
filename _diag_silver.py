"""Diagnostic: check actual row counts / date ranges in silver tables."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "databricks"))
from warehouse import connect  # noqa: E402

QUERIES = {
    "market_data": "SELECT COUNT(*), MIN(date), MAX(date), COUNT(DISTINCT symbol) FROM workspace.silver.market_data",
    "macro_data": "SELECT series, COUNT(*), MIN(date), MAX(date) FROM workspace.silver.macro_data GROUP BY series",
    "attention_data": "SELECT article, COUNT(*), MIN(date), MAX(date) FROM workspace.silver.attention_data GROUP BY article",
    "research_pace": "SELECT category, COUNT(*), MIN(snapshot_date), MAX(snapshot_date) FROM workspace.silver.research_pace GROUP BY category",
}

conn = connect()
with conn.cursor() as cursor:
    for name, query in QUERIES.items():
        print(f"=== {name} ===")
        cursor.execute(query)
        for row in cursor.fetchall():
            print(" ", row)
    print("=== tables in workspace.silver ===")
    cursor.execute("SHOW TABLES IN workspace.silver")
    for row in cursor.fetchall():
        print(" ", row)
conn.close()
