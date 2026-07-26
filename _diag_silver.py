"""Diagnostic: check actual row counts / date ranges in silver tables."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "databricks"))
from warehouse import connect  # noqa: E402

QUERIES = {
    "silver market_data": "SELECT COUNT(*), MIN(date), MAX(date), COUNT(DISTINCT symbol) FROM workspace.silver.market_data",
    "gold market_daily": "SELECT COUNT(*), MIN(date), MAX(date), COUNT(DISTINCT symbol) FROM workspace.gold.market_daily",
    "gold sector_rotation": "SELECT COUNT(*), MIN(date), MAX(date) FROM workspace.gold.sector_rotation",
    "gold volatility": "SELECT COUNT(*), MIN(date), MAX(date) FROM workspace.gold.volatility",
    "gold macro_snapshot": "SELECT series, COUNT(*), MIN(date), MAX(date) FROM workspace.gold.macro_snapshot GROUP BY series",
    "gold research_pace": "SELECT category, COUNT(*), MIN(snapshot_date), MAX(snapshot_date) FROM workspace.gold.research_pace GROUP BY category",
    "gold attention_index": "SELECT article, COUNT(*), MIN(date), MAX(date) FROM workspace.gold.attention_index GROUP BY article",
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
