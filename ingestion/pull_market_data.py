"""Pull recent market data via yfinance: the S&P 500 benchmark, sector
ETFs (for sector_rotation), and the AI basket (for ai_vs_market).

Captures the trailing few settled days per symbol each run, not just the
single latest one. Yahoo/yfinance's backend can lag publishing a trading
day's finalized close by more than the ~12 hours between market close and
the next morning's cron run - confirmed 2026-08-04, when Monday
2026-08-03's close still wasn't available when Tuesday's scheduled run
fired, and by the time it was, a single-day-per-run design had already
moved on to whatever was then latest, permanently skipping 2026-08-03
until it was manually backfilled. bronze_to_silver.py already MERGEs
market_data by (symbol, date), so writing overlapping days each run is a
no-op for dates already captured and a real recovery for ones that
weren't - this makes the pipeline self-healing against that class of
provider lag instead of needing a manual backfill every time it recurs.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

BENCHMARK = "^GSPC"
SECTOR_ETFS = ["XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLB", "XLRE", "XLU", "XLC"]
AI_BASKET = [
    "NVDA", "AMD", "AVGO", "TSM", "AMAT", "MU",  # chip design, foundry, equipment, memory
    "MSFT", "GOOGL", "AMZN", "CRWV",  # hyperscale cloud + neocloud compute
    "META", "PLTR",  # AI capex / enterprise software
    "VRT", "DLR", "BE", "CEG",  # datacenter power, real estate, on-site + grid-scale generation
    "ANET",  # datacenter networking
    "SMCI",  # AI server/systems integration
    "BOTZ",  # thematic ETF, passive diversification check
]
ALL_SYMBOLS = [BENCHMARK] + SECTOR_ETFS + AI_BASKET

DEFAULT_OUTPUT = Path("data/raw/market_data.json")


def symbol_category(symbol: str) -> str:
    if symbol == BENCHMARK:
        return "benchmark"
    if symbol in SECTOR_ETFS:
        return "sector"
    return "ai_basket"


RECENT_DAYS_PER_RUN = 3  # trailing settled days captured each run; see module docstring


def fetch_latest_day_all(symbols: list[str] = ALL_SYMBOLS) -> list[dict]:
    data = yf.download(symbols, period="5d", interval="1d", group_by="ticker", progress=False)

    records = []
    failed_symbols = []
    for symbol in symbols:
        # dropna(how="all") only drops a row if every column is NaN. yfinance
        # can return a most-recent row with real volume but NaN OHLC when
        # that day's price data hasn't fully settled yet - drop any row
        # missing an OHLC value specifically, so only usable rows get kept.
        history = data[symbol].dropna(subset=["Open", "High", "Low", "Close"])
        if history.empty:
            # One symbol missing data (confirmed for real 2026-08-07, XLV)
            # shouldn't discard the other ~30 symbols' perfectly good data -
            # skip it and continue, same "only fail loudly if everything
            # failed" principle as run_ingestion.py's cross-source isolation.
            print(f"  no data returned for {symbol}, skipping it this run")
            failed_symbols.append(symbol)
            continue

        for idx, row in history.tail(RECENT_DAYS_PER_RUN).iterrows():
            records.append(
                {
                    "symbol": symbol,
                    "category": symbol_category(symbol),
                    "date": idx.strftime("%Y-%m-%d"),
                    "open": round(float(row["Open"]), 2),
                    "high": round(float(row["High"]), 2),
                    "low": round(float(row["Low"]), 2),
                    "close": round(float(row["Close"]), 2),
                    "volume": int(row["Volume"]),
                }
            )

    if failed_symbols and len(failed_symbols) == len(symbols):
        raise RuntimeError(f"No data returned for any symbol: {', '.join(failed_symbols)}")
    return records


def run(output: Path = DEFAULT_OUTPUT) -> Path:
    payload = {
        "records": fetch_latest_day_all(),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2))
    print(f"Wrote {output}")
    print(json.dumps(payload, indent=2))
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    run(args.output)


if __name__ == "__main__":
    main()
