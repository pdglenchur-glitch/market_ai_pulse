"""Queries each gold table via the Databricks SQL connector and writes it
as JSON into docs/data/, for the static dashboard to read (steps 4.1-4.8).
"""
import json
import math
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "databricks"))
from warehouse import connect  # noqa: E402

# Order matters: several dashboard.js chart functions assume rows come back
# sorted ascending by date (e.g. "latest = last element"). SELECT * with no
# ORDER BY doesn't guarantee row order at all - fix it here, once, at the
# source, rather than defensively in every chart function that reads it.
TABLES = {
    "market_daily": "symbol, date",
    "sector_rotation": "symbol, date",
    "volatility": "date",
    "macro_snapshot": "series",
    "ai_vs_market": "date",
    "attention_index": "article, date",
    "dev_momentum": "repo, snapshot_date",
    "research_pace": "category, snapshot_date",
}
OUTPUT_DIR = Path(__file__).parent.parent / "docs" / "data"


def json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Not JSON serializable: {value!r}")


def sanitize(value):
    # A NaN/inf float serializes as a bare NaN/Infinity token under Python's
    # default allow_nan=True - technically valid per json.dumps, but not
    # valid JSON per spec, and browsers' JSON.parse rejects it outright,
    # breaking every chart fed by that file. Normalize to null instead,
    # which every chart already renders as "no data" ("-", empty state).
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def export_table(cursor, table: str, order_by: str) -> None:
    cursor.execute(f"SELECT * FROM workspace.gold.{table} ORDER BY {order_by}")
    columns = [d[0] for d in cursor.description]
    rows = [{col: sanitize(v) for col, v in zip(columns, row)} for row in cursor.fetchall()]

    output_path = OUTPUT_DIR / f"{table}.json"
    # allow_nan=False as a hard backstop: if sanitize() ever misses a case,
    # fail loudly here (triggering the pipeline's failure alert) instead of
    # silently publishing invalid JSON that breaks the live dashboard.
    output_path.write_text(json.dumps(rows, default=json_default, indent=2, allow_nan=False))
    print(f"Wrote {output_path} ({len(rows)} rows)")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect()
    with conn.cursor() as cursor:
        for table, order_by in TABLES.items():
            export_table(cursor, table, order_by)
    conn.close()


if __name__ == "__main__":
    main()
