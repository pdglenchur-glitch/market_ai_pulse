"""Phase 2 step 2.6: pull current star counts for curated AI/ML repos.

Snapshots stargazers_count each week; week-over-week growth is computed
later in the silver/gold transform. Unauthenticated GitHub REST API is
enough at weekly cadence (add GH_TOKEN later only if rate-limited).
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

REPOS = [
    "openai/openai-python",
    "huggingface/transformers",
    "pytorch/pytorch",
    "langchain-ai/langchain",
    "ollama/ollama",
]
DEFAULT_OUTPUT = Path("data/raw/dev_momentum.json")


def fetch_repo_stars(repo: str) -> dict:
    response = requests.get(f"https://api.github.com/repos/{repo}", timeout=30)
    response.raise_for_status()
    data = response.json()
    return {"stars": data["stargazers_count"]}


def fetch_all() -> dict:
    record = {repo: fetch_repo_stars(repo) for repo in REPOS}
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
