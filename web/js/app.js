import {
  loadCandles,
  loadCompanyProfile,
  loadLastUpdated,
  loadMarketOverview,
  loadMarketMovers,
  loadModelPerformance,
  loadNews,
  loadPrediction,
  loadProjection,
  loadSymbols,
  loadTopPredictions,
} from "./data-loader.js";
import { flashRefresh, setupRevealAnimations } from "./animations.js";
import {
  RANGE_CONFIG,
  updateIndexChart,
  updateMainChart,
  updateProjectionChart,
} from "./chart.js";
import { setupFullscreenChart } from "./fullscreen-chart.js";
import { renderCompanyLogo } from "./logo.js";
import {
  renderMarketMovers,
  renderMoversLoading,
  renderPredictionRankings,
  renderPredictionRankingsLoading,
} from "./market.js";
import { bindNewsControls, renderNews, renderNewsLoading } from "./news.js";
import {
  renderModelLoading,
  renderModelPerformance,
  renderProjection,
  renderProjectionLoading,
} from "./prediction.js";
import {
  formatNumber,
  formatPercent,
  isFiniteNumber,
  animateMetricText,
  setupNavbarActiveState,
  setLoading,
  showEmpty,
  showToast,
  signedClass,
} from "./ui.js";

const state = {
  indexRange: "1Y",
  range: "1Y",
  selectedTicker: "BBCA",
  selectedSymbol: "BBCA.JK",
  newsTicker: "BBCA",
  symbols: new Map(),
  indexCandles: [],
  stockCandles: [],
};

const nodes = {};
let fullscreenWorkspace;

document.addEventListener("DOMContentLoaded", initialize);

async function initialize() {
  bindNodes();
  setupNavbarActiveState();
  setupRevealAnimations();
  bindInteractions();
  setProjectionDefaults();
  await loadSymbolOptions();
  fullscreenWorkspace = setupFullscreenChart({
    getState: () => ({
      selectedTicker: state.selectedTicker,
      selectedSymbol: state.selectedSymbol,
      range: state.range,
      symbols: state.symbols,
    }),
    onTickerChange: (ticker) => selectChartSymbol(ticker),
  });
  await Promise.all([
    refreshLastUpdated(),
    refreshMarketOverview(),
    refreshIndexChart(),
    refreshChart(),
    refreshMarketMovers(),
    refreshSelectedPredictionSummary(),
    refreshPredictionRankings(),
    refreshNewsContext(),
    refreshProjection(),
    refreshModelPerformance(),
  ]);
  window.setInterval(refreshDashboardSnapshot, 180000);
}

