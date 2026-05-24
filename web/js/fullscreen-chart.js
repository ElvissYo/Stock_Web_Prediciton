import { loadChart, loadNews, loadNlpSummary, loadPrediction, loadStocks } from "./data-loader.js";
import { DrawingLayer } from "./drawing-layer.js";
import { TOOL_GROUPS, TOOLS } from "./drawing-tools.js";
import { formatNumber, formatPercent, isFiniteNumber, showToast, signedClass } from "./ui.js";

const RANGES = ["1D", "5D", "1M", "3M", "6M", "YTD", "1Y", "5Y", "ALL"];
const SIDEBAR_KEY = "ihsg-fullscreen-watchlist-collapsed";

export function setupFullscreenChart({ getState, onTickerChange }) {
  return new FullscreenChartWorkspace({ getState, onTickerChange });
}

class FullscreenChartWorkspace {
  constructor({ getState, onTickerChange }) {
    this.getState = getState;
    this.onTickerChange = onTickerChange;
    this.isOpen = false;
    this.currentTicker = "BBCA";
    this.range = "1Y";
    this.candles = [];
    this.newsRows = [];
    this.prediction = null;
    this.nlpSummary = null;
    this.stocks = [];
    this.filteredStocks = [];
    this.watchlistQuery = "";
    this.watchlistFilter = "all";
    this.watchlistSort = "change";
    this.showVolume = true;
    this.showSma20 = true;
    this.showSma50 = true;
    this.showPredictionMarkers = true;
    this.showNewsMarkers = true;
    this.sidebarCollapsed = window.localStorage.getItem(SIDEBAR_KEY) === "1";
    this.markerDetails = new Map();

    this.createOverlay();
    this.bindOpenTriggers();
    this.bindOverlayEvents();
  }

  createOverlay() {
    document.body.insertAdjacentHTML("beforeend", this.overlayMarkup());
    this.root = document.getElementById("chartFullscreenOverlay");
    this.workspace = this.root.querySelector(".fs-workspace");
    this.chartStage = document.getElementById("fullscreenChartStage");
    this.chartNode = document.getElementById("fullscreenChart");
    this.drawingSvg = document.getElementById("fullscreenDrawingLayer");
    this.tooltipNode = document.getElementById("fullscreenOhlcTooltip");
    this.loadingNode = document.getElementById("fullscreenChartLoading");
    this.emptyNode = document.getElementById("fullscreenChartEmpty");
    this.toolbarNode = document.getElementById("fullscreenDrawingToolbar");
    this.watchlistNode = document.getElementById("fullscreenWatchlistRows");
    this.watchlistStatusNode = document.getElementById("fullscreenWatchlistStatus");
    this.sidebarNode = document.getElementById("fullscreenWatchlistSidebar");
    this.root.classList.toggle("watchlist-collapsed", this.sidebarCollapsed);
    this.renderToolbar();
  }

