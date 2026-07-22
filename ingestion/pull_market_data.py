"""Pull one day of market data via yfinance: the S&P 500 benchmark, sector
ETFs (for sector_rotation), and the AI basket (for ai_vs_market).
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

BENCHMARK = "^GSPC"
SECTOR_ETFS = ["XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLB", "XLRE", "XLU", "XLC"]
AI_BASKET = ["NVDA", "MSFT", "GOOGL", "META", "PLTR", "AMD", "BOTZ"]
ALL_SYMBOLS = [BENCHMARK] + SECTOR_ETFS + AI_BASKET

DEFAULT_OUTPUT = Path("data/raw/market_data.json")


def symbol_category(symbol: str) -> str:
    if symbol == BENCHMARK:
        return "benchmark"
    if symbol in SECTOR_ETFS:
        return "sector"
    return "ai_basket"


def fetch_latest_day_all(symbols: list[str] = ALL_SYMBOLS) -> list[dict]:
    data = yf.download(symbols, period="5d", interval="1d", group_by="ticker", progress=False)

    records = []
    for symbol in symbols:
        history = data[symbol].dropna(how="all")
        if history.empty:
            raise RuntimeError(f"No data returned for {symbol}")

        latest = history.iloc[-1]
        records.append(
            {
                "symbol": symbol,
                "category": symbol_category(symbol),
                "date": history.index[-1].strftime("%Y-%m-%d"),
                "open": round(float(latest["Open"]), 2),
                "high": round(float(latest["High"]), 2),
                "low": round(float(latest["Low"]), 2),
                "close": round(float(latest["Close"]), 2),
                "volume": int(latest["Volume"]),
            }
        )
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
