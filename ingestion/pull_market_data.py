"""Phase 1 thin vertical slice: pull one day of S&P 500 data via yfinance.

Fetches the most recent daily bar for the S&P 500 index (^GSPC) and writes
it to a local JSON file, to be picked up by land_to_r2.py (step 1.3).
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

SYMBOL = "^GSPC"
DEFAULT_OUTPUT = Path("data/raw/market_data.json")


def fetch_latest_day(symbol: str = SYMBOL) -> dict:
    history = yf.Ticker(symbol).history(period="5d", interval="1d")
    if history.empty:
        raise RuntimeError(f"No data returned for {symbol}")

    latest = history.iloc[-1]
    return {
        "symbol": symbol,
        "date": history.index[-1].strftime("%Y-%m-%d"),
        "open": round(float(latest["Open"]), 2),
        "high": round(float(latest["High"]), 2),
        "low": round(float(latest["Low"]), 2),
        "close": round(float(latest["Close"]), 2),
        "volume": int(latest["Volume"]),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    record = fetch_latest_day()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2))
    print(f"Wrote {args.output}")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
