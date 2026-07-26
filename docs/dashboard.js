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

function statTile(label, value, deltaText, deltaCls, titleAttr) {
  return `
    <div class="stat-tile"${titleAttr ? ` title="${titleAttr}"` : ""}>
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

// ---- time-window helpers ---------------------------------------------
// Shared across every chart that lets the viewer pick how far back to look.
// Two computation primitives cover every metric on the dashboard:
//   - compoundReturn: for series that already have a daily % return column
//     (sector_rotation, ai_vs_market) - compounds those returns over the
//     window, which is mathematically the same as (end-start)/start but
//     doesn't require re-fetching raw prices.
//   - windowDeltaByGroup: for level-valued series (star counts, macro
//     rates) - just end-value minus start-value within the window.

const WINDOW_OPTIONS = [
  { label: "1D", days: 1 },
  { label: "7D", days: 7 },
  { label: "30D", days: 30 },
  { label: "90D", days: 90 },
  { label: "All", days: null },
];

function addDaysToDateStr(dateStr, delta) {
  const d = new Date(`${dateStr}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + delta);
  return d.toISOString().slice(0, 10);
}

function filterByWindow(rows, dateKey, days) {
  if (days == null || rows.length === 0) return rows;
  const latest = rows.reduce((max, r) => (r[dateKey] > max ? r[dateKey] : max), rows[0][dateKey]);
  const cutoff = addDaysToDateStr(latest, -days);
  return rows.filter((r) => r[dateKey] >= cutoff);
}

function groupBy(rows, keyFn) {
  const groups = {};
  for (const row of rows) (groups[keyFn(row)] ??= []).push(row);
  return groups;
}

// Both return { value, startDate, endDate } (or null if there's not enough
// history yet) so callers can show exactly which dates a comparison covers,
// not just the computed number.

// filterByWindow's cutoff spans `days + 1` calendar days (inclusive of both
// ends), which is what a level-to-level endpoint comparison needs (e.g.
// windowDeltaByGroup) - but daily_return rows are each *already* a 1-day-back
// delta, so compounding them only needs a span of exactly `days`. Without
// this adjustment, an "N-day" window silently compounds N+1 days of return.
function periodSpanDays(days) {
  return days == null ? null : Math.max(days - 1, 0);
}

function compoundReturn(rows, dateKey, valueKey, days) {
  const sorted = rows.slice().sort((a, b) => a[dateKey].localeCompare(b[dateKey]));
  const windowed = filterByWindow(sorted, dateKey, periodSpanDays(days)).filter((r) => r[valueKey] !== null);
  if (windowed.length === 0) return null;
  const value = windowed.reduce((acc, r) => acc * (1 + r[valueKey]), 1) - 1;
  // A daily-return series values day T against day T-1's close, so the true
  // comparison start is one trading day before the first windowed row, not
  // the row itself - look it up in the full (unfiltered-by-window) history.
  const firstIdx = sorted.findIndex((r) => r[dateKey] === windowed[0][dateKey]);
  const startDate = firstIdx > 0 ? sorted[firstIdx - 1][dateKey] : windowed[0][dateKey];
  const endDate = windowed[windowed.length - 1][dateKey];
  return { value, startDate, endDate };
}

function windowCompoundReturnByGroup(rows, groupKey, dateKey, valueKey, days) {
  const groups = groupBy(rows, (r) => r[groupKey]);
  const result = {};
  for (const [key, groupRows] of Object.entries(groups)) {
    result[key] = compoundReturn(groupRows, dateKey, valueKey, days);
  }
  return result;
}

function windowDeltaByGroup(rows, groupKey, dateKey, valueKey, days) {
  const groups = groupBy(
    rows.filter((r) => r[valueKey] !== null && r[valueKey] !== undefined),
    (r) => r[groupKey]
  );
  const result = {};
  for (const [key, groupRows] of Object.entries(groups)) {
    const windowed = filterByWindow(groupRows, dateKey, days).sort((a, b) => a[dateKey].localeCompare(b[dateKey]));
    result[key] =
      windowed.length < 2
        ? null
        : {
            value: windowed[windowed.length - 1][valueKey] - windowed[0][valueKey],
            startDate: windowed[0][dateKey],
            endDate: windowed[windowed.length - 1][dateKey],
          };
  }
  return result;
}

