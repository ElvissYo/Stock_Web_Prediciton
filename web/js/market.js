import { loadCompanyProfile } from "./data-loader.js";
import { logoCandidates, logoFallbackText, renderCompanyLogo } from "./logo.js";
import { formatNumber, formatPercent, hideEmpty, showEmpty, signedClass } from "./ui.js";

export function renderMoversLoading(gainersNode, losersNode, emptyNode) {
  hideEmpty(emptyNode);
  [gainersNode, losersNode].forEach((node) => {
    node.innerHTML = "";
    for (let index = 0; index < 5; index += 1) {
      const skeleton = document.createElement("div");
      skeleton.className = "skeleton block";
      node.appendChild(skeleton);
    }
  });
}

const DEFAULT_VISIBLE_ROWS = 5;

export function renderMarketMovers(gainersNode, losersNode, emptyNode, sourceNode, payload, options = {}) {
  gainersNode.innerHTML = "";
  losersNode.innerHTML = "";

  const gainers = payload?.gainers || [];
  const losers = payload?.losers || [];
  const available = payload?.available_tickers || 0;
  if (!available || (!gainers.length && !losers.length)) {
    sourceNode.textContent = "";
    showEmpty(emptyNode, "Data unavailable: market movers belum tersedia. Jalankan pipeline collect_prices.py terlebih dahulu.");
    return;
  }

  hideEmpty(emptyNode);
  const latestDate = gainers[0]?.date || losers[0]?.date;
  sourceNode.textContent = latestDate
    ? `${available} tickers | latest price date ${latestDate}`
    : `${available} tickers from latest price artifact`;
  renderMoverList(gainersNode, gainers, options);
  renderMoverList(losersNode, losers, options);
}

function renderMoverList(container, rows, options) {
  const expanded = container.dataset.expanded === "true";
  const visibleRows = expanded ? rows : rows.slice(0, DEFAULT_VISIBLE_ROWS);
  visibleRows.forEach((row, index) => container.appendChild(moverRow(row, index + 1, options)));

  if (rows.length > DEFAULT_VISIBLE_ROWS) {
    const toggle = document.createElement("button");
    toggle.className = "mover-toggle";
    toggle.type = "button";
    toggle.textContent = expanded ? "Show top 5" : `Show all ${rows.length}`;
    toggle.addEventListener("click", () => {
      container.dataset.expanded = expanded ? "false" : "true";
      container.innerHTML = "";
      renderMoverList(container, rows, options);
    });
    container.appendChild(toggle);
  }
}

function moverRow(row, rank, options = {}) {
  const node = document.createElement("button");
  node.type = "button";
  node.className = `mover-row ${signedClass(row.change_pct)}`;
  node.dataset.ticker = row.ticker || "";
  node.title = row.ticker ? `Load ${row.ticker} in the main chart` : "Load ticker in the main chart";
  node.innerHTML = `
    <span class="mover-rank"></span>
    <span class="company-logo mover-logo fallback"></span>
    <span class="mover-name"><strong></strong><small></small></span>
    <span class="mover-price"></span>
    <span class="mover-change"></span>
  `;
  node.querySelector(".mover-rank").textContent = String(rank);
  renderMoverLogo(node.querySelector(".mover-logo"), row);
  node.querySelector(".mover-name strong").textContent = row.ticker || "n/a";
  node.querySelector(".mover-name small").textContent = row.name || row.symbol || "";
  node.querySelector(".mover-price").textContent = formatNumber(row.close);
  node.querySelector(".mover-change").innerHTML = `${directionIcon(row.change_pct)} ${formatPercent(row.change_pct)}`;
  node.addEventListener("click", () => {
    if (row.ticker) options.onTickerClick?.(row.ticker);
  });
  return node;
}

function directionIcon(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number === 0) return '<span class="mover-direction-icon">-</span>';
  const isUp = number > 0;
  return `<span class="mover-direction-icon ${isUp ? "up" : "down"}" aria-hidden="true">${isUp ? "▲" : "▼"}</span>`;
}

function renderMoverLogo(container, row, allowHydrate = true) {
  renderCompanyLogo(container, row);
  const candidates = logoCandidates(row);
  if (!candidates.length) {
    if (allowHydrate) hydrateMoverLogo(container, row.ticker);
  }
}

async function hydrateMoverLogo(container, ticker) {
  if (!ticker) return;

  try {
    const payload = await loadCompanyProfile(ticker);
    const profile = payload.profile || {};
    if (!profile.logo_url) return;
    renderMoverLogo(container, profile, false);
  } catch {
    container.textContent = logoFallbackText(ticker);
    container.classList.add("fallback");
  }
}
