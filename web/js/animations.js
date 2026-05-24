export function setupRevealAnimations() {
  const targets = document.querySelectorAll(".section, .metric-card, .panel, .news-card, .data-metric");
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.08, rootMargin: "0px 0px -8% 0px" },
  );
  targets.forEach((target) => {
    target.classList.add("reveal-ready");
    observer.observe(target);
  });
}

export function restartMarquee(track) {
  if (!track) return;
  track.style.animation = "none";
  void track.offsetHeight;
  track.style.animation = "";
}

export function flashRefresh(button) {
  if (!button) return;
  button.classList.add("refreshing");
  window.setTimeout(() => button.classList.remove("refreshing"), 900);
}
