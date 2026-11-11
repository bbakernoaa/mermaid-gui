// Render component: owns the preview state machine, the error panel, zoom and
// the preview -> export handoff.
//
// Why the component owns this: `st.components.v1.html` is a one-way
// (parent -> iframe) channel, so Python cannot see or react to render state
// (research R-4). Everything a user must see about a render therefore lives in
// this file, and Python only ever sends AppearanceKnobs / ResolvedAppearance +
// source.
//
// Authored as an ES module so tests and a standalone page can import it. app.py
// inlines the body into one self-contained document and calls the exported
// `handle(payload)` per command.

export const SCHEMA_VERSION = 1;
export const STATE_ENUM = ['rendering', 'rendered', 'invalid', 'empty'];
export const ERROR_KINDS = ['parseError', 'renderError', 'unsupportedType', 'inputTooLarge', 'bridgeVersion'];
export const COMMAND_ENUM = ['render', 'exportSvg', 'exportPng', 'copySvg', 'zoomIn', 'zoomOut', 'fit', 'reset', 'interfaceMode'];

export const MAX_SOURCE_CHARS = 50000;   // data-model §1 editorLimits.maxPasteChars
export const STALL_NOTICE_MS = 8000;      // FR-012 / SC-003 "still working" upgrade
export const ZOOM_STEPS = [0.5, 0.67, 1, 1.5, 2, 3, 4];
export const ZOOM_DEFAULT_INDEX = 2;

const MERMAID_URL = 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';

// Frozen settings — appearance-contract §6. `htmlLabels`/`useHtmlLabels: false`
// is the export-fidelity fix from commit ed4bb3e; `securityLevel: strict` and
// `suppressErrorRendering: true` come from SC-010 / research R-3. They are not
// knobs: nothing in ResolvedAppearance may turn them off.
export const FROZEN_SETTINGS = {
  startOnLoad: false,
  htmlLabels: false,
  securityLevel: 'strict',
  suppressErrorRendering: true,
  flowchart: { htmlLabels: false, useHtmlLabels: false },
  sequence: { useHtmlLabels: false, htmlLabels: false },
  gantt: { useHtmlLabels: false, htmlLabels: false },
};

// Plain-language rewrite table for the error classes users actually hit
// (T021). `ERROR_REWRITES` may embed the offending token; `%s` in the rendered
// text is substituted from the raw message by `rewriteError()`.
export const PLAIN_FOR = {
  parseError: 'The diagram text cannot be read.',
  renderError: 'Mermaid understood the text but could not draw it.',
  unsupportedType: 'This diagram type is not supported by this build.',
  inputTooLarge: 'The diagram is too large to preview live.',
  bridgeVersion: 'The preview component and the app do not match. Reload the page.',
};

export const ERROR_REWRITES = [
  // Jison reports the offending line/column as `Error: Parse error on line N`
  // plus a `<br>`-joined snippet whose caret sits under the bad token.
  { test: /parse error on line/i, text: 'Something here is not valid for a %type diagram.' },
  { test: /expecting .*got/i, text: 'This text is something Mermaid does not expect for a %type diagram.' },
  { test: /invalid (text|diagram type)/i, text: '%s.' },
  { test: /no statement|nothing to draw|cannot read properties/i, text: 'The text stops before there is anything to draw.' },
  { test: /duplicate|already defined/i, text: 'A name is used twice: %s.' },
  { test: /unsupported/i, text: 'Mermaid cannot draw this: %s.' },
];

export const TOO_LARGE_MESSAGE =
  'This diagram has %n characters, above the %max limit for live preview. Break it into smaller '
  + 'diagrams, or save the text as a .mmd file and open it in the Mermaid CLI.';

const DOC = typeof document !== 'undefined' ? document : null;

const state = {
  mermaid: null,
  mermaidPromise: null,
  doc: DOC,
  els: null,
  newestRequestId: null,   // newest request started
  newestTerminalId: null,  // newest terminal status published
  lastGood: null,          // { svg, source, diagramType, requestId, node }
  lastParsedSource: null,  // enables the "appearance-only changed" skip
  lastSourceOf: null,      // where each setting came from, for the status chips
  parsedOnce: null,
  zoomIndex: ZOOM_DEFAULT_INDEX,
  fitToView: false,
  interfaceMode: 'auto',
  stallTimer: null,
  storageNoticeShown: false,
  renderSeq: 0,
  diagramName: '',
};

// --------------------------------------------------------------- pure parts --

export function compareId(a, b) {
  const na = Number(String(a == null ? '' : a).replace(/\D/g, ''));
  const nb = Number(String(b == null ? '' : b).replace(/\D/g, ''));
  if (Number.isFinite(na) && Number.isFinite(nb) && String(a).replace(/\D/g, '') && String(b).replace(/\D/g, '')) {
    return na === nb ? 0 : (na > nb ? 1 : -1);
  }
  const sa = String(a == null ? '' : a);
  const sb = String(b == null ? '' : b);
  return sa === sb ? 0 : (sa > sb ? 1 : -1);
}

export function truncate(text, max) {
  const t = String(text == null ? '' : text);
  return t.length <= max ? t : t.slice(0, Math.max(1, max - 1)) + '\u2026';
}

// Jison puts the offending line in `Error: Parse error on line 3:` and, in the
// HTML-ish message, a caret line. `caretLine` extracts that so a failure whose
// message names no line still gets a 1-based line number (FR-014).
export function findCaretLine(rawMessage) {
  const text = String(rawMessage == null ? '' : rawMessage);
  const m = text.match(/line (\d+)/i);
  if (m) return Number(m[1]);
  const segments = text.split(/<br\s*\/?>/i);
  for (let i = 0; i < segments.length; i += 1) {
    if (/[-^]*\^[-^]*\s*$/.test(segments[i])) return i;
  }
  return null;
}

export function caretColumn(lineText, caretToken) {
  const raw = String(lineText == null ? '' : lineText);
  const token = String(caretToken == null ? '' : caretToken);
  if (!token) return null;
  const idx = raw.indexOf(token);
  return idx === -1 ? null : idx + 1;
}