// Sums valueKey per group within the window (e.g. total trading volume per
// symbol) rather than differencing endpoints. Every group shares the same
// window, so the date range is returned once for the whole result rather
// than per group.
function windowSumByGroup(rows, groupKey, dateKey, valueKey, days) {
  const windowed = filterByWindow(
    rows.filter((r) => r[valueKey] !== null && r[valueKey] !== undefined),
    dateKey,
    days
  );
  const sums = {};
  for (const row of windowed) {
    sums[row[groupKey]] = (sums[row[groupKey]] || 0) + row[valueKey];
  }
  const dates = windowed.map((r) => r[dateKey]).sort();
  return {
    sums,
    startDate: dates[0],
    endDate: dates[dates.length - 1],
  };
}

// Keeps the top n groups by value (descending) and folds the rest into a
// single "Other" bucket, for donut/pie forms where too many slices stop
// being colorblind-distinguishable.
function topNPlusOther(sums, n, otherLabel = "Other") {
  const entries = Object.entries(sums).sort((a, b) => b[1] - a[1]);
  const kept = entries.slice(0, n);
  const rest = entries.slice(n);
  const otherTotal = rest.reduce((acc, [, v]) => acc + v, 0);
  const result = kept.map(([key, value]) => ({ key, value }));
  if (rest.length > 0) result.push({ key: otherLabel, value: otherTotal });
  return result;
}

function windowSelectorHtml(active) {
  const buttons = WINDOW_OPTIONS.map(
    (opt) =>
      `<button type="button" data-days="${opt.days}" class="${opt.days === active ? "active" : ""}">${opt.label}</button>`
  ).join("");
  return `<div class="window-selector">${buttons}</div>`;
}

function wireWindowSelector(container, onSelect) {
  container.querySelectorAll(".window-selector button").forEach((btn) => {
    btn.addEventListener("click", () => {
      const days = btn.dataset.days === "null" ? null : Number(btn.dataset.days);
      onSelect(days);
    });
  });
}

// ---- chart builders -----------------------------------------------------

function divergingBarChart(canvas, labels, values, formatValue, tooltipLabels, dateRanges) {
  const good = cssVar("--delta-good");
  const bad = cssVar("--delta-bad");
  const gridline = cssVar("--gridline");
  const textMuted = cssVar("--text-muted");
  const fullLabels = tooltipLabels || labels;

  return deferredResize(new Chart(canvas, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          data: values.map((v) => (v === null ? 0 : v)),
          backgroundColor: values.map((v) => (v === null ? textMuted : v >= 0 ? good : bad)),
          borderRadius: 4,
          borderSkipped: false,
          minBarLength: 4,
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
            title: (items) => fullLabels[items[0].dataIndex],
            label: (ctx) => formatValue(values[ctx.dataIndex]),
            afterLabel: (ctx) => (dateRanges && dateRanges[ctx.dataIndex]) || undefined,
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

function lineChart(canvas, labels, values, formatValue, colorVar = "--series-1") {
  const color = cssVar(colorVar);
  const gridline = cssVar("--gridline");
  const textMuted = cssVar("--text-muted");

  return deferredResize(new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          data: values,
          borderColor: color,
          backgroundColor: color,
          pointRadius: 3,
          pointHoverRadius: 5,
          borderWidth: 2,
          tension: 0.15,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (ctx) => formatValue(ctx.raw) } },
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: textMuted } },
        y: { grid: { color: gridline }, ticks: { color: textMuted, callback: (v) => formatValue(v) } },
      },
    },
  }));
}

