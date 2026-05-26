import { formatNumber, hideEmpty, isFiniteNumber, showEmpty, signedClass } from "./ui.js";

const INITIAL_NEWS_LIMIT = 8;
let activeFilter = "all";
let currentRows = [];
let currentCarouselNode = null;
let currentEmptyNode = null;

export function bindNewsControls(filterBar) {
  filterBar?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-news-filter]");
    if (!button) return;
    activeFilter = button.dataset.newsFilter || "all";
    filterBar.querySelectorAll("[data-news-filter]").forEach((node) => {
      node.classList.toggle("active", node === button);
    });
    renderCurrentCarousel({ transition: true });
  });
}

export function renderNews(carouselNode, emptyNode, rows) {
  currentCarouselNode = carouselNode;
  currentEmptyNode = emptyNode;
  currentRows = rows || [];
  renderCurrentCarousel({ transition: false });
}

export function renderNewsLoading(carouselNode, emptyNode) {
  hideEmpty(emptyNode);
  carouselNode.innerHTML = "";
  for (let index = 0; index < 4; index += 1) {
    const skeleton = document.createElement("article");
    skeleton.className = "news-card news-carousel-card skeleton news";
    carouselNode.appendChild(skeleton);
  }
}

function renderCurrentCarousel({ transition }) {
  if (!currentCarouselNode || !currentEmptyNode) return;
  const render = () => {
    currentCarouselNode.innerHTML = "";
    const selectedRows = filteredRows();
    if (!selectedRows.length) {
      showEmpty(currentEmptyNode, "Using latest available market news. No article rows are available in the current artifact.");
      currentCarouselNode.appendChild(placeholderCard("Using latest available market news"));
      return;
    }

    const fallbackUsed = activeFilter !== "all" && !currentRows.some((row) => sentimentBucket(row) === activeFilter);
    if (fallbackUsed) {
      showEmpty(currentEmptyNode, `No recent ${activeFilter} news found. Showing latest available market news.`);
    } else {
      hideEmpty(currentEmptyNode);
    }

    renderNewsCarousel(currentCarouselNode, selectedRows.slice(0, INITIAL_NEWS_LIMIT));
  };

  if (!transition) {
    render();
    return;
  }

  currentCarouselNode.classList.add("is-transitioning");
  window.setTimeout(() => {
    render();
    window.requestAnimationFrame(() => {
      currentCarouselNode.classList.remove("is-transitioning");
    });
  }, 180);
}

function filteredRows() {
  if (activeFilter === "all") return currentRows;
  const exactRows = currentRows.filter((row) => sentimentBucket(row) === activeFilter);
  return exactRows.length ? exactRows : currentRows;
}

function renderNewsCarousel(container, rows) {
  const visibleRows = rows.filter((row) => row.title).slice(0, INITIAL_NEWS_LIMIT);
  if (!visibleRows.length) {
    container.appendChild(placeholderCard("Using latest available market news"));
    return;
  }

  const loopRows = visibleRows.length > 1 ? [...visibleRows, ...visibleRows] : visibleRows;
  loopRows.forEach((row) => {
    const card = newsCard(row);
    card.classList.add("news-carousel-card");
    container.appendChild(card);
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

function placeholderCard(text) {
  const item = document.createElement("article");
  item.className = "news-card news-carousel-card news-placeholder-card";
  item.textContent = text;
  return item;
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
