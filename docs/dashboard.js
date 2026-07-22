const DATA_DIR = "data";

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function fmtNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return Number(value).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function fmtPct(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(2)}%`;
}

function deltaClass(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "neutral";
  return value > 0 ? "good" : value < 0 ? "bad" : "neutral";
}

function deltaArrow(value) {
  if (value === null || value === undefined || Number.isNaN(value) || value === 0) return "";
  return value > 0 ? "▲ " : "▼ ";
}

function statTile(label, value, deltaText, deltaCls) {
  return `
    <div class="stat-tile">
      <div class="stat-label">${label}</div>
      <div class="stat-value">${value}</div>
      ${deltaText !== undefined ? `<div class="stat-delta ${deltaCls}">${deltaText}</div>` : ""}
    </div>`;
}

async function fetchJson(name) {
  const response = await fetch(`${DATA_DIR}/${name}.json`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Failed to load ${name}.json (${response.status})`);
  return response.json();
}

function deferredResize(chart) {
  // Chart.js sizes the canvas from its container on creation; if that
  // container's layout hasn't fully settled yet (e.g. a grid/flex parent
  // inserted moments ago), the initial size can be wrong. A resize deferred
  // a couple frames forces a remeasure once layout has actually settled.
  requestAnimationFrame(() => requestAnimationFrame(() => chart.resize()));
  return chart;
}

function divergingBarChart(canvas, labels, values, formatValue) {
  const good = cssVar("--delta-good");
  const bad = cssVar("--delta-bad");
  const gridline = cssVar("--gridline");
  const textMuted = cssVar("--text-muted");

  return deferredResize(new Chart(canvas, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          data: values,
          backgroundColor: values.map((v) => (v === null ? textMuted : v >= 0 ? good : bad)),
          borderRadius: 4,
          borderSkipped: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => formatValue(ctx.raw),
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: textMuted },
        },
        y: {
          grid: { color: gridline },
          ticks: {
            color: textMuted,
            callback: (v) => formatValue(v),
          },
        },
      },
    },
  }));
}

function categoricalBarChart(canvas, labels, values, formatValue, tooltipLabels) {
  const seriesColors = ["--series-1", "--series-2", "--series-3", "--series-4", "--series-5"].map(cssVar);
  const gridline = cssVar("--gridline");
  const textMuted = cssVar("--text-muted");
  const fullLabels = tooltipLabels || labels;

  return deferredResize(new Chart(canvas, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          data: values,
          backgroundColor: labels.map((_, i) => seriesColors[i % seriesColors.length]),
          borderRadius: 4,
          borderSkipped: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { right: 70 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: (items) => fullLabels[items[0].dataIndex],
            label: (ctx) => formatValue(ctx.raw),
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: textMuted, autoSkip: false, maxRotation: 45, minRotation: 45 },
        },
        y: {
          grid: { color: gridline },
          ticks: { color: textMuted, callback: (v) => formatValue(v) },
        },
      },
    },
  }));
}

async function renderMarketSnapshot() {
  const el = document.getElementById("market-content");
  try {
    const data = await fetchJson("market_daily");
    const benchmark = data.find((r) => r.symbol === "^GSPC");
    if (!benchmark) throw new Error("Benchmark row not found");

    const deltaText = benchmark.daily_return === null
      ? "First reading — no prior day yet"
      : `${deltaArrow(benchmark.daily_return)}${fmtPct(benchmark.daily_return)} (${fmtNumber(benchmark.change)})`;

    el.innerHTML = `
      <div class="kpi-row">
        ${statTile("S&amp;P 500 (^GSPC)", fmtNumber(benchmark.close), deltaText, deltaClass(benchmark.daily_return))}
        ${statTile("Open", fmtNumber(benchmark.open))}
        ${statTile("High", fmtNumber(benchmark.high))}
        ${statTile("Low", fmtNumber(benchmark.low))}
      </div>
      <p class="panel-meta" style="margin-top:12px">As of ${benchmark.date}</p>
    `;
  } catch (err) {
    el.innerHTML = `<p class="panel-error">Couldn't load market data: ${err.message}</p>`;
  }
}

async function renderSectorRotation() {
  const el = document.getElementById("sector-content");
  try {
    const data = await fetchJson("market_daily");
    const sectors = data
      .filter((r) => r.category === "sector")
      .sort((a, b) => (b.daily_return ?? -Infinity) - (a.daily_return ?? -Infinity));

    if (sectors.every((r) => r.daily_return === null)) {
      el.innerHTML = `
        <div class="stat-tile">
          <div class="stat-label">Daily return by sector</div>
          <div class="stat-value">—</div>
          <div class="stat-delta neutral">Accumulating history — needs a second day of data</div>
        </div>`;
      return;
    }

    el.innerHTML = `<div class="chart-wrap chart-tall"><canvas id="sector-chart"></canvas></div>`;
    divergingBarChart(
      document.getElementById("sector-chart"),
      sectors.map((r) => r.symbol),
      sectors.map((r) => r.daily_return),
      fmtPct
    );
  } catch (err) {
    el.innerHTML = `<p class="panel-error">Couldn't load sector data: ${err.message}</p>`;
  }
}