function multiLineChart(canvas, labels, series, formatValue) {
  const gridline = cssVar("--gridline");
  const textMuted = cssVar("--text-muted");

  return deferredResize(new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: series.map((s) => ({
        label: s.label,
        data: s.data,
        borderColor: cssVar(s.colorVar),
        backgroundColor: cssVar(s.colorVar),
        pointRadius: 3,
        pointHoverRadius: 5,
        borderWidth: 2,
        tension: 0.15,
        spanGaps: true,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true, position: "bottom", labels: { color: textMuted, boxWidth: 12, font: { size: 11 } } },
        tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${formatValue(ctx.raw)}` } },
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: textMuted } },
        y: { grid: { color: gridline }, ticks: { color: textMuted, callback: (v) => formatValue(v) } },
      },
    },
  }));
}

function donutChart(canvas, labels, values, formatValue, colors) {
  const surface = cssVar("--surface-1");
  const textMuted = cssVar("--text-muted");
  const total = values.reduce((acc, v) => acc + v, 0);

  return deferredResize(new Chart(canvas, {
    type: "doughnut",
    data: {
      labels,
      datasets: [
        {
          data: values,
          backgroundColor: colors,
          borderColor: surface,
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: true,
          position: "bottom",
          labels: { color: textMuted, boxWidth: 12, font: { size: 11 } },
        },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const pct = total > 0 ? (ctx.raw / total) * 100 : 0;
              return `${ctx.label}: ${pct.toFixed(1)}% (${formatValue(ctx.raw)})`;
            },
          },
        },
      },
    },
  }));
}

function latestPerKey(rows, keyFn, dateFn) {
  const byKey = {};
  for (const row of rows) {
    const key = keyFn(row);
    const prev = byKey[key];
    if (!prev || dateFn(row) > dateFn(prev)) byKey[key] = row;
  }
  return Object.values(byKey);
}

function meter(pct, label) {
  return `
    <div class="meter">
      <div class="meter-track"><div class="meter-fill" style="width:${Math.min(100, Math.max(0, pct))}%"></div></div>
      <div class="meter-label">${label}</div>
    </div>`;
}

// ---- panels ---------------------------------------------------------------

async function renderMarketSnapshot() {
  const el = document.getElementById("market-content");
  try {
    const data = await fetchJson("market_daily");
    const rows = data.filter((r) => r.symbol === "^GSPC").sort((a, b) => a.date.localeCompare(b.date));
    if (rows.length === 0) throw new Error("Benchmark row not found");
    const latest = rows[rows.length - 1];

    let days = 30;
    const draw = () => {
      const windowed = filterByWindow(rows, "date", periodSpanDays(days));
      const first = windowed[0];
      const periodHigh = Math.max(...windowed.map((r) => r.high));
      const periodLow = Math.min(...windowed.map((r) => r.low));
      const ret = compoundReturn(rows, "date", "daily_return", days);
      const deltaText = ret === null ? "First reading — no prior day yet" : `${deltaArrow(ret.value)}${fmtPct(ret.value)}`;
      const rangeText = ret ? `${ret.startDate} → ${ret.endDate}` : `As of ${latest.date}`;

      el.innerHTML = `
        <div class="chart-header">
          <h3>S&amp;P 500 snapshot</h3>
          ${windowSelectorHtml(days)}
        </div>
        <div class="kpi-row">
          ${statTile(
            "S&amp;P 500 (^GSPC)",
            fmtNumber(latest.close),
            deltaText,
            deltaClass(ret ? ret.value : null),
            ret ? `Compared to close on ${ret.startDate}` : undefined
          )}
          ${statTile("Open", fmtNumber(first.open), undefined, undefined, `Open on ${first.date}`)}
          ${statTile("High", fmtNumber(periodHigh), undefined, undefined, `Highest daily high, ${first.date} → ${latest.date}`)}
          ${statTile("Low", fmtNumber(periodLow), undefined, undefined, `Lowest daily low, ${first.date} → ${latest.date}`)}
        </div>
        <p class="panel-meta" style="margin-top:12px" title="${rangeText}">Window: ${rangeText}</p>
      `;
      wireWindowSelector(el, (newDays) => {
        days = newDays;
        draw();
      });
    };
    draw();
  } catch (err) {
    el.innerHTML = `<p class="panel-error">Couldn't load market data: ${err.message}</p>`;
  }
}

async function renderSectorRotation() {
  const el = document.getElementById("sector-content");
  try {
    const data = await fetchJson("sector_rotation");

    if (data.every((r) => r.daily_return === null)) {
      el.innerHTML = `
        <div class="stat-tile">
          <div class="stat-label">Return by sector</div>
          <div class="stat-value">—</div>
          <div class="stat-delta neutral">Accumulating history — needs a second day of data</div>
        </div>`;
      return;
    }

    el.innerHTML = `
      <div id="sector-return-panel"></div>
      <div id="sector-volume-panel" class="subsection"></div>
    `;
    renderSectorReturnChart(document.getElementById("sector-return-panel"), data);
    renderSectorVolumeChart(document.getElementById("sector-volume-panel"), data);
  } catch (err) {
    el.innerHTML = `<p class="panel-error">Couldn't load sector data: ${err.message}</p>`;
  }
}

function renderSectorReturnChart(container, data) {
  let days = 30;
  const draw = () => {
    const changes = windowCompoundReturnByGroup(data, "symbol", "date", "daily_return", days);
    const symbols = Object.keys(changes)
      .filter((s) => changes[s] !== null)
      .sort((a, b) => changes[b].value - changes[a].value);

    container.innerHTML = `
      <div class="chart-header">
        <h3>Return by sector</h3>
        ${windowSelectorHtml(days)}
      </div>
      <div class="chart-wrap chart-tall"><canvas id="sector-chart"></canvas></div>
    `;
    wireWindowSelector(container, (newDays) => {
      days = newDays;
      draw();
    });
    divergingBarChart(
      document.getElementById("sector-chart"),
      symbols,
      symbols.map((s) => changes[s].value),
      fmtPct,
      undefined,
      symbols.map((s) => `${changes[s].startDate} → ${changes[s].endDate}`)
    );
  };
  draw();
}

function renderSectorVolumeChart(container, data) {
  let days = 30;
  const draw = () => {
    const { sums, startDate, endDate } = windowSumByGroup(data, "symbol", "date", "volume", days);
    const slices = topNPlusOther(sums, 6);
    const ready = slices.length > 0;

    container.innerHTML = `
      <div class="chart-header">
        <h3>Trading volume share by sector</h3>
        ${windowSelectorHtml(days)}
      </div>
      ${
        ready
          ? `<div class="chart-wrap"><canvas id="sector-volume-chart"></canvas></div>
             <p class="panel-meta" style="margin-top:8px">Window: ${startDate} → ${endDate}</p>`
          : `<p class="panel-meta">Not enough history in this window yet</p>`
      }
    `;
    wireWindowSelector(container, (newDays) => {
      days = newDays;
      draw();
    });

    if (ready) {
      const colors = slices.map((s, i) => (s.key === "Other" ? cssVar("--text-muted") : cssVar(`--series-${i + 1}`)));
      donutChart(
        document.getElementById("sector-volume-chart"),
        slices.map((s) => s.key),
        slices.map((s) => s.value),
        (v) => fmtNumber(v, 0),
        colors
      );
    }
  };
  draw();
}

async function renderVolatility() {
  const el = document.getElementById("volatility-content");
  try {
    const data = await fetchJson("volatility");
    const withValues = data.filter((d) => d.rolling_20d_volatility !== null);
    const latest = data[data.length - 1];

    if (withValues.length === 0) {
      const collected = data.length;
      el.innerHTML = `
        <div class="stat-tile">
          <div class="stat-label">Rolling 20-day volatility</div>
          <div class="stat-value">—</div>
          ${meter((collected / 20) * 100, `${collected} / 20 trading days collected`)}
        </div>`;
      return;
    }

    let days = 30;
    const draw = () => {
      const windowed = filterByWindow(withValues, "date", days);
      el.innerHTML = `
        ${statTile("Rolling 20-day volatility", fmtPct(latest.rolling_20d_volatility), `As of ${latest.date}`, "neutral")}
        <div class="subsection">
          <div class="chart-header">
            <h3>Volatility over time</h3>
            ${windowSelectorHtml(days)}
          </div>
          <div class="chart-wrap"><canvas id="volatility-chart"></canvas></div>
        </div>
      `;
      wireWindowSelector(el, (newDays) => {
        days = newDays;
        draw();
      });
      lineChart(
        document.getElementById("volatility-chart"),
        windowed.map((d) => d.date),
        windowed.map((d) => d.rolling_20d_volatility),
        fmtPct
      );
    };
    draw();
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
    // CPI is an index level, not a percentage - it stays in the KPI row only.
    // The three rate-like series share a unit (%), so they're comparable on one chart.
    const rateSeries = ["unemployment_rate", "fed_funds_rate", "10y_yield"];
    const rateRows = data.filter((row) => rateSeries.includes(row.series));

    let days = 30;
    const draw = () => {
      const latestRows = latestPerKey(data, (r) => r.series, (r) => r.date);
      const tiles = latestRows
        .map((row) => {
          const label = labels[row.series] || row.series;
          const cls = row.trend === "up" ? "good" : row.trend === "down" ? "bad" : "neutral";
          const deltaText = row.trend === "n/a" ? `As of ${row.date}` : `${trendArrow[row.trend]} ${fmtNumber(row.change)} (${row.date})`;
          return statTile(label, fmtNumber(row.value), deltaText, cls);
        })
        .join("");

      const changes = windowDeltaByGroup(rateRows, "series", "date", "value", days);
      const anyData = rateSeries.some((s) => changes[s] !== undefined);
      const pending = rateSeries.filter((s) => changes[s] === undefined || changes[s] === null).map((s) => labels[s] || s);

      el.innerHTML = `
        <div class="kpi-row">${tiles}</div>
        <div class="subsection">
          <div class="chart-header">
            <h3>Rates: change (percentage points)</h3>
            ${windowSelectorHtml(days)}
          </div>
          ${
            anyData
              ? `<div class="chart-wrap" style="height:170px"><canvas id="macro-rate-chart"></canvas></div>`
              : `<p class="panel-meta">Accumulating history</p>`
          }
          ${
            anyData && pending.length > 0
              ? `<p class="panel-meta">${pending.join(" and ")} update monthly — no bar until a second reading lands.</p>`
              : ""
          }
        </div>
      `;
      wireWindowSelector(el, (newDays) => {
        days = newDays;
        draw();
      });

      if (anyData) {
        divergingBarChart(
          document.getElementById("macro-rate-chart"),
          rateSeries.map((s) => labels[s] || s),
          rateSeries.map((s) => (changes[s] ? changes[s].value : null)),
          (v) => (v === null ? "Not enough history in this window yet" : `${v >= 0 ? "+" : ""}${fmtNumber(v)}pp`),
          undefined,
          rateSeries.map((s) => (changes[s] ? `${changes[s].startDate} → ${changes[s].endDate}` : undefined))
        );
      }
    };
    draw();
  } catch (err) {
    el.innerHTML = `<p class="panel-error">Couldn't load macro data: ${err.message}</p>`;
  }
}

// Fixed roster, fixed color per symbol (never rank-based) since these seven
// names don't change day to day, unlike sector volume share above.
const AI_BASKET_COLOR_ORDER = ["NVDA", "MSFT", "GOOGL", "META", "PLTR", "AMD", "BOTZ"];

function renderSpreadChart(container, aiVsMarket, aiBasketDetail) {
  container.innerHTML = `
    <div id="ai-spread-return-panel"></div>
    <div id="ai-basket-volume-panel" class="subsection"></div>
  `;
  renderAiSpreadReturnChart(document.getElementById("ai-spread-return-panel"), aiVsMarket);
  renderAiBasketVolumeChart(document.getElementById("ai-basket-volume-panel"), aiBasketDetail);
}

function renderAiSpreadReturnChart(container, aiVsMarket) {
  if (aiVsMarket.every((r) => r.spread === null)) {
    container.innerHTML = `
      <h3>AI basket vs. S&amp;P 500</h3>
      <div class="stat-tile">
        <div class="stat-label">Spread</div>
        <div class="stat-value">—</div>
        <div class="stat-delta neutral">Accumulating history — needs a second day of data</div>
      </div>`;
    return;
  }

  let days = 30;
  const draw = () => {
    const aiReturn = compoundReturn(aiVsMarket, "date", "ai_basket_return", days);
    const benchReturn = compoundReturn(aiVsMarket, "date", "benchmark_return", days);
    const ready = aiReturn !== null && benchReturn !== null;

    container.innerHTML = `
      <div class="chart-header">
        <h3>AI basket vs. S&amp;P 500</h3>
        ${windowSelectorHtml(days)}
      </div>
      ${
        ready
          ? `<div class="chart-wrap" style="height:160px"><canvas id="ai-spread-chart"></canvas></div>`
          : `<p class="panel-meta">Not enough history in this window yet</p>`
      }
    `;
    wireWindowSelector(container, (newDays) => {
      days = newDays;
      draw();
    });

    if (ready) {
      divergingBarChart(
        document.getElementById("ai-spread-chart"),
        ["AI basket", "S&P 500"],
        [aiReturn.value, benchReturn.value],
        fmtPct,
        undefined,
        [`${aiReturn.startDate} → ${aiReturn.endDate}`, `${benchReturn.startDate} → ${benchReturn.endDate}`]
      );
    }
  };
  draw();
}

function renderAiBasketVolumeChart(container, aiBasketDetail) {
  let days = 30;
  const draw = () => {
    const { sums, startDate, endDate } = windowSumByGroup(aiBasketDetail, "symbol", "date", "volume", days);
    const symbols = AI_BASKET_COLOR_ORDER.filter((s) => sums[s] > 0);
    const ready = symbols.length > 0;

    container.innerHTML = `
      <div class="chart-header">
        <h3>AI basket composition (trading volume)</h3>
        ${windowSelectorHtml(days)}
      </div>
      ${
        ready
          ? `<div class="chart-wrap"><canvas id="ai-basket-volume-chart"></canvas></div>
             <p class="panel-meta" style="margin-top:8px">Window: ${startDate} → ${endDate}</p>`
          : `<p class="panel-meta">Not enough history in this window yet</p>`
      }
    `;
    wireWindowSelector(container, (newDays) => {
      days = newDays;
      draw();
    });

    if (ready) {
      const colors = symbols.map((s) => cssVar(`--series-${AI_BASKET_COLOR_ORDER.indexOf(s) + 1}`));
      donutChart(
        document.getElementById("ai-basket-volume-chart"),
        symbols,
        symbols.map((s) => sums[s]),
        (v) => fmtNumber(v, 0),
        colors
      );
    }
  };
  draw();
}

function renderResearchChart(container, researchPace) {
  const dates = [...new Set(researchPace.map((r) => r.snapshot_date))].sort();

  if (dates.length < 2) {
    container.innerHTML = `
      <h3>Research pace (arXiv, trailing 7d)</h3>
      <div class="chart-wrap" style="height:160px"><canvas id="research-chart"></canvas></div>
    `;
    categoricalBarChart(
      document.getElementById("research-chart"),
      researchPace.map((r) => r.category),
      researchPace.map((r) => r.count),
      (v) => fmtNumber(v, 0)
    );
    return;
  }

  let days = 30;
  const draw = () => {
    const windowed = filterByWindow(researchPace, "snapshot_date", days);
    const windowDates = [...new Set(windowed.map((r) => r.snapshot_date))].sort();
    const byCategory = groupBy(windowed, (r) => r.category);
    const categories = Object.keys(byCategory);

    container.innerHTML = `
      <div class="chart-header">
        <h3>Research pace trend (arXiv, trailing 7d count)</h3>
        ${windowSelectorHtml(days)}
      </div>
      <div class="chart-wrap" style="height:160px"><canvas id="research-chart"></canvas></div>
    `;
    wireWindowSelector(container, (newDays) => {
      days = newDays;
      draw();
    });

    const series = categories.map((category, i) => ({
      label: category,
      data: windowDates.map((d) => byCategory[category].find((r) => r.snapshot_date === d)?.count ?? null),
      colorVar: `--series-${(i % 5) + 1}`,
    }));
    multiLineChart(document.getElementById("research-chart"), windowDates, series, (v) => fmtNumber(v, 0));
  };
  draw();
}

function renderAttentionChart(container, attention) {
  const dates = [...new Set(attention.map((r) => r.date))].sort();
  const byArticle = groupBy(attention, (r) => r.article);
  const articles = Object.keys(byArticle);

  if (dates.length < 2) {
    container.innerHTML = `
      <h3>Public attention (Wikipedia pageviews)</h3>
      <div class="chart-wrap"><canvas id="attention-chart"></canvas></div>
    `;
    const latestRows = articles.map((a) => byArticle[a][byArticle[a].length - 1]);
    categoricalBarChart(
      document.getElementById("attention-chart"),
      latestRows.map((r) => r.article.replace(/_/g, " ")),
      latestRows.map((r) => r.views),
      (v) => fmtNumber(v, 0)
    );
    return;
  }

  let days = 30;
  const draw = () => {
    const windowed = filterByWindow(attention, "date", days);
    const windowDates = [...new Set(windowed.map((r) => r.date))].sort();
    const byArticleWindowed = groupBy(windowed, (r) => r.article);

    container.innerHTML = `
      <div class="chart-header">
        <h3>Public attention trend (Wikipedia pageviews, indexed to window start = 100)</h3>
        ${windowSelectorHtml(days)}
      </div>
      <div class="chart-wrap"><canvas id="attention-chart"></canvas></div>
    `;
    wireWindowSelector(container, (newDays) => {
      days = newDays;
      draw();
    });

    const series = Object.keys(byArticleWindowed).map((article, i) => {
      const rows = byArticleWindowed[article].slice().sort((a, b) => a.date.localeCompare(b.date));
      const baseline = rows[0]?.views;
      return {
        label: article.replace(/_/g, " "),
        data: windowDates.map((d) => {
          const row = rows.find((r) => r.date === d);
          return row && baseline ? (row.views / baseline) * 100 : null;
        }),
        colorVar: `--series-${(i % 5) + 1}`,
      };
    });
    multiLineChart(document.getElementById("attention-chart"), windowDates, series, (v) => fmtNumber(v, 0));
  };
  draw();
}

function renderDevChart(container, devMomentum) {
  const dates = [...new Set(devMomentum.map((r) => r.snapshot_date))].sort();
  const byRepo = groupBy(devMomentum, (r) => r.repo);
  const repos = Object.keys(byRepo);

  if (dates.length < 2) {
    container.innerHTML = `
      <h3>Dev momentum (GitHub stars)</h3>
      <div class="chart-wrap"><canvas id="dev-chart"></canvas></div>
    `;
    const latestRows = repos.map((r) => byRepo[r][byRepo[r].length - 1]).sort((a, b) => b.stars - a.stars);
    categoricalBarChart(
      document.getElementById("dev-chart"),
      latestRows.map((r) => r.repo.split("/")[1]),
      latestRows.map((r) => r.stars),
      (v) => fmtNumber(v, 0),
      latestRows.map((r) => r.repo)
    );
    return;
  }

  let days = 30;
  const draw = () => {
    const changes = windowDeltaByGroup(devMomentum, "repo", "snapshot_date", "stars", days);
    const withChanges = Object.keys(changes)
      .filter((r) => changes[r] !== null)
      .sort((a, b) => changes[b].value - changes[a].value);

    container.innerHTML = `
      <div class="chart-header">
        <h3>Dev momentum (star growth)</h3>
        ${windowSelectorHtml(days)}
      </div>
      ${
        withChanges.length === 0
          ? `<p class="panel-meta">Not enough history in this window yet</p>`
          : `<div class="chart-wrap"><canvas id="dev-chart"></canvas></div>`
      }
    `;
    wireWindowSelector(container, (newDays) => {
      days = newDays;
      draw();
    });

    if (withChanges.length > 0) {
      divergingBarChart(
        document.getElementById("dev-chart"),
        withChanges.map((r) => r.split("/")[1]),
        withChanges.map((r) => changes[r].value),
        (v) => fmtNumber(v, 0),
        withChanges,
        withChanges.map((r) => `${changes[r].startDate} → ${changes[r].endDate}`)
      );
    }
  };
  draw();
}

async function renderAiPulse() {
  const el = document.getElementById("ai-content");
  try {
    const [aiVsMarket, aiBasketDetail, attention, devMomentum, researchPace] = await Promise.all([
      fetchJson("ai_vs_market"),
      fetchJson("ai_basket_detail"),
      fetchJson("attention_index"),
      fetchJson("dev_momentum"),
      fetchJson("research_pace"),
    ]);

    el.innerHTML = `
      <div class="two-col">
        <div id="ai-spread-panel"></div>
        <div id="ai-research-panel"></div>
      </div>
      <div class="two-col subsection">
        <div id="ai-attention-panel"></div>
        <div id="ai-dev-panel"></div>
      </div>
    `;

    renderSpreadChart(document.getElementById("ai-spread-panel"), aiVsMarket, aiBasketDetail);
    renderResearchChart(document.getElementById("ai-research-panel"), researchPace);
    renderAttentionChart(document.getElementById("ai-attention-panel"), attention);
    renderDevChart(document.getElementById("ai-dev-panel"), devMomentum);
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
