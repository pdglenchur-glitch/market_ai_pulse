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

# --- sector_rotation: trailing performance by sector ETF ---
spark.sql(
    """
    CREATE OR REPLACE TABLE workspace.gold.sector_rotation AS
    SELECT
        symbol, date,
        (close - LAG(close) OVER (PARTITION BY symbol ORDER BY date))
            / LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS daily_return,
        (close - LAG(close, 5) OVER (PARTITION BY symbol ORDER BY date))
            / LAG(close, 5) OVER (PARTITION BY symbol ORDER BY date) AS trailing_5d_return
    FROM workspace.silver.market_data
    WHERE category = 'sector'
    """
)
print("Built workspace.gold.sector_rotation")

# --- volatility: rolling 20-observation realized volatility of the S&P 500 ---
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
    )
    SELECT
        symbol, date,
        STDDEV(daily_return) OVER (
            PARTITION BY symbol ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
        ) AS rolling_20d_volatility
    FROM returns
    """
)
print("Built workspace.gold.volatility")

# --- macro_snapshot: latest value per series + trend direction ---
spark.sql(
    """
    CREATE OR REPLACE TABLE workspace.gold.macro_snapshot AS
    SELECT series, date, value, change, trend FROM (
        SELECT
            series, date, value,
            value - LAG(value) OVER (PARTITION BY series ORDER BY date) AS change,
            CASE
                WHEN LAG(value) OVER (PARTITION BY series ORDER BY date) IS NULL THEN 'n/a'
                WHEN value > LAG(value) OVER (PARTITION BY series ORDER BY date) THEN 'up'
                WHEN value < LAG(value) OVER (PARTITION BY series ORDER BY date) THEN 'down'
                ELSE 'flat'
            END AS trend,
            ROW_NUMBER() OVER (PARTITION BY series ORDER BY date DESC) AS rn
        FROM workspace.silver.macro_data
    )
    WHERE rn = 1
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

# --- dev_momentum: week-over-week star growth per repo.
# Pipeline runs daily, so one row accumulates per repo per day - lag by 7
# rows (not 1) to compare against ~7 days ago rather than yesterday. ---
spark.sql(
    """
    CREATE OR REPLACE TABLE workspace.gold.dev_momentum AS
    SELECT
        repo, snapshot_date, stars,
        stars - LAG(stars, 7) OVER (PARTITION BY repo ORDER BY snapshot_date) AS weekly_star_growth
    FROM workspace.silver.dev_momentum
    """
)
print("Built workspace.gold.dev_momentum")

# --- research_pace: week-over-week change in arXiv submission counts.
# Same daily-cadence lag-by-7 reasoning as dev_momentum above. ---
spark.sql(
    """
    CREATE OR REPLACE TABLE workspace.gold.research_pace AS
    SELECT
        category, snapshot_date, count,
        count - LAG(count, 7) OVER (PARTITION BY category ORDER BY snapshot_date) AS change_from_prior_week
    FROM workspace.silver.research_pace
    """
)
print("Built workspace.gold.research_pace")

print("silver_to_gold complete")
