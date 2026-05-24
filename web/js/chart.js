import { formatNumber, formatPercent, isFiniteNumber, showEmpty, hideEmpty } from "./ui.js";

export const RANGE_CONFIG = {
  "1D": { period: "1d", interval: "5m", historyPeriod: "1mo", historyInterval: "5m" },
  "5D": { period: "5d", interval: "30m", historyPeriod: "3mo", historyInterval: "30m" },
  "1M": { period: "1mo", interval: "1d", historyPeriod: "max", historyInterval: "1d" },
  "3M": { period: "3mo", interval: "1d", historyPeriod: "max", historyInterval: "1d" },
  "6M": { period: "6mo", interval: "1d", historyPeriod: "max", historyInterval: "1d" },
  YTD: { period: "ytd", interval: "1d", historyPeriod: "max", historyInterval: "1d" },
  "1Y": { period: "1y", interval: "1d", historyPeriod: "max", historyInterval: "1d" },
  "5Y": { period: "5y", interval: "1d", historyPeriod: "max", historyInterval: "1d" },
  "20Y": { period: "20y", interval: "1d" },
  ALL: { period: "max", interval: "1d" },
};

let mainChart;
let candleSeries;
let volumeSeries;
let sma20Series;
let sma50Series;
let indexChart;
let indexCandleSeries;
let indexVolumeSeries;
let indexSma20Series;
let indexSma50Series;
let technicalChart;
let closeSeries;
let technicalSma20Series;
let technicalSma50Series;
let predictionChart;
let predictionCloseSeries;
let predictionForecastSeries;
let projectionChart;
let projectionValueSeries;
let projectionLowerSeries;
let projectionUpperSeries;
let latestCandles = [];
let latestIndexCandles = [];
let resizeRegistered = false;

