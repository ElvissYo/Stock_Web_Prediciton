export function renderCompanyLogo(container, profile = {}) {
  if (!container) return;

  const ticker = normalizeTicker(profile.ticker || profile.symbol || "?");
  setLogoFallback(container, ticker);
  const candidates = logoCandidates(profile);
  if (!candidates.length) return;

  let index = 0;
  const loadNext = () => {
    if (index >= candidates.length) {
      setLogoFallback(container, ticker);
      return;
    }

    const image = document.createElement("img");
    image.alt = `${ticker} logo`;
    image.loading = "lazy";
    image.decoding = "async";
    image.src = candidates[index];
    index += 1;
    image.addEventListener("load", () => {
      container.innerHTML = "";
      container.classList.remove("fallback");
      container.appendChild(image);
    });
    image.addEventListener("error", loadNext, { once: true });
  };

  loadNext();
}

export function logoCandidates(profile = {}) {
  const candidates = [];
  const add = (value) => {
    if (!isHttpUrl(value) || candidates.includes(value)) return;
    candidates.push(value);
  };

  add(profile.logo_url);
  const domain = domainFromProfile(profile);
  if (domain) {
    add(`https://img.logo.dev/${encodeURIComponent(domain)}?size=128&format=png&fallback=404`);
  }

  const website = httpUrl(profile.website);
  if (website) {
    add(new URL("/favicon.ico", website).toString());
    const hostname = new URL(website).hostname;
    add(`https://icons.duckduckgo.com/ip3/${hostname}.ico`);
    add(`https://www.google.com/s2/favicons?domain_url=${encodeURIComponent(website)}&sz=128`);
  }

  (profile.logo_candidates || []).forEach(add);
  return candidates;
}

export function logoFallbackText(ticker) {
  return normalizeTicker(ticker).slice(0, 4) || "?";
}

function setLogoFallback(container, ticker) {
  container.innerHTML = "";
  container.textContent = logoFallbackText(ticker);
  container.classList.add("fallback");
}

function normalizeTicker(value) {
  return String(value || "?").trim().toUpperCase().replace(".JK", "");
}

function domainFromProfile(profile) {
  const rawDomain = String(profile.domain || "").trim().toLowerCase().replace(/^www\./, "");
  if (rawDomain) return rawDomain;
  const website = httpUrl(profile.website);
  return website ? new URL(website).hostname.replace(/^www\./, "") : "";
}

function httpUrl(value) {
  const text = String(value || "").trim();
  if (!isHttpUrl(text)) return "";
  try {
    return new URL(text).toString();
  } catch {
    return "";
  }
}

function isHttpUrl(value) {
  const text = String(value || "").trim();
  return text.startsWith("https://") || text.startsWith("http://");
}
