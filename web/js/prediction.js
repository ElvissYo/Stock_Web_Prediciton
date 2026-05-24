import {
  animateMetricText,
  formatNumber,
  formatPercent,
  hideEmpty,
  isFiniteNumber,
  renderMetric,
  showEmpty,
  signedClass,
} from "./ui.js";

export function renderPrediction(container, emptyNode, payload) {
  container.innerHTML = "";
  if (!payload || payload.status !== "ok") {
    const message = payload?.message || "Prediction data belum tersedia. Jalankan pipeline model terlebih dahulu.";
    showEmpty(emptyNode, message);
    updateOverviewPrediction(null);
    return;
  }

  hideEmpty(emptyNode);
  const direction = payload.predicted_direction === 1 ? "UP" : "DOWN";
  const predictedClose =
    isFiniteNumber(payload.close) && isFiniteNumber(payload.predicted_return)
      ? Number(payload.close) * (1 + Number(payload.predicted_return))
      : null;
  renderMetric(container, "Next-day Return", formatPercent(payload.predicted_return), signedClass(payload.predicted_return));
  renderMetric(container, "Direction", direction, payload.predicted_direction === 1 ? "positive" : "negative");
  renderMetric(container, "Confidence", formatPercent(payload.confidence));
  renderMetric(container, "Predicted Close", formatNumber(predictedClose), signedClass(payload.predicted_return));
  renderMetric(container, "Latest Close", formatNumber(payload.close));
  renderMetric(container, "Prediction Date", payload.date || "n/a");
  renderMetric(container, "Model Status", payload.model_type || payload.model_name || "artifact");
  animateMetricText(
    container.querySelector(".data-metric .value"),
    payload.predicted_return,
    formatPercent,
  );
  updateOverviewPrediction(payload);
}

export function renderPredictionLoading(container, emptyNode) {
  hideEmpty(emptyNode);
  container.innerHTML = "";
  for (let index = 0; index < 4; index += 1) {
    const skeleton = document.createElement("div");
    skeleton.className = "skeleton metric";
    container.appendChild(skeleton);
  }
}

export function renderProjection(container, emptyNode, payload) {
  container.innerHTML = "";
  const projection = payload?.projection;
  if (!payload || payload.status !== "ok" || !projection) {
    showEmpty(emptyNode, payload?.message || "Projection belum tersedia untuk input ini.");
    return;
  }

  hideEmpty(emptyNode);
  renderMetric(container, "Mode", projection.mode === "projected" ? "Projected" : "Historical");
  renderMetric(container, "Initial Amount", formatNumber(projection.initial_amount));
  renderMetric(container, "Entry Close", formatNumber(projection.entry_close));
  renderMetric(container, "Shares", formatNumber(projection.shares));
  renderMetric(container, "Target Value", formatNumber(projection.exit_value), signedClass(projection.profit_loss));
  renderMetric(container, "Profit / Loss", formatNumber(projection.profit_loss), signedClass(projection.profit_loss));
  renderMetric(container, "Return", formatPercent(projection.profit_loss_pct), signedClass(projection.profit_loss_pct));
  renderMetric(container, "Target Date", projection.requested_exit_date || "n/a");
}

export function renderProjectionLoading(container, emptyNode) {
  hideEmpty(emptyNode);
  container.innerHTML = "";
  for (let index = 0; index < 6; index += 1) {
    const skeleton = document.createElement("div");
    skeleton.className = "skeleton metric";
    container.appendChild(skeleton);
  }
}

export function renderNlpSummary(container, summary) {
  container.innerHTML = "";
  if (!summary || !Object.keys(summary).length) {
    renderMetric(container, "Overall Sentiment", "n/a");
    renderMetric(container, "Related News", "n/a");
    renderInsightCard(container, "NLP summary belum tersedia dari artifact untuk ticker ini.");
    return;
  }

  renderMetric(container, "Overall Sentiment", summary.overall_sentiment || "Unknown", signedClass(summary.sentiment_mean));
  renderMetric(container, "Sentiment Score", formatNumber(summary.sentiment_mean), signedClass(summary.sentiment_mean));
  renderMetric(container, "Related News", formatNumber(summary.news_count));
  renderMetric(container, "Sentiment Momentum", formatNumber(summary.sentiment_momentum), signedClass(summary.sentiment_momentum));
  renderMetric(container, "Latest News", summary.latest_news_timestamp || summary.date || "n/a");
  renderInsightCard(container, summary.summary_text || "NLP summary text is not available.", [
    ["Main theme", summary.main_theme],
    ["Top positive", summary.top_positive_headline],
    ["Top negative", summary.top_negative_headline],
  ]);
}

export function renderPredictionDrivers(container, emptyNode, summaryNode, payload) {
  container.innerHTML = "";
  summaryNode.textContent = "";

  const drivers = payload?.drivers || [];
  if (!payload || payload.status !== "ok" || !drivers.length) {
    summaryNode.textContent = payload?.summary || "Prediction drivers belum tersedia dari artifact saat ini.";
    showEmpty(emptyNode, payload?.message || "Prediction data belum tersedia. Jalankan pipeline model terlebih dahulu.");
    return;
  }

  hideEmpty(emptyNode);
  summaryNode.textContent = payload.summary || `${payload.ticker || "Selected ticker"} driver summary loaded from API.`;
  drivers.forEach((driver) => container.appendChild(driverCard(driver)));
}