  overlayMarkup() {
    return `
      <div id="chartFullscreenOverlay" class="chart-fullscreen-overlay hidden" aria-hidden="true">
        <div class="fs-workspace" role="dialog" aria-modal="true" aria-label="Fullscreen trading chart workspace">
          <header class="fs-topbar">
            <div class="fs-symbol-block">
              <strong id="fsTickerLabel">BBCA</strong>
              <span id="fsCompanyLabel">Loading company...</span>
            </div>
            <div class="fs-price-strip">
              <span id="fsLastPrice">n/a</span>
              <span id="fsDailyChange" class="neutral">n/a</span>
            </div>
            <div class="fs-range-tabs" id="fsRangeTabs" aria-label="Fullscreen chart time range">
              ${RANGES.map((range) => `<button type="button" data-range="${range}">${range}</button>`).join("")}
            </div>
            <div class="fs-chart-controls" aria-label="Chart controls">
              <button type="button" data-control="volume" class="active">Volume</button>
              <button type="button" data-control="sma20" class="active">SMA 20</button>
              <button type="button" data-control="sma50" class="active">SMA 50</button>
              <button type="button" data-control="prediction" class="active">Prediction</button>
              <button type="button" data-control="news" class="active">News</button>
              <button type="button" data-action="fit">Fit</button>
              <button type="button" data-action="reset">Reset Zoom</button>
            </div>
            <div class="fs-persist-controls">
              <button type="button" data-action="undo">Undo</button>
              <button type="button" data-action="redo">Redo</button>
              <button type="button" data-action="save">Save Drawing</button>
              <button type="button" data-action="clear">Clear Drawings</button>
              <button type="button" class="fs-close-button" id="closeFullscreenChart" aria-label="Close fullscreen chart">Close</button>
            </div>
          </header>

          <aside class="fs-left-toolbar" id="fullscreenDrawingToolbar" aria-label="Drawing tools"></aside>

          <main class="fs-chart-panel">
            <div class="fs-chart-stage" id="fullscreenChartStage">
              <div class="fs-chart-grid"></div>
              <div id="fullscreenChart" class="fs-chart"></div>
              <svg id="fullscreenDrawingLayer" class="fs-drawing-layer drawing-passive" aria-label="Drawing layer"></svg>
              <div id="fullscreenOhlcTooltip" class="fs-ohlc-tooltip hidden"></div>
              <div id="fullscreenChartLoading" class="fs-loading hidden">
                <div class="spinner"></div>
                <span>Loading chart data...</span>
              </div>
              <div id="fullscreenChartEmpty" class="fs-empty hidden"></div>
            </div>
          </main>

          <aside class="fs-watchlist-sidebar" id="fullscreenWatchlistSidebar">
            <button type="button" class="watchlist-collapse" id="watchlistCollapseButton" aria-label="Collapse watchlist"></button>
            <div class="watchlist-expanded">
              <div class="watchlist-heading">
                <div>
                  <p class="eyebrow">Market Watchlist</p>
                  <h2>Stock Watchlist</h2>
                </div>
                <button type="button" id="watchlistMobileClose" aria-label="Close watchlist">Hide</button>
              </div>
              <input id="fullscreenWatchlistSearch" class="watchlist-search" type="search" placeholder="Search ticker or company" autocomplete="off" />
              <div class="watchlist-filters" id="fullscreenWatchlistFilters">
                <button type="button" data-filter="all" class="active">All</button>
                <button type="button" data-filter="gainers">Gainers</button>
                <button type="button" data-filter="losers">Losers</button>
                <button type="button" data-filter="up">Predicted Up</button>
                <button type="button" data-filter="down">Predicted Down</button>
                <button type="button" data-filter="volume">High Volume</button>
              </div>
              <select id="fullscreenWatchlistSort" class="watchlist-sort" aria-label="Sort watchlist">
                <option value="change">Sort by daily change %</option>
                <option value="ticker">Sort by ticker</option>
                <option value="volume">Sort by volume</option>
                <option value="confidence">Sort by prediction confidence</option>
                <option value="active">Sort by most active</option>
              </select>
              <div id="fullscreenWatchlistStatus" class="watchlist-status"></div>
              <div id="fullscreenWatchlistRows" class="watchlist-rows"></div>
              <div class="fs-side-details">
                <section>
                  <span>OHLC</span>
                  <strong id="fsOhlcDetails">Hover chart for candle details.</strong>
                </section>
                <section>
                  <span>Prediction</span>
                  <strong id="fsPredictionDetails">Prediction loading...</strong>
                </section>
                <section>
                  <span>Sentiment</span>
                  <strong id="fsSentimentDetails">NLP summary loading...</strong>
                </section>
                <section>
                  <span>News</span>
                  <strong id="fsNewsDetails">News markers loading...</strong>
                </section>
              </div>
            </div>
            <button type="button" class="watchlist-slim-button" id="watchlistSlimButton" aria-label="Expand watchlist">WL</button>
          </aside>

          <button type="button" class="watchlist-mobile-button" id="watchlistMobileButton">Watchlist</button>
        </div>
      </div>
    `;
  }

