"""Phase 2 step 2.7: pull weekly new-paper counts from arXiv (cs.AI, cs.LG).

Uses the arXiv API's submittedDate range filter combined with
opensearch:totalResults, so we only need the count, not every entry.
"""
import json
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

    response = requests.get(
        ARXIV_URL,
        params={"search_query": search_query, "max_results": 1},
        timeout=30,
    )
    response.raise_for_status()
    root = ElementTree.fromstring(response.text)
    total = root.find("opensearch:totalResults", NAMESPACES)
    return int(total.text)


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