function bindNodes() {
  Object.assign(nodes, {
    symbolInput: document.getElementById("symbolInput"),
    manualRefresh: document.getElementById("manualRefresh"),
    lastUpdatedLabel: document.getElementById("lastUpdatedLabel"),
    marketOverview: document.getElementById("marketOverview"),
    heroMarketStatus: document.getElementById("heroMarketStatus"),
    heroLastUpdated: document.getElementById("heroLastUpdated"),
    overviewPrice: document.getElementById("overviewPrice"),
    overviewChange: document.getElementById("overviewChange"),
    overviewPrediction: document.getElementById("overviewPrediction"),
    overviewDirection: document.getElementById("overviewDirection"),
    overviewConfidence: document.getElementById("overviewConfidence"),
    overviewPriceSource: document.getElementById("overviewPriceSource"),
    overviewSentiment: document.getElementById("overviewSentiment"),
    overviewSentimentMeta: document.getElementById("overviewSentimentMeta"),
    overviewTopGainer: document.getElementById("overviewTopGainer"),
    overviewTopGainerMeta: document.getElementById("overviewTopGainerMeta"),
    overviewTopLoser: document.getElementById("overviewTopLoser"),
    overviewTopLoserMeta: document.getElementById("overviewTopLoserMeta"),
    overviewCoverage: document.getElementById("overviewCoverage"),
    overviewCoverageMeta: document.getElementById("overviewCoverageMeta"),
    symbolSelect: document.getElementById("symbolSelect"),
    stockForm: document.getElementById("stockForm"),
    stockUniverseCount: document.getElementById("stockUniverseCount"),
    symbolOptions: document.getElementById("symbolOptions"),
    projectionForm: document.getElementById("projectionForm"),
    projectionTicker: document.getElementById("projectionTicker"),
    projectionTickerDisplay: document.getElementById("projectionTickerDisplay"),
    projectionAmount: document.getElementById("projectionAmount"),
    projectionEntryDate: document.getElementById("projectionEntryDate"),
    projectionExitDate: document.getElementById("projectionExitDate"),
    projectionApply: document.getElementById("projectionApply"),
    projectionResult: document.getElementById("projectionResult"),
    projectionEmpty: document.getElementById("projectionEmpty"),
    projectionChartEmpty: document.getElementById("projectionChartEmpty"),
    indexRangeTabs: document.getElementById("indexRangeTabs"),
    indexChartTitle: document.getElementById("indexChartTitle"),
    indexDataCoverage: document.getElementById("indexDataCoverage"),
    indexChartLoading: document.getElementById("indexChartLoading"),
    indexChartEmpty: document.getElementById("indexChartEmpty"),
    rangeTabs: document.getElementById("rangeTabs"),
    chartTitle: document.getElementById("chartTitle"),
    stockLogo: document.getElementById("stockLogo"),
    stockCompanyName: document.getElementById("stockCompanyName"),
    stockDataCoverage: document.getElementById("stockDataCoverage"),
    chartLoading: document.getElementById("chartLoading"),
    chartEmpty: document.getElementById("chartEmpty"),
    moversSource: document.getElementById("moversSource"),
    topGainers: document.getElementById("topGainers"),
    topLosers: document.getElementById("topLosers"),
    moversEmpty: document.getElementById("moversEmpty"),
    predictionRankingsSource: document.getElementById("predictionRankingsSource"),
    topPredictedUp: document.getElementById("topPredictedUp"),
    topPredictedDown: document.getElementById("topPredictedDown"),
    predictionRankingsEmpty: document.getElementById("predictionRankingsEmpty"),
    modelMetrics: document.getElementById("modelMetrics"),
    metricsEmpty: document.getElementById("metricsEmpty"),
    modelSummary: document.getElementById("modelSummary"),
    newsMarqueeTrack: document.getElementById("newsMarqueeTrack"),
    newsPrev: document.getElementById("newsPrev"),
    newsNext: document.getElementById("newsNext"),
    newsFilterBar: document.getElementById("newsFilterBar"),
    newsContextLabel: document.getElementById("newsContextLabel"),
    newsEmpty: document.getElementById("newsEmpty"),
  });
}

function bindInteractions() {
  nodes.manualRefresh.addEventListener("click", () => {
    flashRefresh(nodes.manualRefresh);
    showToast("Refreshing latest available dashboard data...");
    refreshDashboardSnapshot();
  });

  nodes.newsPrev.addEventListener("click", () => {
    nodes.newsMarqueeTrack.closest(".news-marquee")?.scrollBy({ left: -320, behavior: "smooth" });
  });

  nodes.newsNext.addEventListener("click", () => {
    nodes.newsMarqueeTrack.closest(".news-marquee")?.scrollBy({ left: 320, behavior: "smooth" });
  });
  bindNewsControls(nodes.newsFilterBar);

  nodes.indexRangeTabs.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-range]");
    if (!button) return;
    const range = button.dataset.range;
    if (!RANGE_CONFIG[range] || range === state.indexRange) return;
    state.indexRange = range;
    updateRangeButtons(nodes.indexRangeTabs, state.indexRange);
    refreshIndexChartViewport();
  });

  nodes.rangeTabs.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-range]");
    if (!button) return;
    const range = button.dataset.range;
    if (!RANGE_CONFIG[range] || range === state.range) return;
    state.range = range;
    updateRangeButtons(nodes.rangeTabs, state.range);
    refreshChartViewport();
  });

  nodes.stockForm.addEventListener("submit", (event) => {
    event.preventDefault();
    selectChartSymbol(nodes.symbolInput.value);
  });
  nodes.symbolSelect.addEventListener("change", () => {
    nodes.symbolInput.value = nodes.symbolSelect.value;
    selectChartSymbol(nodes.symbolSelect.value);
  });
  nodes.symbolInput.addEventListener("change", () => selectChartSymbol(nodes.symbolInput.value));
  nodes.symbolInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      selectChartSymbol(nodes.symbolInput.value);
    }
  });

  nodes.projectionForm.addEventListener("submit", (event) => {
    event.preventDefault();
    refreshProjection();
  });
}

