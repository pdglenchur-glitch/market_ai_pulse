"""One-off historical backfill: lands 365 days of history (2025-07-22 through
2026-07-21, the day before the live pipeline's first real day) directly into
the silver layer for market_data, macro_data, attention_data, and
research_pace - bypassing bronze/R2 entirely, since bronze is a
daily-overwritten staging area, not built to hold a bulk historical load.

Deliberately excludes dev_momentum (GitHub has no historical star-count
API; the user asked to leave it as-is).

Run once, manually, via a throwaway GitHub Actions workflow (same pattern as
every other one-off script this project has used for real Databricks/API
credentials) - never part of the daily pipeline. Safe to re-run: every write
is a MERGE keyed by the same natural keys bronze_to_silver.py uses, so
re-running just re-applies the same historical rows rather than duplicating
anything, and the live daily rows (2026-07-22 onward) are never touched
since this script never writes to those dates.
"""
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree

import requests
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent / "databricks"))
sys.path.insert(0, str(Path(__file__).parent / "ingestion"))
from warehouse import connect  # noqa: E402
from pull_market_data import ALL_SYMBOLS, symbol_category  # noqa: E402

BACKFILL_START = date(2025, 7, 22)
BACKFILL_END = date(2026, 7, 21)  # live pipeline's first real day is 7/22

FRED_SERIES = {
    "cpi": "CPIAUCSL",
    "unemployment_rate": "UNRATE",
    "fed_funds_rate": "FEDFUNDS",
    "10y_yield": "DGS10",
}
ARTICLES = ["Artificial_intelligence", "ChatGPT", "Large_language_model"]
RESEARCH_CATEGORIES = ["cs.AI", "cs.LG"]
ARXIV_URL = "http://export.arxiv.org/api/query"
ARXIV_NS = {"opensearch": "http://a9.com/-/spec/opensearch/1.1/"}
USER_AGENT = "market-ai-pulse/1.0 (https://github.com/pdglenchur-glitch/market_ai_pulse)"


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


# --- market_data --------------------------------------------------------
def fetch_market_history() -> list[tuple]:
    print("Fetching market data history from yfinance...")
    data = yf.download(
        ALL_SYMBOLS,
        start=BACKFILL_START.isoformat(),
        end=(BACKFILL_END + timedelta(days=1)).isoformat(),
        interval="1d",
        group_by="ticker",
        progress=False,
    )
    fetched_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for symbol in ALL_SYMBOLS:
        history = data[symbol].dropna(how="all")
        for idx, r in history.iterrows():
            rows.append(
                (
                    symbol,
                    symbol_category(symbol),
                    idx.strftime("%Y-%m-%d"),
                    round(float(r["Open"]), 2),
                    round(float(r["High"]), 2),
                    round(float(r["Low"]), 2),
                    round(float(r["Close"]), 2),
                    int(r["Volume"]),
                    fetched_at,
                )
            )
    print(f"  {len(rows)} market rows across {len(ALL_SYMBOLS)} symbols")
    return rows


def backfill_market_data(cursor) -> None:
    rows = fetch_market_history()
    columns = ["symbol", "category", "date", "open", "high", "low", "close", "volume", "fetched_at"]
    stage = "workspace.silver._backfill_stage_market"
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


# --- macro_data ----------------------------------------------------------
def fetch_macro_history(api_key: str) -> list[tuple]:
    print("Fetching macro data history from FRED...")
    fetched_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for name, series_id in FRED_SERIES.items():
        response = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "observation_start": BACKFILL_START.isoformat(),
                "observation_end": BACKFILL_END.isoformat(),
            },
            timeout=30,
        )
        response.raise_for_status()
        observations = response.json()["observations"]
        for obs in observations:
            if obs["value"] == ".":
                continue
            rows.append((name, obs["date"], float(obs["value"]), fetched_at))
        print(f"  {name}: {len(observations)} observations")
    return rows


def backfill_macro_data(cursor, api_key: str) -> None:
    rows = fetch_macro_history(api_key)
    columns = ["series", "date", "value", "fetched_at"]
    stage = "workspace.silver._backfill_stage_macro"
    cursor.execute(
        f"""
        CREATE OR REPLACE TABLE {stage} (
            series STRING, date DATE, value DOUBLE, fetched_at TIMESTAMP
        )
        """
    )
    batch_insert(cursor, stage, columns, rows)
    merge_and_cleanup(cursor, stage, "workspace.silver.macro_data", ["series", "date"])


