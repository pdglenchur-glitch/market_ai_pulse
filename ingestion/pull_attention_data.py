"""Phase 2 step 2.5: pull public-attention signal from Wikipedia Pageviews.

Fetches recent daily pageviews for a few AI-related articles. The API has
a reporting lag of a couple of days, so we request a trailing window and
keep the most recent day actually returned. When the requested range's end
date (today) hasn't been published yet, the API returns a 404 for the
*entire* range rather than the range minus the unready day(s) - confirmed
by a real scheduled-run failure on 2026-07-31 where the exact URL that
404'd at run time returned 200 a couple of hours later. On a 404
specifically, walk the end date back a day at a time and retry, rather
than treating it as a hard failure; genuine transient errors (timeouts,
5xx) still get a short retry-with-backoff at the same end date first.
"""
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ARTICLES = ["Artificial_intelligence", "ChatGPT", "Large_language_model"]
DEFAULT_OUTPUT = Path("data/raw/attention_data.json")
LOOKBACK_DAYS = 10
MAX_END_DATE_RETREAT_DAYS = 4  # Wikimedia's documented lag is "a couple of days"; leave margin
USER_AGENT = "market-ai-pulse/1.0 (https://github.com/pdglenchur-glitch/market_ai_pulse)"


def fetch_latest_pageviews(article: str) -> dict:
    today = datetime.now(timezone.utc).date()

    for retreat in range(MAX_END_DATE_RETREAT_DAYS + 1):
        end = today - timedelta(days=retreat)
        start = end - timedelta(days=LOOKBACK_DAYS)
        url = (
            "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
            f"en.wikipedia/all-access/all-agents/{article}/daily/"
            f"{start:%Y%m%d}/{end:%Y%m%d}"
        )

        backoff = 5
        last_exc = None
        for attempt in range(3):
            try:
                response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
                if response.status_code == 404:
                    last_exc = None
                    break
                response.raise_for_status()
                items = response.json()["items"]
                if not items:
                    raise RuntimeError(f"No pageview data returned for {article}")
                latest = items[-1]
                return {
                    "date": datetime.strptime(latest["timestamp"][:8], "%Y%m%d").strftime("%Y-%m-%d"),
                    "views": latest["views"],
                }
            except requests.exceptions.RequestException as exc:
                last_exc = exc
                print(f"  request error for {article}: {exc!r}, backing off {backoff}s")
                time.sleep(backoff)
                backoff *= 2

        if last_exc is not None:
            raise RuntimeError(f"exhausted retries fetching pageviews for {article}") from last_exc

        print(f"  404 for {article} through {end}, retrying with an earlier end date")

    raise RuntimeError(
        f"no pageview data available for {article} after retreating {MAX_END_DATE_RETREAT_DAYS} days"
    )


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