function setProjectionDefaults() {
  const today = new Date();
  const entryDate = new Date(today);
  entryDate.setFullYear(today.getFullYear() - 1);
  const exitDate = new Date(today);
  exitDate.setMonth(today.getMonth() + 1);

  syncProjectionTicker(state.selectedTicker);
  nodes.projectionEntryDate.value = isoDate(entryDate);
  nodes.projectionExitDate.value = isoDate(exitDate);
}

function syncProjectionTicker(ticker) {
  const resolved = resolveTickerAndSymbol(ticker, { defaultTicker: state.selectedTicker || "BBCA" });
  const value = resolved.ticker === "IHSG" ? state.selectedTicker || "BBCA" : resolved.ticker;
  if (nodes.projectionTicker) {
    nodes.projectionTicker.value = value;
  }
  if (nodes.projectionTickerDisplay) {
    nodes.projectionTickerDisplay.textContent = value;
    const company = state.symbols.get(value)?.name || state.symbols.get(`${value}.JK`)?.name;
    nodes.projectionTickerDisplay.title = company ? `${value} - ${company}` : value;
  }
}

async function loadSymbolOptions() {
  try {
    const payload = await loadSymbols();
    payload.symbols.forEach((row) => {
      state.symbols.set(row.ticker.toUpperCase(), { ...row, ticker: row.ticker.toUpperCase() });
    });
    renderSymbolOptions();
    syncProjectionTicker(state.selectedTicker);
  } catch (error) {
    showToast(`Failed to load symbols: ${error.message}`, "error");
  }
}

async function refreshDashboardSnapshot() {
  await Promise.allSettled([
    refreshLastUpdated(),
    refreshMarketOverview(),
    refreshMarketMovers(),
    refreshSelectedPredictionSummary(),
    refreshPredictionRankings(),
    refreshNewsContext(),
    refreshModelPerformance(),
  ]);
}

async function refreshLastUpdated() {
  try {
    const payload = await loadLastUpdated();
    const updated = payload.latest_artifact_update
      ? new Date(payload.latest_artifact_update).toLocaleString()
      : "unknown";
    nodes.lastUpdatedLabel.textContent = `${payload.status_label || "Latest available data"} | Updated ${updated}`;
    nodes.heroLastUpdated.textContent = `Last updated: ${updated}`;
    renderMarketStatusBadge();
  } catch (error) {
    nodes.lastUpdatedLabel.textContent = "Data status unavailable";
    nodes.heroLastUpdated.textContent = "Last updated: data unavailable";
    renderMarketStatusBadge();
    showToast(`Data status failed: ${error.message}`, "error");
  }
}

async function refreshMarketOverview() {
  try {
    const payload = await loadMarketOverview();
    renderMarketOverview(payload);
  } catch (error) {
    nodes.marketOverview?.classList.remove("is-loading");
    [
      nodes.overviewPrice,
      nodes.overviewChange,
      nodes.overviewPrediction,
      nodes.overviewDirection,
      nodes.overviewSentiment,
      nodes.overviewTopGainer,
      nodes.overviewTopLoser,
      nodes.overviewCoverage,
    ].forEach((node) => {
      if (node) node.textContent = "Data unavailable";
    });
    showToast(`Market overview failed: ${error.message}`, "error");
  }
}

