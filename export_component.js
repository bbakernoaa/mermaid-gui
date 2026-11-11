// Export component: one entry point (`exportAs`) that produces SVG, PNG or a
// clipboard copy from the SVG the user is currently looking at.
//
// Split out of app.py's giant f-string (T040) without weakening any of the
// three fixes this repo already paid for:
//   * commit ce61056 / 02ae868  - `getSerializedSVG` keeps xmlns + xlink and
//     rewrites absolute `url(http://…#id)` marker references to `url(#id)`,
//     which is what stops a tainted canvas / broken arrowheads. `canvg` stays.
//   * commit ed4bb3e            - SVG labels (`htmlLabels: false`, frozen in
//     render_component.js) plus the widened inline whitelist below, so
//     hierarchy/emphasis colour survives the round trip.
//   * commits 02ae868 / 89bf9cc - `<<interface>>` never reaches the HTML parser
//     unescaped (handled on the Python side).

const SVG_NS = 'http://www.w3.org/2000/svg';
const XLINK_NS = 'http://www.w3.org/1999/xlink';

// Export scales are named, not numeric, so "screen"/"print" map onto a frozen
// table (appearance-contract A-9: PNG at `print` vs `screen` must differ by
// exactly the advertised ratio).
export const EXPORT_SCALES = { screen: 2, high: 3, print: 4 };
export const DEFAULT_EXPORT_SCALE = 'high';             // replaces the old hard-coded 3
export const EXPORT_BACKGROUNDS = ['diagram', 'white', 'transparent'];
export const DEFAULT_EXPORT_BACKGROUND = 'diagram';

/**
 * A browser cannot raster an arbitrarily large picture: a 2D canvas over the
 * implementation's edge or area limit silently yields an *empty* data URL, so the
 * download would be a 0-byte PNG and the notice would still say "Saved". Long
 * chain diagrams are legitimate here (the 50 000-character ceiling allows a
 * 1 155-node spine, whose viewBox measured 404 x 133 933), so the limit is checked
 * up front and reported in the same breath as the alternative that always works.
 * Generous but well inside every engine's documented canvas limits.
 */
export const RASTER_LIMITS = { maxSide: 16384, maxPixels: 134217728 };  // 16k px edge / 128 MP

// Inlining whitelist. Markers/fonts kept from app.py's original list; the
// additions are what make derived/emphasised colours survive (research R-2).
export const INLINE_PROPS = [
  'fill', 'fill-opacity', 'fill-rule', 'color',
  'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin', 'stroke-dasharray', 'stroke-opacity', 'stroke-miterlimit',
  'font-family', 'font-size', 'font-weight', 'font-style', 'font-variant', 'letter-spacing', 'word-spacing', 'text-decoration',
  'text-anchor', 'dominant-baseline', 'alignment-baseline', 'baseline-shift', 'writing-mode', 'direction', 'unicode-bidi',
  'opacity', 'visibility', 'display', 'clip-path', 'filter',
  'stop-color', 'stop-opacity',
  'marker-start', 'marker-end', 'marker-mid',
  // `mask` is deliberately absent above. Chromium reports a computed `mask: none` on
  // every SVG element here (mermaid emits no <mask> node at all in this
  // configuration: zero in the exported file), and canvg 4.0.1 mis-parses even that
  // no-op declaration -- this markup with `mask:` inlined painted 0 of 102 400
  // sampled pixels, and with it removed painted 11 975. A declaration whose value
  // equals the property's initial one cannot change what a browser draws, so
  // inlining it bought no fidelity and blanked every PNG export.
  'paint-order', 'shape-rendering', 'text-rendering', 'image-rendering',
];

export const EXPORT_KINDS = ['svg', 'png', 'copySvg', 'exportSvg', 'exportPng'];

const CANVG_URL = 'https://cdn.jsdelivr.net/npm/canvg@4.0.1/+esm';

let canvgPromise = null;
let lastEcho = null;

const DOC = typeof document !== 'undefined' ? document : null;