  bindOpenTriggers() {
    const openButton = document.getElementById("openFullscreenChart");
    const mainChart = document.getElementById("mainChart");
    openButton?.addEventListener("click", () => this.open());
    mainChart?.addEventListener("click", () => this.open());
    mainChart?.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        this.open();
      }
    });
  }

  bindOverlayEvents() {
    this.root.querySelector("#closeFullscreenChart").addEventListener("click", () => this.close());
    this.root.querySelector("#fsRangeTabs").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-range]");
      if (!button || button.dataset.range === this.range) return;
      this.range = button.dataset.range;
      this.updateRangeButtons();
      this.loadTicker(this.currentTicker);
    });
    this.root.querySelector(".fs-chart-controls").addEventListener("click", (event) => {
      const button = event.target.closest("button");
      if (!button) return;
      if (button.dataset.control) this.toggleControl(button.dataset.control, button);
      if (button.dataset.action) this.handleTopbarAction(button.dataset.action);
    });
    this.root.querySelector(".fs-persist-controls").addEventListener("click", (event) => {
      const action = event.target.closest("button")?.dataset.action;
      if (action) this.handleTopbarAction(action);
    });
    this.root.querySelector("#fullscreenWatchlistSearch").addEventListener("input", (event) => {
      this.watchlistQuery = event.target.value;
      this.renderWatchlist();
    });
    this.root.querySelector("#fullscreenWatchlistFilters").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-filter]");
      if (!button) return;
      this.watchlistFilter = button.dataset.filter;
      this.root.querySelectorAll("[data-filter]").forEach((node) => {
        node.classList.toggle("active", node === button);
      });
      this.renderWatchlist();
    });
    this.root.querySelector("#fullscreenWatchlistSort").addEventListener("change", (event) => {
      this.watchlistSort = event.target.value;
      this.renderWatchlist();
    });
    this.watchlistNode.addEventListener("click", (event) => {
      const row = event.target.closest("[data-watchlist-ticker]");
      if (!row) return;
      this.switchTicker(row.dataset.watchlistTicker);
    });
    this.root.querySelector("#watchlistCollapseButton").addEventListener("click", () => this.setSidebarCollapsed(!this.sidebarCollapsed));
    this.root.querySelector("#watchlistSlimButton").addEventListener("click", () => this.setSidebarCollapsed(false));
    this.root.querySelector("#watchlistMobileButton").addEventListener("click", () => this.root.classList.toggle("watchlist-mobile-open", true));
    this.root.querySelector("#watchlistMobileClose").addEventListener("click", () => this.root.classList.toggle("watchlist-mobile-open", false));
    document.addEventListener("keydown", (event) => this.handleShortcut(event));
  }

  renderToolbar() {
    const groups = TOOL_GROUPS.map((group) => {
      const buttons = group
        .map(
          (tool) => `
            <button type="button" class="drawing-tool-button" data-tool="${tool.id}" title="${tool.label}${tool.shortcut ? ` (${tool.shortcut})` : ""}" aria-label="${tool.label}">
              ${tool.icon}
            </button>
          `,
        )
        .join("");
      return `<div class="drawing-tool-group">${buttons}</div>`;
    }).join("");
    this.toolbarNode.innerHTML = groups;
    this.toolbarNode.addEventListener("click", (event) => {
      const button = event.target.closest("[data-tool]");
      if (!button) return;
      this.handleToolButton(button.dataset.tool);
    });
    this.updateToolButtons();
  }

  handleToolButton(toolId) {
    if (!this.drawingLayer) return;
    if (toolId === "magnet") this.drawingLayer.setMagnet(!this.drawingLayer.settings.magnet);
    else if (toolId === "lock") this.drawingLayer.setGlobalLock(!this.drawingLayer.settings.lockAll);
    else if (toolId === "hide") this.drawingLayer.setHidden(!this.drawingLayer.settings.hidden);
    else if (toolId === "delete") {
      if (!this.drawingLayer.deleteSelected()) this.drawingLayer.setTool("delete");
    } else {
      this.drawingLayer.setTool(toolId);
    }
    this.updateToolButtons();
  }

  updateToolButtons() {
    if (!this.drawingLayer) return;
    this.toolbarNode.querySelectorAll("[data-tool]").forEach((button) => {
      const tool = button.dataset.tool;
      const active =
        tool === this.drawingLayer.activeTool ||
        (tool === "magnet" && this.drawingLayer.settings.magnet) ||
        (tool === "lock" && this.drawingLayer.settings.lockAll) ||
        (tool === "hide" && this.drawingLayer.settings.hidden);
      button.classList.toggle("active", active);
    });
  }

  async open() {
    const current = this.getState();
    this.currentTicker = normalizeTicker(current.selectedTicker || current.ticker || "BBCA");
    this.range = current.range || "1Y";
    this.isOpen = true;
    this.root.classList.remove("hidden");
    this.root.setAttribute("aria-hidden", "false");
    document.body.classList.add("chart-fullscreen-open");
    this.updateRangeButtons();
    this.ensureChart();
    await Promise.allSettled([this.loadWatchlist(), this.loadTicker(this.currentTicker)]);
    window.setTimeout(() => this.resizeChart(), 80);
  }

  close() {
    this.drawingLayer?.saveDrawings();
    this.isOpen = false;
    this.root.classList.add("hidden");
    this.root.classList.remove("watchlist-mobile-open");
    this.root.setAttribute("aria-hidden", "true");
    document.body.classList.remove("chart-fullscreen-open");
  }

  ensureChart() {
    if (this.chart) return;
    const charts = window.LightweightCharts;
    if (!charts) {
      this.showEmpty("Lightweight Charts library is not loaded.");
      return;
    }
    this.chart = charts.createChart(this.chartNode, this.chartOptions());
    this.candleSeries = this.chart.addCandlestickSeries({
      upColor: "#36e58d",
      downColor: "#ff5d6c",
      borderVisible: false,
      wickUpColor: "#36e58d",
      wickDownColor: "#ff5d6c",
    });
    this.volumeSeries = this.chart.addHistogramSeries({
      color: "rgba(114, 198, 255, 0.28)",
      priceFormat: { type: "volume" },
      priceScaleId: "",
    });
    this.volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    this.sma20Series = this.chart.addLineSeries({ color: "#72c6ff", lineWidth: 1, priceLineVisible: false });
    this.sma50Series = this.chart.addLineSeries({ color: "#f2c15f", lineWidth: 1, priceLineVisible: false });
    this.chart.subscribeCrosshairMove((param) => this.updateCrosshairTooltip(param));
    this.drawingLayer = new DrawingLayer({
      svg: this.drawingSvg,
      host: this.chartStage,
      tooltipNode: this.tooltipNode,
      toast: showToast,
    });
    this.drawingLayer.attach({
      chart: this.chart,
      candleSeries: this.candleSeries,
      ticker: this.currentTicker,
      candles: this.candles,
    });
    this.drawingLayer.setTool("crosshair");
    this.resizeObserver = new ResizeObserver(() => this.resizeChart());
    this.resizeObserver.observe(this.chartStage);
  }

  chartOptions() {
    return {
      width: this.chartNode.clientWidth,
      height: this.chartNode.clientHeight || 640,
      autoSize: true,
      layout: {
        background: { color: "transparent" },
        textColor: "#9fb0aa",
        fontFamily: "Inter, sans-serif",
      },
      grid: {
        vertLines: { color: "rgba(148, 163, 184, 0.09)" },
        horzLines: { color: "rgba(148, 163, 184, 0.1)" },
      },
      crosshair: {
        mode: window.LightweightCharts.CrosshairMode.Normal,
        vertLine: { color: "rgba(237, 244, 241, 0.42)", width: 1, style: 3, labelVisible: true },
        horzLine: { color: "rgba(237, 244, 241, 0.42)", width: 1, style: 3, labelVisible: true },
      },
      rightPriceScale: { borderColor: "rgba(148, 163, 184, 0.24)" },
      timeScale: {
        borderColor: "rgba(148, 163, 184, 0.24)",
        rightOffset: 12,
        barSpacing: 8,
        lockVisibleTimeRangeOnResize: true,
      },
      handleScale: true,
      handleScroll: true,
    };
  }

  async loadTicker(ticker) {
    this.currentTicker = normalizeTicker(ticker);
    this.setLoading(true);
    this.hideEmpty();
    this.updateHeader();
    this.renderWatchlist();

    const [chartResult, predictionResult, newsResult, nlpResult] = await Promise.allSettled([
      loadChart(this.currentTicker, this.range, "1d"),
      loadPrediction(this.currentTicker),
      loadNews(this.currentTicker, 100),
      loadNlpSummary(this.currentTicker),
    ]);

    if (chartResult.status === "fulfilled") {
      this.candles = normalizeCandles(chartResult.value.candles || []);
      this.renderChartData();
    } else {
      this.candles = [];
      this.candleSeries?.setData([]);
      this.volumeSeries?.setData([]);
      this.sma20Series?.setData([]);
      this.sma50Series?.setData([]);
      this.showEmpty(`Gagal memuat chart ${this.currentTicker}: ${chartResult.reason.message}`);
    }

    this.prediction = predictionResult.status === "fulfilled" ? predictionResult.value : null;
    this.newsRows = newsResult.status === "fulfilled" ? newsResult.value.news || [] : [];
    this.nlpSummary = nlpResult.status === "fulfilled" ? nlpResult.value.summary || {} : {};
    this.renderMarkers();
    this.updateHeader();
    this.updateSideDetails();
    this.drawingLayer?.setTicker(this.currentTicker, this.candles);
    this.setLoading(false);
  }

  renderChartData() {
    if (!this.candles.length) {
      this.showEmpty(`Chart ${this.currentTicker} kosong. Pastikan artifact harga sudah tersedia.`);
      return;
    }
    this.hideEmpty();
    this.candleSeries.setData(this.candles.map(toCandlePoint));
    this.volumeSeries.setData(this.showVolume ? this.candles.map(toVolumePoint) : []);
    this.sma20Series.setData(this.showSma20 ? movingAverage(this.candles, 20) : []);
    this.sma50Series.setData(this.showSma50 ? movingAverage(this.candles, 50) : []);
    this.chart.timeScale().fitContent();
    this.drawingLayer?.updateCandles(this.candles);
  }

  renderMarkers() {
    if (!this.candleSeries) return;
    const markers = [];
    this.markerDetails = new Map();

    if (this.showNewsMarkers) {
      const grouped = new Map();
      for (const row of this.newsRows || []) {
        const time = toChartTime(row.date);
        if (!time) continue;
        if (!grouped.has(time)) grouped.set(time, []);
        grouped.get(time).push(row);
      }
      for (const [time, rows] of grouped.entries()) {
        markers.push({
          time,
          position: "aboveBar",
          color: "#f2c15f",
          shape: "circle",
          text: `${rows.length} news`,
        });
        this.markerDetails.set(time, [...(this.markerDetails.get(time) || []), ...rows.map((row) => ({ kind: "news", row }))]);
      }
    }

    if (this.showPredictionMarkers && this.prediction?.status === "ok") {
      const time = toChartTime(this.prediction.date) || this.candles.at(-1)?.time;
      if (time) {
        const isUp = Number(this.prediction.predicted_direction) === 1 || Number(this.prediction.predicted_return) > 0;
        markers.push({
          time,
          position: isUp ? "belowBar" : "aboveBar",
          color: isUp ? "#36e58d" : "#ff5d6c",
          shape: isUp ? "arrowUp" : "arrowDown",
          text: `Pred ${formatPercent(this.prediction.predicted_return)}`,
        });
        this.markerDetails.set(time, [
          ...(this.markerDetails.get(time) || []),
          { kind: "prediction", row: this.prediction },
        ]);
      }
    }

    markers.sort((a, b) => a.time - b.time);
    this.candleSeries.setMarkers(markers);
  }

  updateCrosshairTooltip(param) {
    const detailNode = document.getElementById("fsOhlcDetails");
    if (!param.time || !param.seriesData || !param.seriesData.has(this.candleSeries)) {
      this.tooltipNode.classList.add("hidden");
      if (detailNode) detailNode.textContent = "Hover chart for candle details.";
      return;
    }
    const value = param.seriesData.get(this.candleSeries);
    const candle = this.candles.find((row) => row.time === normalizeTime(param.time));
    const previous = previousCandle(this.candles, candle?.time);
    const change = previous?.close ? value.close / previous.close - 1 : null;
    const rows = [
      `<strong>${dateLabel(param.time)}</strong>`,
      `O ${formatNumber(value.open)} H ${formatNumber(value.high)}`,
      `L ${formatNumber(value.low)} C ${formatNumber(value.close)}`,
      `V ${formatNumber(candle?.volume)} ${formatPercent(change)}`,
    ];
    const markerDetails = this.markerDetails.get(normalizeTime(param.time)) || [];
    markerDetails.slice(0, 3).forEach((item) => {
      if (item.kind === "prediction") {
        rows.push(`Prediction: ${directionLabel(item.row)} ${formatPercent(item.row.predicted_return)}`);
      } else {
        rows.push(`News: ${escapeHtml(item.row.title || item.row.source || "headline")}`);
      }
    });
    this.tooltipNode.innerHTML = rows.join("<br>");
    this.tooltipNode.style.left = `${Math.min(param.point?.x + 18 || 18, this.chartStage.clientWidth - 260)}px`;
    this.tooltipNode.style.top = `${Math.max(12, (param.point?.y || 0) + 18)}px`;
    this.tooltipNode.classList.remove("hidden");
    if (detailNode) {
      detailNode.textContent = `O ${formatNumber(value.open)} H ${formatNumber(value.high)} L ${formatNumber(value.low)} C ${formatNumber(value.close)} V ${formatNumber(candle?.volume)} ${formatPercent(change)}`;
    }
  }

  async loadWatchlist() {
    this.renderWatchlistLoading();
    try {
      const payload = await loadStocks(100);
      this.stocks = payload.stocks || [];
      this.updateHeader();
      this.renderWatchlist();
    } catch (error) {
      this.watchlistStatusNode.innerHTML = `<span class="negative">Watchlist gagal dimuat: ${escapeHtml(error.message)}</span><button type="button" id="watchlistRetry">Retry</button>`;
      this.watchlistNode.innerHTML = "";
      this.watchlistStatusNode.querySelector("#watchlistRetry").addEventListener("click", () => this.loadWatchlist());
    }
  }

  renderWatchlistLoading() {
    this.watchlistStatusNode.textContent = "Loading market watchlist...";
    this.watchlistNode.innerHTML = Array.from({ length: 8 }, () => '<div class="watchlist-skeleton"></div>').join("");
  }

  renderWatchlist() {
    if (!this.watchlistNode) return;
    if (!this.stocks.length) {
      this.watchlistStatusNode.textContent = "Stock watchlist belum tersedia. Pastikan data prices/predictions sudah digenerate.";
      this.watchlistNode.innerHTML = "";
      return;
    }
    const medianVolume = median(this.stocks.map((row) => row.volume).filter(isFiniteNumber));
    const query = this.watchlistQuery.trim().toLowerCase();
    let rows = this.stocks.filter((row) => {
      const matchesSearch = !query || row.ticker.toLowerCase().includes(query) || String(row.company_name || row.name || "").toLowerCase().includes(query);
      const change = Number(row.daily_change_pct || 0);
      const filterMatch =
        this.watchlistFilter === "all" ||
        (this.watchlistFilter === "gainers" && change > 0) ||
        (this.watchlistFilter === "losers" && change < 0) ||
        (this.watchlistFilter === "up" && row.prediction_direction === "UP") ||
        (this.watchlistFilter === "down" && row.prediction_direction === "DOWN") ||
        (this.watchlistFilter === "volume" && isFiniteNumber(row.volume) && Number(row.volume) >= medianVolume);
      return matchesSearch && filterMatch;
    });
    rows = rows.sort((a, b) => this.watchlistComparator(a, b));
    this.filteredStocks = rows;
    this.watchlistStatusNode.textContent = `${rows.length} stocks | ${this.watchlistFilter}`;
    this.watchlistNode.innerHTML = rows.map((row) => this.watchlistRow(row)).join("");
  }

  watchlistComparator(a, b) {
    if (this.watchlistSort === "ticker") return a.ticker.localeCompare(b.ticker);
    if (this.watchlistSort === "volume" || this.watchlistSort === "active") {
      return Number(b.volume || 0) - Number(a.volume || 0);
    }
    if (this.watchlistSort === "confidence") {
      return Number(b.prediction_confidence || 0) - Number(a.prediction_confidence || 0);
    }
    return Math.abs(Number(b.daily_change_pct || 0)) - Math.abs(Number(a.daily_change_pct || 0));
  }

  watchlistRow(row) {
    const changeClass = signedClass(row.daily_change_pct);
    const active = row.ticker === this.currentTicker ? "active" : "";
    const badgeClass = String(row.prediction_direction || "NEUTRAL").toLowerCase();
    return `
      <button type="button" class="watchlist-row ${active}" data-watchlist-ticker="${escapeHtml(row.ticker)}">
        <span class="watchlist-main">
          <strong>${escapeHtml(row.ticker)}</strong>
          <small>${escapeHtml(row.company_name || row.name || row.symbol || "")}</small>
        </span>
        <span class="watchlist-price">
          <strong>${formatNumber(row.last_price)}</strong>
          <small class="${changeClass}">${formatSignedNumber(row.daily_change)} ${formatPercent(row.daily_change_pct)}</small>
        </span>
        <span class="prediction-badge ${badgeClass}">${escapeHtml(row.prediction_direction || "NEUTRAL")}</span>
      </button>
    `;
  }

  async switchTicker(ticker) {
    const nextTicker = normalizeTicker(ticker);
    if (!nextTicker || nextTicker === this.currentTicker) return;
    this.drawingLayer?.saveDrawings();
    this.currentTicker = nextTicker;
    this.renderWatchlist();
    this.onTickerChange?.(nextTicker);
    await this.loadTicker(nextTicker);
    this.root.classList.remove("watchlist-mobile-open");
  }

  toggleControl(control, button) {
    const property = {
      volume: "showVolume",
      sma20: "showSma20",
      sma50: "showSma50",
      prediction: "showPredictionMarkers",
      news: "showNewsMarkers",
    }[control];
    if (!property) return;
    this[property] = !this[property];
    button.classList.toggle("active", this[property]);
    if (["prediction", "news"].includes(control)) this.renderMarkers();
    else this.renderChartData();
  }

  handleTopbarAction(action) {
    if (action === "fit" || action === "reset") this.chart?.timeScale().fitContent();
    if (action === "save" && this.drawingLayer?.saveDrawings()) showToast(`Drawings saved for ${this.currentTicker}`);
    if (action === "clear") this.drawingLayer?.clearDrawings();
    if (action === "undo") {
      if (!this.drawingLayer?.undo()) showToast("Nothing to undo", "error");
    }
    if (action === "redo") {
      if (!this.drawingLayer?.redo()) showToast("Nothing to redo", "error");
    }
  }

  handleShortcut(event) {
    if (!this.isOpen || shortcutTargetIsEditable(event.target)) return;
    const key = event.key.toLowerCase();
    if (event.key === "Escape") {
      event.preventDefault();
      this.close();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && key === "s") {
      event.preventDefault();
      this.handleTopbarAction("save");
      return;
    }
    if ((event.ctrlKey || event.metaKey) && key === "z") {
      event.preventDefault();
      this.drawingLayer?.undo();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && key === "y") {
      event.preventDefault();
      this.drawingLayer?.redo();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key === "0") {
      event.preventDefault();
      this.chart?.timeScale().fitContent();
      return;
    }
    if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault();
      this.drawingLayer?.deleteSelected();
      return;
    }
    const shortcutTool = {
      v: "select",
      t: "trendline",
      h: "horizontal",
      f: "fibonacci",
      r: "rectangle",
    }[key];
    if (shortcutTool) {
      event.preventDefault();
      this.drawingLayer?.setTool(shortcutTool);
      this.updateToolButtons();
    }
  }

  updateHeader() {
    const stock = this.stocks.find((row) => row.ticker === this.currentTicker) || {};
    const latest = this.candles.at(-1);
    const previous = this.candles.at(-2);
    const price = stock.last_price ?? latest?.close;
    const change = isFiniteNumber(stock.daily_change_pct)
      ? stock.daily_change_pct
      : previous?.close
        ? latest.close / previous.close - 1
        : null;
    document.getElementById("fsTickerLabel").textContent = `${this.currentTicker} ${this.range}`;
    document.getElementById("fsCompanyLabel").textContent = stock.company_name || stock.name || "IDX stock";
    document.getElementById("fsLastPrice").textContent = formatNumber(price);
    const changeNode = document.getElementById("fsDailyChange");
    changeNode.textContent = `${formatSignedNumber(stock.daily_change)} ${formatPercent(change)}`;
    changeNode.className = signedClass(change);
  }

  updateSideDetails() {
    const predictionNode = document.getElementById("fsPredictionDetails");
    const sentimentNode = document.getElementById("fsSentimentDetails");
    const newsNode = document.getElementById("fsNewsDetails");
    if (this.prediction?.status === "ok") {
      predictionNode.textContent = `${directionLabel(this.prediction)} | return ${formatPercent(this.prediction.predicted_return)} | confidence ${formatPercent(this.prediction.confidence)}`;
    } else {
      predictionNode.textContent = this.prediction?.message || "Prediction belum tersedia.";
    }
    sentimentNode.textContent = this.nlpSummary?.summary_text || "NLP summary belum tersedia.";
    newsNode.textContent = this.newsRows.length
      ? `${this.newsRows.length} recent news rows. Latest: ${this.newsRows[0]?.title || this.newsRows[0]?.source || "headline"}`
      : "News marker belum tersedia untuk ticker ini.";
  }

  updateRangeButtons() {
    this.root.querySelectorAll("[data-range]").forEach((button) => {
      button.classList.toggle("active", button.dataset.range === this.range);
    });
  }

  setSidebarCollapsed(collapsed) {
    this.sidebarCollapsed = collapsed;
    this.root.classList.toggle("watchlist-collapsed", collapsed);
    window.localStorage.setItem(SIDEBAR_KEY, collapsed ? "1" : "0");
    window.setTimeout(() => this.resizeChart(), 220);
  }

  resizeChart() {
    if (!this.chart) return;
    this.chart.resize(this.chartNode.clientWidth, this.chartNode.clientHeight || 640);
    this.drawingLayer?.render();
  }

  setLoading(enabled) {
    this.loadingNode.classList.toggle("hidden", !enabled);
  }

  showEmpty(message) {
    this.emptyNode.textContent = message;
    this.emptyNode.classList.remove("hidden");
  }

  hideEmpty() {
    this.emptyNode.textContent = "";
    this.emptyNode.classList.add("hidden");
  }
}