function renderMarketOverview(payload) {
  nodes.marketOverview?.classList.remove("is-loading");
  const index = payload?.index || {};
  const sentiment = payload?.sentiment || {};
  const prediction = payload?.prediction || {};
  const movers = payload?.movers || {};
  const topGainer = movers.top_gainer;
  const topLoser = movers.top_loser;

  nodes.overviewPrice.dataset.lockedTo = "market-overview";
  animateMetricText(nodes.overviewPrice, index.close, formatNumber);
  animateDirectionalMetric(nodes.overviewChange, index.daily_change, {
    formatter: formatPercent,
    showNeutral: true,
  });
  nodes.overviewChange.className = signedClass(index.daily_change);
  nodes.overviewPriceSource.textContent = index.date
    ? `Latest available close | ${index.date}`
    : `Source: ${payload?.source || "local artifacts"}`;

  nodes.overviewSentiment.textContent = sentiment.label || "n/a";
  nodes.overviewSentiment.className = signedClass(sentiment.score);
  nodes.overviewSentimentMeta.textContent = isFiniteNumber(sentiment.score)
    ? `${formatNumber(sentiment.news_count)} news rows | score ${formatNumber(sentiment.score)}`
    : `${formatNumber(sentiment.news_count)} news rows`;

  setTickerMoverMetric(nodes.overviewTopGainer, topGainer);
  nodes.overviewTopGainer.className = signedClass(topGainer?.change_pct);
  nodes.overviewTopGainerMeta.textContent = topGainer
    ? `Most Up | ${formatPercent(topGainer.change_pct)} latest change`
    : "From latest local prices";

  setTickerMoverMetric(nodes.overviewTopLoser, topLoser);
  nodes.overviewTopLoser.className = signedClass(topLoser?.change_pct);
  nodes.overviewTopLoserMeta.textContent = topLoser
    ? `Most Down | ${formatPercent(topLoser.change_pct)} latest change`
    : "From latest local prices";

  nodes.overviewCoverage.textContent = formatNumber(prediction.covered_stocks);
  nodes.overviewCoverageMeta.textContent = prediction.bias
    ? `${prediction.bias} model bias | ${formatPercent(prediction.avg_confidence)} avg confidence`
    : "Stocks with prediction snapshot";
}

function renderOverviewPrediction(payload) {
  if (!payload || !["ok", "technical_snapshot"].includes(payload.status)) {
    nodes.overviewPrediction.textContent = "n/a";
    nodes.overviewPrediction.className = "";
    nodes.overviewDirection.textContent = "n/a";
    nodes.overviewDirection.className = "";
    nodes.overviewConfidence.textContent = "Confidence: n/a";
    return;
  }

  if (payload.status === "technical_snapshot") {
    nodes.overviewPrediction.textContent = "Tech only";
    nodes.overviewPrediction.className = "neutral";
    nodes.overviewDirection.textContent = "Limited";
    nodes.overviewDirection.className = "neutral";
    nodes.overviewConfidence.textContent = "Confidence: limited model signal";
    return;
  }

  const isUp = payload.predicted_direction === 1;
  nodes.overviewPrediction.textContent = formatPercent(payload.predicted_return);
  nodes.overviewPrediction.className = signedClass(payload.predicted_return);
  nodes.overviewDirection.textContent = isUp ? "UP" : "DOWN";
  nodes.overviewDirection.className = isUp ? "positive" : "negative";
  nodes.overviewConfidence.textContent = `Confidence: ${formatPercent(payload.confidence)}`;
}