export function ensureCharts() {
  const charts = window.LightweightCharts;
  if (!charts) {
    throw new Error("Lightweight Charts library is not loaded.");
  }
  if (!indexChart) {
    const container = document.getElementById("indexChart");
    if (container) {
      indexChart = charts.createChart(container, chartOptions(container));
      indexCandleSeries = indexChart.addCandlestickSeries({
        upColor: "#2fd47a",
        downColor: "#ef5965",
        borderVisible: false,
        wickUpColor: "#2fd47a",
        wickDownColor: "#ef5965",
      });
      indexVolumeSeries = indexChart.addHistogramSeries({
        color: "rgba(88, 166, 255, 0.32)",
        priceFormat: { type: "volume" },
        priceScaleId: "",
      });
      indexVolumeSeries.priceScale().applyOptions({
        scaleMargins: { top: 0.82, bottom: 0 },
      });
      indexSma20Series = indexChart.addLineSeries({ color: "#58a6ff", lineWidth: 1, priceLineVisible: false });
      indexSma50Series = indexChart.addLineSeries({ color: "#f0b84f", lineWidth: 1, priceLineVisible: false });
      indexChart.subscribeCrosshairMove((param) => {
        updateCrosshairReadout(param, "ihsgReadout", indexCandleSeries, latestIndexCandles);
      });
    }
  }
  if (!mainChart) {
    const container = document.getElementById("mainChart");
    mainChart = charts.createChart(container, chartOptions(container));
    candleSeries = mainChart.addCandlestickSeries({
      upColor: "#2fd47a",
      downColor: "#ef5965",
      borderVisible: false,
      wickUpColor: "#2fd47a",
      wickDownColor: "#ef5965",
    });
    volumeSeries = mainChart.addHistogramSeries({
      color: "rgba(88, 166, 255, 0.32)",
      priceFormat: { type: "volume" },
      priceScaleId: "",
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });
    sma20Series = mainChart.addLineSeries({ color: "#58a6ff", lineWidth: 1, priceLineVisible: false });
    sma50Series = mainChart.addLineSeries({ color: "#f0b84f", lineWidth: 1, priceLineVisible: false });
    mainChart.subscribeCrosshairMove((param) => {
      updateCrosshairReadout(param, "ohlcReadout", candleSeries, latestCandles);
    });
  }
  if (!technicalChart) {
    const container = document.getElementById("technicalChart");
    if (container) {
      technicalChart = charts.createChart(container, {
        ...chartOptions(container),
        height: container.clientHeight || 320,
      });
      closeSeries = technicalChart.addLineSeries({ color: "#e6edf3", lineWidth: 2 });
      technicalSma20Series = technicalChart.addLineSeries({ color: "#58a6ff", lineWidth: 1 });
      technicalSma50Series = technicalChart.addLineSeries({ color: "#f0b84f", lineWidth: 1 });
    }
  }
  if (!predictionChart) {
    const container = document.getElementById("predictionChart");
    if (container) {
      predictionChart = charts.createChart(container, {
        ...chartOptions(container),
        height: container.clientHeight || 280,
      });
      predictionCloseSeries = predictionChart.addLineSeries({ color: "#e6edf3", lineWidth: 2 });
      predictionForecastSeries = predictionChart.addLineSeries({
        color: "#2fd47a",
        lineWidth: 2,
        lineStyle: window.LightweightCharts.LineStyle.Dashed,
        priceLineVisible: true,
      });
    }
  }
  if (!projectionChart) {
    const container = document.getElementById("projectionChart");
    if (container) {
      projectionChart = charts.createChart(container, {
        ...chartOptions(container),
        height: container.clientHeight || 280,
      });
      projectionValueSeries = projectionChart.addLineSeries({ color: "#58a6ff", lineWidth: 2 });
      projectionLowerSeries = projectionChart.addLineSeries({
        color: "rgba(239, 89, 101, 0.8)",
        lineStyle: window.LightweightCharts.LineStyle.Dashed,
        lineWidth: 1,
        priceLineVisible: false,
      });
      projectionUpperSeries = projectionChart.addLineSeries({
        color: "rgba(47, 212, 122, 0.8)",
        lineStyle: window.LightweightCharts.LineStyle.Dashed,
        lineWidth: 1,
        priceLineVisible: false,
      });
    }
  }
  if (!resizeRegistered) {
    window.addEventListener("resize", resizeCharts);
    resizeRegistered = true;
  }
}

export function updateIndexChart(candles, emptyNode, range = "ALL") {
  ensureCharts();
  if (candles) {
    latestIndexCandles = normalizeCandles(candles);
  }
  if (!latestIndexCandles.length) {
    indexCandleSeries.setData([]);
    indexVolumeSeries.setData([]);
    indexSma20Series.setData([]);
    indexSma50Series.setData([]);
    showEmpty(emptyNode, "Data IHSG belum tersedia. Cek koneksi yfinance atau jalankan pipeline harga.");
    return;
  }
  hideEmpty(emptyNode);
  indexCandleSeries.setData(latestIndexCandles.map(toCandlePoint));
  indexVolumeSeries.setData(latestIndexCandles.map(toVolumePoint));
  indexSma20Series.setData(movingAverage(latestIndexCandles, 20));
  indexSma50Series.setData(movingAverage(latestIndexCandles, 50));
  applyVisibleRange(indexChart, latestIndexCandles, range);
}

export function updateMainChart(candles, emptyNode, range = "ALL") {
  ensureCharts();
  if (candles) {
    latestCandles = normalizeCandles(candles);
  }
  if (!latestCandles.length) {
    candleSeries.setData([]);
    volumeSeries.setData([]);
    sma20Series.setData([]);
    sma50Series.setData([]);
    showEmpty(emptyNode, "Data belum tersedia. Jalankan pipeline atau cek koneksi yfinance.");
    return;
  }
  hideEmpty(emptyNode);
  candleSeries.setData(latestCandles.map(toCandlePoint));
  volumeSeries.setData(latestCandles.map(toVolumePoint));
  sma20Series.setData(movingAverage(latestCandles, 20));
  sma50Series.setData(movingAverage(latestCandles, 50));
  applyVisibleRange(mainChart, latestCandles, range);
  updateOverviewFromCandles(latestCandles);
}

