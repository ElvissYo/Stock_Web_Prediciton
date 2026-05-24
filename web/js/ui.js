export const numberFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

export function formatNumber(value) {
  if (!isFiniteNumber(value)) return "n/a";
  return numberFormatter.format(Number(value));
}

export function formatPercent(value) {
  if (!isFiniteNumber(value)) return "n/a";
  return `${(Number(value) * 100).toFixed(2)}%`;
}

export function signedClass(value) {
  if (!isFiniteNumber(value)) return "";
  if (Number(value) > 0) return "positive";
  if (Number(value) < 0) return "negative";
  return "neutral";
}

export function isFiniteNumber(value) {
  return value !== null && value !== undefined && Number.isFinite(Number(value));
}

export function showEmpty(node, message) {
  node.textContent = message;
  node.classList.remove("hidden");
}

export function hideEmpty(node) {
  node.textContent = "";
  node.classList.add("hidden");
}

export function setLoading(node, isLoading) {
  node.classList.toggle("hidden", !isLoading);
}

export function renderMetric(parent, label, value, className = "") {
  const node = document.createElement("div");
  node.className = `data-metric ${className}`;
  node.innerHTML = '<div class="label"></div><div class="value"></div>';
  node.querySelector(".label").textContent = label;
  node.querySelector(".value").textContent = value ?? "n/a";
  parent.appendChild(node);
}

export function animateMetricText(node, value, formatter = formatNumber) {
  if (!isFiniteNumber(value)) {
    node.textContent = "n/a";
    return;
  }
  const target = Number(value);
  const start = 0;
  const duration = 520;
  const startTime = performance.now();
  function tick(now) {
    const progress = Math.min((now - startTime) / duration, 1);
    const eased = 1 - (1 - progress) ** 3;
    node.textContent = formatter(start + (target - start) * eased);
    if (progress < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

export function showToast(message, type = "success") {
  const host = document.getElementById("toastHost");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  host.appendChild(toast);
  window.setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(8px)";
    window.setTimeout(() => toast.remove(), 180);
  }, 3200);
}

export function setupNavbarActiveState() {
  const links = [...document.querySelectorAll(".nav-link")];
  const sections = links
    .map((link) => document.querySelector(link.getAttribute("href")))
    .filter(Boolean);
  const observer = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (!visible) return;
      links.forEach((link) => {
        link.classList.toggle("active", link.getAttribute("href") === `#${visible.target.id}`);
      });
    },
    { rootMargin: "-18% 0px -72% 0px", threshold: [0.05, 0.2, 0.6] },
  );
  sections.forEach((section) => observer.observe(section));
}
