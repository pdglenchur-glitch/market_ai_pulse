"""Queries each gold table via the Databricks SQL connector and writes it
as JSON into docs/data/, for the static dashboard to read (steps 4.1-4.8).
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "databricks"))
from warehouse import connect  # noqa: E402

TABLES = [
    "market_daily",
    "sector_rotation",
    "volatility",
    "macro_snapshot",
    "ai_vs_market",
    "attention_index",
    "dev_momentum",
    "research_pace",
]
OUTPUT_DIR = Path(__file__).parent.parent / "docs" / "data"


def json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Not JSON serializable: {value!r}")


def export_table(cursor, table: str) -> None:
    cursor.execute(f"SELECT * FROM workspace.gold.{table}")
    columns = [d[0] for d in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    output_path = OUTPUT_DIR / f"{table}.json"
    output_path.write_text(json.dumps(rows, default=json_default, indent=2))
    print(f"Wrote {output_path} ({len(rows)} rows)")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect()
    with conn.cursor() as cursor:
        for table in TABLES:
            export_table(cursor, table)
    conn.close()


if __name__ == "__main__":
    main()