async function refreshIndexChart() {
  const rangeConfig = chartLoadConfig(state.indexRange);
  nodes.indexChartTitle.textContent = `IHSG ${state.indexRange}`;
  nodes.indexChartTitle.closest(".panel").classList.add("fade-update");
  setLoading(nodes.indexChartLoading, true);

  try {
    const payload = await loadCandles("^JKSE", rangeConfig);
    state.indexCandles = payload.candles || [];
    updateIndexChart(state.indexCandles, nodes.indexChartEmpty, state.indexRange);
    renderDataCoverage(nodes.indexDataCoverage, state.indexCandles, state.indexRange);
    showToast(`IHSG market history loaded from ${payload.source || "API"}`);
  } catch (error) {
    showEmpty(nodes.indexChartEmpty, `Gagal memuat chart IHSG: ${error.message}`);
    showToast(`IHSG chart load failed: ${error.message}`, "error");
  } finally {
    setLoading(nodes.indexChartLoading, false);
    nodes.indexChartTitle.closest(".panel").classList.remove("fade-update");
  }
}

function refreshIndexChartViewport() {
  nodes.indexChartTitle.textContent = `IHSG ${state.indexRange}`;
  renderDataCoverage(nodes.indexDataCoverage, state.indexCandles, state.indexRange);
  try {
    updateIndexChart(null, nodes.indexChartEmpty, state.indexRange);
  } catch (error) {
    showToast(`IHSG range failed: ${error.message}`, "error");
  }
}

async function refreshChart() {
  const rangeConfig = chartLoadConfig(state.range);
  const displayTicker = displayTickerForSymbol(state.selectedSymbol);
  nodes.chartTitle.textContent = `${displayTicker} ${state.range}`;
  renderKnownCompanyIdentity(displayTicker, {
    prediction: displayTicker === state.selectedTicker,
    stock: true,
  });
  nodes.chartTitle.closest(".panel").classList.add("fade-update");
  setLoading(nodes.chartLoading, true);

  try {
    const payload = await loadCandles(state.selectedSymbol, rangeConfig);
    state.stockCandles = payload.candles || [];
    updateMainChart(state.stockCandles, nodes.chartEmpty, state.range);
    renderDataCoverage(nodes.stockDataCoverage, state.stockCandles, state.range);
    refreshCompanyProfile(displayTicker);
    showToast(`${displayTicker} market history loaded from ${payload.source || "API"}`);
  } catch (error) {
    showEmpty(nodes.chartEmpty, `Gagal memuat data chart: ${error.message}`);
    showToast(`Chart load failed: ${error.message}`, "error");
  } finally {
    setLoading(nodes.chartLoading, false);
    nodes.chartTitle.closest(".panel").classList.remove("fade-update");
  }
}

function refreshChartViewport() {
  const displayTicker = displayTickerForSymbol(state.selectedSymbol);
  nodes.chartTitle.textContent = `${displayTicker} ${state.range}`;
  renderDataCoverage(nodes.stockDataCoverage, state.stockCandles, state.range);
  try {
    updateMainChart(null, nodes.chartEmpty, state.range);
  } catch (error) {
    showToast(`Chart range failed: ${error.message}`, "error");
  }
}

async function refreshSelectedPredictionSummary() {
  try {
    const payload = await loadPrediction(state.selectedTicker);
    renderOverviewPrediction(payload);
  } catch (error) {
    renderOverviewPrediction(null);
    showToast(`Prediction summary failed: ${error.message}`, "error");
  }
}

async function refreshPredictionRankings() {
  renderPredictionRankingsLoading(
    nodes.topPredictedUp,
    nodes.topPredictedDown,
    nodes.predictionRankingsEmpty,
  );
  try {
    const payload = await loadTopPredictions(10);
    renderPredictionRankings(
      nodes.topPredictedUp,
      nodes.topPredictedDown,
      nodes.predictionRankingsEmpty,
      nodes.predictionRankingsSource,
      payload,
      { onTickerClick: selectChartSymbol },
    );
  } catch (error) {
    renderPredictionRankings(
      nodes.topPredictedUp,
      nodes.topPredictedDown,
      nodes.predictionRankingsEmpty,
      nodes.predictionRankingsSource,
      { status: "empty", up: [], down: [] },
    );
    showToast(`Prediction rankings failed: ${error.message}`, "error");
  }
}