export function updateTechnicalChart(rows, emptyNode) {
  ensureCharts();
  if (!technicalChart) return;
  const normalizedRows = normalizeCandles(rows);
  if (!normalizedRows.length) {
    closeSeries.setData([]);
    technicalSma20Series.setData([]);
    technicalSma50Series.setData([]);
    showEmpty(emptyNode, "Data belum tersedia. Jalankan pipeline build_price_features.py terlebih dahulu.");
    return;
  }
  hideEmpty(emptyNode);
  closeSeries.setData(
    normalizedRows
      .filter((row) => isFiniteNumber(row.close))
      .map((row) => ({ time: row.time, value: Number(row.close) })),
  );
  technicalSma20Series.setData(indicatorSeries(normalizedRows, "SMA_20"));
  technicalSma50Series.setData(indicatorSeries(normalizedRows, "SMA_50"));
  technicalChart.timeScale().fitContent();
}

export function updatePredictionChart(rows, prediction, emptyNode) {
  ensureCharts();
  if (!predictionChart) return;

  const normalizedRows = normalizeCandles(rows).filter((row) => isFiniteNumber(row.close));
  if (!normalizedRows.length || !prediction || prediction.status !== "ok") {
    predictionCloseSeries.setData([]);
    predictionForecastSeries.setData([]);
    predictionForecastSeries.setMarkers([]);
    showEmpty(emptyNode, "Prediction chart belum tersedia. Jalankan pipeline model dan price features terlebih dahulu.");
    return;
  }

  const history = normalizedRows.slice(-120);
  const latest = history[history.length - 1];
  const latestClose = isFiniteNumber(prediction.close) ? Number(prediction.close) : latest.close;
  const predictedClose = latestClose * (1 + Number(prediction.predicted_return || 0));
  const nextTime = nextTradingTime(latest.time);

  hideEmpty(emptyNode);
  predictionCloseSeries.setData(history.map((row) => ({ time: row.time, value: row.close })));
  predictionForecastSeries.applyOptions({
    color: predictedClose >= latestClose ? "#2fd47a" : "#ef5965",
  });
  predictionForecastSeries.setData([
    { time: latest.time, value: latestClose },
    { time: nextTime, value: predictedClose },
  ]);
  predictionForecastSeries.setMarkers([
    {
      time: nextTime,
      position: predictedClose >= latestClose ? "aboveBar" : "belowBar",
      color: predictedClose >= latestClose ? "#2fd47a" : "#ef5965",
      shape: predictedClose >= latestClose ? "arrowUp" : "arrowDown",
      text: `Next ${formatPercent(prediction.predicted_return)}`,
    },
  ]);
  predictionChart.timeScale().fitContent();
}

export function updateProjectionChart(projection, emptyNode) {
  ensureCharts();
  if (!projectionChart) return;

  const rows = (projection?.rows || [])
    .map((row) => ({
      ...row,
      time: toChartTime(row.date),
      value: Number(row.value),
      lower_value: Number(row.lower_value),
      upper_value: Number(row.upper_value),
    }))
    .filter((row) => row.time && isFiniteNumber(row.value))
    .sort((a, b) => a.time - b.time);

  if (!rows.length) {
    projectionValueSeries.setData([]);
    projectionLowerSeries.setData([]);
    projectionUpperSeries.setData([]);
    showEmpty(emptyNode, "Projection belum tersedia untuk input ini.");
    return;
  }

  hideEmpty(emptyNode);
  projectionValueSeries.applyOptions({
    color: Number(projection.profit_loss || 0) >= 0 ? "#2fd47a" : "#ef5965",
  });
  projectionValueSeries.setData(rows.map((row) => ({ time: row.time, value: row.value })));
  projectionLowerSeries.setData(
    rows
      .filter((row) => row.kind === "projected" && isFiniteNumber(row.lower_value))
      .map((row) => ({ time: row.time, value: row.lower_value })),
  );
  projectionUpperSeries.setData(
    rows
      .filter((row) => row.kind === "projected" && isFiniteNumber(row.upper_value))
      .map((row) => ({ time: row.time, value: row.upper_value })),
  );
  projectionChart.timeScale().fitContent();
}

