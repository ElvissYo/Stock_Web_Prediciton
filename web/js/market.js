import { loadCompanyProfile } from "./data-loader.js";
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

export function renderMarketMovers(gainersNode, losersNode, emptyNode, sourceNode, payload) {
  gainersNode.innerHTML = "";
  losersNode.innerHTML = "";

  const gainers = payload?.gainers || [];
  const losers = payload?.losers || [];
  const available = payload?.available_tickers || 0;
  if (!available || (!gainers.length && !losers.length)) {
    sourceNode.textContent = "";
    showEmpty(emptyNode, "Market movers belum tersedia. Jalankan pipeline collect_prices.py terlebih dahulu.");
    return;
  }

  hideEmpty(emptyNode);
  const latestDate = gainers[0]?.date || losers[0]?.date;
  sourceNode.textContent = latestDate
    ? `${available} tickers | latest price date ${latestDate}`
    : `${available} tickers from latest price artifact`;
  gainers.forEach((row, index) => gainersNode.appendChild(moverRow(row, index + 1)));
  losers.forEach((row, index) => losersNode.appendChild(moverRow(row, index + 1)));
}

function moverRow(row, rank) {
  const node = document.createElement("div");
  node.className = `mover-row ${signedClass(row.change_pct)}`;
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
  node.querySelector(".mover-change").textContent = formatPercent(row.change_pct);
  return node;
}

function renderMoverLogo(container, row, allowHydrate = true) {
  container.textContent = tickerFallback(row.ticker);
  const candidates = logoCandidates(row);
  if (!candidates.length) {
    if (allowHydrate) hydrateMoverLogo(container, row.ticker);
    return;
  }

  let index = 0;
  const loadNext = () => {
    if (index >= candidates.length) {
      if (allowHydrate) hydrateMoverLogo(container, row.ticker);
      container.textContent = tickerFallback(row.ticker);
      container.classList.add("fallback");
      return;
    }

    const image = document.createElement("img");
    image.alt = `${row.ticker} logo`;
    image.loading = "lazy";
    image.decoding = "async";
    image.src = candidates[index];
    index += 1;
    image.addEventListener("load", () => {
      container.textContent = "";
      container.classList.remove("fallback");
      container.appendChild(image);
    });
    image.addEventListener("error", loadNext, { once: true });
  };
  loadNext();
}

async function hydrateMoverLogo(container, ticker) {
  if (!ticker) return;

  try {
    const payload = await loadCompanyProfile(ticker);
    const profile = payload.profile || {};
    if (!profile.logo_url) return;
    renderMoverLogo(container, profile, false);
  } catch {
    container.textContent = tickerFallback(ticker);
    container.classList.add("fallback");
  }
}

function tickerFallback(ticker) {
  return String(ticker || "?").slice(0, 4);
}

function logoCandidates(row) {
  const candidates = [row?.logo_url, ...(row?.logo_candidates || [])].filter(Boolean);
  return candidates.filter((value, index) => candidates.indexOf(value) === index);
}
