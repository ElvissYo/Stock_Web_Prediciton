import { formatNumber, hideEmpty, isFiniteNumber, showEmpty, signedClass } from "./ui.js";

const INITIAL_NEWS_LIMIT = 6;
let activeFilter = "all";
let visibleLimit = INITIAL_NEWS_LIMIT;
let currentRows = [];
let currentContainer = null;
let currentEmptyNode = null;
let currentLoadMoreButton = null;

export function bindNewsControls(filterBar, loadMoreButton) {
  currentLoadMoreButton = loadMoreButton;
  filterBar?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-news-filter]");
    if (!button) return;
    activeFilter = button.dataset.newsFilter || "all";
    visibleLimit = INITIAL_NEWS_LIMIT;
    filterBar.querySelectorAll("[data-news-filter]").forEach((node) => {
      node.classList.toggle("active", node === button);
    });
    renderCurrentNewsCards();
  });
  loadMoreButton?.addEventListener("click", () => {
    visibleLimit = Number.POSITIVE_INFINITY;
    renderCurrentNewsCards();
  });
}

export function renderNews(container, emptyNode, rows, marqueeNode = null) {
  container.innerHTML = "";
  currentContainer = container;
  currentEmptyNode = emptyNode;
  currentRows = rows || [];
  visibleLimit = INITIAL_NEWS_LIMIT;
  if (marqueeNode) marqueeNode.innerHTML = "";
  if (!currentRows.length) {
    showEmpty(emptyNode, "Data unavailable: news artifact belum tersedia. Jalankan pipeline collect_news.py terlebih dahulu.");
    if (marqueeNode) {
      const item = document.createElement("span");
      item.className = "headline-chip neutral";
      item.textContent = "Data unavailable: news artifact belum tersedia.";
      marqueeNode.appendChild(item);
    }
    return;
  }

  hideEmpty(emptyNode);
  if (marqueeNode) renderNewsMarquee(marqueeNode, currentRows);
  renderCurrentNewsCards();
}

export function renderNewsLoading(container, emptyNode) {
  hideEmpty(emptyNode);
  currentLoadMoreButton?.classList.add("hidden");
  container.innerHTML = "";
  for (let index = 0; index < 3; index += 1) {
    const skeleton = document.createElement("div");
    skeleton.className = "skeleton news";
    container.appendChild(skeleton);
  }
}

function renderCurrentNewsCards() {
  if (!currentContainer || !currentEmptyNode) return;
  currentContainer.innerHTML = "";
  const filteredRows = currentRows.filter((row) => activeFilter === "all" || sentimentBucket(row) === activeFilter);
  if (!filteredRows.length) {
    showEmpty(currentEmptyNode, "Data unavailable: tidak ada berita untuk filter sentimen ini.");
    currentLoadMoreButton?.classList.add("hidden");
    return;
  }

  hideEmpty(currentEmptyNode);
  filteredRows.slice(0, visibleLimit).forEach((row) => currentContainer.appendChild(newsCard(row)));
  if (currentLoadMoreButton) {
    const hasMore = Number.isFinite(visibleLimit) && filteredRows.length > visibleLimit;
    currentLoadMoreButton.classList.toggle("hidden", !hasMore);
    currentLoadMoreButton.textContent = `Load more (${filteredRows.length - visibleLimit} more)`;
  }
}

function renderNewsMarquee(container, rows) {
  const visibleRows = rows.filter((row) => row.title);
  const loopRows = [...visibleRows, ...visibleRows];
  loopRows.forEach((row) => {
    const chip = safeArticleLink(row);
    chip.className = `headline-chip ${signedClass(row.sentiment_score) || "neutral"}`;
    chip.innerHTML = '<strong></strong><span></span>';
    chip.querySelector("strong").textContent = row.ticker || "IDX";
    chip.querySelector("span").textContent = row.title || "Untitled article";
    container.appendChild(chip);
  });
}

function newsCard(row) {
  const card = document.createElement("article");
  card.className = "news-card";

  card.appendChild(newsImage(row.image_url));

  const body = document.createElement("div");
  body.className = "news-body";

  const meta = document.createElement("div");
  meta.className = "news-meta";
  meta.textContent = [row.source, row.date, row.ticker].filter(Boolean).join(" | ");

  const title = safeArticleLink(row);
  title.className = "news-title";
  title.textContent = row.title || "Untitled article";

  const summary = document.createElement("p");
  summary.className = "news-summary";
  summary.textContent = row.summary || "No article summary available from the source feed.";

  body.append(meta, title, summary, sentimentPill(row));
  card.appendChild(body);
  return card;
}

function newsImage(imageUrl) {
  const holder = document.createElement("div");
  holder.className = "news-image skeleton";

  if (!imageUrl) {
    renderImageFallback(holder);
    return holder;
  }

  const image = document.createElement("img");
  image.loading = "lazy";
  image.decoding = "async";
  image.referrerPolicy = "no-referrer";
  image.alt = "News thumbnail from article source";
  image.src = imageUrl;
  image.addEventListener("load", () => {
    holder.classList.remove("skeleton");
    image.classList.add("loaded");
  });
  image.addEventListener("error", () => renderImageFallback(holder));
  holder.appendChild(image);
  return holder;
}

function renderImageFallback(holder) {
  holder.classList.remove("skeleton");
  holder.innerHTML = "";
  const fallback = document.createElement("div");
  fallback.className = "news-fallback";
  fallback.textContent = "No source image";
  holder.appendChild(fallback);
}

function safeArticleLink(row) {
  if (!row.url) {
    return document.createElement("span");
  }

  const link = document.createElement("a");
  link.href = row.url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  return link;
}

function sentimentPill(row) {
  const pill = document.createElement("span");
  const score = row.sentiment_score;
  const label = row.sentiment_label || "Unknown";
  const scoreText = isFiniteNumber(score) ? formatNumber(score) : "n/a";
  pill.className = `sentiment-pill ${signedClass(score) || "unknown"}`;
  pill.textContent = `${label} ${scoreText}`;
  return pill;
}

function sentimentBucket(row) {
  const label = String(row.sentiment_label || "").toLowerCase();
  if (label.includes("positive")) return "positive";
  if (label.includes("negative")) return "negative";
  if (label.includes("neutral")) return "neutral";
  const score = Number(row.sentiment_score);
  if (!Number.isFinite(score)) return "neutral";
  if (score > 0.05) return "positive";
  if (score < -0.05) return "negative";
  return "neutral";
}
