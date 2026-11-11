// Shared helpers for the browser suites.
//
// Two layers, matching production: the *host* page (a Playwright `Page`) owns
// the address bar, localStorage and the iframe height, exactly like the real
// index.html, because it loads the same host_bridge.js; the *component* lives
// in a null-origin srcdoc iframe inside it, and is reached as a `Frame`.
//
//   const h = await openFixture(page, "good");
//   await expect(h.comp.locator(".mmd-badge")).toHaveText("Ready");
//
// `openApp()` is the same shape against the real Stlite boot (opt-in with
// MMD_LIVE=1) so contract tests can run either way.
import { expect, type Frame, type Locator, type Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

export const GENERATED = path.join(__dirname, '.generated');
export const MANIFEST: {
  sources: Record<string, string>;
  schemeLabels: Record<string, string>;
  order: string[];
  /** The source text and resolved payload baked into each generated page. */
  baked: Record<string, { source: string; appearance: any; chrome: any }>;
  payloads: Record<string, any>;
  catalog: { plain: { name: string; type: string; source: string }[]; stress: string | null; rows: Record<string, string>[] };
} = JSON.parse(fs.readFileSync(path.join(GENERATED, 'manifest.json'), 'utf8'));

const MERMAID_DELAY = process.env.MMD_MERMAID_DELAY_MS;
const MERMAID_FAIL = process.env.MMD_MERMAID_FAIL === '1';

/** One fixture under test: the host page and the component frame inside it. */
export type Harness = {
  page: Page;
  comp: Frame;
  source: string;
  payload: Record<string, unknown>;
};

/** The Stlite app frame (the Streamlit script runs inside it). */
export function appFrame(page: Page): Frame | undefined {
  return page.frames().find((frame) => frame !== page.mainFrame() && frame.url() !== 'about:srcdoc');
}

/** The preview component: a null-origin srcdoc frame, at any nesting depth. */
export function previewFrame(page: Page): Frame | undefined {
  return page.frames().find((frame) => frame.url() === 'about:srcdoc');
}

async function componentFrame(page: Page): Promise<Frame> {
  await page.waitForFunction(() => !!(window as any).__mmdFrame, undefined, { timeout: 15000 });
  const deadline = Date.now() + 15000;
  for (;;) {
    const frame = page.frames().find((candidate) => candidate.url() === 'about:srcdoc');
    if (frame) return frame;
    if (Date.now() > deadline) throw new Error('the component iframe never appeared');
    await page.waitForTimeout(50);
  }
}

/**
 * Load a fixture page. `payloadPatch` overrides parts of the resolved-appearance
 * payload before it is written into the component, which is how the appearance
 * matrix is driven. `mermaidUrlOverride` points the component at the local
 * stub so tests can control mermaid's timing and failures.
 */
export async function openFixture(
  page: Page,
  caseName: string,
  options: { payloadPatch?: Record<string, unknown>; mermaidUrlOverride?: boolean; fragment?: string; blockStorage?: boolean } = {},
): Promise<Harness> {
  if (options.blockStorage) {
    // Simulate private mode / a store that refuses writes: the app must stay usable.
    await page.addInitScript(() => {
      Object.defineProperty(window, 'localStorage', {
        configurable: true,
        get() {
          throw new DOMException('denied', 'SecurityError');
        },
      });
    });
  }
  initCapture(page);
  let url = '/tests/.generated/runner.html?case=' + encodeURIComponent(caseName);
  if (options.mermaidUrlOverride) {
    url += '&mermaidUrl=' + encodeURIComponent('/tests/.generated/mermaid-stub.mjs');
  }
  if (options.payloadPatch) {
    url += '&patch=' + encodeURIComponent(JSON.stringify(options.payloadPatch));
  }
  if (MERMAID_DELAY) url += '&delayMs=' + encodeURIComponent(MERMAID_DELAY);
  if (MERMAID_FAIL) url += '&fail=1';
  if (options.fragment) url += options.fragment;
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  await page.evaluate((variants) => {
    (window as any).__mmdVariants = variants;
  }, MANIFEST.payloads);
  const fixture = await openFrame(page, caseName);
  active = fixture;
  if (process.env.MMD_DEBUG === '1') {
    await page.screenshot({ path: `test-results/debug-host-${caseName}.png`, fullPage: true });
  }
  return fixture;
}

export async function openFrame(page: Page, caseName: string): Promise<Harness> {
  const comp = await componentFrame(page);
  await comp.waitForLoadState('domcontentloaded');
  await expect(comp.locator('#mmd-payload')).toHaveCount(1, { timeout: 15000 });
  return {
    page,
    comp,
    source: (MANIFEST.baked[caseName] || {}).source ?? '',
    payload: (MANIFEST.baked[caseName] || {}).appearance ?? {},
  };
}

// ---------------------------------------------------------------- host side
/**
 * Messages the host actually received. The status envelope carries the whole
 * SVG, so only the fields tests reason about are copied out of the browser --
 * shuttling 20 KB of markup per poll would dominate the suite.
 */
export async function hostMessages(page: Page, type: string): Promise<any[]> {
  // The runner already trimmed the markup, so this is a straight copy.
  return page.evaluate((wanted) => ((window as any).__mmdMessages || []).filter((msg: any) => msg.type === wanted), type);
}

export async function hostStateHistory(page: Page): Promise<string[]> {
  const messages = await hostMessages(page, 'mmd-status');
  return messages.map((message: any) => (message.payload || {}).state).filter((state: unknown) => typeof state === 'string');
}

export async function hostLastStatus(page: Page): Promise<any> {
  const messages = await hostMessages(page, 'mmd-status');
  const last = messages.filter((message: any) => message.payload).pop();
  return last ? last.payload : null;
}

export async function hostHeightMessages(page: Page): Promise<any[]> {
  return hostMessages(page, 'mmd-height');
}

/** What the host would hand the app before its first render. */
export function hostBoot(page: Page): Promise<any> {
  return page.evaluate(() => (window as any).__mermaidGuiBoot);
}

export function hostStored(page: Page, key: 'draft' | 'appearance'): Promise<any> {
  const name = key === 'draft' ? 'mermaidGui.draft' : 'mermaidGui.appearance';
  return page.evaluate((wanted) => {
    try {
      const raw = window.localStorage.getItem(wanted);
      return raw ? JSON.parse(raw) : null;
    } catch (denied) {
      return { denied: String((denied as Error).name) };
    }
  }, name);
}

export function hostAddress(page: Page): Promise<string> {
  return page.evaluate(() => window.location.href);
}

export function hostStorageLength(page: Page): Promise<number> {
  return page.evaluate(() => {
    try {
      return window.localStorage.length;
    } catch (denied) {
      return -1;
    }
  });
}

/** Host message counts, for coalescing rules that are about *how often* the page is asked. */
export async function hostMessageCounts(page: Page): Promise<Record<string, number>> {
  return page.evaluate(() => {
    const out: Record<string, number> = {};
    ((window as any).__mmdMessages || []).forEach((msg: any) => {
      out[msg.type] = (out[msg.type] || 0) + 1;
    });
    return out;
  });
}

// --------------------------------------------------------- component actions
/** The source text to render, driven through the component's own payload API. */
let requestSeq = 500;
/** Ids the harness invents are always newer than the one baked into a page. */
export function nextRequestId(): string {
  requestSeq += 1;
  return 'req-' + String(requestSeq).padStart(5, '0');
}

export async function send(comp: Frame, patch: Record<string, unknown>): Promise<string> {
  const payload = { requestId: nextRequestId(), ...patch };
  const requestId = await comp.evaluate((input) => {
    const node = document.querySelector('#mmd-payload');
    if (!node) return '';
    const payload = JSON.parse(node.textContent || '{}');
    Object.assign(payload, input);
    (window as any).__mermaidGuiRender__.handle(payload as any);
    return String(payload.requestId || '');
  }, payload);
  expect(requestId, 'component page must carry a payload node').not.toBe('');
  return requestId;
}

// ------------------------------------------------------------------- queries
export function badge(target: Frame | Page, state: string): Locator {
  return scope(target).locator(`.mmd-badge.mmd-badge--${state}`);
}

/** Story suites pass the `Page`; fixture mode resolves it to the component frame. */
export function scope(target: Frame | Page): Frame {
  // A Page exposes `frames()`; a Frame does not. Duck-typed because Playwright
  // exports Page only as a type.
  if (typeof (target as Page).frames === 'function') return subject(target as Page);
  return target as Frame;
}

export async function currentState(target: Frame | Page): Promise<string> {
  const comp = scope(target);
  // The badge carries the state in its modifier class, which is also what the
  // user reads, so this is the honest selector.
  return comp.evaluate(() => {
    const node = document.querySelector('.mmd-badge');
    if (!node) return 'missing';
    const match = Array.from(node.classList).find((name) => name.indexOf('mmd-badge--') === 0);
    return match ? match.slice('mmd-badge--'.length) : 'unknown';
  });
}

export async function waitTerminal(target: Frame | Page, state?: string): Promise<void> {
  const comp = scope(target);
  const timeout = (process.env.MMD_MERMAID_DELAY_MS ? Number(process.env.MMD_MERMAID_DELAY_MS) : 0) + 25000;
  const wanted = state ?? null;
  await expect
    .poll(
      async () => {
        const current = await currentState(comp);
        return wanted === null ? current !== 'rendering' && current !== 'missing' : current === wanted;
      },
      { timeout, message: wanted ? `waiting for state ${wanted}` : 'waiting for a terminal state' },
    )
    .toBe(true);
}

export async function waitState(target: Frame | Page, state: string): Promise<void> {
  const comp = scope(target);
  await expect(badge(comp, state), `state should reach ${state}`).toBeVisible({
    timeout: (process.env.MMD_MERMAID_DELAY_MS ? Number(process.env.MMD_MERMAID_DELAY_MS) : 0) + 25000,
  });
}

export function errorText(comp: Frame): Promise<string> {
  return comp.evaluate(() => {
    const status = document.querySelector('.mmd-status');
    return status ? status.textContent || '' : '';
  });
}

export function svg(target: Frame | Page): Locator {
  return scope(target).locator('.mmd-canvas svg');
}

/**
 * Mermaid always emits one empty <text> element, so "the first text node" is
 * meaningless -- filter to labels that actually contain characters.
 */
export function svgLabels(target: Frame | Page): Locator {
  return svg(target).locator('text').filter({ hasText: /\S/ });
}

/** The label text of the rendered picture, exactly as the browser sees it. */
export async function labelStrings(target: Frame | Page): Promise<string[]> {
  const comp = scope(target);
  return svgLabels(comp).evaluateAll((nodes) => nodes.map((node) => (node.textContent || '').trim()));
}

/** Deprecated alias kept so older spec text still reads. */
export async function labelText(comp: Frame): Promise<string> {
  return (await labelStrings(comp)).join(' ');
}

export function errorPanel(target: Frame | Page): Locator {
  return scope(target).locator('.mmd-panel--error:not(.mmd-hidden)');
}

export function busyPanel(target: Frame | Page): Locator {
  return scope(target).locator('.mmd-panel--busy:not(.mmd-hidden)');
}

/** The clamped/frozen notice area (`.mmd-panel--hint` doubles as a notice). */
export function noticeLines(target: Frame | Page): Locator {
  return scope(target).locator('.mmd-panel--hint:not(.mmd-hidden) .mmd-hint-line');
}

export function noticePanel(target: Frame | Page): Locator {
  return scope(target).locator('.mmd-panel--hint:not(.mmd-hidden)');
}

/** The neutral "nothing to preview yet" slot (contract: empty != invalid). */
export function emptyPanelSlot(target: Frame | Page): Locator {
  return scope(target).locator('.mmd-panel--busy:not(.mmd-hidden)');
}

export function hintPanel(target: Frame | Page): Locator {
  return scope(target).locator('.mmd-panel--hint:not(.mmd-hidden)');
}

export function badgeAt(target: Frame | Page, state: string): Locator {
  return scope(target).locator(`.mmd-badge.mmd-badge--${state}`);
}

export function originChip(target: Frame | Page, origin = 'frontmatter'): Locator {
  return scope(target).locator(`.mmd-chip[data-origin="${origin}"]`);
}

export function toolbar(target: Frame | Page): Locator {
  return scope(target).locator('.mmd-toolbar:not(.mmd-hidden)');
}

export function toolbarButton(target: Frame | Page, label: string | RegExp): Locator {
  return scope(target).locator('.mmd-toolbar').getByRole('button', { name: label });
}

export function zoomControl(comp: Frame): Locator {
  return comp.locator('.mmd-zoom');
}

export function zoomLabel(comp: Frame): Locator {
  return comp.locator('.mmd-zoom-label');
}

/** The picture the user is actually looking at while a rerender is in flight. */
export function visibleSvg(target: Frame | Page): Locator {
  return scope(target).locator('.mmd-render-host:not(.mmd-hidden) svg');
}

export async function lastGoodVisible(comp: Frame): Promise<boolean> {
  return comp.locator('.mmd-render-host[data-last-good]:not(.mmd-hidden) svg').isVisible().catch(() => false);
}

/** Font size in px of the first real label. */
export function textFontPx(target: Frame | Page): Promise<number> {
  const comp = scope(target);
  return svgLabels(comp)
    .first()
    .evaluate((node) => Number.parseFloat(getComputedStyle(node).fontSize || '0'));
}

/** The family the browser actually resolved for labels. */
export function textFontFamily(comp: Frame): Promise<string> {
  return svgLabels(comp)
    .first()
    .evaluate((node) => getComputedStyle(node).fontFamily || '');
}

export function colorAttrs(comp: Frame, selector = '.mmd-canvas'): Promise<{ nodes: number; fill: string[]; stroke: string[] }> {
  return comp.evaluate((sel) => {
    const host = document.querySelector(sel);
    if (!host) return { nodes: 0, fill: [], stroke: [] };
    const nodes = Array.from(host.querySelectorAll('rect, path, circle, polygon, ellipse, text')).slice(0, 300);
    const fills: string[] = [];
    const strokes: string[] = [];
    nodes.forEach((node) => {
      const view = getComputedStyle(node as Element);
      fills.push(view.fill);
      strokes.push(view.stroke);
    });
    return { nodes: nodes.length, fill: fills.slice(0, 24), stroke: strokes.slice(0, 24) };
  }, selector);
}

/** Average stroke width of the connector paths, used by the emphasis knob. */
export function strokeWidths(comp: Frame): Promise<number[]> {
  return comp.evaluate(() => {
    const host = document.querySelector('.mmd-canvas');
    if (!host) return [];
    return Array.from(host.querySelectorAll('path, line'))
      .map((node) => Number.parseFloat(getComputedStyle(node as Element).strokeWidth || '0'))
      .filter((value) => value > 0);
  });
}

/**
 * Labels whose drawn box falls outside the picture's own bounding box, i.e.
 * text the user would see cut off. Measured in screen pixels after transforms.
 */
export function clippedLabels(comp: Frame): Promise<number> {
  return comp.evaluate(() => {
    const host = document.querySelector('.mmd-canvas');
    if (!host) return 0;
    const picture = host.querySelector('svg');
    if (!picture) return 0;
    const box = picture.getBoundingClientRect();
    let clipped = 0;
    Array.from(picture.querySelectorAll('text')).forEach((node) => {
      const text = (node.textContent || '').trim();
      if (!text) return;
      const transform = (node as SVGTextElement).getScreenCTM();
      if (!transform) return;
      let rect: DOMRect;
      try {
        rect = (node as SVGTextElement).getBBox();
      } catch {
        return;
      }
      const left = new DOMPoint(rect.x, rect.y).matrixTransform(transform);
      const right = new DOMPoint(rect.x + rect.width, rect.y + rect.height).matrixTransform(transform);
      if (left.x < box.left - 2 || right.x > box.right + 2 || left.y < box.top - 2 || right.y > box.bottom + 2) {
        clipped += 1;
      }
    });
    return clipped;
  });
}

/** Label width vs the width of the shape it sits in, for truncation checks. */
export function labelBoxes(comp: Frame): Promise<{ text: string; width: number }[]> {
  return comp.evaluate(() => {
    const picture = document.querySelector('.mmd-canvas svg');
    if (!picture) return [];
    const out: { text: string; width: number }[] = [];
    Array.from(picture.querySelectorAll('text')).forEach((node) => {
      const text = (node.textContent || '').trim();
      if (!text) return;
      try {
        out.push({ text, width: Math.round((node as SVGTextElement).getBBox().width) });
      } catch {
        /* a label the browser cannot measure is not evidence either way */
      }
    });
    return out;
  });
}

export async function svgMarkup(comp: Frame): Promise<string> {
  const node = comp.locator('.mmd-canvas svg');
  return node.evaluate((element) => element.outerHTML);
}

/**
 * Wrap `mermaid.render()` so a test can prove the engine was or was not asked
 * to draw. The instance lives in the module's closure, so the patch is applied
 * to the object itself through the exported loader.
 */
export async function armRenderSpy(comp: Frame): Promise<void> {
  await comp.evaluate(async () => {
    const api = (window as any).__mermaidGuiRender__;
    const instance = await api.loadMermaid();
    if (!(window as any).__mmdSpy) {
      (window as any).__mmdSpy = { calls: 0 };
      const original = instance.render.bind(instance);
      instance.render = function (this: unknown, ...args: unknown[]) {
        (window as any).__mmdSpy.calls += 1;
        return (original as (...a: unknown[]) => unknown)(...args);
      };
    }
  });
}

export async function renderSpyCalls(comp: Frame): Promise<number> {
  return comp.evaluate(() => ((window as any).__mmdSpy || { calls: -1 }).calls);
}

// ------------------------------------------------------------------ console
type Capture = { text: string; location: string };
type Failure = { type: string; message: string; location: string };

function captured(page: Page) {
  return (page as Page & { __mmdCaptured?: { console: Capture[]; failures: Failure[] } }).__mmdCaptured;
}

function initCapture(page: Page): void {
  if (captured(page)) return;
  const store: { console: Capture[]; failures: Failure[] } = { console: [], failures: [] };
  Object.defineProperty(page, '__mmdCaptured', { value: store, configurable: true });
  page.on('console', (message) => {
    if (message.type() !== 'error' && message.type() !== 'warning') return;
    const location = message.location() || {};
    store.console.push({ text: message.text(), location: `${location.url || ''}:${location.lineNumber ?? 0}` });
  });
  page.on('pageerror', (error) => {
    const stack = String(error.stack || '');
    const match = stack.match(/(?:mermaid|cdn|\.mjs|\.js)[^\s'"]*:\d+/);
    store.failures.push({ type: 'error', message: error.message, location: match ? match[0] : '(unknown source)' });
  });
}

export function consoleProblems(page: Page): Capture[] {
  return captured(page)?.console ?? [];
}

export function pageErrors(page: Page): Failure[] {
  return captured(page)?.failures ?? [];
}

export function expectNoErrors(target: Page | Failure[] | Capture[], maybeProblems?: Capture[]): void {
  // Two call shapes are used by the suites: expectNoErrors(page) and the older
  // expectNoErrors(await pageErrors(page), await consoleProblems(page)).
  const isArray = Array.isArray(target);
  const page: Page | null = isArray ? active?.page ?? null : (target as Page);
  if (page) initCapture(page);
  // Playwright's dev server (python http.server) has no favicon, and the console
  // line does not name it -- only the location does -- so both are checked.
  const noise = /favicon|net::ERR_(FILE_NOT_FOUND|FAILED)/i;
  const noisy = (text: string, location: string) => noise.test(text) || noise.test(location);
  const failures = (isArray ? (target as Failure[]) : pageErrors(page as Page)).filter(
    (item) => !noisy((item as Failure).message ?? '', (item as Failure).location ?? ''),
  );
  const problems = (isArray ? (maybeProblems ?? []) : consoleProblems(page as Page)).filter(
    (item) => !noisy(item.text, item.location),
  );
  const report = [
    ...failures.map((item) => `page error: ${item.message} (${item.location})`),
    ...problems.map((item) => `${item.text} (${item.location})`),
  ];
  if (report.length) throw new Error('unexpected browser errors:\n  ' + report.join('\n  '));
}


// ------------------------------------------------- widget-shaped compatibility
//
// The story suites are written the way a user works: set the text, turn a knob,
// look at the picture. Under MMD_LIVE those words drive real Streamlit widgets
// in the sidebar. Without a Pyodide boot they drive the *same* resolved payloads,
// produced by tests/build_fixture.py through appearance.resolve(), and handed to
// the shipped component -- so a knob assertion can never disagree with Python.
let active: Harness | null = null;

/**
 * Two ways to drive the component:
 *
 *  - **fixture mode (default)**: the shipped component document with a canned
 *    payload, built by `tests/build_fixture.py`. Fast, no CDN, no Pyodide boot.
 *  - **live mode (`MMD_APP=live`)**: the deployed shape -- index.html, Stlite, the
 *    real Streamlit sidebar and the srcdoc component iframe.
 *
 * `tests/live-app.spec.ts` is gated on `MMD_LIVE=1`, so a plain `playwright test`
 * never boots Pyodide by accident.
 */
const LIVE_APP = process.env.MMD_APP === 'live';

const KNOB_VARIANTS: Record<string, Record<string, string>> = {
  'Text size': { smallest: 'text-smallest', small: 'text-small', medium: 'text-medium', large: 'text-large', largest: 'text-largest', left: 'text-smallest', right: 'text-largest' },
  Spacing: { compact: 'density-compact', normal: 'density-normal', roomy: 'density-roomy', open: 'density-open', left: 'density-compact', right: 'density-open' },
  'Line emphasis': { off: 'emphasis-off', soft: 'emphasis-soft', strong: 'emphasis-strong', left: 'emphasis-off', right: 'emphasis-strong' },
  Font: { sans: 'font-sans', serif: 'font-serif', mono: 'font-mono', left: 'font-sans', right: 'font-mono' },
  'Colour scheme': {
    default: 'scheme-default', base: 'scheme-base', neo: 'scheme-neo', dark: 'scheme-dark', neutral: 'scheme-neutral',
    forest: 'scheme-forest', redux: 'scheme-redux', 'redux-color': 'scheme-redux-color', 'neo-dark': 'scheme-neo-dark',
    'redux-dark': 'scheme-redux-dark-color',
    Default: 'scheme-default', Neo: 'scheme-neo', Dark: 'scheme-dark', Neutral: 'scheme-neutral', Forest: 'scheme-forest',
    Redux: 'scheme-redux', 'Redux Colour': 'scheme-redux-color', 'Neo Dark': 'scheme-neo-dark', 'Redux Dark': 'scheme-redux-dark-color',
    left: 'scheme-default', right: 'scheme-redux-dark-color',
  },
  'Base colours': { light: 'base-light', dark: 'base-dark', left: 'base-light', right: 'base-dark' },
  'PNG scale': { screen: 'export-screen', high: 'export-high', print: 'export-print', left: 'export-screen', right: 'export-print' },
  'PNG background': { diagram: 'background-transparent', white: 'background-white', transparent: 'background-transparent', left: 'background-diagram', right: 'background-transparent' },
};

function variant(_prefix: string, knob: string, value: string): Record<string, unknown> {
  const table = KNOB_VARIANTS[knob];
  if (!table) throw new Error('no knob named ' + knob);
  const key = table[String(value)] ?? table[String(value).toLowerCase()];
  const payload = key ? MANIFEST.payloads[key] : undefined;
  if (!payload) throw new Error(`no fixture payload for ${knob}=${value} (looked for ${key})`);
  return payload;
}

/** Open a fixture page (or the real Stlite app under MMD_LIVE) as the subject. */
export async function openApp(page: Page, caseName = 'good'): Promise<Harness> {
  if (LIVE_APP) return openStlite(page, caseName);
  active = await openFixture(page, caseName);
  return active;
}

/** Story suites keep using `component(page)`; in fixture mode that is the frame. */
export function component(page: Page): Frame {
  return subject(page);
}

export function subject(page: Page): Frame {
  if (active && active.page === page) return active.comp;
  throw new Error('open the app or fixture before querying the component');
}

/** The text currently on stage, so a knob change never loses it. */
export function currentSource(): string {
  return active?.source ?? '';
}

export async function setSource(page: Page, text: string): Promise<void> {
  if (LIVE_APP) return setStliteSource(page, text);
  await send(subject(page), { source: text });
  if (active) active.source = text;
}

/** Live knob vocabulary: the order of each select_slider, rightward = larger. */
const SLIDER_ORDER: Record<string, string[]> = {
  'Text size': ['smallest', 'small', 'medium', 'large', 'largest'],
  Spacing: ['compact', 'normal', 'roomy', 'open'],
  'Line emphasis': ['off', 'soft', 'strong'],
};

/**
 * The scheme selectbox shows a friendly label, not the stored word -- and the
 * labels come from appearance.py through the manifest, so a rename can never
 * make this test pass by accident.
 */
export function optionLabelFor(knob: string, value: string): string {
  if (knob === 'Colour scheme') return MANIFEST.schemeLabels[value] ?? value;
  return value;
}

/** The caption Streamlit shows (and puts on the thumb) for each slider knob. */
const SLIDER_LABELS: Record<string, string> = {
  'Text size': 'Text size',
  Spacing: 'Spacing',
  'Line emphasis': 'Line emphasis',
};

const KNOB_LABELS: Record<string, string> = {
  'Colour scheme': 'Colour scheme',
  Font: 'Font',
  'PNG scale': 'PNG scale',
  'PNG background': 'PNG background',
};

export async function setKnob(page: Page, knob: string, value: string): Promise<void> {
  if (LIVE_APP) return setLiveKnob(page, knob, value);
  const payload = variant('', knob, value);
  await send(subject(page), {
    source: currentSource(),
    appearance: payload.appearance,
    chrome: payload.chrome,
  });
}

/**
 * The live path drives the real widget. A select_slider commits on the keyboard:
 * its tick labels are decoration, and Streamlit names the thumb with the widget's
 * caption ("Text size") while showing the value as its text.
 */
async function setLiveKnob(page: Page, knob: string, value: string): Promise<void> {
  const order = SLIDER_ORDER[knob];
  if (!order) return pickOption(page, KNOB_LABELS[knob] ?? knob, optionLabelFor(knob, value));
  const caption = SLIDER_LABELS[knob] ?? knob;
  const thumb = page.getByRole('slider', { name: caption });
  await expect(thumb, `no live slider captioned ${caption}`).toBeVisible({ timeout: 45_000 });
  const current = (await thumb.textContent() || '').trim();
  const from = order.indexOf(current);
  const to = order.indexOf(value);
  expect(to, `${value} is not one of ${order.join('/')}`).toBeGreaterThan(-1);
  if (from === to) return;
  await thumb.click();
  const key = to > from ? 'ArrowRight' : 'ArrowLeft';
  for (let i = 0; i < Math.abs(to - from); i += 1) await thumb.press(key);
}

/**
 * Streamlit replaces the component iframe on every rerun, so a held `Frame` goes
 * stale as soon as the script runs again. Poll with a freshly resolved frame
 * instead: `check` is asked against whatever component document is current.
 */
export async function pollLive(page: Page, check: (frame: Frame) => Promise<boolean>, options: { timeout?: number; message?: string } = {}): Promise<void> {
  const timeout = options.timeout ?? 120_000;
  const deadline = Date.now() + timeout;
  let last = 'no component frame yet';
  for (;;) {
    try {
      const frame = await liveComponentFrame(page);
      last = String(await check(frame));
      if (last === true) return;
    } catch (detached) {
      last = 'frame detached: ' + String((detached as Error).message).slice(0, 60);
    }
    if (Date.now() > deadline) throw new Error(options.message || 'live check never passed (' + last + ')');
    await page.waitForTimeout(500);
  }
}

/** The badge class of the current live component document. */
export function liveState(page: Page): Promise<string> {
  return liveComponentFrame(page).then((frame) => currentState(frame));
}

/** What a live slider currently reads. */

/** Story suites use `setSlider(page, 'Text size', 'right')` for the two ends. */
export async function setSlider(page: Node | Page, knob: string, end: string): Promise<void> {
  const order = SLIDER_ORDER[knob];
  const wanted = order && (end === 'left' || end === 'right')
    ? end === 'right'
      ? order[order.length - 1]
      : order[0]
    : end;
  return setKnob(page as Page, knob, wanted);
}

/** Every colour the browser resolves for the picture's own shapes. */
export function svgColors(page: Page): Promise<string[]> {
  return colorsOf(subject(page));
}

export function colorsOf(comp: Frame): Promise<string[]> {
  return comp.evaluate(() => {
    const host = document.querySelector('.mmd-canvas');
    if (!host) return [];
    const out: string[] = [];
    Array.from(host.querySelectorAll('rect, path, circle, polygon, ellipse, text, line'))
      .slice(0, 200)
      .forEach((node) => {
        const view = getComputedStyle(node as Element);
        if (view.fill && view.fill !== 'none') out.push(view.fill);
        if (view.stroke && view.stroke !== 'none') out.push(view.stroke);
      });
    return out;
  });
}

export function svgFontPx(page: Page): Promise<number> {
  return textFontPx(page);
}

export function consoleErrors(page: Page): Array<{ text: string; location: string }> {
  return consoleProblems(page);
}

/** The draft as the host page actually stored it. */
export function storedDraft(page: Page): Promise<string | null> {
  return page.evaluate(() => window.localStorage.getItem('mermaidGui.draft'));
}

export function storedAppearance(page: Page): Promise<string | null> {
  return page.evaluate(() => window.localStorage.getItem('mermaidGui.appearance'));
}

// ------------------------------------------------------------ live Stlite app
export type AppComponent = { page: Page; frame: Frame };

async function openStlite(page: Page, caseName = 'good'): Promise<Harness> {
  if (!captured(page)) initCapture(page);
  await page.goto('/index.html', { waitUntil: 'load', timeout: 120000 });
  // Stlite mounts Streamlit straight into index.html, so the sidebar widgets and
  // the editor are top-page DOM; the preview component is the single srcdoc iframe.
  await expect(page.locator('[data-testid="stApp"]').first(), 'Streamlit never started').toBeVisible({ timeout: 180000 });
  await expect(page.locator('textarea').first(), 'the editor never appeared').toBeVisible({ timeout: 180000 });
  const frame = await liveComponentFrame(page);
  const harness: Harness = {
    page,
    comp: frame,
    source: (MANIFEST.baked[caseName] || {}).source ?? '',
    payload: (MANIFEST.baked[caseName] || {}).appearance ?? {},
  };
  active = harness;
  return harness;
}

/** The preview component frame: the one srcdoc iframe inside the app page. */
export async function liveComponentFrame(page: Page): Promise<Frame> {
  const deadline = Date.now() + 180000;
  for (;;) {
    const frame = page.frames().find((candidate) => candidate.url() === 'about:srcdoc');
    if (frame) {
      try {
        await frame.waitForLoadState('domcontentloaded');
        await expect(frame.locator('#mmd-payload'), 'the preview component never mounted').toHaveCount(1, { timeout: 60000 });
        return frame;
      } catch {
        /* Streamlit replaces the component iframe on every rerun; keep looking. */
      }
    }
    if (Date.now() > deadline) throw new Error('the preview component frame never appeared');
    await page.waitForTimeout(400);
  }
}

export async function componentLive(page: Page): Promise<Frame> {
  return liveComponentFrame(page);
}

/** The Streamlit sidebar, which under Stlite lives in the top document. */
export function sidebar(page: Page): Locator {
  return page.locator('[data-testid="stSidebar"]');
}

async function setStliteSource(page: Page, text: string): Promise<void> {
  const editor = page.locator('textarea').first();
  await editor.fill(text);
  await editor.blur();
  if (active) active.source = text;
}

/**
 * Streamlit's selectbox is a BaseWeb combobox, not a <select>, so it is opened
 * and chosen the way a user does it.
 */
export async function pickOption(page: Page, caption: string, label: string): Promise<void> {
  const box = page.getByRole('combobox', { name: caption });
  await expect(box, `no live control captioned ${caption}`).toBeVisible({ timeout: 45_000 });
  await box.click();
  const option = page.getByRole('option', { name: label, exact: true }).first();
  await expect(option, `option ${label} never appeared for ${caption}`).toBeVisible({ timeout: 15_000 });
  await option.click();
  const shown = page.locator('[data-testid="stSelectbox"]', { hasText: caption }).first();
  await expect
    .poll(() => shown.innerText().catch(() => box.innerText()), { timeout: 20_000, message: `${caption} did not take ${label}` })
    .toContain(label);
}


/**
 * A live Streamlit `select_slider` commits on the keyboard: its tick labels are
 * decoration, so the thumb is the only honest handle. Streamlit gives it an
 * aria-label of the widget caption ("Text size") and shows the value as its text.
 */
/** Move the caret inside the app's own editor, as a user's arrow click would. */
export async function caretPosition(page: Page, start: number, end = start): Promise<void> {
  await page.locator('textarea').first().evaluate((node, range) => {
    const box = node as HTMLTextAreaElement;
    box.focus();
    box.setSelectionRange(range.start, range.end);
    box.dispatchEvent(new Event('keyup', { bubbles: true }));
  }, { start, end });
}

export async function stepSlider(page: Page, caption: string, steps: number): Promise<void> {
  const thumb = page.getByRole('slider', { name: caption });
  await expect(thumb, `no live slider captioned ${caption}`).toBeVisible({ timeout: 30_000 });
  await thumb.click();
  const key = steps >= 0 ? 'ArrowRight' : 'ArrowLeft';
  for (let i = 0; i < Math.abs(steps); i += 1) await thumb.press(key);
}

/** What a live slider currently reads. */
export function sliderValue(page: Page, caption: string): Promise<string> {
  return page.getByRole('slider', { name: caption }).textContent().then((text) => (text || '').trim());
}