export function updateOverviewFromCandles(candles) {
  if (!candles?.length) return;
  const priceNode = document.getElementById("overviewPrice");
  if (priceNode?.dataset.lockedTo === "market-overview") return;
  const changeNode = document.getElementById("overviewChange");
  const sourceNode = document.getElementById("overviewPriceSource");
  const latest = candles[candles.length - 1];
  const previous = candles[candles.length - 2];
  const change = previous?.close ? latest.close / previous.close - 1 : null;
  priceNode.textContent = formatNumber(latest.close);
  changeNode.textContent = formatPercent(change);
  changeNode.className = change > 0 ? "positive" : change < 0 ? "negative" : "neutral";
  sourceNode.textContent = `Source: ${latest.source || "Yahoo Finance / yfinance"}`;
}

function chartOptions(container) {
  return {
    width: container.clientWidth,
    height: container.clientHeight || 540,
    autoSize: true,
    layout: {
      background: { color: "transparent" },
      textColor: "#8ea0ae",
      fontFamily: "Inter, sans-serif",
    },
    grid: {
      vertLines: { color: "rgba(148, 163, 184, 0.08)" },
      horzLines: { color: "rgba(148, 163, 184, 0.1)" },
    },
    crosshair: {
      mode: window.LightweightCharts.CrosshairMode.Normal,
      vertLine: { color: "rgba(230, 237, 243, 0.38)", width: 1, style: 3, labelVisible: true },
      horzLine: { color: "rgba(230, 237, 243, 0.38)", width: 1, style: 3, labelVisible: true },
    },
    rightPriceScale: {
      borderColor: "rgba(148, 163, 184, 0.18)",
    },
    timeScale: {
      borderColor: "rgba(148, 163, 184, 0.18)",
      rightOffset: 12,
      barSpacing: 7,
      fixLeftEdge: false,
      lockVisibleTimeRangeOnResize: true,
    },
    handleScale: true,
    handleScroll: true,
  };
}

function updateCrosshairReadout(param, readoutId, series, rows) {
  const readout = document.getElementById(readoutId);
  if (!param.time || !param.seriesData || !param.seriesData.has(series)) {
    readout.textContent = readoutId === "ihsgReadout" ? "Hover over the IHSG chart for OHLCV" : "Hover over the stock chart for OHLCV";
    return;
  }
  const value = param.seriesData.get(series);
  const candle = rows.find((row) => row.time === param.time);
  readout.textContent = [
    `O ${formatNumber(value.open)}`,
    `H ${formatNumber(value.high)}`,
    `L ${formatNumber(value.low)}`,
    `C ${formatNumber(value.close)}`,
    `V ${formatNumber(candle?.volume)}`,
  ].join("  ");
}

function normalizeCandles(rows) {
  return (rows || [])
    .map((row) => ({
      ...row,
      time: toChartTime(row.date),
      open: Number(row.open),
      high: Number(row.high),
      low: Number(row.low),
      close: Number(row.close),
      volume: Number(row.volume || 0),
    }))
    .filter(
      (row) =>
        row.time &&
        isFiniteNumber(row.open) &&
        isFiniteNumber(row.high) &&
        isFiniteNumber(row.low) &&
        isFiniteNumber(row.close),
    )
    .sort((a, b) => a.time - b.time);
}

function toChartTime(value) {
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return null;
  return Math.floor(timestamp / 1000);
}