function loadCanvg(url) {
  if (!canvgPromise) {
    canvgPromise = import(url || CANVG_URL).then((mod) => mod.Canvg || (mod.default && mod.default.Canvg) || mod.default || mod);
  }
  return canvgPromise;
}

// Mirrors `messages.sanitize_filename` in Python (T043): strip path separators
// and control characters, collapse repeated dots, keep non-ASCII, empty ->
// 'untitled'. Both download paths use it so a name behaves the same for .mmd
// and for .svg/.png.
export function sanitizeFilename(name) {
  let text = String(name == null ? '' : name);
  text = text.replace(/[\u0000-\u001f\u007f]/g, '');   // control characters
  text = text.replace(/[\\/:*?"<>|]/g, '');              // path separators + shell-hostile
  text = text.replace(/\.{2,}/g, '.');                   // collapse dot runs
  text = text.replace(/^\.+/, '').replace(/\.+$/, '');   // no leading/trailing dots
  text = text.replace(/\s+/g, ' ').trim();
  if (!text) return 'untitled';
  if (text.length > 100) text = text.slice(0, 100).replace(/[\s.]+$/, '');
  return text || 'untitled';
}

export function exportFilename(name, kind, scaleName) {
  const base = sanitizeFilename(name);
  if (kind === 'png') {
    const suffix = scaleName && scaleName !== DEFAULT_EXPORT_SCALE ? '-' + scaleName : '';
    return base + suffix + '.png';
  }
  return base + '.svg';
}

export function resolveScale(scale) {
  if (typeof scale === 'number') return EXPORT_SCALES[String(scale)] || scale;
  return EXPORT_SCALES[String(scale)] || EXPORT_SCALES[DEFAULT_EXPORT_SCALE];
}

export function backgroundFill(background) {
  const value = String(background || DEFAULT_EXPORT_BACKGROUND);
  if (value === 'transparent') return null;             // paints no backdrop at all
  if (value === 'white') return '#ffffff';
  return null;                                          // 'diagram': whatever the SVG already has
}

// ---------------------------------------------------------------- serialize --

export function getSerializedSVG(sourceSvg, doc) {
  const document2 = doc || sourceSvg.ownerDocument || DOC;
  const clone = sourceSvg.cloneNode(true);

  // Absolute dimensions for consistency in tools like canvg (kept from app.py).
  const viewBox = sourceSvg.viewBox ? sourceSvg.viewBox.baseVal : null;
  const width = (viewBox && viewBox.width) || sourceSvg.clientWidth || 800;
  const height = (viewBox && viewBox.height) || sourceSvg.clientHeight || 600;

  clone.setAttribute('width', String(width));
  clone.setAttribute('height', String(height));
  clone.setAttribute('xml:space', 'preserve');
  clone.setAttribute('text-rendering', 'geometricPrecision');

  const computed = (el) => (sourceSvg.ownerView && sourceSvg.ownerView.getComputedStyle
    ? sourceSvg.ownerView.getComputedStyle(el)
    : window.getComputedStyle(el));

  // Journey keeps HTML labels no matter what `htmlLabels` says: mermaid 11 renders
  // its section and task boxes through <foreignObject>, and the frozen
  // `htmlLabels:false` (research R-2) has no effect on that diagram type -- verified
  // by re-initializing with `htmlLabels:false`, `journey.htmlLabels:false` and
  // `journey.useMaxWidth:false`, each of which still produced nine foreignObjects.
  // A standalone file cannot depend on a stylesheet, and a rasteriser that ignores
  // foreignObject would lose every journey label, so their text is carried over as
  // real <text>, styled from what the browser computed for the live element.
  function htmlLabelsToText() {
    const liveBoxes = Array.prototype.slice.call(sourceSvg.querySelectorAll('foreignObject'));
    const cloneBoxes = Array.prototype.slice.call(clone.querySelectorAll('foreignObject'));
    cloneBoxes.forEach((box, index) => {
      const live = liveBoxes[index];
      if (!live || !box.parentNode) return;
      const label = live.querySelector('.label, div') || live;
      const text = (live.textContent || '').replace(/\s+/g, ' ').trim();
      if (!text) {
        box.parentNode.removeChild(box);
        return;
      }
      const style = computed(label);
      const fontSize = parseFloat(style.fontSize || '') || 12;
      const boxWidth = parseFloat(box.getAttribute('width') || '') || 0;
      const boxHeight = parseFloat(box.getAttribute('height') || '') || fontSize * 1.5;
      const x = parseFloat(box.getAttribute('x') || '') || 0;
      const y = parseFloat(box.getAttribute('y') || '') || 0;
      const lines = wrapWords(text, boxWidth || 120, fontSize);
      const lineHeight = Math.round(fontSize * 1.2);
      const firstBaseline = y + boxHeight / 2 - ((lines.length - 1) * lineHeight) / 2 + fontSize * 0.35;
      const node = document2.createElementNS('http://www.w3.org/2000/svg', 'text');
      node.setAttribute('x', String(x + boxWidth / 2));
      node.setAttribute('text-anchor', 'middle');
      lines.forEach((line, lineIndex) => {
        const child = document2.createElementNS('http://www.w3.org/2000/svg', 'tspan');
        child.setAttribute('x', String(x + boxWidth / 2));
        child.setAttribute('y', String(Math.round(firstBaseline + lineIndex * lineHeight)));
        child.textContent = line;
        node.appendChild(child);
      });
      ['color', 'font-family', 'font-size', 'font-weight', 'font-style'].forEach((prop) => {
        const value = style.getPropertyValue(prop);
        if (value) node.style[prop === 'color' ? 'fill' : prop] = value;
      });
      box.parentNode.replaceChild(node, box);
    });
  }

  function wrapWords(text, maxWidth, fontSize) {
    // Mermaid wrapped this text inside a box of `maxWidth`; the same greedy pass at
    // an average glyph width keeps it on the same lines without measuring fonts.
    const perChar = Math.max(1, fontSize * 0.55);
    const limit = Math.max(1, Math.floor(maxWidth / perChar));
    const lines = [];
    let current = '';
    text.split(' ').forEach((word) => {
      if (current && (current.length + word.length + 1) > limit) {
        lines.push(current);
        current = word;
      } else {
        current = current ? current + ' ' + word : word;
      }
    });
    if (current) lines.push(current);
    return lines.length ? lines : [text];
  }

  function inlineStyles(source, target) {
    const style = computed(source);
    for (const prop of INLINE_PROPS) {
      const value = style.getPropertyValue(prop);
      if (!value) continue;
      if (prop.indexOf('marker') === 0 && value.indexOf('url(') !== -1) {
        const match = value.match(/url\(["']?.*?(#[^"')]+)["']?\)/);
        if (match) {
          target.style[prop] = 'url(' + match[1] + ')';
          continue;
        }
      }
      target.style[prop] = value;
    }
    // background-color -> fill for nodes that paint via CSS background
    const fill = style.getPropertyValue('fill');
    const bgColor = style.getPropertyValue('background-color');
    if ((!fill || fill === 'none' || fill === 'transparent' || fill === 'rgba(0, 0, 0, 0)') &&
        bgColor && bgColor !== 'rgba(0, 0, 0, 0)' && bgColor !== 'transparent') {
      target.style.fill = bgColor;
    }
  }

  const allSource = sourceSvg.querySelectorAll('*');
  const allClone = clone.querySelectorAll('*');
  for (let i = 0; i < allSource.length; i += 1) {
    inlineStyles(allSource[i], allClone[i]);
    const tagName = String(allSource[i].tagName || '').toLowerCase();
    if (tagName === 'text' || tagName === 'tspan') {
      allClone[i].setAttribute('xml:space', 'preserve');
    }
  }

  // Drop Mermaid's injected <style> blocks (they reference classes we have now
  // inlined) and re-add only the whitespace rule text needs.
  Array.prototype.slice.call(clone.querySelectorAll('style')).forEach((node) => node.remove());
  const styleElement = document2.createElementNS(SVG_NS, 'style');
  styleElement.textContent = 'text, tspan { white-space: pre; }';
  clone.prepend(styleElement);

  if (!clone.getAttribute('xmlns')) clone.setAttribute('xmlns', SVG_NS);
  if (!clone.getAttribute('xmlns:xlink')) clone.setAttribute('xmlns:xlink', XLINK_NS);

    // Must run after the style walk and before serialization.
  htmlLabelsToText();

const serializer = new XMLSerializer();
  let out = serializer.serializeToString(clone);

  // Any absolute url(...) that sneaked in during serialization must become a
  // fragment reference, or the PNG rasteriser taints the canvas (ce61056).
  out = out.replace(/url\(["']?https?:\/\/[^#^"^')]+(#[^"^')]+?)["']?\)/g, 'url($1)');

  if (!/^<svg[^>]+xmlns="http:\/\/www\.w3\.org\/2000\/svg"/.test(out)) {
    out = out.replace(/^<svg/, '<svg xmlns="' + SVG_NS + '"');
  }
  if (!/^<svg[^>]+xmlns:xlink="http:\/\/www\.w3\.org\/1999\/xlink"/.test(out)) {
    out = out.replace(/^<svg/, '<svg xmlns:xlink="' + XLINK_NS + '"');
  }
  return out;
}

function triggerDownload(href, filename) {
  const link = DOC.createElement('a');
  link.href = href;
  link.download = filename;
  link.rel = 'noopener';
  DOC.body.appendChild(link);
  link.click();
  DOC.body.removeChild(link);
}

export function downloadText(text, filename, mime) {
  const url = 'data:' + (mime || 'image/svg+xml') + ';charset=utf-8,' + encodeURIComponent(text);
  triggerDownload(url, filename);
  return filename;
}

async function rasterise(svgMarkup, scale, background, Canvg) {
  const container = DOC.createElement('div');
  container.style.position = 'absolute';
  container.style.left = '-10000px';
  container.innerHTML = svgMarkup;
  DOC.body.appendChild(container);
  const svg = container.querySelector('svg');
  // Mermaid emits width="100%" together with a viewBox, so the picture has no
  // numeric width to read. Number('100%') is NaN, and NaN silently became
  // "ignore the scale", which is why every scale setting produced the same PNG.
  // The viewBox is the picture's real size; a rendered box is the fallback.
  const intrinsic = intrinsicSize(svg);
  const width = intrinsic.width;
  const height = intrinsic.height;
  // canvg sizes the canvas from the *markup* it is handed, so the scale has to be
  // written into the root <svg> before it parses. Pre-setting canvas.width here was
  // silently overwritten, which is how every scale setting produced the same PNG.
  //
  // A-9 says `print` and `screen` must differ by the scale difference *exactly*.
  // Rounding each result separately breaks that promise as soon as the diagram's own
  // width is fractional -- on Linux font metrics a 252.x px viewBox gave 506 px at
  // screen and 1014 px at print, a 2.004 ratio, while the same file was exactly 2.0
  // on macOS. So the base size is rounded once and every scale multiplies that
  // integer: the ratio is 4/2 == 2.0 by construction, in any environment.
  const baseWidth = Math.max(1, Math.round(width));
  const baseHeight = Math.max(1, Math.round(height));
  const rasterWidth = baseWidth * scale;
  const rasterHeight = baseHeight * scale;
  const plan = rasterPlan(rasterWidth, rasterHeight, baseWidth, baseHeight, scale);
  if (!plan.ok) return plan;
  if (svg) {
    svg.setAttribute('width', String(rasterWidth));
    svg.setAttribute('height', String(rasterHeight));
  }
  const scaledMarkup = container.innerHTML;
  const canvas = DOC.createElement('canvas');
  canvas.width = rasterWidth;
  canvas.height = rasterHeight;
  const ctx = canvas.getContext('2d');
  const fill = backgroundFill(background);
  if (fill) {
    ctx.fillStyle = fill;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
  }
  try {
    const instance = await Canvg.from(ctx, scaledMarkup, { ignoreMouse: true, ignoreAnimation: true });
    await instance.render();
  } finally {
    DOC.body.removeChild(container);
  }
  // `ok` is set on both paths: exportAs treats a missing flag as "the raster could
  // not be drawn", and a silently-empty first version of this check produced a
  // canvas that never downloaded.
  return { ok: true, canvas: canvas, width: rasterWidth, height: rasterHeight, scale: scale };
}

/**
 * Whether a raster this size can actually be drawn, and what to tell the user if
 * it cannot. `feasible` is the highest advertised scale that fits, or 0 when the
 * picture is too big at any scale -- in which case SVG is the answer, because a
 * vector file carries the whole diagram at any size.
 */
export function rasterPlan(rasterWidth, rasterHeight, baseWidth, baseHeight, scale) {
  const longest = Math.max(rasterWidth, rasterHeight);
  const pixels = rasterWidth * rasterHeight;
  if (longest <= RASTER_LIMITS.maxSide && pixels <= RASTER_LIMITS.maxPixels) {
    return { ok: true };
  }
  const feasible = ['screen', 'high', 'print']
    .map((name) => EXPORT_SCALES[name])
    .filter((value) => Math.max(baseWidth, baseHeight) * value <= RASTER_LIMITS.maxSide
      && baseWidth * baseHeight * value * value <= RASTER_LIMITS.maxPixels)
    .sort((a, b) => a - b)
    .pop() || 0;
  const name = feasible ? Object.keys(EXPORT_SCALES).filter((key) => EXPORT_SCALES[key] === feasible)[0] : null;
  return {
    ok: false,
    reason: 'rasterTooLarge',
    requested: { width: rasterWidth, height: rasterHeight, scale: scale },
    feasibleScale: feasible,
    message: 'This diagram would need a ' + rasterWidth + ' x ' + rasterHeight
      + ' pixel image, which is larger than a browser can draw. '
      + (name ? 'Try the ' + name + ' scale instead.' : 'Use Export SVG: a vector file holds the whole diagram at any size.')
  };
}

function intrinsicSize(svg) {
  if (!svg) return { width: 800, height: 600 };
  const view = svg.viewBox && svg.viewBox.baseVal;
  if (view && view.width > 0 && view.height > 0) return { width: view.width, height: view.height };
  const numbers = String(svg.getAttribute('viewBox') || '').split(/[^0-9.]+/).filter(Boolean).map(Number);
  if (numbers.length >= 4 && numbers[2] > 0 && numbers[3] > 0) return { width: numbers[2], height: numbers[3] };
  const box = typeof svg.getBoundingClientRect === 'function' ? svg.getBoundingClientRect() : null;
  if (box && box.width > 0 && box.height > 0) return { width: box.width, height: box.height };
  const attrWidth = Number(svg.getAttribute('width'));
  const attrHeight = Number(svg.getAttribute('height'));
  return {
    width: attrWidth > 0 ? attrWidth : 800,
    height: attrHeight > 0 ? attrHeight : 600,
  };
}

// ----------------------------------------------------------------- entrypoint --

// Single export path (FR-028..032): every gesture goes through here, so the
// frozen settings, the inlining whitelist and the filename rule are applied
// exactly once (T042: "no bespoke export path may remain").
export async function exportAs(kind, options) {
  const opts = options || {};
  const svg = opts.svg || (opts.sourceSvg) || (DOC && DOC.querySelector('.mmd-render-host svg'));
  if (!svg) {
    return { ok: false, reason: 'noSvg', message: 'Nothing to export yet — the diagram has not rendered.' };
  }
  const render = globalThis.__mermaidGuiRender__;
  if (opts.expectedRequestId && render && render.stateSnapshot) {
    const snap = render.stateSnapshot();
    if (snap.newestTerminalId && String(snap.newestTerminalId) !== String(opts.expectedRequestId)) {
      return { ok: false, reason: 'stale', message: 'The diagram changed while you were exporting. Try again.' };
    }
  }
  const normalizedKind = String(kind || 'svg').replace(/^export/, '').toLowerCase();
  const scaleName = opts.scale && EXPORT_SCALES[opts.scale] != null ? opts.scale : DEFAULT_EXPORT_SCALE;
  const scale = resolveScale(opts.scale);
  const background = EXPORT_BACKGROUNDS.indexOf(opts.background) === -1 ? DEFAULT_EXPORT_BACKGROUND : opts.background;
  const filename = exportFilename(opts.name, normalizedKind === 'copy' ? 'svg' : normalizedKind, scaleName);
  const markup = getSerializedSVG(svg);

  if (normalizedKind === 'copy' || kind === 'copySvg') {
    return copyText(markup, filename);
  }
  if (normalizedKind === 'svg') {
    downloadText(markup, filename, 'image/svg+xml');
    lastEcho = { kind: 'svg', filename: filename, width: null, height: null };
    return Object.assign({ ok: true }, lastEcho);
  }
  if (normalizedKind === 'png') {
    const Canvg = await loadCanvg(opts.canvgUrl);
    const raster = await rasterise(markup, scale, background, Canvg);
    if (!raster.ok) return raster;
    const pngUrl = raster.canvas.toDataURL('image/png', 1.0);
    if (!pngUrl || pngUrl.length < 32) {
      // A canvas the engine refused, rather than one we predicted it would refuse.
      return {
        ok: false,
        reason: 'rasterFailed',
        message: 'The browser could not draw an image this size. Use Export SVG instead.',
      };
    }
    triggerDownload(pngUrl, filename);
    lastEcho = { kind: 'png', filename: filename, width: raster.width, height: raster.height, scale: scale };
    return Object.assign({ ok: true }, lastEcho);
  }
  return { ok: false, reason: 'unknownKind', message: 'Unknown export request: ' + kind };
}

async function copyText(text, filename) {
  const clipboard = globalThis.navigator && globalThis.navigator.clipboard;
  if (clipboard && clipboard.writeText) {
    try {
      await clipboard.writeText(text);
      lastEcho = { kind: 'copy', filename: filename };
      return { ok: true, kind: 'copy', filename: filename, copied: true };
    } catch (err) {
      // refused (permissions / non-secure context): fall back to a download
    }
  }
  downloadText(text, filename, 'image/svg+xml');
  lastEcho = { kind: 'copy', filename: filename };
  return { ok: true, kind: 'copy', filename: filename, copied: false, fallback: 'download', message: 'Copy is not available in this browser, so the SVG was downloaded instead.' };
}

export function lastExportEcho() {
  return lastEcho;
}

export function __resetForTests__() {
  lastEcho = null;
  canvgPromise = null;
}

export const EXPORT_CONTRACT = {
  scales: EXPORT_SCALES,
  defaultScale: DEFAULT_EXPORT_SCALE,
  backgrounds: EXPORT_BACKGROUNDS,
  defaultBackground: DEFAULT_EXPORT_BACKGROUND,
  inlineProps: INLINE_PROPS,
};

export function __selfRegister__() {
  globalThis.__mermaidGuiExport__ = {
    EXPORT_SCALES: EXPORT_SCALES,
    DEFAULT_EXPORT_SCALE: DEFAULT_EXPORT_SCALE,
    EXPORT_BACKGROUNDS: EXPORT_BACKGROUNDS,
    DEFAULT_EXPORT_BACKGROUND: DEFAULT_EXPORT_BACKGROUND,
    EXPORT_KINDS: EXPORT_KINDS,
    RASTER_LIMITS: RASTER_LIMITS,
    rasterPlan: rasterPlan,
    INLINE_PROPS: INLINE_PROPS,
    EXPORT_CONTRACT: EXPORT_CONTRACT,
    exportAs: exportAs,
    exportFilename: exportFilename,
    sanitizeFilename: sanitizeFilename,
    resolveScale: resolveScale,
    backgroundFill: backgroundFill,
    getSerializedSVG: getSerializedSVG,
    downloadText: downloadText,
    lastExportEcho: lastExportEcho,
    __resetForTests__: __resetForTests__,
  };
  return globalThis.__mermaidGuiExport__;
}