async function refreshNewsContext(ticker = state.newsTicker) {
  renderNewsLoading(nodes.newsMarqueeTrack, nodes.newsEmpty);
  try {
    const payload = await loadNews(ticker, 50);
    if (nodes.newsContextLabel) {
      nodes.newsContextLabel.textContent = payload.context_message || "Using latest available market news";
    }
    renderNews(nodes.newsMarqueeTrack, nodes.newsEmpty, payload.news || []);
  } catch (error) {
    if (nodes.newsContextLabel) {
      nodes.newsContextLabel.textContent = "Using latest available market news";
    }
    renderNews(nodes.newsMarqueeTrack, nodes.newsEmpty, []);
    showToast(`News load failed: ${error.message}`, "error");
  }
}

async function refreshProjection() {
  const resolved = resolveTickerAndSymbol(state.selectedTicker, {
    defaultTicker: "BBCA",
  });
  if (resolved.ticker === "IHSG") {
    renderProjection(nodes.projectionResult, nodes.projectionEmpty, {
      status: "error",
      message: "Projection requires a stock ticker, not IHSG.",
    });
    updateProjectionChart(null, nodes.projectionChartEmpty);
    showToast("Projection requires a stock ticker, not IHSG.", "error");
    return;
  }

  syncProjectionTicker(resolved.ticker);
  const amountText = String(nodes.projectionAmount.value || "").trim();
  const amount = Number(amountText);
  if (!amountText || !Number.isFinite(amount) || amount <= 0) {
    renderProjection(nodes.projectionResult, nodes.projectionEmpty, {
      status: "error",
      message: "Nominal harus berupa angka positif.",
    });
    nodes.projectionEmpty.classList.add("compact-empty");
    updateProjectionChart(null, nodes.projectionChartEmpty);
    return;
  }
  nodes.projectionEmpty.classList.remove("compact-empty");
  renderProjectionLoading(nodes.projectionResult, nodes.projectionEmpty);
  updateProjectionChart(null, nodes.projectionChartEmpty);

  try {
    const payload = await loadProjection({
      ticker: resolved.ticker,
      amount,
      entryDate: nodes.projectionEntryDate.value,
      exitDate: nodes.projectionExitDate.value,
    });
    renderProjection(nodes.projectionResult, nodes.projectionEmpty, payload);
    updateProjectionChart(payload.projection, nodes.projectionChartEmpty);
  } catch (error) {
    const payload = { status: "error", message: error.message };
    renderProjection(nodes.projectionResult, nodes.projectionEmpty, payload);
    updateProjectionChart(null, nodes.projectionChartEmpty);
    showToast(`Projection failed: ${error.message}`, "error");
  }
}

async function refreshModelPerformance() {
  renderModelLoading(nodes.modelMetrics, nodes.metricsEmpty, nodes.modelSummary);
  try {
    const payload = await loadModelPerformance();
    renderModelPerformance(nodes.modelMetrics, nodes.metricsEmpty, nodes.modelSummary, payload);
  } catch (error) {
    renderModelPerformance(nodes.modelMetrics, nodes.metricsEmpty, nodes.modelSummary, {});
    showToast(`Model metrics failed: ${error.message}`, "error");
  }
}

async function refreshMarketMovers() {
  renderMoversLoading(nodes.topGainers, nodes.topLosers, nodes.moversEmpty);
  try {
    const payload = await loadMarketMovers(10);
    renderMarketMovers(nodes.topGainers, nodes.topLosers, nodes.moversEmpty, nodes.moversSource, payload, {
      onTickerClick: selectChartSymbol,
    });
  } catch (error) {
    renderMarketMovers(nodes.topGainers, nodes.topLosers, nodes.moversEmpty, nodes.moversSource, {
      available_tickers: 0,
      gainers: [],
      losers: [],
    });
    showToast(`Market movers failed: ${error.message}`, "error");
  }
}

