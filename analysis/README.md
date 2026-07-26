# Key Findings

A monthly-refreshable analysis notebook, separate from the automated pipeline in the rest of this repo. The pipeline's job is to keep the dashboard current; this notebook's job is to periodically step back and ask what the accumulated history actually shows.

**[`key_findings.ipynb`](key_findings.ipynb)** pulls directly from the live dashboard's exported JSON (the same files the dashboard itself reads), so it always analyzes whatever the pipeline has published as of the moment you run it. No local data sync, no credentials, no Databricks access needed.

## What's in it

1. AI basket vs. S&P 500 cumulative return
2. AI-sector search attention vs. stock moves: a lead-lag investigation (day-to-day correlation, then an event study on the biggest attention spikes)
3. AI basket trading-volume concentration
4. Sector return sensitivity to interest-rate moves
5. Realized volatility trend and its outlier window

## Running it

```
pip install -r requirements.txt
jupyter notebook key_findings.ipynb
```

Then **Kernel → Restart & Run All**. Every number, table, and chart regenerates from whatever data is live at that moment — there's nothing to edit or update by hand.

## Refreshing monthly

Since the notebook always reads from the live dashboard rather than a saved snapshot, re-running it next month (or any time) picks up everything the pipeline has accumulated since. To keep a monthly record instead of just overwriting the same file:

```
jupyter nbconvert --to notebook --execute --output key_findings_2026-08.ipynb key_findings.ipynb
```

(swap the month in the output filename) — or just re-run and re-commit `key_findings.ipynb` in place if you'd rather keep a single always-current version and rely on git history for the trail of how findings changed over time.
