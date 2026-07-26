"""One-off: remove the corrupt NaN-OHLC rows a yfinance data-freshness
glitch wrote into silver.market_data (date=2026-07-24). A subsequent
pipeline run will naturally re-populate that date with real data once
yfinance has settled it; until then, no row is more honest than a NaN row.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "databricks"))
from warehouse import connect  # noqa: E402

conn = connect()
with conn.cursor() as cursor:
    cursor.execute(
        """
        DELETE FROM workspace.silver.market_data
        WHERE isnan(open) OR isnan(high) OR isnan(low) OR isnan(close)
        """
    )
    print("Deleted NaN rows from workspace.silver.market_data")
    cursor.execute(
        "SELECT COUNT(*), MIN(date), MAX(date) FROM workspace.silver.market_data"
    )
    for row in cursor.fetchall():
        print(" ", row)
conn.close()
