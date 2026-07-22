"""Phase 2 step 2.4: pull macro indicators from FRED (St. Louis Fed).

Fetches the latest observation for each tracked series: CPI, unemployment
rate, fed funds rate, and the 10Y treasury yield.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

SERIES = {
    "cpi": "CPIAUCSL",
    "unemployment_rate": "UNRATE",
    "fed_funds_rate": "FEDFUNDS",
    "10y_yield": "DGS10",
}
DEFAULT_OUTPUT = Path("data/raw/macro_data.json")
FRED_URL = "https://api.stlouisfed.org/fred/series/observations"


def fetch_latest_observation(series_id: str, api_key: str) -> dict:
    response = requests.get(
        FRED_URL,
        params={
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 1,
        },
        timeout=30,
    )
    response.raise_for_status()
    observations = response.json()["observations"]
    if not observations:
        raise RuntimeError(f"No observations returned for {series_id}")

    latest = observations[0]
    return {
        "date": latest["date"],
        "value": None if latest["value"] == "." else float(latest["value"]),
    }


def fetch_all(api_key: str) -> dict:
    record = {name: fetch_latest_observation(series_id, api_key) for name, series_id in SERIES.items()}
    record["fetched_at"] = datetime.now(timezone.utc).isoformat()
    return record


def run(output: Path = DEFAULT_OUTPUT) -> Path:
    api_key = os.environ["FRED_API_KEY"]
    record = fetch_all(api_key)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2))
    print(f"Wrote {output}")
    print(json.dumps(record, indent=2))
    return output


if __name__ == "__main__":
    run()