function normalizeTicker(ticker) {
  return String(ticker || "BBCA").trim().toUpperCase().replace(".JK", "");
}

function normalizeCandles(rows) {
  return (rows || [])
    .map((row) => ({
      ...row,
      time: toChartTime(row.date || row.time),
      open: Number(row.open),
      high: Number(row.high),
      low: Number(row.low),
      close: Number(row.close),
      volume: Number(row.volume || 0),
    }))
    .filter((row) => row.time && isFiniteNumber(row.open) && isFiniteNumber(row.high) && isFiniteNumber(row.low) && isFiniteNumber(row.close))
    .sort((a, b) => a.time - b.time);
}

function toChartTime(value) {
  if (!value) return null;
  if (typeof value === "number") return Math.floor(value);
  if (typeof value === "object" && value.year && value.month && value.day) {
    return Math.floor(Date.UTC(value.year, value.month - 1, value.day) / 1000);
  }
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? Math.floor(timestamp / 1000) : null;
}

function toCandlePoint(row) {
  return { time: row.time, open: row.open, high: row.high, low: row.low, close: row.close };
}

function toVolumePoint(row) {
  return {
    time: row.time,
    value: row.volume || 0,
    color: row.close >= row.open ? "rgba(54, 229, 141, 0.3)" : "rgba(255, 93, 108, 0.3)",
  };
}