export function renderModelPerformance(metricsNode, emptyNode, summaryNode, payload) {
  metricsNode.innerHTML = "";
  summaryNode.innerHTML = "";

  if (!payload || payload.status !== "ok") {
    showEmpty(emptyNode, payload?.message || "Model performance report belum ditemukan.");
    return;
  }

  hideEmpty(emptyNode);
  renderMetric(metricsNode, "Baseline MAPE", formatPercent(payload.baseline_mape));
  renderMetric(metricsNode, "NLP Model MAPE", formatPercent(payload.nlp_model_mape));
  renderMetric(metricsNode, "Directional Accuracy", formatPercent(payload.directional_accuracy));
  renderMetric(metricsNode, "Direction Classifier", formatPercent(payload.direction_classifier_accuracy));
  renderMetric(metricsNode, "Improvement", formatPctValue(payload.improvement_pct), signedClass(payload.improvement_pct));
  renderMetric(metricsNode, "Rank IC", formatNumber(payload.rank_ic), signedClass(payload.rank_ic));
  renderMetric(metricsNode, "Top Basket Excess", formatPercent(payload.top_n_excess_return), signedClass(payload.top_n_excess_return));
  renderMetric(metricsNode, "Stocks Covered", formatNumber(payload.stocks_covered));
  renderMetric(metricsNode, "Training Rows", formatNumber(payload.data_rows));
  renderMetric(metricsNode, "News Articles", formatNumber(payload.news_articles));
  renderMetric(metricsNode, "Last Training Date", payload.last_training_date || "n/a");
  renderMetric(metricsNode, "Latest News Date", payload.latest_news_date || "n/a");

  const note = document.createElement("div");
  note.className = "model-note";
  note.textContent = payload.narrative || "Model performance is loaded from the latest local evaluation report.";
  summaryNode.appendChild(note);
}

export function renderModelLoading(metricsNode, emptyNode, summaryNode) {
  hideEmpty(emptyNode);
  summaryNode.innerHTML = "";
  metricsNode.innerHTML = "";
  for (let index = 0; index < 4; index += 1) {
    const skeleton = document.createElement("div");
    skeleton.className = "skeleton metric";
    metricsNode.appendChild(skeleton);
  }
}

function updateOverviewPrediction(payload) {
  const returnNode = document.getElementById("overviewPrediction");
  const directionNode = document.getElementById("overviewDirection");
  const confidenceNode = document.getElementById("overviewConfidence");
  if (!payload) {
    returnNode.textContent = "n/a";
    returnNode.className = "";
    directionNode.textContent = "n/a";
    directionNode.className = "";
    confidenceNode.textContent = "Confidence: n/a";
    return;
  }

  returnNode.textContent = formatPercent(payload.predicted_return);
  returnNode.className = signedClass(payload.predicted_return);
  directionNode.textContent = payload.predicted_direction === 1 ? "UP" : "DOWN";
  directionNode.className = payload.predicted_direction === 1 ? "positive" : "negative";
  confidenceNode.textContent = `Confidence: ${formatPercent(payload.confidence)}`;
}

function driverCard(row) {
  const score = Math.min(Math.abs(Number(row.score) || 0), 1);
  const item = document.createElement("article");
  item.className = `driver-card ${row.status || "neutral"}`;
  item.innerHTML = `
    <div class="driver-head">
      <span></span>
      <strong></strong>
    </div>
    <p></p>
    <div class="driver-progress"><span></span></div>
    <small></small>
  `;
  item.querySelector(".driver-head span").textContent = row.label || "Driver";
  item.querySelector(".driver-head strong").textContent = row.value || "n/a";
  item.querySelector("p").textContent = row.detail || "Loaded from the dashboard API.";
  item.querySelector(".driver-progress span").style.width = `${Math.max(4, score * 100)}%`;
  item.querySelector("small").textContent = driverRawText(row);
  return item;
}

function renderInsightCard(container, summaryText, rows = []) {
  const card = document.createElement("article");
  card.className = "insight-card";

  const summary = document.createElement("p");
  summary.textContent = summaryText;
  card.appendChild(summary);

  rows
    .filter(([, value]) => value)
    .forEach(([label, value]) => {
      const item = document.createElement("div");
      item.className = "insight-row";
      item.innerHTML = "<span></span><strong></strong>";
      item.querySelector("span").textContent = label;
      item.querySelector("strong").textContent = value;
      card.appendChild(item);
    });

  container.appendChild(card);
}

function driverRawText(row) {
  if (!isFiniteNumber(row.raw_value)) {
    return `Signal score ${formatNumber(row.score)}`;
  }
  if (row.key === "momentum") return `5-session return ${formatPercent(row.raw_value)}`;
  if (row.key === "volume") return `Volume ratio ${formatNumber(row.raw_value)}x`;
  if (row.key === "sentiment") return `Sentiment score ${formatNumber(row.raw_value)}`;
  if (row.key === "volatility") return `Recent volatility ${formatPercent(row.raw_value)}`;
  if (row.key === "model") return `Confidence ${formatPercent(row.raw_value)}`;
  return `Signal score ${formatNumber(row.score)}`;
}

function formatPctValue(value) {
  if (!isFiniteNumber(value)) return "n/a";
  return `${Number(value).toFixed(2)}%`;
}