# --- attention_data --------------------------------------------------------
def fetch_attention_history() -> list[tuple]:
    print("Fetching attention data history from Wikipedia Pageviews...")
    fetched_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for article in ARTICLES:
        url = (
            "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
            f"en.wikipedia/all-access/all-agents/{article}/daily/"
            f"{BACKFILL_START:%Y%m%d}/{BACKFILL_END:%Y%m%d}"
        )
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        response.raise_for_status()
        items = response.json()["items"]
        for item in items:
            item_date = datetime.strptime(item["timestamp"][:8], "%Y%m%d").strftime("%Y-%m-%d")
            rows.append((article, item_date, item["views"], fetched_at))
        print(f"  {article}: {len(items)} days")
    return rows


def backfill_attention_data(cursor) -> None:
    rows = fetch_attention_history()
    columns = ["article", "date", "views", "fetched_at"]
    stage = "workspace.silver._backfill_stage_attention"
    cursor.execute(
        f"""
        CREATE OR REPLACE TABLE {stage} (
            article STRING, date DATE, views BIGINT, fetched_at TIMESTAMP
        )
        """
    )
    batch_insert(cursor, stage, columns, rows)
    merge_and_cleanup(cursor, stage, "workspace.silver.attention_data", ["article", "date"])


# --- research_pace ---------------------------------------------------------
def fetch_trailing_7d_count(category: str, as_of: date) -> int:
    end = datetime(as_of.year, as_of.month, as_of.day, 23, 59, 59, tzinfo=timezone.utc)
    start = end - timedelta(days=7)
    date_range = f"[{start:%Y%m%d%H%M%S} TO {end:%Y%m%d%H%M%S}]"
    search_query = f"cat:{category} AND submittedDate:{date_range}"
    backoff = 15
    last_exc = None
    for attempt in range(8):
        try:
            response = requests.get(ARXIV_URL, params={"search_query": search_query, "max_results": 1}, timeout=60)
            if response.status_code == 429:
                print(f"  429 for {category} {as_of}, backing off {backoff}s")
                time.sleep(backoff)
                backoff = min(backoff * 2, 120)
                continue
            response.raise_for_status()
            root = ElementTree.fromstring(response.text)
            total = root.find("opensearch:totalResults", ARXIV_NS)
            return int(total.text)
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            print(f"  request error for {category} {as_of}: {exc!r}, backing off {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 120)
    raise RuntimeError(f"exhausted retries for {category} {as_of}") from last_exc


def fetch_research_pace_history() -> list[tuple]:
    print("Fetching research pace history from arXiv (this takes a while, one query per day)...")
    fetched_at = datetime.now(timezone.utc).isoformat()
    rows = []
    day = BACKFILL_START
    n_days = (BACKFILL_END - BACKFILL_START).days + 1
    i = 0
    while day <= BACKFILL_END:
        for category in RESEARCH_CATEGORIES:
            count = fetch_trailing_7d_count(category, day)
            rows.append((category, day.isoformat(), count, fetched_at))
            time.sleep(4)
        i += 1
        if i % 30 == 0:
            print(f"  ...{i}/{n_days} days done")
        day += timedelta(days=1)
    print(f"  {len(rows)} research pace rows")
    return rows


def backfill_research_pace(cursor) -> None:
    rows = fetch_research_pace_history()
    columns = ["category", "snapshot_date", "count", "fetched_at"]
    stage = "workspace.silver._backfill_stage_research"
    cursor.execute(
        f"""
        CREATE OR REPLACE TABLE {stage} (
            category STRING, snapshot_date DATE, count BIGINT, fetched_at TIMESTAMP
        )
        """
    )
    batch_insert(cursor, stage, columns, rows)
    merge_and_cleanup(cursor, stage, "workspace.silver.research_pace", ["category", "snapshot_date"])


ALL_SOURCES = ["market_data", "macro_data", "attention_data", "research_pace"]


def main() -> None:
    # Pass source names as argv to re-run a subset (e.g. after a partial
    # failure) instead of redoing sources that already succeeded - each
    # source's MERGE is independent and idempotent either way.
    sources = sys.argv[1:] or ALL_SOURCES
    conn = connect()
    with conn.cursor() as cursor:
        if "market_data" in sources:
            print("=== market_data ===")
            backfill_market_data(cursor)
        if "macro_data" in sources:
            print("=== macro_data ===")
            backfill_macro_data(cursor, os.environ["FRED_API_KEY"])
        if "attention_data" in sources:
            print("=== attention_data ===")
            backfill_attention_data(cursor)
        if "research_pace" in sources:
            print("=== research_pace ===")
            backfill_research_pace(cursor)
    conn.close()
    print("Backfill complete.")


if __name__ == "__main__":
    main()
