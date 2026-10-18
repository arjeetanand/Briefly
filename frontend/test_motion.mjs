import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { test } from "node:test";

const source = readFileSync(new URL("./static/motion.js", import.meta.url), "utf8");

function room(reduced = false) {
  const events = new Map();
  const frames = [];
  const node = (rect = {}) => ({
    dataset: {}, style: { setProperty(name, value) { this[name] = value; } }, hidden: true, textContent: "", attrs: {},
    classList: { add() {}, toggle() {} },
    getBoundingClientRect: () => ({ top: 0, height: 800, ...rect }),
    addEventListener: (name, handler) => events.set(`button:${name}`, handler),
    setAttribute(name, value) { this.attrs[name] = value; },
  });
  const root = node();
  const art = node();
  const toggle = node();
  const progress = node();
  const hero = node();
  const storyRect = { top: 0, height: 2100 };
  const story = node(storyRect);
  story.getBoundingClientRect = () => storyRect;
  const chapters = [node(), node(), node()];
  const media = { matches: reduced, addEventListener: (name, handler) => events.set(`media:${name}`, handler) };
  const single = { ".hero-section": hero, ".hero-art-layer": art, ".scroll-story": story, ".story-progress span": progress, "#motion-toggle": toggle };
  const document = {
    documentElement: root, hidden: false,
    querySelector: (selector) => single[selector] || null,
    querySelectorAll: (selector) => selector === ".story-chapter" ? chapters : [],
    addEventListener: (name, handler) => events.set(`document:${name}`, handler),
  };
  const window = {
    innerHeight: 900, innerWidth: 1440, matchMedia: () => media,
    addEventListener: (name, handler) => events.set(name, handler),
    requestAnimationFrame: (handler) => { frames.push(handler); return frames.length; },
    dispatchEvent() {},
  };
  runInNewContext(source, { document, window, requestAnimationFrame: window.requestAnimationFrame, CustomEvent: class {} });
  const flush = () => { while (frames.length) frames.shift()(); };
  flush();
  return { root, art, toggle, progress, media, events, storyRect, flush, window };
}

test("a visitor can pause and resume decorative motion", () => {
  const page = room();
  assert.equal(page.toggle.hidden, false);
  page.events.get("button:click")();
  assert.equal(page.root.dataset.motionPaused, "true");
  assert.equal(page.toggle.attrs["aria-pressed"], "true");
  page.events.get("button:click")();
  assert.equal(page.root.dataset.motionPaused, "false");
});

test("the system reduced-motion preference wins, including when it changes", () => {
  const page = room(true);
  assert.equal(page.root.dataset.motionPaused, "true");
  assert.equal(page.art.style.transform, "");
  page.media.matches = false;
  page.events.get("media:change")();
  assert.equal(page.root.dataset.motionPaused, "false");
});

test("the scroll story reaches the final chapter and clamps its progress", () => {
  const page = room();
  page.storyRect.top = -4000;
  page.events.get("scroll")();
  page.flush();
  assert.equal(page.root.dataset.storyStep, "2");
  assert.equal(page.progress.style.transform, "scaleX(1)");
});

test("scroll layers move at different rates and freeze when motion is paused", () => {
  const page = room();
  const back = page.root.style["--story-back-drift"];
  assert.notEqual(back, page.root.style["--story-mid-drift"]);
  assert.notEqual(page.root.style["--story-mid-drift"], page.root.style["--story-front-drift"]);
  page.storyRect.top = -500;
  page.events.get("scroll")();
  page.flush();
  assert.notEqual(page.root.style["--story-back-drift"], back);
  page.events.get("button:click")();
  page.flush();
  assert.equal(page.root.style["--story-back-drift"], "0px");
});