function renderMarketStatusBadge() {
  if (!nodes.heroMarketStatus) return;
  const status = currentMarketStatus();
  nodes.heroMarketStatus.className = `market-status-badge ${status.open ? "open" : "closed"}`;
  nodes.heroMarketStatus.textContent = status.open ? "Market Open" : "Market Closed";
  nodes.heroMarketStatus.title = "Approximate IDX regular market hours in Asia/Jakarta.";
}

function currentMarketStatus() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Jakarta",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  const weekday = values.weekday;
  const minutes = Number(values.hour) * 60 + Number(values.minute);
  const isWeekday = !["Sat", "Sun"].includes(weekday);
  return { open: isWeekday && minutes >= 9 * 60 && minutes <= 16 * 60 };
}

function setDirectionalMetric(node, value, { formatter = formatNumber, showNeutral = false } = {}) {
  if (!isFiniteNumber(value)) {
    node.textContent = "n/a";
    return;
  }
  const number = Number(value);
  const icon = number > 0 ? "▲" : number < 0 ? "▼" : showNeutral ? "-" : "";
  const iconClass = number > 0 ? "up" : number < 0 ? "down" : "";
  node.innerHTML = `<span class="direction-icon ${iconClass}" aria-hidden="true">${icon}</span><span>${formatter(number)}</span>`;
}