function toCandlePoint(row) {
  return {
    time: row.time,
    open: row.open,
    high: row.high,
    low: row.low,
    close: row.close,
  };
}

function toVolumePoint(row) {
  return {
    time: row.time,
    value: row.volume || 0,
    color: row.close >= row.open ? "rgba(47, 212, 122, 0.32)" : "rgba(239, 89, 101, 0.32)",
  };
}

function movingAverage(rows, window) {
  const values = [];
  rows.forEach((row, index) => {
    if (index + 1 < window) return;
    const slice = rows.slice(index + 1 - window, index + 1);
    const average = slice.reduce((sum, item) => sum + item.close, 0) / window;
    values.push({ time: row.time, value: average });
  });
  return values;
}

function indicatorSeries(rows, key) {
  return rows
    .filter((row) => isFiniteNumber(row[key]))
    .map((row) => ({ time: row.time, value: Number(row[key]) }));
}

function resizeCharts() {
  if (indexChart) {
    const container = document.getElementById("indexChart");
    indexChart.resize(container.clientWidth, container.clientHeight || 540);
  }
  if (mainChart) {
    const container = document.getElementById("mainChart");
    mainChart.resize(container.clientWidth, container.clientHeight || 540);
  }
  if (technicalChart) {
    const container = document.getElementById("technicalChart");
    if (container) {
      technicalChart.resize(container.clientWidth, container.clientHeight || 320);
    }
  }
  if (predictionChart) {
    const container = document.getElementById("predictionChart");
    predictionChart.resize(container.clientWidth, container.clientHeight || 280);
  }
  if (projectionChart) {
    const container = document.getElementById("projectionChart");
    projectionChart.resize(container.clientWidth, container.clientHeight || 280);
  }
}

function rangeStartTime(latestTime, range) {
  const latest = new Date(latestTime);
  if (range === "1D") return latestTime - 24 * 60 * 60 * 1000;
  if (range === "5D") return latestTime - 5 * 24 * 60 * 60 * 1000;
  if (range === "1M") return subtractMonths(latest, 1);
  if (range === "3M") return subtractMonths(latest, 3);
  if (range === "6M") return subtractMonths(latest, 6);
  if (range === "YTD") return new Date(latest.getFullYear(), 0, 1).getTime();
  if (range === "1Y") return subtractYears(latest, 1);
  if (range === "5Y") return subtractYears(latest, 5);
  if (range === "20Y") return subtractYears(latest, 20);
  return Number.NaN;
}

function applyVisibleRange(chart, rows, range) {
  if (!rows.length || range === "ALL") {
    chart.timeScale().fitContent();
    return;
  }

  const latestTime = rows[rows.length - 1].time * 1000;
  const fromMs = rangeStartTime(latestTime, range);
  if (!Number.isFinite(fromMs)) {
    chart.timeScale().fitContent();
    return;
  }

  const first = rows[0].time;
  const from = Math.max(first, Math.floor(fromMs / 1000));
  const to = rows[rows.length - 1].time;
  if (from >= to) {
    chart.timeScale().fitContent();
    return;
  }
  chart.timeScale().setVisibleRange({ from, to });
}

function nextTradingTime(time) {
  const next = new Date(time * 1000);
  next.setDate(next.getDate() + 1);
  while (next.getDay() === 0 || next.getDay() === 6) {
    next.setDate(next.getDate() + 1);
  }
  return Math.floor(next.getTime() / 1000);
}

function subtractMonths(date, months) {
  const copy = new Date(date);
  const dayOfMonth = copy.getDate();
  copy.setMonth(copy.getMonth() - months);
  if (copy.getDate() !== dayOfMonth) copy.setDate(0);
  return copy.getTime();
}

function subtractYears(date, years) {
  const copy = new Date(date);
  copy.setFullYear(copy.getFullYear() - years);
  return copy.getTime();
}