async function renderVolatility() {
  const el = document.getElementById("volatility-content");
  try {
    const data = await fetchJson("volatility");
    const latest = data[data.length - 1];
    if (!latest || latest.rolling_20d_volatility === null) {
      el.innerHTML = `
        <div class="stat-tile">
          <div class="stat-label">Rolling 20-day volatility</div>
          <div class="stat-value">—</div>
          <div class="stat-delta neutral">Accumulating history — needs 20 trading days</div>
        </div>`;
      return;
    }
    el.innerHTML = statTile(
      "Rolling 20-day volatility",
      fmtPct(latest.rolling_20d_volatility),
      `As of ${latest.date}`,
      "neutral"
    );
  } catch (err) {
    el.innerHTML = `<p class="panel-error">Couldn't load volatility data: ${err.message}</p>`;
  }
}

async function renderMacro() {
  const el = document.getElementById("macro-content");
  try {
    const data = await fetchJson("macro_snapshot");
    const labels = {
      cpi: "CPI",
      unemployment_rate: "Unemployment",
      fed_funds_rate: "Fed Funds Rate",
      "10y_yield": "10Y Yield",
    };
    const trendArrow = { up: "▲", down: "▼", flat: "→", "n/a": "" };

    const tiles = data
      .map((row) => {
        const label = labels[row.series] || row.series;
        const cls = row.trend === "up" ? "good" : row.trend === "down" ? "bad" : "neutral";
        const deltaText = row.trend === "n/a" ? `As of ${row.date}` : `${trendArrow[row.trend]} ${fmtNumber(row.change)} (${row.date})`;
        return statTile(label, fmtNumber(row.value), deltaText, cls);
      })
      .join("");

    el.innerHTML = `<div class="kpi-row">${tiles}</div>`;
  } catch (err) {
    el.innerHTML = `<p class="panel-error">Couldn't load macro data: ${err.message}</p>`;
  }
}

async function renderAiPulse() {
  const el = document.getElementById("ai-content");
  try {
    const [aiVsMarket, attention, devMomentum, researchPace] = await Promise.all([
      fetchJson("ai_vs_market"),
      fetchJson("attention_index"),
      fetchJson("dev_momentum"),
      fetchJson("research_pace"),
    ]);

    const latestSpread = aiVsMarket[aiVsMarket.length - 1];
    const spreadText = latestSpread && latestSpread.spread !== null
      ? fmtPct(latestSpread.spread)
      : "Accumulating history";

    el.innerHTML = `
      <div class="kpi-row">
        ${statTile("AI basket vs. S&amp;P 500 (spread)", spreadText, latestSpread ? `As of ${latestSpread.date}` : undefined, deltaClass(latestSpread && latestSpread.spread))}
        ${statTile("arXiv cs.AI (7d)", researchPace.find((r) => r.category === "cs.AI")?.count ?? "—")}
        ${statTile("arXiv cs.LG (7d)", researchPace.find((r) => r.category === "cs.LG")?.count ?? "—")}
      </div>

      <div class="two-col subsection">
        <div>
          <h3>Public attention (Wikipedia pageviews, indexed to 100)</h3>
          <div class="chart-wrap"><canvas id="attention-chart"></canvas></div>
        </div>
        <div>
          <h3>Dev momentum (GitHub stars)</h3>
          <div class="chart-wrap"><canvas id="dev-chart"></canvas></div>
        </div>
      </div>
    `;

    const latestByArticle = {};
    for (const row of attention) {
      const prev = latestByArticle[row.article];
      if (!prev || row.date > prev.date) latestByArticle[row.article] = row;
    }
    const attentionRows = Object.values(latestByArticle);
    categoricalBarChart(
      document.getElementById("attention-chart"),
      attentionRows.map((r) => r.article.replace(/_/g, " ")),
      attentionRows.map((r) => r.attention_index),
      (v) => fmtNumber(v, 0)
    );

    const latestByRepo = {};
    for (const row of devMomentum) {
      const prev = latestByRepo[row.repo];
      if (!prev || row.snapshot_date > prev.snapshot_date) latestByRepo[row.repo] = row;
    }
    const devRows = Object.values(latestByRepo).sort((a, b) => b.stars - a.stars);
    categoricalBarChart(
      document.getElementById("dev-chart"),
      devRows.map((r) => r.repo.split("/")[1]),
      devRows.map((r) => r.stars),
      (v) => fmtNumber(v, 0),
      devRows.map((r) => r.repo)
    );
  } catch (err) {
    el.innerHTML = `<p class="panel-error">Couldn't load AI pulse data: ${err.message}</p>`;
  }
}

async function renderLastUpdated() {
  const el = document.getElementById("last-updated");
  try {
    const data = await fetchJson("market_daily");
    const dates = data.map((r) => r.date).sort();
    el.textContent = `Last updated: ${dates[dates.length - 1]}`;
  } catch (err) {
    el.textContent = "Last updated: unavailable";
  }
}

function initThemeToggle() {
  const button = document.getElementById("theme-toggle");
  const stored = localStorage.getItem("theme");
  if (stored) document.documentElement.setAttribute("data-theme", stored);

  button.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme")
      || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("theme", next);
    // Charts read CSS vars at creation time, so re-render on theme change.
    renderAll();
  });
}

function renderAll() {
  renderLastUpdated();
  renderMarketSnapshot();
  renderSectorRotation();
  renderVolatility();
  renderMacro();
  renderAiPulse();
}

initThemeToggle();
renderAll();