export function extractSnippet(source, line, column) {
  const text = String(source == null ? '' : source);
  const lines = text.split(/\r?\n/);
  let index = Number(line) > 0 ? Number(line) - 1 : -1;
  let atBeginning = false;
  if (index < 0) {
    // Mermaid names no position: point at the first line that has text in it,
    // which is where a diagram type would have to be declared.
    index = lines.findIndex((entry) => entry.trim() !== '');
    if (index < 0) index = 0;
    atBeginning = index === 0;
  } else if (index >= lines.length) {
    // A position past the end (mermaid reports EOF one line too far in a
    // unterminated statement) belongs to the last line with content on it.
    for (let probeLine = lines.length - 1; probeLine >= 0; probeLine -= 1) {
      if (lines[probeLine].trim() !== '') { index = probeLine; break; }
    }
    if (index >= lines.length) index = lines.length - 1;
  }
  const raw = lines[index] == null ? '' : lines[index];
  const trimmed = raw.replace(/\s+$/, '');
  let caret = Number(column) > 0 ? Number(column) - 1 : Math.max(0, trimmed.length);
  if (!raw.trim()) caret = 0;
  caret = Math.max(0, Math.min(caret, Math.max(0, trimmed.length)));
  return {
    snippet: truncate(raw.trim(), 120),
    startLine: index + 1,
    endLine: index + 1,
    caret: caret,
    atBeginning: atBeginning,
  };
}

export function buildDetail(kind, line, snippetInfo) {
  // No line number is useful when the diagram type itself is the problem, or
  // when the text is simply too big to try.
  if (kind === 'inputTooLarge' || kind === 'unsupportedType') return '';
  if (line) return ' on line ' + line + '.';
  if (snippetInfo && snippetInfo.atBeginning) return ' at the very start of the text, before the diagram type is named.';
  return ' somewhere in the diagram text.';
}

export function stripJargon(text) {
  let out = String(text == null ? '' : text);
  out = out.replace(/\bJison\b/gi, 'the parser')
    .replace(/\bBNF\b/gi, 'the grammar')
    .replace(/\bEOF\b/g, 'the end of the text')
    .replace(/\btoken\b/gi, 'piece of text')
    .replace(/\bgot '[^']*'/g, 'what is written there')
    .replace(/\bnewline\b/gi, 'end of line')
    .replace(/\s{2,}/g, ' ')
    .replace(/\s+([.,;:!])/g, '$1');
  return out.trim();
}

