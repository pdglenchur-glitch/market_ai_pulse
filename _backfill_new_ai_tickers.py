"""One-off historical backfill for the four tickers added to the AI basket
on 2026-07-28 (AVGO, AMZN, VRT, DLR) - lands their market history directly
into the silver layer so they have the same depth as the rest of the basket
and every window (7D/30D/90D/All) works for them immediately, instead of
starting from zero and taking a year to catch up organically.

Same pattern as the original _backfill_history.py (already deleted after
its one-time use, recovered from git history commit 315d008): writes
straight to workspace.silver.market_data via the SQL warehouse connector,
bypassing bronze/R2 (bronze is daily-overwritten, not a bulk-load target),
keyed by MERGE on (symbol, date) so it's safe to re-run. Only touches these
four new symbols - the existing seven basket members and the sector/
benchmark rows are untouched.

Run once, manually, via a throwaway GitHub Actions workflow, then delete
both this file and the workflow.
"""
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent / "databricks"))
from warehouse import connect  # noqa: E402

NEW_SYMBOLS = ["AVGO", "AMZN", "VRT", "DLR"]
BACKFILL_START = date(2025, 7, 22)
BACKFILL_END = date.today() - timedelta(days=1)  # up through yesterday; today's row comes from the normal daily run


def sql_str(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def sql_val(v):
    if v is None:
        return "NULL"
    if isinstance(v, str):
        return sql_str(v)
    return str(v)


def batch_insert(cursor, table: str, columns: list[str], rows: list[tuple], batch_size: int = 500) -> None:
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        values_sql = ",\n".join("(" + ", ".join(sql_val(v) for v in row) + ")" for row in batch)
        cursor.execute(f"INSERT INTO {table} ({', '.join(columns)}) VALUES {values_sql}")
    print(f"  inserted {len(rows)} rows into {table}")


def merge_and_cleanup(cursor, stage_table: str, real_table: str, key_cols: list[str]) -> None:
    condition = " AND ".join(f"t.{c} = s.{c}" for c in key_cols)
    cursor.execute(
        f"""
        MERGE INTO {real_table} AS t
        USING {stage_table} AS s
        ON {condition}
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
        """
    )
    cursor.execute(f"DROP TABLE {stage_table}")
    print(f"  merged into {real_table}, dropped staging table")


def fetch_market_history() -> list[tuple]:
    print(f"Fetching {NEW_SYMBOLS} history from yfinance ({BACKFILL_START} to {BACKFILL_END})...")
    data = yf.download(
        NEW_SYMBOLS,
        start=BACKFILL_START.isoformat(),
        end=(BACKFILL_END + timedelta(days=1)).isoformat(),
        interval="1d",
        group_by="ticker",
        progress=False,
    )
    fetched_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for symbol in NEW_SYMBOLS:
        history = data[symbol].dropna(subset=["Open", "High", "Low", "Close"])
        for idx, r in history.iterrows():
            rows.append(
                (
                    symbol,
                    "ai_basket",
                    idx.strftime("%Y-%m-%d"),
                    round(float(r["Open"]), 2),
                    round(float(r["High"]), 2),
                    round(float(r["Low"]), 2),
                    round(float(r["Close"]), 2),
                    int(r["Volume"]),
                    fetched_at,
                )
            )
    print(f"  {len(rows)} market rows across {len(NEW_SYMBOLS)} symbols")
    return rows


def backfill_market_data(cursor) -> None:
    rows = fetch_market_history()
    columns = ["symbol", "category", "date", "open", "high", "low", "close", "volume", "fetched_at"]
    stage = "workspace.silver._backfill_stage_new_ai_tickers"
    cursor.execute(
        f"""
        CREATE OR REPLACE TABLE {stage} (
            symbol STRING, category STRING, date DATE, open DOUBLE, high DOUBLE,
            low DOUBLE, close DOUBLE, volume BIGINT, fetched_at TIMESTAMP
        )
        """
    )
    batch_insert(cursor, stage, columns, rows)
    merge_and_cleanup(cursor, stage, "workspace.silver.market_data", ["symbol", "date"])


def main() -> None:
    conn = connect()
    with conn.cursor() as cursor:
        backfill_market_data(cursor)
    conn.close()
    print("Backfill complete.")


if __name__ == "__main__":
    main()
