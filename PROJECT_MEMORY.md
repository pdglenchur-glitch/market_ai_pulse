# Project Memory — Market & AI Pulse

Narrative continuity doc for picking this project back up after a context reset. `PROJECT_PLAN.md` is the authoritative step-by-step checklist (read it for exact status); this file is the *why* behind what's there — the bugs hit, the decisions made and why, and the things a fresh session would otherwise have to re-derive from scratch.

**Live dashboard:** https://pdglenchur-glitch.github.io/market_ai_pulse/
**Repo:** https://github.com/pdglenchur-glitch/market_ai_pulse
**Local dev preview:** `python -m http.server 8000` from inside `docs/`, then open `http://localhost:8000` — faster than pushing + waiting for a Pages rebuild when iterating on the dashboard.

---

## Where things stand

Phases 0–5 are complete, and Phase 6 is nearly done. Only **6.2 remains**: let one real *scheduled* (not manually dispatched) daily run fire on its own at 06:00 UTC and confirm the dashboard updates untouched. This can't be forced — it just needs the cron to actually fire once naturally and then be checked. Everything else is buildable/verifiable on demand and has been:

- 6.1 — a clean manual full-pipeline run confirmed (run [29950196867](https://github.com/pdglenchur-glitch/market_ai_pulse/actions/runs/29950196867), all 4 steps passed, ~4 min)
- 6.3/6.4 — `README.md` now has real screenshots (`screenshots/dashboard-{light,dark}.png`) and a full design-decisions section (R2 vs S3, Free Edition constraints, why the dashboard is static, why one workflow, why crypto was cut)
- 6.5 — failure alerting via GitHub Issues: opens an issue labeled `pipeline-failure` on `failure()`, comments instead of duplicating if one's already open, auto-closes on the next `success()`. No new secrets — uses the default `GITHUB_TOKEN` with `issues: write` added to `permissions`. All three paths (create/comment/close) were verified with a temporary test workflow (`_tmp_test_alert.yml`, a fake step that could be forced to fail or succeed) before wiring the real logic into `pipeline.yml` — same "prove it in isolation first" pattern used throughout this project.

Once the project reaches this point, the **only genuinely open item** is the historical-depth question below — everything else in the original plan is done.

**Open question not yet settled:** how much historical depth to retain for trend charts (e.g., cap at a 1-year rolling window, or let it grow unbounded). Not urgent — irrelevant until months of daily history accumulate.

---

## Environment / tooling set up along the way

These aren't in the repo but matter for continuing the work from this machine:

- **`gh` CLI** installed via `winget` and authenticated (`gh auth login`) — used constantly to dispatch workflows and read run logs directly instead of asking the user to check the Actions tab.
- **Node.js** installed via `winget` (`OpenJS.NodeJS.LTS`) specifically to run the dataviz skill's `validate_palette.js` — needed for the muted-palette work, not part of the pipeline itself.
- **`.venv`** at the project root, `requirements.txt` installed into it. `.vscode/settings.json` points the editor at it so imports resolve correctly.
- **Local credentials were never set up** — `.env.example` exists but is unused. R2 access keys and the Databricks token are one-time-reveal secrets that can't be retrieved after creation, so local testing pivoted to running everything through GitHub Actions (which already has the secrets) instead. This shaped a lot of the early workflow: throwaway `_tmp_*.yml` workflows were created, dispatched, read, and deleted repeatedly as a substitute for local iteration. That pattern (scratch workflow → `gh workflow run` → `gh run watch` / `gh run view --log` → delete once proven) is the established way to test anything that needs real Databricks/R2 credentials.

---

## Design decisions and why

**Separate bronze/silver/gold schemas** (`workspace.bronze`, `workspace.silver`, `workspace.gold`), not one flat schema with prefixed table names. The plan's "established config" section only listed `workspace.default` as provisioned (for the volume), which created a real ambiguity about where transform tables should live. Asked the user; they picked the standard medallion convention. These schemas are created via `CREATE SCHEMA IF NOT EXISTS` as part of the build, not manually provisioned.

**SQL warehouse resolved dynamically**, never hardcoded. `databricks/warehouse.py` calls `WorkspaceClient.warehouses.list()` and uses whatever it finds (Free Edition provisions one "Serverless Starter Warehouse" per workspace). Avoids a brittle hardcoded warehouse ID.

**The Lakeflow job is a real Databricks Job**, not just more Python run from GitHub Actions. This was a genuine fork in the road: Phase 1's bronze-table proof used the SQL connector driven remotely from GitHub Actions (works fine, technically), but the architecture calls for the transform to run *inside* Databricks via the Jobs API (`git_source` pulls the `.py` files straight from this GitHub repo at run time, executed as `spark_python_task`s on serverless compute). This was de-risked with a standalone probe *before* building the real transform logic — created a trivial job, ran it, confirmed `git_source` + serverless compute actually works on Free Edition, then deleted the probe. That probe surfaced the requirement that serverless tasks need an explicit `environments` block (`environment_version: "3"`) — omitting it fails immediately with a clear error.

**Job definition is idempotent (create-or-update by name).** `trigger_and_poll_job.py` reads `databricks/lakeflow_job_config.yml` and does `jobs.list(name=...)` → `jobs.reset()` if found, `jobs.create()` if not — every single pipeline run. This means the job definition can never drift from what's in git; there's no separate manual "set up the job once" step to forget. Verified by running the pipeline twice in a row and confirming the second run logged "Updated existing job_id=..." with the *same* ID, not a new one.

**Bronze is overwritten each run; silver accumulates via MERGE upsert.** Bronze = whatever's currently in the raw volume (untouched snapshot). Silver tables have natural keys (e.g. `(symbol, date)`, `(repo, snapshot_date)`) and use `MERGE ... WHEN MATCHED UPDATE ... WHEN NOT MATCHED INSERT` so reruns on the same day update in place instead of duplicating, and history genuinely accumulates run over run. Gold tables are fully recomputed (`CREATE OR REPLACE TABLE ... AS SELECT`) every run since they're cheap derivations of the already-accumulated silver history.

**Weekly → daily cadence switch (2026-07-22).** User asked for a feasibility read before committing. Rate-limit review: yfinance/FRED/Wikipedia/arXiv/R2 all have generous headroom at daily volume; GitHub REST API's 5 req/day is trivial even unauthenticated (deliberately skipped `GH_TOKEN` — user's call when offered). The one real unknown is Databricks Free Edition's compute quota, untested at ~30 job-runs/month vs. the ~4/month this was proven against. **Rollback is a single line**: change the cron in `pipeline.yml` back to `"0 6 * * 1"`. Switching also required fixing `dev_momentum`/`research_pace`'s week-over-week columns, which used `LAG(1)` — correct at weekly cadence, silently wrong (day-over-day) at daily cadence. Now `LAG(..., 7)` since one row accumulates per source per day.

**Market data expanded from 1 symbol to 19** (`^GSPC` benchmark + 11 SPDR sector ETFs + 7-symbol AI basket incl. `BOTZ` as the thematic ETF) partway through Phase 3, once it became clear the `sector_rotation` and `ai_vs_market` gold tables were meaningless with only the S&P 500 pulled. This was flagged to the user as a real scope gap against the original plan (Section 4) before implementing, not silently expanded.

**Custom muted/darker color palette**, replacing the dataviz skill's bright default. User wanted darker, more neutral tones that still read clearly in dark mode. Did *not* eyeball this — installed Node specifically to run `validate_palette.js`, iterated through several candidate hex sets against the actual CVD-safety/contrast/lightness-band checks (chroma-floor failures, CVD-separation failures) until both light and dark variants passed every check. Final categorical hues: slate blue `#2d6bab`/`#4a7bc4`, terracotta `#b35a2a`/`#c96b3a`, pine teal `#1f8a6f`/`#2ba17f`, muted ochre `#b8862f`/`#b0832f`, muted mauve `#9c4f6b`/`#b05f7d` (light/dark).

**Every panel needed its own real visualization** (user feedback — dashboard originally had 3 panels with charts and 2 with only stat tiles). Added: an OHLC-style range bar for Market Snapshot (single floating bar now, will read as a poor-man's candlestick chart once multiple days accumulate); a progress meter for Volatility while accumulating toward its 20-day window, switching to a line chart once ready; a 3-bar rate-comparison chart for Macro Backdrop (deliberately *excluding* CPI, which is an index level not a percentage — mixing units on one axis would have been a real dataviz mistake, not just a style choice); a diverging two-bar chart for AI-vs-market spread and a new cs.AI-vs-cs.LG bar for research pace.

**Bar charts of a single day's value were the wrong form for Research Pace and Dev Momentum specifically** (separate round of user feedback, after the above). Both metrics are fundamentally about *change over time* — a bar chart of today's number can never show "accelerating" or "slowing down," no matter how the underlying window is defined. Research Pace's "trailing 7d" count was already a rolling window; the fix was plotting that rolling value over time (a line chart, same pattern as Public Attention) instead of just showing today's snapshot as a bar. Dev Momentum's raw star count barely moves day to day and is dominated by each repo's overall size, so it switches to `weekly_star_growth` (a diverging bar, colored by sign) once that's available at 7 days of history — the level was never the interesting number, the growth rate was. Verified both new code paths by temporarily swapping fabricated multi-day JSON into `docs/data/` locally (never committed) before trusting them, since real history won't exist for weeks — same empirical-verification pattern used throughout this project.

**Failure alerting via GitHub Issues, not Slack/Discord/email.** Considered a webhook-based notification but that requires the user to go create one and add it as a new secret — real setup friction for a "nice to have." GitHub Issues needed nothing new: the workflow already has `GITHUB_TOKEN`, just needed `issues: write` added to `permissions`. Opens an issue labeled `pipeline-failure` on `failure()`, comments instead of duplicating if one's already open (checked via `gh issue list --label pipeline-failure --state open`), and auto-closes it on the next `success()` — a full create/dedupe/recover loop with zero user setup.

---

## Bugs found and fixed (the non-obvious ones)

Roughly chronological. Several of these were only caught by actually running things (locally, in CI, or via headless-browser screenshots) rather than by code review — that pattern held up repeatedly and is worth continuing.

1. **`read_files(...)` schema inference failure on the first bronze table.** Our JSON is pretty-printed (multi-line), but Spark's JSON reader defaults to line-delimited. Fix: `multiLine => true`.
2. **`DELTA_METADATA_MISMATCH` on bronze overwrite.** After `pull_market_data.py`'s output shape changed (single object → `{records: [...], fetched_at}`), overwriting the old bronze table's schema needs `.option("overwriteSchema", "true")` — `mode("overwrite")` alone doesn't replace schema.
3. **Serverless Databricks Job tasks need an explicit `environments` block.** `InvalidParameterValue: An environment is required for serverless task`. Fixed by adding `environment_version: "3"` and wiring `environment_key` on each task.
4. **A `melt_named_structs` abstraction in `bronze_to_silver.py` had a duplicate-column bug** (struct's own `.date` field collided with an externally-computed `date` column via `.* ` expansion). Simplified to explicit per-source blocks instead of one clever shared helper — matches the general steer toward avoiding premature abstraction.
5. **`.gitignore` almost silently broke publishing.** An unanchored `data/` pattern (meant to ignore local scratch dirs like `ingestion/data/`) was also matching `docs/data/` — the actual published output. Caught because the "Commit and push updated data" step failed with "paths are ignored." Fixed with anchored `/data/` and `/ingestion/data/`.
6. **arXiv API 500s on `max_results=0`.** Wanted just the `totalResults` count without fetching entries; `max_results=1` works, `0` doesn't.
7. **Literal `+` characters in a manually-built query string got double-encoded by `requests`** (`+` → `%2B` instead of being read as a space), silently zeroing out arXiv result counts (200 instead of 785). Fixed by using real spaces and letting `requests` percent-encode them correctly.
8. **Chart.js bars rendering at ~1/4 height, only under `responsive: true` + `maintainAspectRatio: false`.** An initial-sizing race — the canvas gets measured before its container's layout (inside a newly-inserted grid/flex parent) has actually settled. Fixed with a `requestAnimationFrame`-deferred `chart.resize()` after every chart creation (`deferredResize()` helper). Confirmed via headless-Edge screenshots with a minimal isolated Chart.js test page before touching the real dashboard code.
9. **Rotated x-axis labels clipping within their own canvas** at narrow (mobile) widths — the *last* category's rotated label has no neighbor to share space with. Fixed with a consistent 45° rotation (not an auto 0–40° range), more right-side chart padding, and shortening `dev_momentum` labels to bare repo name (full `owner/repo` still in the tooltip).
10. **The Market Snapshot range-bar chart's x-axis auto-started at 0**, so a ~40-point daily high/low spread on a ~7500 base rendered as an invisible sliver. Fixed by explicitly scaling the axis to the actual low/high range with padding.
11. **`attention_index` was showing 100 for every article and looked broken — it wasn't broken, it was badly designed.** The metric is `views / baseline_views * 100` where baseline = each article's first-observed day; with only one day of history, baseline always equals today, so it's trivially 100 for everyone. On top of that, a *bar chart* of a trend-indexed metric was the wrong chart type from the start — it can never show "rising or falling" even with more data. Fixed by conditionally showing raw pageviews (informative immediately) until 2+ distinct days exist, then switching to a multi-line chart of the indexed trend over time. General lesson: a metric/chart can be technically correct and still be uninformative by construction — worth sanity-checking what a visualization *actually communicates* on day one, not just whether the numbers are right.

---

## Things to remember about how this user likes to work

- Wants to see real output, not just be told something works — screenshots (via headless browser), live-URL checks with a fresh/incognito session, actual query results, not just "the workflow succeeded."
- Appreciates being asked before scope expands beyond what was literally planned (e.g., the market-data ticker expansion, the schema-layout ambiguity) rather than having it silently decided.
- Wants a clear, cheap rollback path documented whenever a change carries real uncertainty (the daily-cadence switch).
- Comfortable with iterative empirical debugging (try it, read the actual error, fix, retry) over long chains of reasoning about what *might* be wrong — this project's bug list above all got resolved that way, fast.
