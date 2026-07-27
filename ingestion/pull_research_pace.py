"""Phase 2 step 2.7: pull weekly new-paper counts from arXiv (cs.AI, cs.LG).

Uses the arXiv API's submittedDate range filter combined with
opensearch:totalResults, so we only need the count, not every entry.
"""
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree

import requests

CATEGORIES = ["cs.AI", "cs.LG"]
DEFAULT_OUTPUT = Path("data/raw/research_pace.json")
LOOKBACK_DAYS = 7
ARXIV_URL = "http://export.arxiv.org/api/query"
NAMESPACES = {"opensearch": "http://a9.com/-/spec/opensearch/1.1/"}


def fetch_weekly_count(category: str) -> int:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=LOOKBACK_DAYS)
    date_range = f"[{start:%Y%m%d%H%M%S} TO {end:%Y%m%d%H%M%S}]"
    search_query = f"cat:{category} AND submittedDate:{date_range}"

    # arXiv occasionally rate-limits (429) or times out on a cold request;
    # a bare, unretried call failing the whole daily pipeline over a
    # transient blip is a worse failure mode than waiting a few seconds.
    backoff = 5
    last_exc = None
    for attempt in range(4):
        try:
            response = requests.get(
                ARXIV_URL,
                params={"search_query": search_query, "max_results": 1},
                timeout=30,
            )
            if response.status_code == 429:
                print(f"  429 for {category}, backing off {backoff}s")
                time.sleep(backoff)
                backoff *= 2
                continue
            response.raise_for_status()
            root = ElementTree.fromstring(response.text)
            total = root.find("opensearch:totalResults", NAMESPACES)
            return int(total.text)
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            print(f"  request error for {category}: {exc!r}, backing off {backoff}s")
            time.sleep(backoff)
            backoff *= 2
    raise RuntimeError(f"exhausted retries fetching arXiv count for {category}") from last_exc


def fetch_all() -> dict:
    record = {category: {"count": fetch_weekly_count(category)} for category in CATEGORIES}
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
