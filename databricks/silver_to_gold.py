"""Lakeflow job task: silver -> gold (steps 3.6-3.13).

Each gold table is fully recomputed from silver on every run (cheap, since
silver already holds the accumulated history) — no merge/upsert needed here.

Runs inside the job via git_source; `spark` is provided by the runtime.
"""
spark.sql("CREATE SCHEMA IF NOT EXISTS workspace.gold")

# --- market_daily: per-symbol daily return ---
spark.sql(
    """
    CREATE OR REPLACE TABLE workspace.gold.market_daily AS
    SELECT
        symbol, category, date, open, high, low, close, volume,
        close - LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS change,
        (close - LAG(close) OVER (PARTITION BY symbol ORDER BY date))
            / LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS daily_return
    FROM workspace.silver.market_data
    """
)
print("Built workspace.gold.market_daily")

# --- sector_rotation: per-sector daily return (dashboard compounds this over
# whatever window the viewer selects, client-side). volume carried through for
# the trading-volume-share donut. ---
spark.sql(
    """
    CREATE OR REPLACE TABLE workspace.gold.sector_rotation AS
    SELECT
        symbol, date, volume,
        (close - LAG(close) OVER (PARTITION BY symbol ORDER BY date))
            / LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS daily_return
    FROM workspace.silver.market_data
    WHERE category = 'sector'
    """
)
print("Built workspace.gold.sector_rotation")

# --- volatility: rolling 20-observation realized volatility of the S&P 500 ---
# STDDEV over a ROWS BETWEEN 19 PRECEDING frame happily returns a (very noisy)
# value from as few as 2 real observations - it doesn't require the frame to
# actually be full. Gate it explicitly on a running count of real returns so
# "rolling 20-day" only ever reports once 20 real observations exist, instead
# of silently emitting a near-meaningless number labeled as a 20-day figure.
spark.sql(
    """
    CREATE OR REPLACE TABLE workspace.gold.volatility AS
    WITH returns AS (
        SELECT
            symbol, date,
            (close - LAG(close) OVER (PARTITION BY symbol ORDER BY date))
                / LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS daily_return
        FROM workspace.silver.market_data
        WHERE symbol = '^GSPC'
    ),
    numbered AS (
        SELECT *,
            SUM(CASE WHEN daily_return IS NOT NULL THEN 1 ELSE 0 END)
                OVER (PARTITION BY symbol ORDER BY date) AS return_count
        FROM returns
    )
    SELECT
        symbol, date,
        CASE
            WHEN return_count >= 20 THEN STDDEV(daily_return) OVER (
                PARTITION BY symbol ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
            )
        END AS rolling_20d_volatility
    FROM numbered
    """
)
print("Built workspace.gold.volatility")

# --- macro_snapshot: full history per series + trend direction vs. the prior
# observation. Exports every observation (not just the latest) so the
# dashboard can compute change over an arbitrary window client-side; the
# "latest" reading it shows by default is just the max date per series. ---
spark.sql(
    """
    CREATE OR REPLACE TABLE workspace.gold.macro_snapshot AS
    SELECT
        series, date, value,
        value - LAG(value) OVER (PARTITION BY series ORDER BY date) AS change,
        CASE
            WHEN LAG(value) OVER (PARTITION BY series ORDER BY date) IS NULL THEN 'n/a'
            WHEN value > LAG(value) OVER (PARTITION BY series ORDER BY date) THEN 'up'
            WHEN value < LAG(value) OVER (PARTITION BY series ORDER BY date) THEN 'down'
            ELSE 'flat'
        END AS trend
    FROM workspace.silver.macro_data
    """
)
print("Built workspace.gold.macro_snapshot")

# --- ai_vs_market: AI basket average return spread vs the S&P 500 benchmark ---
spark.sql(
    """
    CREATE OR REPLACE TABLE workspace.gold.ai_vs_market AS
    WITH returns AS (
        SELECT
            symbol, category, date,
            (close - LAG(close) OVER (PARTITION BY symbol ORDER BY date))
                / LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS daily_return
        FROM workspace.silver.market_data
        WHERE category IN ('ai_basket', 'benchmark')
    ),
    ai_avg AS (
        SELECT date, AVG(daily_return) AS ai_basket_return
        FROM returns WHERE category = 'ai_basket'
        GROUP BY date
    ),
    benchmark AS (
        SELECT date, daily_return AS benchmark_return
        FROM returns WHERE category = 'benchmark'
    )
    SELECT
        COALESCE(a.date, b.date) AS date,
        a.ai_basket_return,
        b.benchmark_return,
        a.ai_basket_return - b.benchmark_return AS spread
    FROM ai_avg a
    FULL OUTER JOIN benchmark b ON a.date = b.date
    """
)
print("Built workspace.gold.ai_vs_market")

# --- ai_basket_detail: per-symbol rows for the AI basket, for the
# trading-volume-composition donut (ai_vs_market above only has the
# basket-level average, not individual holdings) ---
spark.sql(
    """
    CREATE OR REPLACE TABLE workspace.gold.ai_basket_detail AS
    SELECT
        symbol, date, volume,
        (close - LAG(close) OVER (PARTITION BY symbol ORDER BY date))
            / LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS daily_return
    FROM workspace.silver.market_data
    WHERE category = 'ai_basket'
    """
)
print("Built workspace.gold.ai_basket_detail")

# --- attention_index: normalized pageview trend, indexed to each article's first observed day ---
spark.sql(
    """
    CREATE OR REPLACE TABLE workspace.gold.attention_index AS
    WITH baseline AS (
        SELECT article, MIN(date) AS baseline_date
        FROM workspace.silver.attention_data
        GROUP BY article
    ),
    baseline_views AS (
        SELECT a.article, a.views AS baseline_views
        FROM workspace.silver.attention_data a
        JOIN baseline b ON a.article = b.article AND a.date = b.baseline_date
    )
    SELECT
        s.article, s.date, s.views,
        s.views / bv.baseline_views * 100 AS attention_index
    FROM workspace.silver.attention_data s
    JOIN baseline_views bv ON s.article = bv.article
    """
)
print("Built workspace.gold.attention_index")

# --- dev_momentum: star count per repo per day (dashboard computes growth
# over whatever window the viewer selects, client-side) ---
spark.sql(
    """
    CREATE OR REPLACE TABLE workspace.gold.dev_momentum AS
    SELECT repo, snapshot_date, stars
    FROM workspace.silver.dev_momentum
    """
)
print("Built workspace.gold.dev_momentum")

# --- research_pace: arXiv trailing-7d submission count per day (dashboard
# plots this as a trend line, filterable to whatever window is selected) ---
spark.sql(
    """
    CREATE OR REPLACE TABLE workspace.gold.research_pace AS
    SELECT category, snapshot_date, count
    FROM workspace.silver.research_pace
    """
)
print("Built workspace.gold.research_pace")

print("silver_to_gold complete")
