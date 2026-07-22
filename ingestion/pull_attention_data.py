"""Phase 2 step 2.5: pull public-attention signal from Wikipedia Pageviews.

Fetches recent daily pageviews for a few AI-related articles. The API has
a reporting lag of a couple of days, so we request a trailing window and
keep the most recent day actually returned.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ARTICLES = ["Artificial_intelligence", "ChatGPT", "Large_language_model"]
DEFAULT_OUTPUT = Path("data/raw/attention_data.json")
LOOKBACK_DAYS = 10
USER_AGENT = "market-ai-pulse/1.0 (https://github.com/pdglenchur-glitch/market_ai_pulse)"


def fetch_latest_pageviews(article: str) -> dict:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=LOOKBACK_DAYS)
    url = (
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        f"en.wikipedia/all-access/all-agents/{article}/daily/"
        f"{start:%Y%m%d}/{end:%Y%m%d}"
    )
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    items = response.json()["items"]
    if not items:
        raise RuntimeError(f"No pageview data returned for {article}")

    latest = items[-1]
    return {
        "date": datetime.strptime(latest["timestamp"][:8], "%Y%m%d").strftime("%Y-%m-%d"),
        "views": latest["views"],
    }


def fetch_all() -> dict:
    record = {article: fetch_latest_pageviews(article) for article in ARTICLES}
    record["fetched_at"] = datetime.now(timezone.utc).isoformat()
    return record


def run(output: Path = DEFAULT_OUTPUT) -> Path:
    record = fetch_all()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2))
    print(f"Wrote {output}")
    print(json.dumps(record, indent=2))
    return output


if __name__ == "__main__":
    run()
