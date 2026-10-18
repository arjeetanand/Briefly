/* Native, progressive motion: content and normal scrolling work without JS. */
(() => {
  const root = document.documentElement;
  const media = window.matchMedia("(prefers-reduced-motion: reduce)");
  const hero = document.querySelector(".hero-section");
  const art = document.querySelector(".hero-art-layer");
  const story = document.querySelector(".scroll-story");
  const progress = document.querySelector(".story-progress span");
  const chapters = [...document.querySelectorAll(".story-chapter")];
  const sections = [...document.querySelectorAll("[data-scene]")];
  const toggle = document.querySelector("#motion-toggle");
  let paused = false;
  let frame = 0;
  let observer;

  function noMotion() { return paused || media.matches; }
  function syncPreference() {
    root.dataset.reducedMotion = String(media.matches);
    root.dataset.motionPaused = String(noMotion());
    if (art) art.style.transform = "";
    toggle?.setAttribute("aria-pressed", String(noMotion()));
    if (toggle) {
      toggle.textContent = media.matches ? "Reduced motion on" : paused ? "Resume motion" : "Pause motion";
      toggle.disabled = media.matches;
    }
    schedule();
  }

  function update() {
    frame = 0;
    const height = window.innerHeight;
    const reduced = noMotion();
    if (art && hero && !reduced) {
      const top = hero.getBoundingClientRect().top;
      const fraction = Math.min(1, Math.max(0, -top / height));
      art.style.transform = `translate3d(0, ${fraction * 95}px, 0) rotate(${fraction * 5}deg)`;
    }
    if (story) {
      const rect = story.getBoundingClientRect();
      const fraction = Math.max(0, Math.min(1, (104 - rect.top) / Math.max(1, rect.height - height)));
      const step = Math.min(2, Math.floor(fraction * 3));
      const drift = reduced ? 0 : fraction - 0.5;
      root.style.setProperty("--story-back-drift", `${drift * 58}px`);
      root.style.setProperty("--story-mid-drift", `${drift * 22}px`);
      root.style.setProperty("--story-front-drift", `${drift * -36}px`);
      root.dataset.storyStep = String(step);
      chapters.forEach((chapter, index) => chapter.classList.toggle("is-current", index === step));
      if (progress) progress.style.transform = `scaleX(${fraction})`;
    }
    let closest = 0;
    let distance = Infinity;
    sections.forEach((section, index) => {
      const rect = section.getBoundingClientRect();
      const next = Math.abs(rect.top + Math.min(rect.height, height) / 2 - height / 2);
      if (next < distance) { distance = next; closest = Number(section.dataset.scene ?? index); }
    });
    root.dataset.storyScene = String(closest);
    document.querySelectorAll("[data-scene-count]").forEach((counter) => { counter.textContent = String(closest + 1).padStart(2, "0"); });
  }

  function schedule() {
    if (!frame && !document.hidden) frame = window.requestAnimationFrame(update);
  }

  // Only hide reveal targets when the observer is installed successfully.
  if ("IntersectionObserver" in window) {
    observer = new window.IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting && entry.boundingClientRect.bottom >= 0) return;
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.08 });
    document.querySelectorAll("[data-reveal]").forEach((element) => observer.observe(element));
    root.classList.add("motion-enabled");
  }

  window.PitchroomScene = {
    setPhase(phase) { root.dataset.voicePhase = phase || "ready"; },
    setAudioLevel(level) { root.style.setProperty("--voice-level", Math.max(0, Math.min(.12, Number(level) || 0))); },
    setGrounded(value) { root.dataset.answerGrounded = String(Boolean(value)); },
  };
  window.PitchroomMotion = { ready: true, reducedMotion: media.matches };
  media.addEventListener("change", () => {
    window.PitchroomMotion.reducedMotion = media.matches;
    syncPreference();
  });
  toggle?.addEventListener("click", () => { paused = !paused; syncPreference(); });
  if (toggle) toggle.hidden = false;
  window.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("resize", schedule, { passive: true });
  document.addEventListener("visibilitychange", () => {
    root.dataset.motionHidden = String(document.hidden);
    if (!document.hidden) schedule();
  });
  syncPreference();
})();
