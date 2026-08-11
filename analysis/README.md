# Key Findings

An analysis notebook that refreshes automatically every Monday, separate from the daily automated pipeline in the rest of this repo. The pipeline's job is to keep the dashboard current; this notebook's job is to periodically step back and ask what the accumulated history actually shows.

**[`key_findings.ipynb`](key_findings.ipynb)** pulls directly from the live dashboard's exported JSON (the same files the dashboard itself reads), so it always analyzes whatever the pipeline has published as of the moment it runs. No local data sync, no credentials, no Databricks access needed.

## What's in it

1. AI basket vs. S&P 500 cumulative return
2. AI-sector search attention vs. stock moves: a lead-lag investigation (day-to-day correlation, then an event study on the biggest attention spikes)
3. AI basket trading-volume concentration
4. Sector return sensitivity to interest-rate moves
5. Realized volatility trend and its outlier window
6. AI infrastructure vs. the original core basket: return and volatility comparison

## Refreshing automatically (weekly)

`pipeline.yml` adds a Monday-only step, after the day's dashboard data is already published, that re-executes this notebook and commits the result. It waits for GitHub Pages to actually be serving that day's data before running, since the notebook reads the live site rather than Databricks directly. This step is entirely additive: it never runs on any day but Monday, never blocks or modifies the daily dashboard pipeline, and only ever touches this notebook and `key_findings_history.json`.

Each key finding above states how its headline number moved versus the prior week's run, computed directly from `key_findings_history.json`, a small file this notebook's own last cell appends to and that's committed alongside it. The comparison text is generated from that stored number, not written by hand, so it stays accurate as the numbers change week to week.

## Running it manually

```
pip install -r requirements.txt
jupyter notebook key_findings.ipynb
```

Then **Kernel → Restart & Run All**. Every number, table, and chart regenerates from whatever data is live at that moment, and the run adds its own entry to `key_findings_history.json` the same way the automated weekly run does, with nothing to edit or update by hand.
