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
    const message = payload?.message || "Data unavailable: prediction data belum tersedia. Jalankan pipeline model terlebih dahulu.";
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
  container.appendChild(predictionHeroCard(payload, direction));
  renderMetric(container, "Predicted Close", formatNumber(predictedClose), signedClass(payload.predicted_return));
  renderMetric(container, "Latest Close", formatNumber(payload.close));
  renderMetric(container, "Prediction Date", payload.date || "n/a");
  renderMetric(container, "Model Status", payload.model_type || payload.model_name || "artifact");
  renderMetric(container, "Next-day Return", formatPercent(payload.predicted_return), signedClass(payload.predicted_return));
  animateMetricText(
    container.querySelector(".prediction-return strong"),
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
    showEmpty(emptyNode, payload?.message || "Data unavailable: projection belum tersedia untuk input ini.");
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
    renderInsightCard(container, "Data unavailable: NLP summary belum tersedia dari artifact untuk ticker ini.");
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
    summaryNode.textContent = payload?.summary || "Data unavailable: prediction drivers belum tersedia dari artifact saat ini.";
    showEmpty(emptyNode, payload?.message || "Data unavailable: prediction data belum tersedia. Jalankan pipeline model terlebih dahulu.");
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
    showEmpty(emptyNode, payload?.message || "Data unavailable: model health report belum ditemukan.");
    return;
  }

  hideEmpty(emptyNode);
  const health = modelHealth(payload);
  const header = document.createElement("div");
  header.className = "model-health-header";
  header.innerHTML = `
    <div>
      <span class="model-health-badge ${health.className}">${health.icon} ${health.label}</span>
      <p>${health.description}</p>
    </div>
  `;
  metricsNode.appendChild(header);
  renderMetric(metricsNode, "Baseline MAPE", formatPercent(payload.baseline_mape));
  metricsNode.lastElementChild.querySelector(".label").classList.add("tooltip");
  metricsNode.lastElementChild.querySelector(".label").dataset.tooltip = "MAPE mengukur rata-rata besar error prediksi. Lebih kecil berarti lebih baik.";
  metricsNode.lastElementChild.querySelector(".label").title = "MAPE mengukur rata-rata besar error prediksi. Lebih kecil berarti lebih baik.";
  renderMetric(metricsNode, "NLP Model MAPE", formatPercent(payload.nlp_model_mape), "", {
    tooltip: "MAPE model yang memakai fitur harga dan sentimen berita. Lebih kecil berarti prediksi return lebih dekat.",
  });
  renderMetric(metricsNode, "Directional Accuracy", formatPercent(payload.directional_accuracy), "", {
    tooltip: "Persentase prediksi arah naik/turun yang benar. Lebih besar berarti sinyal arah lebih konsisten.",
  });
  renderMetric(metricsNode, "Direction Classifier", formatPercent(payload.direction_classifier_accuracy), "", {
    tooltip: "Akurasi classifier untuk menentukan arah pasar. Nilai lebih tinggi lebih baik.",
  });
  renderMetric(metricsNode, "Improvement", formatPctValue(payload.improvement_pct), signedClass(payload.improvement_pct));
  renderMetric(metricsNode, "Rank IC", formatNumber(payload.rank_ic), signedClass(payload.rank_ic), {
    tooltip: "Rank IC menunjukkan apakah ranking saham dari model sejalan dengan hasil aktual. Positif lebih baik.",
  });
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
  const isUp = payload.predicted_direction === 1;
  directionNode.innerHTML = `<span class="direction-icon ${isUp ? "up" : "down"}" aria-hidden="true">${isUp ? "▲" : "▼"}</span><span>${isUp ? "UP" : "DOWN"}</span>`;
  directionNode.className = payload.predicted_direction === 1 ? "positive" : "negative";
  confidenceNode.textContent = `Confidence: ${formatPercent(payload.confidence)}`;
}

function predictionHeroCard(payload, direction) {
  const isUp = direction === "UP";
  const confidence = boundedPercent(payload.confidence);
  const card = document.createElement("article");
  card.className = `data-metric prediction-hero-card ${isUp ? "positive" : "negative"}`;
  card.innerHTML = `
    <div class="prediction-hero-top">
      <div>
        <div class="label">Direction</div>
        <div class="prediction-direction">
          <span class="direction-icon ${isUp ? "up" : "down"}" aria-hidden="true">${isUp ? "▲" : "▼"}</span>
          <span>${direction}</span>
        </div>
      </div>
      <div class="prediction-return">
        Next-day return
        <strong>${formatPercent(payload.predicted_return)}</strong>
      </div>
    </div>
    <div class="confidence-block">
      <div class="confidence-head">
        <span class="tooltip" data-tooltip="Confidence adalah tingkat keyakinan relatif model berdasarkan pola historis dan fitur yang tersedia. Ini bukan probabilitas keuntungan pasti." title="Confidence adalah tingkat keyakinan relatif model berdasarkan pola historis dan fitur yang tersedia. Ini bukan probabilitas keuntungan pasti.">Confidence</span>
        <span class="confidence-value">${formatPercent(payload.confidence)}</span>
      </div>
      <div class="confidence-bar" aria-label="Confidence ${formatPercent(payload.confidence)}">
        <span style="width: 100%"></span>
        <i class="confidence-marker" style="left: ${confidence}%"></i>
      </div>
      <div class="confidence-scale"><span>Low</span><span>Medium</span><span>High</span></div>
    </div>
    <p class="prediction-disclaimer">&#9888;&#65039; This prediction is not investment advice. For educational purposes only.</p>
  `;
  return card;
}

function modelHealth(payload) {
  const directionalAccuracy = Number(payload.directional_accuracy ?? payload.direction_classifier_accuracy);
  const nlpMape = Number(payload.nlp_model_mape);
  const baselineMape = Number(payload.baseline_mape);
  const hasAccuracy = Number.isFinite(directionalAccuracy);
  const hasMape = Number.isFinite(nlpMape);
  const mapeImproved = Number.isFinite(baselineMape) && hasMape ? nlpMape <= baselineMape : true;

  if ((hasAccuracy && directionalAccuracy < 0.48) || (Number.isFinite(baselineMape) && hasMape && nlpMape > baselineMape * 1.15)) {
    return {
      className: "degraded",
      icon: "&#10060;",
      label: "Degraded",
      description: "Model perlu dicek karena akurasi arah rendah atau error prediksi naik dibanding baseline.",
    };
  }
  if ((hasAccuracy && directionalAccuracy >= 0.52 && mapeImproved) || (hasMape && nlpMape <= 0.08)) {
    return {
      className: "healthy",
      icon: "&#9989;",
      label: "Healthy",
      description: "Metrik terbaru masih berada dalam batas yang layak untuk dashboard edukasi.",
    };
  }
  return {
    className: "review",
    icon: "&#9888;&#65039;",
    label: "Review Needed",
    description: "Metrik belum buruk, tetapi perlu dipantau karena sinyal belum cukup kuat.",
  };
}

function boundedPercent(value) {
  if (!isFiniteNumber(value)) return 0;
  return Math.min(100, Math.max(0, Number(value) * 100));
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
