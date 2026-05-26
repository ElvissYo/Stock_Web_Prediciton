export async function api(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  let payload;
  try {
    payload = await response.json();
  } catch (error) {
    throw new Error(`Invalid JSON response from ${path}: ${error.message}`);
  }
  if (!response.ok) {
    throw new Error(payload.message || `Request failed: ${response.status}`);
  }
  return payload;
}

export async function loadSymbols() {
  return api("/api/market/symbols?limit=100");
}

export async function loadStocks(limit = 100) {
  return api(`/api/stocks?limit=${encodeURIComponent(String(limit))}`);
}

export async function loadStockMetadata(limit = 100) {
  return api(`/api/stocks/metadata?limit=${encodeURIComponent(String(limit))}`);
}

export async function loadMarketOverview() {
  return api("/api/market/overview");
}

export async function loadLastUpdated() {
  return api("/api/last-updated");
}

export async function loadCompanyProfile(ticker) {
  return api(`/api/market/profile?ticker=${encodeURIComponent(ticker)}`);
}

export async function loadCandles(symbol, rangeConfig) {
  const parameters = new URLSearchParams({
    symbol,
    period: rangeConfig.period,
    interval: rangeConfig.interval,
  });
  return api(`/api/market/candles?${parameters.toString()}`);
}

export async function loadChart(ticker, range = "1Y", interval = "1d") {
  const parameters = new URLSearchParams({
    ticker,
    range,
    interval,
  });
  return api(`/api/chart?${parameters.toString()}`);
}

export async function loadPredictions() {
  return api("/api/predictions");
}

export async function loadTopPredictions(limit = 10) {
  return api(`/api/predictions/top?limit=${encodeURIComponent(String(limit))}`);
}

export async function loadPrediction(ticker) {
  return api(`/api/prediction?ticker=${encodeURIComponent(ticker)}`);
}

export async function loadPredictionDrivers(ticker) {
  return api(`/api/prediction-drivers?ticker=${encodeURIComponent(ticker)}`);
}

export async function loadProjection({ ticker, amount, entryDate, exitDate }) {
  const parameters = new URLSearchParams({
    ticker,
    amount: String(amount),
    entry_date: entryDate,
    exit_date: exitDate,
  });
  return api(`/api/projection?${parameters.toString()}`);
}

export async function loadPriceFeatures(ticker) {
  return api(`/api/price-features?ticker=${encodeURIComponent(ticker)}`);
}

export async function loadNlpSummary(ticker) {
  return api(`/api/nlp-summary?ticker=${encodeURIComponent(ticker)}`);
}

export async function loadNews(ticker, limit = 9) {
  const parameters = new URLSearchParams({ limit: String(limit) });
  if (ticker) parameters.set("ticker", ticker);
  return api(`/api/news?${parameters.toString()}`);
}

export async function loadMetrics() {
  return api("/api/metrics");
}

export async function loadModelPerformance() {
  return api("/api/model/performance");
}

export async function loadMarketMovers(limit = 10) {
  return api(`/api/market/movers?limit=${encodeURIComponent(String(limit))}`);
}
