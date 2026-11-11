/**
 * The page-side half of the preview bridge. Plain script, no build step,
 * loaded by index.html before Stlite mounts (and by the Playwright host fixture).
 *
 * Why this exists on the page rather than inside the app:
 *   * Stlite runs the Streamlit script in a Web Worker, which has no
 *     ``window``/``localStorage`` at all, so Python cannot own persistence.
 *   * ``st.components.v1.html`` renders into a ``srcdoc`` iframe whose origin is
 *     opaque, so the component can neither read nor write localStorage, nor move
 *     the address bar.
 * The one same-origin, real-DOM context is this page, so it owns storage, the
 * ``#p=`` share fragment, and the preview iframe's height, and relays results
 * back to the component with ``postMessage``. The component never touches
 * anything outside those messages (render-bridge contract, section 4).
 */
(function attachHostBridgeToWindow(root) {
  'use strict';

  const DRAFT_KEY = 'mermaidGui.draft';
  const APPEARANCE_KEY = 'mermaidGui.appearance';
  const FRAGMENT_PREFIX = '#p=';
  const HOST_MESSAGE = 'mmd-host';

  let storageState = 'unavailable';

  function probe() {
    try {
      const probeKey = DRAFT_KEY + '.probe';
      root.localStorage.setItem(probeKey, '1');
      root.localStorage.removeItem(probeKey);
      storageState = 'available';
      return true;
    } catch (denied) {
      storageState = 'denied';
      return false;
    }
  }

  function readStore(key) {
    if (storageState !== 'available') return null;
    try {
      const raw = root.localStorage.getItem(key);
      return raw ? JSON.parse(raw) : null;
    } catch (unreadable) {
      return null;
    }
  }

  // Counted so a caller (and the test suite) can tell "nothing to write" apart
  // from "the browser refused the write".
  const writeTally = { ok: 0, refused: 0, failed: 0 };

  function writeStore(key, value) {
    if (storageState !== 'available') {
      writeTally.refused += 1;
      return false;
    }
    try {
      root.localStorage.setItem(key, JSON.stringify(value));
      writeTally.ok += 1;
      return true;
    } catch (quota) {
      // A full store must not break the editor; the app shows a notice instead.
      storageState = 'full';
      writeTally.failed += 1;
      return false;
    }
  }

  /** The encoded payload inside ``#p=...`` (or null). */
  function fragmentPayload() {
    const hash = String(root.location.hash || '');
    const index = hash.indexOf(FRAGMENT_PREFIX);
    return index === -1 ? null : hash.slice(index + FRAGMENT_PREFIX.length);
  }

  /**
   * Put (or remove) the payload in the address bar, leaving history alone: a
   * share link must never add an entry per keystroke (FR-019).
   */
  function setFragment(payload) {
    const hash = payload ? FRAGMENT_PREFIX + payload : '';
    const url = root.location.pathname + root.location.search + hash;
    try {
      root.history.replaceState(null, '', url);
      return true;
    } catch (blocked) {
      return false;
    }
  }

  /** Everything the app needs to know before its first render. */
  function bootSnapshot() {
    return {
      version: 1,
      storage: storageState,
      fragment: fragmentPayload(),
      draft: readStore(DRAFT_KEY),
      appearance: readStore(APPEARANCE_KEY),
      href: root.location.href,
    };
  }

  // An in-memory mirror for the component, which is stateless: a srcdoc
  // document is replaced on every Streamlit rerun, so the last good picture and
  // the zoom level have to live somewhere that survives it. Keeping them here
  // (instead of st.session_state) keeps megabytes of SVG out of every payload.
  const mirror = Object.create(null);

  function resizeComponentFrame(docKey, height) {
    const value = Number(height) || 0;
    if (!value || !docKey) return false;
    const container = root.document.getElementById('root') || root.document.body;
    for (const frame of collectFrames(container, [], 0)) {
      let inner = null;
      try {
        inner = frame.contentDocument;
      } catch (blocked) {
        blocked;
      }
      if (!inner) continue;
      const marker = inner.querySelector('meta[name="mmd-doc-key"]');
      if (marker && marker.getAttribute('content') === String(docKey)) {
        // FR-034: the *page* scrolls, the preview never gets its own scroll bar, so
        // the frame has to be allowed to grow to what the diagram actually needs.
        // A very tall chain of nodes is legitimate; a clipped picture is not.
        frame.style.height = Math.min(24000, Math.max(200, value)) + 'px';
        return true;
      }
    }
    return false;
  }

  /** Iframes up to three levels deep, guarded for cross-origin frames. */
  function collectFrames(scope, out, depth) {
    if (depth > 3) return out;
    scope.querySelectorAll('iframe').forEach((frame) => {
      out.push(frame);
      let inner = null;
      try {
        inner = frame.contentDocument;
      } catch (blocked) {
        blocked;
      }
      if (inner) collectFrames(inner, out, depth + 1);
    });
    return out;
  }

  function reply(event, message) {
    if (event && event.source) {
      try {
        event.source.postMessage(message, '*');
      } catch (unreachable) {
        unreachable;
      }
    }
  }

  function handleHostMessage(event) {
    const data = event && event.data;
    if (!data || typeof data !== 'object' || data.type !== HOST_MESSAGE) return;
    if (data.op === 'get') {
      reply(event, {
        type: 'mmd-host-result',
        key: data.key,
        value: mirror[data.key] === undefined ? null : mirror[data.key],
      });
      return;
    }
    if (data.op === 'set') mirror[data.key] = data.value;
  }

  function handleBridgeMessage(event) {
    const data = event && event.data;
    if (!data || typeof data !== 'object') return;
    switch (data.type) {
      case 'mmd-height':
        resizeComponentFrame(data.docKey, data.height);
        break;
      case 'mmd-store': {
        // A write that fails (private mode, or the store is full) has to be said
        // out loud: the app asked for an autosave and the browser refused it.
        const wanted = data.key === 'draft' ? DRAFT_KEY : data.key === 'appearance' ? APPEARANCE_KEY : null;
        if (!wanted) break;
        const written = writeStore(wanted, data.value);
        if (!written) reply(event, { type: 'mmd-storage-failed', key: data.key, state: storageState });
        break;
      }
      case 'mmd-clear-storage': {
        if (storageState === 'available') {
          try {
            root.localStorage.removeItem(DRAFT_KEY);
            root.localStorage.removeItem(APPEARANCE_KEY);
          } catch (denied) {
            denied;
          }
        }
        mirror.lastGood = null;
        break;
      }
      case 'mmd-link': {
        const ok = setFragment(data.payload || '');
        if (ok && data.copy) {
          const link = root.location.href;
          if (root.navigator.clipboard && root.navigator.clipboard.writeText) {
            root.navigator.clipboard.writeText(link).catch(() => undefined);
          }
        }
        reply(event, { type: 'mmd-link-result', ok: ok, href: root.location.href });
        break;
      }
      default:
        break;
    }
  }

  function install() {
    probe();
    root.addEventListener('message', handleBridgeMessage);
    root.addEventListener('message', handleHostMessage);

    root.__mermaidGuiBoot = bootSnapshot();
    watchForEditor();
    root.__mermaidGuiStorage = {
      draft: () => readStore(DRAFT_KEY),
      appearance: () => readStore(APPEARANCE_KEY),
      saveDraft: (value) => writeStore(DRAFT_KEY, value),
      saveAppearance: (value) => writeStore(APPEARANCE_KEY, value),
      setFragment: setFragment,
      writeTally: () => Object.assign({}, writeTally),
      storageState: () => storageState,
      fragment: () => fragmentPayload(),
      clear: () => {
        mirror.lastGood = null;
        if (storageState !== 'available') return false;
        try {
          root.localStorage.removeItem(DRAFT_KEY);
          root.localStorage.removeItem(APPEARANCE_KEY);
          return true;
        } catch (denied) {
          return false;
        }
      },
      state: () => storageState,
      boot: bootSnapshot,
      resize: resizeComponentFrame,
      keys: { draft: DRAFT_KEY, appearance: APPEARANCE_KEY },
    };
    return root.__mermaidGuiStorage;
  }

  // --- editing assistance inside the app's own textarea -------------------
  // FR-037 asks for reliable tab and indent behaviour. The editor is Streamlit's
  // `st.text_area` inside the mounted app frame, and a browser textarea moves
  // focus on Tab, so the page adds the missing keystrokes. It never touches the
  // text: it inserts or removes the user's own indent and lets Streamlit commit
  // the value as usual (the setter below is the one React reads).
  const INDENT = '  ';

  function indentRange(textarea, outdent) {
    const value = String(textarea.value || '');
    const start = textarea.selectionStart || 0;
    const end = textarea.selectionEnd || 0;
    const lineStart = value.lastIndexOf('\n', start - 1) + 1;
    let next = value;
    let caretStart = start;
    let caretEnd = end;
    if (outdent && start === end) {
      const lead = /^(?: {1,2}|\t)/.exec(value.slice(lineStart));
      if (!lead) return false;
      const removed = lead[0].length;
      next = value.slice(0, lineStart) + value.slice(lineStart + removed);
      caretStart = Math.max(lineStart, start - removed);
      caretEnd = Math.max(lineStart, end - removed);
    } else if (outdent) {
      // Shift-Tab across a selection takes one indent level off every line that
      // has one, which is what an indent means to a reader of this markup.
      let lineEnd = value.indexOf('\n', end - 1);
      if (lineEnd === -1) lineEnd = value.length;
      const block = value.slice(lineStart, lineEnd);
      let removedTotal = 0;
      const lines = block.split('\n').map((line) => {
        const lead = /^(?: {1,2}|\t)/.exec(line);
        if (!lead) return line;
        removedTotal += lead[0].length;
        return line.slice(lead[0].length);
      });
      if (!removedTotal) return false;
      next = value.slice(0, lineStart) + lines.join('\n') + value.slice(lineEnd);
      caretStart = Math.max(lineStart, start - removedTotal);
      caretEnd = Math.max(lineStart, end - removedTotal);
    } else if (start !== end) {
      // A selection indents every line it touches, which is what people mean.
      let lineEnd = value.indexOf('\n', end);
      if (lineEnd === -1) lineEnd = value.length;
      const block = value.slice(lineStart, lineEnd);
      const lines = block.split('\n');
      next = value.slice(0, lineStart) + lines.map((line) => INDENT + line).join('\n') + value.slice(lineEnd);
      caretStart = start + INDENT.length;
      caretEnd = end + INDENT.length * lines.length;
    } else {
      next = value.slice(0, start) + INDENT + value.slice(end);
      caretStart = caretEnd = start + INDENT.length;
    }
    const setter = Object.getOwnPropertyDescriptor(root.HTMLTextAreaElement.prototype, 'value');
    if (setter && setter.set) setter.set.call(textarea, next);
    else textarea.value = next;
    textarea.setSelectionRange(caretStart, caretEnd);
    textarea.dispatchEvent(new root.Event('input', { bubbles: true }));
    return true;
  }

  // The line the caret is on, next to the editor. This is FR-033's line number
  // requirement met where the information actually exists: Python never sees a
  // caret, but this page can read one.
  function caretReadout(textarea) {
    const host = textarea.closest('[data-testid="stElementContainer"]') || textarea.parentElement;
    if (!host) return null;
    let box = host.querySelector('.mmd-caret-readout');
    if (!box) {
      box = root.document.createElement('p');
      box.className = 'mmd-caret-readout';
      box.setAttribute('data-testid', 'mmd-caret-readout');
      host.appendChild(box);
    }
    return box;
  }

  function updateCaret(textarea) {
    const box = caretReadout(textarea);
    if (!box) return;
    const value = String(textarea.value || '');
    const caret = textarea.selectionStart || 0;
    const line = value.slice(0, caret).split('\n').length;
    const total = value.split('\n').length;
    const text = 'Line ' + line + ' of ' + total;
    if (box.textContent !== text) box.textContent = text;
  }

  function wireEditor(textarea) {
    if (textarea.__mmdTabWired) return;
    textarea.__mmdTabWired = true;
    ['keyup', 'click', 'input', 'scroll'].forEach((name) => {
      textarea.addEventListener(name, () => updateCaret(textarea));
    });
    updateCaret(textarea);
    textarea.addEventListener('keydown', (event) => {
      if (event.key !== 'Tab' || event.ctrlKey || event.metaKey || event.altKey) return;
      if (indentRange(textarea, event.shiftKey)) {
        event.preventDefault();
        updateCaret(textarea);
        // Streamlit commits a text_area when the field loses focus, so an
        // explicit commit event keeps the preview in step with what was typed.
        textarea.dispatchEvent(new root.Event('change', { bubbles: true }));
      }
    });
  }

  function assistEditors(root2) {
    let doc = null;
    try {
      doc = root2 === root.document ? root2 : root2.contentDocument;
    } catch (blocked) {
      return [];
    }
    if (!doc) return [];
    const found = Array.prototype.slice.call(doc.querySelectorAll('textarea'));
    found.forEach(wireEditor);
    return found;
  }

  function followSelection() {
    // One document-level listener, because the caret also moves without a keystroke
    // (an arrow click, a text select, or a restored selection).
    root.document.addEventListener('selectionchange', () => {
      const active = root.document.activeElement;
      if (active && active.tagName === 'TEXTAREA' && active.__mmdTabWired) updateCaret(active);
    });
  }

  function watchForEditor() {
    // The app frame and its widgets are created by Stlite some time after this
    // page loads, so look repeatedly rather than once, and cheaply.
    followSelection();
    const scan = () => {
      assistEditors(root.document);
      root.document.querySelectorAll('iframe').forEach((frame) => assistEditors(frame));
    };
    scan();
    if (root.MutationObserver) {
      const observer = new root.MutationObserver(scan);
      observer.observe(root.document.body || root.document.documentElement, { childList: true, subtree: true });
    }
    root.setTimeout(scan, 1500);
    root.setTimeout(scan, 4000);
  }

  const api = {
    install,
    bootSnapshot,
    fragmentPayload,
    setFragment,
    assistEditors,
    indentRange,
    DRAFT_KEY,
    APPEARANCE_KEY,
    FRAGMENT_PREFIX,
  };
  root.__mermaidGuiHost = api;
  // Loading this file *is* the installation: index.html reads the snapshot before
  // it mounts the app, and without the probe the store would be reported as
  // unavailable even in a browser that happily keeps drafts.
  if (!root.__mermaidGuiBoot) install();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