function animateDirectionalMetric(node, value, options = {}) {
  if (!isFiniteNumber(value)) {
    setDirectionalMetric(node, value, options);
    return;
  }
  const target = Number(value);
  const start = 0;
  const duration = 520;
  const startTime = performance.now();
  function tick(now) {
    const progress = Math.min((now - startTime) / duration, 1);
    const eased = 1 - (1 - progress) ** 3;
    setDirectionalMetric(node, start + (target - start) * eased, options);
    if (progress < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

function setTickerMoverMetric(node, row) {
  if (!row?.ticker) {
    node.textContent = "n/a";
    return;
  }
  const change = Number(row.change_pct);
  const icon = change > 0 ? "▲" : change < 0 ? "▼" : "-";
  const iconClass = change > 0 ? "up" : change < 0 ? "down" : "";
  node.innerHTML = `<span class="direction-icon ${iconClass}" aria-hidden="true">${icon}</span><span>${row.ticker}</span>`;
}

function selectChartSymbol(rawValue) {
  const resolved = resolveTickerAndSymbol(rawValue, { defaultTicker: "IHSG" });
  state.selectedSymbol = resolved.symbol;
  nodes.symbolInput.value = resolved.ticker;
  if (nodes.symbolSelect.querySelector(`option[value="${resolved.ticker}"]`)) {
    nodes.symbolSelect.value = resolved.ticker;
  }
  refreshChart();

  if (resolved.ticker !== "IHSG") {
    state.selectedTicker = resolved.ticker;
    state.newsTicker = resolved.ticker;
    syncProjectionTicker(resolved.ticker);
    refreshSelectedPredictionSummary();
    refreshNewsContext();
    refreshProjection();
  } else {
    state.newsTicker = null;
    refreshNewsContext(null);
  }
}

function resolveTickerAndSymbol(rawValue, { defaultTicker }) {
  const cleaned = (rawValue || defaultTicker).trim().toUpperCase();
  if (!cleaned) {
    return resolveTickerAndSymbol(defaultTicker, { defaultTicker: "BBCA" });
  }
  if (state.symbols.has(cleaned)) {
    return { ticker: cleaned, symbol: state.symbols.get(cleaned).symbol };
  }
  if (cleaned === "^JKSE") {
    return { ticker: "IHSG", symbol: "^JKSE" };
  }
  if (cleaned.endsWith(".JK")) {
    return { ticker: cleaned.replace(".JK", ""), symbol: cleaned };
  }
  if (cleaned.startsWith("^") || cleaned.includes(".")) {
    return { ticker: cleaned, symbol: cleaned };
  }
  return { ticker: cleaned, symbol: `${cleaned}.JK` };
}

function renderSymbolOptions() {
  nodes.symbolOptions.innerHTML = "";
  nodes.symbolSelect.innerHTML = "";
  const stockRows = [...state.symbols.entries()].filter(([ticker]) => ticker !== "IHSG");
  stockRows.forEach(([ticker, row]) => {
    const option = document.createElement("option");
    option.value = ticker;
    option.label = `${row.symbol} - ${row.name || ticker}`;
    nodes.symbolOptions.appendChild(option);

    const selectOption = document.createElement("option");
    selectOption.value = ticker;
    selectOption.textContent = `${ticker} - ${row.name || row.symbol}`;
    nodes.symbolSelect.appendChild(selectOption);
  });
  nodes.symbolSelect.value = state.selectedTicker;
  nodes.stockUniverseCount.textContent = `${stockRows.length} IDX companies available`;
}

function renderKnownCompanyIdentity(ticker, targets = { prediction: true, stock: true }) {
  const row = state.symbols.get(ticker);
  const name = row?.name || ticker;
  if (targets.stock) {
    renderCompanyLogo(nodes.stockLogo, { ...(row || {}), ticker });
    nodes.stockCompanyName.textContent = name;
  }
  if (targets.prediction && nodes.predictionLogo && nodes.predictionCompanyName) {
    renderCompanyLogo(nodes.predictionLogo, { ...(row || {}), ticker });
    nodes.predictionCompanyName.textContent = `${name} | Prediction source: trained global model artifact`;
  }
}

async function refreshCompanyProfile(ticker) {
  try {
    const payload = await loadCompanyProfile(ticker);
    const profile = payload.profile || {};
    if (profile.ticker) {
      state.symbols.set(profile.ticker, { ...(state.symbols.get(profile.ticker) || {}), ...profile });
    }
    if (profile.ticker === displayTickerForSymbol(state.selectedSymbol)) {
      renderCompanyLogo(nodes.stockLogo, profile);
      nodes.stockCompanyName.textContent = companyLine(profile);
    }
    if (profile.ticker === state.selectedTicker && nodes.predictionLogo && nodes.predictionCompanyName) {
      renderCompanyLogo(nodes.predictionLogo, profile);
      nodes.predictionCompanyName.textContent = `${companyLine(profile)} | Prediction source: trained global model artifact`;
    }
  } catch (error) {
    showToast(`Company profile failed: ${error.message}`, "error");
  }
}

function companyLine(profile) {
  const parts = [profile.name, profile.sector, profile.industry].filter(Boolean);
  return parts.length ? parts.join(" | ") : profile.ticker || "Unknown company";
}

function renderDataCoverage(node, candles, requestedRange) {
  const rows = (candles || [])
    .filter((row) => Number.isFinite(Date.parse(row.date)))
    .sort((a, b) => Date.parse(a.date) - Date.parse(b.date));
  if (!rows.length) {
    node.textContent = "Available data: none";
    return;
  }

  const first = rows[0].date.slice(0, 10);
  const last = rows[rows.length - 1].date.slice(0, 10);
  const years = (Date.parse(last) - Date.parse(first)) / (365.25 * 24 * 60 * 60 * 1000);
  const yearsText = years >= 1 ? `${years.toFixed(1)} years` : `${Math.max(1, rows.length)} candles`;
  const fullHistoryNote = requestedRange === "ALL" ? " | full available history" : "";
  node.textContent = `Available data: ${first} to ${last} | ${rows.length} candles | ${yearsText}${fullHistoryNote}`;
}

function isoDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function updateRangeButtons(container, activeRange) {
  container.querySelectorAll("button[data-range]").forEach((button) => {
    button.classList.toggle("active", button.dataset.range === activeRange);
  });
}

function displayTickerForSymbol(symbol) {
  for (const [ticker, row] of state.symbols.entries()) {
    if (row.symbol === symbol) return ticker;
  }
  return symbol;
}

function chartLoadConfig(range) {
  const current = RANGE_CONFIG[range] || RANGE_CONFIG["1Y"];
  return {
    period: current.historyPeriod || current.period,
    interval: current.historyInterval || current.interval,
  };
}