function movingAverage(rows, windowSize) {
  const values = [];
  rows.forEach((row, index) => {
    if (index + 1 < windowSize) return;
    const slice = rows.slice(index + 1 - windowSize, index + 1);
    values.push({ time: row.time, value: slice.reduce((sum, item) => sum + item.close, 0) / windowSize });
  });
  return values;
}

function previousCandle(candles, time) {
  const index = candles.findIndex((row) => row.time === time);
  return index > 0 ? candles[index - 1] : null;
}

function directionLabel(prediction) {
  if (Number(prediction?.predicted_direction) === 1) return "UP";
  if (Number(prediction?.predicted_direction) === 0) return "DOWN";
  if (Number(prediction?.predicted_return) > 0) return "UP";
  if (Number(prediction?.predicted_return) < 0) return "DOWN";
  return "NEUTRAL";
}

function dateLabel(value) {
  const time = toChartTime(value);
  return time ? new Date(time * 1000).toISOString().slice(0, 10) : "n/a";
}

function median(values) {
  if (!values.length) return 0;
  const sorted = values.map(Number).sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function formatSignedNumber(value) {
  if (!isFiniteNumber(value)) return "";
  const number = Number(value);
  return `${number > 0 ? "+" : ""}${formatNumber(number)}`;
}

function shortcutTargetIsEditable(target) {
  if (!target) return false;
  const tagName = target.tagName?.toLowerCase();
  return tagName === "input" || tagName === "textarea" || tagName === "select" || target.isContentEditable;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
