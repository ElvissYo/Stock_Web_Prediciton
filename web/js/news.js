import { formatNumber, hideEmpty, isFiniteNumber, showEmpty, signedClass } from "./ui.js";

export function renderNews(container, emptyNode, rows, marqueeNode = null) {
  container.innerHTML = "";
  if (marqueeNode) marqueeNode.innerHTML = "";
  if (!rows || !rows.length) {
    showEmpty(emptyNode, "News data belum tersedia. Jalankan pipeline collect_news.py terlebih dahulu.");
    if (marqueeNode) {
      const item = document.createElement("span");
      item.className = "headline-chip neutral";
      item.textContent = "News data belum tersedia dari artifact.";
      marqueeNode.appendChild(item);
    }
    return;
  }

  hideEmpty(emptyNode);
  if (marqueeNode) renderNewsMarquee(marqueeNode, rows);
  rows.forEach((row) => container.appendChild(newsCard(row)));
}

export function renderNewsLoading(container, emptyNode) {
  hideEmpty(emptyNode);
  container.innerHTML = "";
  for (let index = 0; index < 3; index += 1) {
    const skeleton = document.createElement("div");
    skeleton.className = "skeleton news";
    container.appendChild(skeleton);
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