export function rewriteError(rawMessage, kind, diagramType, fallback) {
  const raw = String(rawMessage == null ? '' : rawMessage);
  const hit = ERROR_REWRITES.find((entry) => entry.test.test(raw));
  const type = diagramType || 'diagram';
  let text;
  if (hit) {
    text = hit.text
      .replace(/%type/g, type)
      .replace(/%s/g, (raw.match(/Invalid [^:]*:\s*([^.]*)/i) || raw.match(/ unsupported (\S+)/i) || raw.match(/duplicate[^\n]*"([^"]*)"|'([^']*)'|(already defined)/i) || [])[1] || raw);
  } else {
    text = fallback || PLAIN_FOR[kind] || PLAIN_FOR.parseError;
  }
  // Mermaid's `Parse error on line N:` is replaced by the plain sentence + line
  // number, so the UI never shows raw parser vocabulary.
  text = text.replace(/^Error:\s*/i, '').replace(/parse error on line \d+:?\s*(on line \d+)?/i, '');
  return stripJargon(text);
}

// Turns anything thrown by parse/render into the RenderError of data-model §3:
// kind, plainMessage (always readable), rawMessage (details only), 1-based
// line/column and a <=120 char snippet. Never throws.
export function normalizeError(error, source, opts) {
  const options = opts || {};
  const rawText = String((error && (error.message || error.str)) || error || '');
  const explicit = options.rawMessage || rawText;
  let kind = options.assumedKind || 'parseError';
  if (options.tooLarge) kind = 'inputTooLarge';
  if (/unsupported diagram type|cannot find declaration|no diagram type detected/i.test(explicit)) kind = 'unsupportedType';
  if (options.unsupportedFirstWord) {
    kind = 'unsupportedType';
  }
  if (options.renderStage) kind = 'renderError';

  const lineFromMessage = (explicit.match(/line (\d+)/i) || [])[1];
  const columnFromMessage = (explicit.match(/column (\d+)/i) || [])[1];
  const position = (error && error.loc) || (error && error.hash && error.hash.loc) || {};
  let line = Number(lineFromMessage) > 0 ? Number(lineFromMessage)
    : Number(position.first_line || 0) || Number((error && error.hash && error.hash.line ? error.hash.line + 1 : 0))
    || Number(options.caretLine || findCaretLine(explicit) || 0) || null;
  let column = Number(columnFromMessage) > 0 ? Number(columnFromMessage) : Number(position.first_column || 0) || null;

  const caretToken = (explicit.match(/\^[-^]*\s*$/) || [])[0] ? (explicit.split(/<br\s*\/?>/i).pop() || '').trim() : '';
  if (!column && caretToken) column = caretColumn((String(source == null ? '' : source).split(/\r?\n/)[(line || 1) - 1]) || '', caretToken.replace(/\^/g, '').trim());

  const snippetInfo = kind === 'inputTooLarge'
    ? { snippet: '', startLine: null, endLine: null, caret: 0, atBeginning: false }
    : extractSnippet(source, line, column);
  if (kind !== 'inputTooLarge') line = snippetInfo.startLine || line;

  let sentence = rewriteError(explicit, kind, options.diagramType, PLAIN_FOR[kind]);
  if (options.unsupportedFirstWord) {
    sentence = 'The first word, "' + options.unsupportedFirstWord + '", is not a diagram type. '
      + 'Start with one of: ' + KNOWN_TYPE_WORDS.join(', ') + '.';
  }
  const detail = buildDetail(kind, line, snippetInfo);
  let plainMessage = sentence;
  if (!/\bline \d+\b/i.test(plainMessage) && kind !== 'inputTooLarge' && detail.trim()) {
    plainMessage = plainMessage.replace(/[.\s]+$/, '') + '. The problem is' + detail.replace(/\.+$/, '') + '.';
  }

  return {
    kind: kind,
    plainMessage: stripJargon(plainMessage),
    rawMessage: truncate(explicit, 600),
    line: (kind === 'inputTooLarge') ? null : line,
    column: kind === 'inputTooLarge' ? null : (column || null),
    snippet: snippetInfo.snippet,
  };
}

export function zoomIndex(current, delta) {
  const max = ZOOM_STEPS.length - 1;
  if (Number(delta) === 0) return ZOOM_DEFAULT_INDEX;
  const next = Number(current) + Number(delta);
  return Math.max(0, Math.min(max, next));
}

// The resolver's report and alias keys are ours, not mermaid's grammar, so they
// must never reach `initialize`; mermaid silently ignores unknown keys, which is
// exactly how a dead control hides itself.
const RESOLVER_ONLY = ['sourceOf', 'clamped', 'frozen', 'diagramType', 'family', 'frontmatterColorKeys', 'export', 'perDiagramConfig', 'diagram_config', 'mermaidTheme'];

export function configureOptions(appearance) {
  const src = appearance && typeof appearance === 'object' ? appearance : {};
  const options = {};
  Object.keys(src).forEach((key) => {
    if (RESOLVER_ONLY.indexOf(key) !== -1) return;
    options[key] = src[key];
  });
  // Two translations the resolver cannot do because they are about the engine:
  // `theme` is mermaid's spelling of the theme family, and each diagram family
 // reads its own spacing from a top-level key named after the family.
  if (src.mermaidTheme) options.theme = src.mermaidTheme;
  const perFamily = src.perDiagramConfig || src.diagram_config || {};
  Object.keys(perFamily).forEach((family) => {
    const value = perFamily[family];
    if (!value || typeof value !== 'object') return;
    options[family] = Object.assign({}, options[family] || {}, value);
  });
  // Frozen values win, per-family objects merge rather than replace.
  Object.keys(FROZEN_SETTINGS).forEach((key) => {
    const frozen = FROZEN_SETTINGS[key];
    if (frozen && typeof frozen === 'object') {
      options[key] = Object.assign({}, options[key] || {}, frozen);
    } else {
      options[key] = frozen;
    }
  });
  Object.keys(options).forEach((key) => {
    if (options[key] === null || options[key] === undefined) delete options[key];
  });
  return options;
}

export function loadMermaid(url) {
  if (state.mermaidPromise) return state.mermaidPromise;
  state.mermaidPromise = import(url || MERMAID_URL).then((mod) => {
    state.mermaid = mod.default || mod.mermaid || mod;
    return state.mermaid;
  });
  return state.mermaidPromise;
}

// --------------------------------------------------------------- the bridge --

// The page that owns the address bar, localStorage and the CDN-loaded app frame.
// Inside Stlite the component document sits in a srcdoc iframe, whose parent is
// the Streamlit frame -- which runs no code of ours and so cannot relay messages.
// ``window.top`` is always traversable across frames (only property *access* is
// restricted by origin), and posting to it is the documented host bridge.
function hostWindow() {
  const win = globalThis.window;
  if (!win) return null;
  if (win.top && win.top !== win) return win.top;
  if (win.parent && win.parent !== win) return win.parent;
  return null;
}

export function postStatus(status) {
  const payload = Object.assign({}, status);
  const stale = state.newestTerminalId && compareId(payload.requestId, state.newestTerminalId) < 0;
  if (payload.state !== 'rendering') {
    // Invariant: exactly one terminal status per requestId. `rendered` is a
    // terminal state too -- leaving it out meant newestTerminalId only ever
    // tracked failures, so an export could not tell a stale picture from a fresh
    // one (contract section 2, and section 5 of the export rules).
    if (!state.newestTerminalId || compareId(payload.requestId, state.newestTerminalId) >= 0) {
      state.newestTerminalId = payload.requestId;
    }
  }
  if (stale) return null;
  if (payload.clamped && !payload.clamped.length) delete payload.clamped;
  if (payload.state !== 'invalid') delete payload.error;
  if (payload.state !== 'rendered') delete payload.metrics;
  if (payload.showLastGood === false) delete payload.showLastGood;
  const statusHost = hostWindow();
  if (statusHost) {
    try {
      statusHost.postMessage({ type: 'mmd-status', payload: payload }, '*');
    } catch (err) { /* host not listening */ }
  }
  return payload;
}

export function startStallTimer(requestId, onStall) {
  stopStallTimer();
  state.stallTimer = setTimeout(() => {
    state.stallTimer = null;
    if (onStall) onStall(requestId);
  }, STALL_NOTICE_MS);
  return state.stallTimer;
}

export function stopStallTimer() {
  if (state.stallTimer) {
    clearTimeout(state.stallTimer);
    state.stallTimer = null;
  }
}

// The whole state machine for one request. Emits `rendering` before any async
// work, then exactly one terminal status for that requestId.
export function runCycle(input) {
  const requestId = String((input && input.requestId) || 'req-0');
  const source = String((input && input.source) || '');
  const appearance = (input && input.appearance) || {};
  const options = (input && (input.chrome || input.options)) || {};

  // A superseded request may not publish anything at all (contract §2 inv. 3).
  if (state.newestRequestId && compareId(requestId, state.newestRequestId) < 0) {
    return Promise.resolve(null);
  }
  state.newestRequestId = requestId;
  emit({ requestId: requestId, state: 'rendering', diagramType: options.selectedTypeId || null });
  startStallTimer(requestId, (id) => {
    emitStatusUI({ requestId: id, state: 'rendering', stalled: true });
  });

  return Promise.resolve()
    .then(() => {
      if (Number(input && input.schemaVersion) && Number(input.schemaVersion) !== SCHEMA_VERSION) {
        return terminal({
          requestId: requestId,
          state: 'invalid',
          diagramType: null,
          error: { kind: 'bridgeVersion', plainMessage: PLAIN_FOR.bridgeVersion, rawMessage: 'schemaVersion ' + input.schemaVersion, line: null, column: null, snippet: '' },
        });
      }
      if (source.length > MAX_SOURCE_CHARS) {
        return terminal({
          requestId: requestId,
          state: 'invalid',
          diagramType: null,
          error: {
            kind: 'inputTooLarge',
            plainMessage: TOO_LARGE_MESSAGE.replace('%n', String(source.length)).replace('%max', String(MAX_SOURCE_CHARS)),
            rawMessage: 'source length ' + source.length + ' > ' + MAX_SOURCE_CHARS,
            line: null, column: null, snippet: '',
          },
        });
      }
      if (/^\s*$/.test(source)) {
        return terminal({ requestId: requestId, state: 'empty', diagramType: null });
      }
      return loadMermaid().then((mermaid) => {
        const initConfig = configureOptions(appearance);
        mermaid.initialize(initConfig);
        const sameSource = state.lastParsedSource === source;
        const parsedPromise = sameSource && state.parsedOnce
          ? Promise.resolve(state.parsedOnce)
          : mermaid.parse(source, { suppressErrors: true });
        return Promise.resolve(parsedPromise).then((parsed) => {
          if (!parsed || parsed === false) return parseFailure(requestId, source, mermaid, appearance, options);
          state.lastParsedSource = source;
          state.parsedOnce = parsed;
          const diagramType = String(parsed.diagramType || options.selectedTypeId || '');
          return renderDiagram(mermaid, source, requestId, diagramType);
        });
      });
    })
    .catch((err) => {
      const message = String((err && (err.message || err.str)) || err || 'render failed');
      return terminal({
        requestId: requestId,
        state: 'invalid',
        diagramType: null,
        error: normalizeError(err, source, { assumedKind: 'renderError', rawMessage: message, diagramType: options.selectedTypeId }),
      });
    })
    .then((status) => {
      stopStallTimer();
      if (!status) return null;
      // A cycle that has been superseded while it was in flight publishes, paints
      // and returns nothing at all (contract section 2, invariant 3).
      return paintStatus(status, input);
    });
}

// Mermaid 11's parse() is a promise API, and the suppressed first call gives no
// details at all — so a second parse asks for them. `suppressErrorRendering` is
// frozen on, and the parse never touches our picture container, so the details
// come back as a rejection instead of as DOM that mermaid paints for itself.
function parseDetails(source, mermaid) {
  return Promise.resolve()
    .then(() => mermaid.parse(source))
    .then(() => null)
    .catch((err) => err || new Error('Mermaid reported the text as unparsable without details.'));
}

function parseFailure(requestId, source, mermaid, appearance, options) {
  return parseDetails(source, mermaid).then((thrown) => parseFailureWith(requestId, source, thrown, options));
}

function parseFailureWith(requestId, source, thrown, options) {
  if (!thrown) {
    const error = normalizeError(null, source, { assumedKind: 'parseError', rawMessage: 'Mermaid reported the text as unparsable without details.', diagramType: options.selectedTypeId });
    return terminalError(requestId, error, null);
  }
  const message = String((thrown && (thrown.message || thrown.str)) || thrown);
  const firstWord = firstToken(source);
  const namesNoType = guessType(source) === null;
  const kind = (/unsupported diagram type|no diagram type detected/i.test(message) || (namesNoType && /parse error|no diagram type|not match given configuration/i.test(message)))
    ? 'unsupportedType' : 'parseError';
  const error = normalizeError(thrown, source, {
    assumedKind: kind,
    rawMessage: message,
    diagramType: options.selectedTypeId || guessType(source),
    // FR-017: the odd word is quoted in the message, so the fix is obvious.
    unsupportedFirstWord: kind === 'unsupportedType' && namesNoType ? firstWord : null,
  });
  return terminalError(requestId, error, error.line ? null : guessType(source));
}

// The type words mermaid@11 accepts as a diagram's first token. Used only to
// *explain* a failure (FR-017); the authority on what parses is mermaid itself.
export const KNOWN_TYPE_WORDS = ['flowchart', 'graph', 'sequencediagram', 'classdiagram',
  'statediagram', 'erdiagram', 'gantt', 'pie', 'journey', 'mindmap', 'timeline',
  'quadrantchart', 'requirementdiagram'];

export function firstToken(source) {
  const first = String(source == null ? '' : source).trimStart().split(/\r?\n/)[0].trim();
  return (first.match(/^[\w-]+/) || [''])[0];
}

export function guessType(source) {
  const first = String(source == null ? '' : source).trimStart().split(/\r?\n/)[0].trim();
  const m = first.match(/^(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|erDiagram|gantt|pie|journey|mindmap|timeline|quadrantChart|requirementDiagram)\b/i);
  return m ? m[1].toLowerCase() : null;
}

function terminalError(requestId, error, diagramType) {
  return terminal({ requestId: requestId, state: 'invalid', diagramType: diagramType || error.diagramType || null, error: error });
}

function renderDiagram(mermaid, text, requestId, diagramType) {
  const started = Date.now();
  const safeId = 'mmd-' + String(requestId).replace(/[^A-Za-z0-9_-]/g, '') + '-' + (state.renderSeq += 1);
  return Promise.resolve(mermaid.render(safeId, text)).then((result) => {
    const svg = result && (result.svg || (typeof result === 'string' ? result : null));
    if (!svg) {
      const error = normalizeError(null, text, { assumedKind: 'renderError', renderStage: true, rawMessage: 'Mermaid returned no SVG for ' + safeId, diagramType: diagramType });
      return terminal({ requestId: requestId, state: 'invalid', diagramType: diagramType, error: error });
    }
    return terminal({
      requestId: requestId,
      state: 'rendered',
      diagramType: String(diagramType || ''),
      metrics: { durationMs: Date.now() - started },
      svg: svg,
    });
  });
}

export function terminal(status) {
  return status;
}

// ---------------------------------------------------------------- the chrome --


// Export toolbar (FR-028..032, T044): component-owned chrome, because the SVG
// to capture lives here. It consumes `ResolvedAppearance.export` — it never
// re-reads a widget or re-resolves an appearance (contract §2 rule 3).
export function buildExportToolbar(toolbar) {
  const doc = state.doc;
  toolbar.textContent = '';
  const scale = selectHost(doc);
  const background = selectHost(doc);
  const name = inputHost(doc);
  const run = (kind) => {
    const svg = currentSvg();
    if (!svg) {
      showNotice('Nothing to export yet — the diagram has not rendered.', 'busy');
      return null;
    }
    const exporter = globalThis.__mermaidGuiExport__;
    if (!exporter || !exporter.exportAs) {
      showNotice('The export component did not load. Reload the page.', 'busy');
      return null;
    }
    const snap = stateSnapshot();
    return Promise.resolve(exporter.exportAs(kind, {
      svg: svg,
      // The toolbar is what the user just chose; the resolved appearance is what
      // the preview was drawn with. The toolbar wins, and the option text ("print")
      // is translated to mermaid's multiplier here rather than reaching exportAs.
      scale: scale.value ? scale.value : undefined,
      background: background.value ? background.value : undefined,
      name: name.value ? name.value : state.diagramName,
      expectedRequestId: snap.newestTerminalId,
    })).then((result) => {
      if (!result) return result;
      if (result.ok === false) {
        showNotice(result.message || 'The export could not be completed.', 'busy');
      } else {
        showNotice(result.filename
          ? (result.copied === false ? result.message : 'Saved ' + result.filename)
          : 'Exported.', null);
      }
      return result;
    });
  };
  toolbar.appendChild(field(doc, 'Scale', scale, ['screen', 'high', 'print']));
  toolbar.appendChild(field(doc, 'Background', background, ['diagram', 'white', 'transparent']));
  toolbar.appendChild(field(doc, 'Name', name, null));
  toolbar.appendChild(el('div', 'mmd-spacer'));
  toolbar.appendChild(button('Export SVG', 'Vector, exact colours', () => run('exportSvg')));
  toolbar.appendChild(button('Export PNG', 'Raster at the scale above', () => run('exportPng'), 'mmd-btn--primary'));
  toolbar.appendChild(button('Copy SVG', 'Markup with inline styles', () => run('copySvg')));
  return toolbar;
}

export function applyExportDefaults(input) {
  const appearance = (input && input.appearance) || {};
  const exportOptions = appearance.export || {};
  const chrome = (input && input.chrome) || {};
  const toolbar = state.els && state.els.toolbar;
  if (chrome.name != null) state.diagramName = String(chrome.name);
  if (chrome.interfaceMode) setInterfaceMode(chrome.interfaceMode);
  if (chrome.storage) state.storageState = chrome.storage;
  if (!toolbar) return;
  const controls = toolbar.querySelectorAll('select');
  if (controls[0] && exportOptions.scaleName) controls[0].value = String(exportOptions.scaleName);
  if (controls[1] && exportOptions.background) controls[1].value = String(exportOptions.background);
  const nameInput = toolbar.querySelector('input[type="text"]');
  if (nameInput && chrome.name != null) nameInput.value = String(chrome.name);
}

function selectHost(doc) {
  const node = doc.createElement('select');
  node.setAttribute('aria-label', 'value');
  return node;
}

function inputHost(doc) {
  const node = doc.createElement('input');
  node.type = 'text';
  node.placeholder = 'untitled';
  node.setAttribute('aria-label', 'file name');
  node.addEventListener('input', () => { state.diagramName = node.value; });
  return node;
}

function field(doc, label, node, options) {
  const wrap = el('label', 'mmd-field');
  wrap.appendChild(el('span', 'mmd-field-label', label));
  // A <label> that wraps "Scale" plus its own option text gives assistive tech
  // "Scalescreenhighprint", so the control names itself explicitly.
  node.setAttribute('aria-label', label);
  if (options) node.__options = options;
  if (node.tagName === 'SELECT' && options) {
    options.forEach((value) => {
      const option = doc.createElement('option');
      option.value = value;
      option.textContent = value;
      node.appendChild(option);
    });
  }
  wrap.appendChild(node);
  return wrap;
}

function el(tag, className, text) {
  const node = DOC.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function button(label, title, handler, extraClass) {
  const node = el('button', 'mmd-btn' + (extraClass ? ' ' + extraClass : ''), label);
  node.type = 'button';
  if (title) node.title = title;
  node.addEventListener('click', handler);
  return node;
}

function zoomButton(label, title, handler) {
  const node = el('button', null, label);
  node.type = 'button';
  node.title = title;
  node.setAttribute('aria-label', title);
  node.addEventListener('click', handler);
  return node;
}

export function buildChrome(options) {
  const doc = options.document || DOC;
  const root = doc.querySelector('.mmd-root') || doc.body;
  state.doc = doc;

  const toolbar = el('div', 'mmd-toolbar mmd-hidden');
  const notice = el('div', 'mmd-panel mmd-panel--hint mmd-hidden');
  const errorPanel = el('div', 'mmd-panel mmd-panel--error mmd-hidden');
  const emptyPanel = el('div', 'mmd-panel mmd-panel--busy mmd-hidden');
  const status = el('div', 'mmd-status');
  const viewport = el('div', 'mmd-viewport');
  const canvas = el('div', 'mmd-canvas mmd-figure');
  const canvasHost = el('div', 'mmd-render-host');
  const lastGoodHost = el('div', 'mmd-render-host mmd-hidden');
  const zoomBar = el('div', 'mmd-zoom');
  const zoomLabel = el('span', 'mmd-zoom-label', 'fit');
  const footer = el('div', 'mmd-footer');

  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  canvas.appendChild(canvasHost);
  canvas.appendChild(lastGoodHost);
  lastGoodHost.dataset.lastGood = '';
  viewport.appendChild(canvas);
  zoomBar.appendChild(zoomButton('\u2212', 'Zoom out', () => setZoomCommand(-1)));
  zoomBar.appendChild(zoomLabel);
  zoomBar.appendChild(zoomButton('+', 'Zoom in', () => setZoomCommand(1)));
  zoomBar.appendChild(zoomButton('Fit', 'Fit to view', () => setFit(true)));
  zoomBar.appendChild(zoomButton('1:1', 'Reset zoom', () => setZoomCommand(0)));
  viewport.appendChild(zoomBar);

  buildExportToolbar(toolbar);
  [toolbar, notice, errorPanel, emptyPanel, status, viewport, footer].forEach((node) => root.appendChild(node));

  state.els = {
    root: root, toolbar: toolbar, notice: notice, error: errorPanel, empty: emptyPanel,
    status: status, viewport: viewport, canvas: canvas, canvasHost: canvasHost,
    lastGoodHost: lastGoodHost, zoomBar: zoomBar, zoomLabel: zoomLabel, footer: footer,
  };
  return state.els;
}

function els() {
  if (!state.els) buildChrome({ document: DOC });
  return state.els;
}

export function emit(status) {
  const published = postStatus(status);
  if (published) emitStatusUI(published);
  return published;
}

export function emitStatusUI(status) {
  if (!status || status.stalled) {
    if (status && status.stalled) showNotice('Still working on this diagram \u2014 large diagrams can take a while.', 'busy');
    return;
  }
  const ui = els();
  showPanel(status.state);
  // FR-032/T044: the export chrome only makes sense once there is a picture to
  // export, so it stays hidden until the first 'rendered' state arrives.
  if (ui.toolbar) ui.toolbar.classList.toggle('mmd-hidden', status.state !== 'rendered');
const badge = el('span', 'mmd-badge mmd-badge--' + status.state, labelFor(status.state));
  ui.status.textContent = '';
  ui.status.appendChild(badge);
  if (status.diagramType) ui.status.appendChild(el('span', 'mmd-chip', status.diagramType));
  // The status line is rebuilt here, so the origin chips belong to this pass: a
  // caller that paints the same status twice (boot, then a host reply) cannot
  // lose them.
  if (state.lastSourceOf) showOriginChips(state.lastSourceOf);
  if (status.state === 'rendered' && status.metrics && status.metrics.durationMs != null) {
    ui.status.appendChild(el('span', 'mmd-panel-meta', status.metrics.durationMs + ' ms'));
  }
  if (status.clamped && status.clamped.length) {
    showNotice('Some colours were adjusted for readability: ' + status.clamped.join(', ') + '.');
  }
  if (status.state === 'rendered') stopStallTimer();
}

function labelFor(stateName) {
  if (stateName === 'rendering') return 'Rendering\u2026';
  if (stateName === 'rendered') return 'Up to date';
  if (stateName === 'invalid') return 'Not drawn';
  return 'Waiting for text';
}

// ``which`` is either a panel name (``showError`` asks for 'error') or a state
// name (``emitStatusUI`` passes 'invalid' / 'empty'), so the two vocabularies are
// mapped here rather than at every call site.
function showPanel(which) {
  const ui = els();
  const wanted = which === 'invalid' ? 'error' : which;
  const map = { notice: ui.notice, error: ui.error, empty: ui.empty };
  Object.keys(map).forEach((name) => {
    const node = map[name];
    if (!node) return;
    if (wanted === name) node.classList.remove('mmd-hidden');
    else node.classList.add('mmd-hidden');
  });
  if (which === 'rendered' || which === 'rendering' || which === 'noop') {
    Object.keys(map).forEach((name) => map[name].classList.add('mmd-hidden'));
  }
}

export function showNotice(text, kind) {
  const ui = els();
  ui.notice.textContent = '';
  const line = el('div', 'mmd-hint-line');
  line.appendChild(el('span', 'mmd-panel-meta', text));
  ui.notice.appendChild(line);
  ui.notice.classList.toggle('mmd-panel--busy', kind === 'busy');
  ui.notice.classList.toggle('mmd-hidden', false);
  measure();
}

export function hideNotice() {
  const ui = els();
  ui.notice.classList.add('mmd-hidden');
  ui.notice.textContent = '';
}

export function showError(renderError, source) {
  const ui = els();
  showPanel('error');
  ui.error.textContent = '';
  const body = el('div', 'mmd-panel-body');
  body.appendChild(el('p', 'mmd-panel-title', (renderError && renderError.plainMessage) || PLAIN_FOR.parseError));
  const info = (renderError && renderError.kind === 'inputTooLarge')
    ? { snippet: '', startLine: null, caret: 0 }
    : extractSnippet(source, renderError && renderError.line, renderError && renderError.column);
  if (info.snippet) {
    const pre = el('pre', 'mmd-snippet');
    pre.appendChild(el('span', 'mmd-caret', '\u00a0'.repeat(Math.min(40, info.caret)) + '\u25b2'));
    pre.appendChild(DOC.createTextNode('\n' + info.snippet));
    body.appendChild(pre);
    body.appendChild(el('p', 'mmd-panel-meta', 'Line ' + info.startLine + (renderError && renderError.column ? ', column ' + renderError.column : '') + '.'));
  }
  if (renderError && renderError.rawMessage && renderError.kind !== 'inputTooLarge') {
    const details = DOC.createElement('details');
    details.className = 'mmd-details';
    const summary = DOC.createElement('summary');
    summary.textContent = 'Technical details';
    details.appendChild(summary);
    details.appendChild(el('pre', 'mmd-snippet', renderError.rawMessage));
    body.appendChild(details);
  }
  ui.error.appendChild(body);
  measure();
}

export function showEmpty() {
  const ui = els();
  // Contract invariant 4: `empty` is a state of its own. The last good picture is
  // kept only while the text is *invalid* (invariant 2), so blanking the editor
  // must blank the stage as well -- otherwise a diagram the user deleted stays on
  // screen and can even be exported.
  if (ui.canvasHost) ui.canvasHost.innerHTML = '';
  if (ui.lastGoodHost) {
    ui.lastGoodHost.innerHTML = '';
    ui.lastGoodHost.classList.add('mmd-hidden');
  }
  if (ui.canvasHost) ui.canvasHost.classList.remove('mmd-hidden');
  state.lastGood = null;
  hostSet('lastGood', null);
  showPanel('empty');
  ui.empty.textContent = '';
  const body = el('div', 'mmd-panel-body');
  body.appendChild(el('p', 'mmd-panel-title', 'Nothing to preview yet'));
  body.appendChild(el('p', 'mmd-panel-meta', 'Type or paste diagram text above and the picture appears here.'));
  ui.empty.appendChild(body);
  measure();
}

// Origin chips: FR-009 discoverability (T016).
export function showOriginChips(sourceOf) {
  if (!sourceOf) return;
  const ui = els();
  Array.prototype.slice.call(ui.status.querySelectorAll('.mmd-chip[data-origin]')).forEach((node) => node.remove());
  Object.keys(sourceOf).forEach((key) => {
    if (sourceOf[key] !== 'frontmatter') return;
    const chip = el('span', 'mmd-chip', key + ' set by your diagram text');
    chip.setAttribute('data-origin', 'frontmatter');
    ui.status.appendChild(chip);
  });
}

function swapDiagram(svgMarkup, requestId, status) {
  const ui = els();
  if (!state.lastGood && HOST.lastGood) rememberLastGood(HOST.lastGood);
  if (status && status.showLastGood && state.lastGood) {
    ui.canvasHost.classList.add('mmd-hidden');
    ui.lastGoodHost.classList.remove('mmd-hidden');
    ui.lastGoodHost.innerHTML = state.lastGood.svg;
    return;
  }
  if (status && status.state === 'invalid') {
    // a failed parse never clears a good picture — it hides nothing and keeps
    // the last good SVG visible behind the error panel (FR-016).
    if (state.lastGood) {
      ui.canvasHost.classList.remove('mmd-hidden');
      ui.lastGoodHost.classList.add('mmd-hidden');
    }
    return;
  }
  if (!svgMarkup) return;
  ui.canvasHost.innerHTML = svgMarkup;
  ui.lastGoodHost.classList.add('mmd-hidden');
  ui.canvasHost.classList.remove('mmd-hidden');
  state.lastGood = { svg: svgMarkup, requestId: requestId, node: ui.canvasHost.cloneNode(true) };
  hostSet('lastGood', { svg: svgMarkup, requestId: requestId });
  fitToViewInit();
}

// Zoom / fit (FR-034/035, T047): scale a wrapper, never the SVG itself, so a
// zoomed view can never leak into a captured export.
export function applyZoom() {
  const ui = els();
  const wrapper = ui.canvasHost;
  if (state.fitToView) {
    wrapper.classList.add('mmd-figure--fit');
    wrapper.style.zoom = '';
    wrapper.style.transform = '';
    els().zoomLabel.textContent = 'fit';
    return;
  }
  const scale = ZOOM_STEPS[state.zoomIndex];
  if ('zoom' in wrapper.style) wrapper.style.zoom = String(scale);
  else {
    wrapper.style.transform = 'scale(' + scale + ')';
    wrapper.style.transformOrigin = 'top left';
  }
  els().zoomLabel.textContent = Math.round(scale * 100) + '%';
}

function fitToViewInit() {
  state.fitToView = true;
  applyZoom();
  measure();
}

export function setZoomCommand(delta) {
  if (state.newestRequestId == null && !state.lastGood) return;
  state.zoomIndex = zoomIndex(state.zoomIndex, delta);
  // "1:1" means one-to-one: the default step with no scaling. Fitting the picture
  // to the pane is its own control, and conflating them made Reset do nothing
  // visible on a diagram that already fitted.
  state.fitToView = false;
  applyZoom();
  measure();
}

export function setFit(value) {
  state.fitToView = !!value;
  applyZoom();
  measure();
}

export function setInterfaceMode(mode) {
  const allowed = ['auto', 'light', 'dark'];
  state.interfaceMode = allowed.indexOf(mode) === -1 ? 'auto' : mode;
  const root = els().root;
  if (root && root.parentElement) root.parentElement.setAttribute('data-interface', state.interfaceMode);
  root.setAttribute('data-interface', state.interfaceMode);
  if (DOC && DOC.body) DOC.body.setAttribute('data-interface', state.interfaceMode);
}

export function measure() {
  const height = Math.ceil((DOC && DOC.body && DOC.body.scrollHeight) || 0);
  if (!height) return 0;
  const marker = DOC && DOC.querySelector && DOC.querySelector('meta[name="mmd-doc-key"]');
  const docKey = marker ? marker.getAttribute('content') : null;
  const heightHost = hostWindow();
  if (heightHost) {
    try {
      heightHost.postMessage({ type: 'mmd-height', height: height, docKey: docKey }, '*');
    } catch (err) { /* ignore */ }
  }
  return height;
}

function paintStatus(status, input) {
  if (!status) return status;
  // Contract section 2, invariant 3. runCycle() only refuses a request that is
  // already old when it *starts*; two cycles started in the same tick (a paste
  // followed immediately by a knob change) both get that way, and the older one
  // must still not publish, paint, or be returned, once the newer one is known.
  if (state.newestRequestId && compareId(status.requestId, state.newestRequestId) < 0) {
    return null;
  }
  const appearance = (input && input.appearance) || {};
  state.lastSourceOf = appearance.sourceOf || null;
  const withMeta = Object.assign({}, status, {
    clamped: status.clamped || appearance.clamped || [],
  });
  const showChips = () => {
    // emitStatusUI rebuilds the status line, so the origin chips have to come
    // after it or they are wiped on every repaint.
    if (appearance.sourceOf) showOriginChips(appearance.sourceOf);
  };
  if (status.state === 'rendered') {
    hideNotice();
    swapDiagram(status.svg, status.requestId, withMeta);
    emitStatusUI(withMeta);
    showChips();
  } else if (status.state === 'invalid') {
    const lastGoodKept = !!state.lastGood;
    withMeta.showLastGood = lastGoodKept;
    if (lastGoodKept) swapDiagram(null, status.requestId, withMeta);
    showError(status.error || {}, input && input.source);
    emitStatusUI(withMeta);
    showChips();
  } else if (status.state === 'empty') {
    hideNotice();
    showEmpty();
    emitStatusUI(withMeta);
  }
  if (withMeta.state !== 'rendering') emit(withMeta);
  measure();
  return withMeta;
}

// Command router used by the inlined wrapper (app.py) and by browser tests.
export function handle(payload) {
  const input = payload || {};
  const command = String(input.command || 'render');
  applyExportDefaults(input);
  if (input.interfaceMode) setInterfaceMode(input.interfaceMode);
  if (command === 'clearStorage') {
    state.lastGood = null;
    hostSet('lastGood', null);
    clearStorage();
    return Promise.resolve({ state: 'noop', command: command });
  }
  if (command === 'link') {
    const options = input.options || input.chrome || {};
    return requestLink(options.payload, options.copy).then((result) => {
      showNotice(result && result.ok
        ? 'Share link ready in the page address.'
        : 'The page address could not be updated. Copy the link from the sidebar field instead.', result && result.ok ? null : 'busy');
      return { state: 'noop', command: command, link: result };
    });
  }
  if (command === 'render') {
    const draft = draftFromPayload(input);
    if (draft) saveDraft(draft);
    const chrome = input.chrome || {};
    if (chrome.knobs) saveAppearanceSoon(chrome.knobs);
    if (chrome.host && chrome.host.action === 'clearStorage') {
      state.lastGood = null;
      hostSet('lastGood', null);
      clearStorage();
    }
    if (chrome.host && chrome.host.action === 'link') {
      requestLink(chrome.host.payload, chrome.host.copy);
    }
    return runCycle(input);
  }
  if (command === 'zoomIn') { setZoomCommand(1); return Promise.resolve({ state: 'noop', command: command }); }
  if (command === 'zoomOut') { setZoomCommand(-1); return Promise.resolve({ state: 'noop', command: command }); }
  if (command === 'fit') { setFit(true); return Promise.resolve({ state: 'noop', command: command }); }
  if (command === 'reset') { setZoomCommand(0); return Promise.resolve({ state: 'noop', command: command }); }
  if (command === 'interfaceMode') { setInterfaceMode(input.options && input.options.interfaceMode); return Promise.resolve({ state: 'noop', command: command }); }
  const exporter = globalThis.__mermaidGuiExport__;
  const svg = els().canvasHost.querySelector('svg');
  if (!exporter || !exporter.exportAs) {
    showNotice('The export component did not load. Reload the page.', 'busy');
    return Promise.resolve({ state: 'noop', command: command });
  }
  if (!svg) {
    showNotice('Nothing to export yet \u2014 the diagram has not rendered.', 'busy');
    return Promise.resolve({ state: 'noop', command: command });
  }
  return Promise.resolve(exporter.exportAs(command, Object.assign({ svg: svg, expectedRequestId: state.newestTerminalId }, input.options || {})));
}

export function boot(options) {
  const opts = options || {};
  if (opts.document) state.doc = opts.document;
  buildChrome({ document: state.doc });
  if (opts.attachHost !== false) attachHostBridge();
  if (opts.interfaceMode) setInterfaceMode(opts.interfaceMode);
  if (opts.mermaidUrl) {
    state.mermaidPromise = import(opts.mermaidUrl).then((mod) => {
      state.mermaid = mod.default || mod.mermaid || mod;
      return state.mermaid;
    });
  }
  return { els: els(), handle: handle, measure: measure, state: state };
}

export function readPayload(doc) {
  const node = (doc || DOC) && (doc || DOC).getElementById('mmd-payload');
  if (!node) return null;
  try {
    return JSON.parse(node.textContent);
  } catch (err) {
    return null;
  }
}

export function currentSvg() {
  const ui = els();
  return ui ? ui.canvasHost.querySelector('svg') : null;
}

export function stateSnapshot() {
  return {
    newestRequestId: state.newestRequestId,
    renderSeq: state.renderSeq,
    newestTerminalId: state.newestTerminalId,
    hasLastGood: !!state.lastGood,
    zoomIndex: state.zoomIndex,
    fitToView: state.fitToView,
    interfaceMode: state.interfaceMode,
    mermaidVersion: state.mermaid && state.mermaid.version ? state.mermaid.version() : null,
  };
}

export function __resetForTests__() {
  stopStallTimer();
  state.newestRequestId = null;
  state.newestTerminalId = null;
  state.lastGood = null;
  state.lastParsedSource = null;
  state.parsedOnce = null;
  state.zoomIndex = ZOOM_DEFAULT_INDEX;
  state.fitToView = false;
  state.renderSeq = 0;
}

// ---------------------------------------------------- host bridge (index.html) --
// A srcdoc component iframe is null-origin: `localStorage` throws and the page
// URL is not ours to touch. index.html keeps the durable state (draft,
// appearance, last good picture, share fragment) and answers these messages.
// Nothing here trusts the host: every handler is total and failures are simply
// ignored, so a page opened without the bridge still previews.

const HOST = { lastGood: null, draft: null, result: null, pending: null };
const DRAFT_COALESCE_MS = 1000;   // share-payload contract §2 rule 1 (SC-009)
let draftTimer = null;
let hostListener = null;

export function postHost(message) {
  const host = hostWindow();
  if (!host) return false;
  try {
    host.postMessage(message, '*');
    return true;
  } catch (err) {
    return false;
  }
}

export function hostAsk(key) {
  return postHost({ type: 'mmd-host', op: 'get', key: key });
}

export function hostSet(key, value) {
  return postHost({ type: 'mmd-host', op: 'set', key: key, value: value });
}

export function saveDraft(draft) {
  if (!draft || !draft.source) return false;      // never save an empty overwrite
  if (draftTimer) clearTimeout(draftTimer);
  return new Promise((resolve) => {
    draftTimer = setTimeout(() => {
      draftTimer = null;
      HOST.pending = draft;
      const ok = postHost({ type: 'mmd-store', key: 'draft', value: draft });
      resolve(ok);
    }, DRAFT_COALESCE_MS);
  });
}

export function saveAppearanceSoon(knobs) {
  return postHost({ type: 'mmd-store', key: 'appearance', value: knobs });
}

export function requestLink(payload, copy) {
  return new Promise((resolve) => {
    const win = globalThis.window;
    const onResult = (event) => {
      const data = event && event.data;
      if (!data || data.type !== 'mmd-link-result') return;
      if (win) win.removeEventListener('message', onResult);
      HOST.result = data;
      resolve(data);
    };
    if (win && win.addEventListener) win.addEventListener('message', onResult);
    const sent = postHost({ type: 'mmd-link', payload: payload, copy: !!copy });
    if (!sent) {
      if (win && win.removeEventListener) win.removeEventListener('message', onResult);
      resolve({ ok: false, reason: 'noHost' });
    }
  });
}

export function clearStorage() {
  return postHost({ type: 'mmd-clear-storage' });
}

export function attachHostBridge() {
  const win = globalThis.window;
  if (!win || !win.addEventListener || hostListener) return false;
  hostListener = (event) => {
    const data = event && event.data;
    if (!data || typeof data !== 'object') return;
    if (data.type === 'mmd-storage-failed') {
      // FR-027: persistence is gone, the editor is not. Say it once, keep going.
      state.storageState = String(data.state || 'unavailable');
      if (!state.storageNoticeShown) {
        state.storageNoticeShown = true;
        showNotice('This browser will not keep a draft (private mode, or storage is full). Everything else works \u2014 download the .mmd file to keep your text.', 'hint');
      }
      return;
    }
    if (data.type === 'mmd-host-result') {
      HOST[data.key] = data.value;
      if (data.key === 'lastGood' && data.value) rememberLastGood(data.value);
    }
  };
  win.addEventListener('message', hostListener);
  hostAsk('lastGood');
  return true;
}

function rememberLastGood(value) {
  if (!state.lastGood && value && value.svg) {
    state.lastGood = { svg: value.svg, requestId: value.requestId || 'host', source: value.source || '' };
  }
}

export function draftFromPayload(input) {
  const chrome = (input && input.chrome) || {};
  if (!chrome.autosave) return null;
  const source = String(input.source == null ? '' : input.source);
  if (/^\s*$/.test(source)) return null;
  return {
    version: 1,
    savedAt: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'),
    source: source,
    name: String(chrome.name || ''),
    knobs: chrome.knobs || null,
  };
}

export function __selfRegister__() {
  const api = {
    SCHEMA_VERSION: SCHEMA_VERSION, STATE_ENUM: STATE_ENUM, ERROR_KINDS: ERROR_KINDS, COMMAND_ENUM: COMMAND_ENUM,
    MAX_SOURCE_CHARS: MAX_SOURCE_CHARS, STALL_NOTICE_MS: STALL_NOTICE_MS, ZOOM_STEPS: ZOOM_STEPS,
    ZOOM_DEFAULT_INDEX: ZOOM_DEFAULT_INDEX, FROZEN_SETTINGS: FROZEN_SETTINGS, TOO_LARGE_MESSAGE: TOO_LARGE_MESSAGE,
    PLAIN_FOR: PLAIN_FOR, ERROR_REWRITES: ERROR_REWRITES,
    normalizeError: normalizeError, rewriteError: rewriteError, stripJargon: stripJargon, extractSnippet: extractSnippet,
    findCaretLine: findCaretLine, buildDetail: buildDetail, configureOptions: configureOptions, loadMermaid: loadMermaid,
    compareId: compareId, zoomIndex: zoomIndex, postStatus: postStatus, terminal: terminal, guessType: guessType,
    runCycle: runCycle, handle: handle, boot: boot, buildChrome: buildChrome, emit: emit, emitStatusUI: emitStatusUI,
    showError: showError, showEmpty: showEmpty, showNotice: showNotice, hideNotice: hideNotice, showOriginChips: showOriginChips,
    applyZoom: applyZoom, setZoomCommand: setZoomCommand, setFit: setFit, setInterfaceMode: setInterfaceMode,
    measure: measure, readPayload: readPayload, currentSvg: currentSvg, stateSnapshot: stateSnapshot,
    postHost: postHost, hostAsk: hostAsk, hostSet: hostSet, saveDraft: saveDraft, saveAppearanceSoon: saveAppearanceSoon,
    requestLink: requestLink, clearStorage: clearStorage, attachHostBridge: attachHostBridge, draftFromPayload: draftFromPayload,
    HOST: HOST, __resetForTests__: __resetForTests__,
  };
  globalThis.__mermaidGuiRender__ = api;
  return api;
}
