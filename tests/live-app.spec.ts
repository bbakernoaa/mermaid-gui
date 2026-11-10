import { expect, test, type Page as PageLike } from '@playwright/test';
import { caretPosition, currentState, liveComponentFrame, openApp, pickOption, pollLive, setKnob, sliderValue, waitTerminal } from './support';

// The end-to-end proof of the *deployed* shape: index.html boots Stlite from the
// CDN, app.py imports its sibling modules inside Pyodide, the real Streamlit
// sidebar drives the shipped srcdoc preview component. Opt-in (MMD_LIVE=1)
// because it needs the network and takes ~20 s per boot.
async function componentPayload(page: import('@playwright/test').Page, text: import('./support').Frame) {
  return text.evaluate(() => JSON.parse(document.querySelector('#mmd-payload')!.textContent || '{}'));
}

const labelPx = (frame: import('./support').Frame) =>
  frame.evaluate(() => {
    const labels = Array.from(document.querySelectorAll('.mmd-canvas text')).filter((node) => (node.textContent || '').trim());
    const node = labels[0] as SVGTextElement | undefined;
    return node ? Number.parseFloat(getComputedStyle(node).fontSize) : 0;
  });

test.describe('live app', () => {
  test.beforeEach(async () => {
    test.skip(!process.env.MMD_LIVE, 'set MMD_LIVE=1 to boot the real app');
    test.setTimeout(240_000);
  });

  test('the sidebar knobs reach the shipped component (V-A 1-3, SC-001)', async ({ page }) => {
    const h = await openApp(page, 'good');
    await waitTerminal(h.comp, 'rendered');
    expect(await sliderValue(page, 'Text size'), 'Text size starts at medium').toBe('medium');
    const before = await labelPx(h.comp);

    await setKnob(page, 'Text size', 'largest');
    await expect.poll(() => sliderValue(page, 'Text size'), { timeout: 30_000 }).toBe('largest');
    await expect
      .poll(async () => (await componentPayload(page, h.comp)).appearance.themeVariables.fontSize, { timeout: 30_000, message: 'the resolver ran in Pyodide' })
      .toBe('28px');
    await expect.poll(() => labelPx(h.comp), { timeout: 30_000, message: 'the new size reached the picture' }).toBeGreaterThan(before);

    await setKnob(page, 'Colour scheme', 'neutral');
    await expect
      .poll(async () => (await componentPayload(page, h.comp)).appearance.mermaidTheme, { timeout: 30_000 })
      .toBe('neutral');

    // The click happens inside an opaque-origin frame, so the export is checked
    // where it is produced: the exporter reports the file it handed to the browser.
    const earlierReport = await h.comp.evaluate(() => (window as any).__mermaidGuiExport__.lastExportEcho());
    await Promise.all([
      page.waitForEvent('download', { timeout: 45_000 }).catch(() => null),
      h.comp.locator('.mmd-toolbar').getByRole('button', { name: 'Export SVG' }).click(),
    ]);
    await expect
      .poll(() => h.comp.evaluate(() => String((window as any).__mermaidGuiExport__.lastExportEcho()?.filename || '')), { timeout: 45_000, message: 'the exporter never reported the new file' })
      .toMatch(/\.svg$/);
    expect(await h.comp.evaluate(() => (window as any).__mermaidGuiExport__.lastExportEcho()), 'and it is a different export than any before').not.toEqual(earlierReport);
  });

  const caret = caretPosition;

  test('text typed into Streamlit reaches the component payload (V-A 4, FR-033)', async ({ page }) => {
    const h = await openApp(page, 'good');
    await waitTerminal(h.comp, 'rendered');
    const editor = page.locator('textarea').first();

    // Streamlit commits a text_area on blur and replaces the component iframe on
    // the rerun, so the stable read is the payload the app wrote, not a frame held
    // across the rerun. The redraw itself is asserted in fixture mode (states,
    // appearance and export suites), where the frame does not move.
    await typeInto(page, editor, 'flowchart TD\n  A[Typed in Streamlit] --> B[Redrawn]\n');
    await expect
      .poll(async () => (await componentPayload(page, await liveComponentFrame(page))).source, { timeout: 90_000, message: 'the app never handed the new text to the component' })
      .toContain('Typed in Streamlit');

    // The line readout is added by the page next to Streamlit's own editor, so it
    // has to appear in the real app, not just in the harness.
    await caret(page, 13, 13);
    // Three lines: the typed text ends with a newline, and the readout counts what
    // is in the field rather than rounding it away.
    await expect(page.locator('[data-testid="mmd-caret-readout"]'), 'the page must state the caret line').toHaveText('Line 2 of 3', { timeout: 20_000 });
  });

  test('text that cannot be drawn is refused by name, in the live app too (V-B)', async ({ page }) => {
    // Its own boot: one edit per live scenario, because a rerun replaces the
    // widgets underneath an in-flight keystroke sequence and the second edit gets
    // lost -- which is a harness fact, not a product one.
    const h = await openApp(page, 'broken-arrow');
    await waitTerminal(h.comp, 'rendered');
    const editor = page.locator('textarea').first();
    await typeInto(page, editor, 'flowchart TD\n  A[Broken]\n  A -->\n');
    await expect
      .poll(() => liveComponentFrame(page).then((frame) => currentState(frame)), { timeout: 90_000, message: 'broken text never reported invalid' })
      .toBe('invalid');
    const message = await (await liveComponentFrame(page)).locator('.mmd-panel--error').innerText();
    expect(message, 'the message has to point at a line').toMatch(/line \d+/i);
    expect(message.toLowerCase(), 'and stay in plain language').not.toMatch(/expecting|got '|jison|parseerror/);
  });

  /** Type like a user: select, clear, keystrokes, then blur to commit. */
  async function typeInto(page: PageLike, editor: ReturnType<PageLike['locator']>, text: string): Promise<void> {
    await editor.click();
    await editor.press('ControlOrMeta+a');
    await editor.press('Backspace');
    await editor.pressSequentially(text, { delay: 10 });
    await editor.blur();
    await expect(editor, 'Streamlit never kept the typed text').toHaveValue(text, { timeout: 30_000 });
  }

  test('the catalogue picker asks before overwriting, then loads its example (V-C 1, FR-020)', async ({ page }) => {
    const h = await openApp(page, 'good');
    await waitTerminal(h.comp, 'rendered');

    await pickOption(page, 'Diagram type', 'Sequence diagram');
    // The editor already holds text, so nothing may be overwritten silently.
    const guard = page.locator('[data-testid="stSidebar"]').getByText(/differs from this starting point/);
    await expect(guard, 'the app never silently replaces typed work').toBeVisible({ timeout: 30_000 });
    expect((await page.locator('textarea').first().inputValue()), 'the old text stayed put').toContain('flowchart');

    await page.getByRole('button', { name: 'Replace it' }).click();
    const editor = page.locator('textarea').first();
    await expect(editor, 'the sequence example never loaded').not.toHaveValue(/flowchart/, { timeout: 60_000 });
    await expect
      .poll(async () => (await componentPayload(page, await liveComponentFrame(page))).source, { timeout: 90_000, message: 'the new example never reached the component' })
      .toContain('sequenceDiagram');
    await expect
      .poll(() => liveComponentFrame(page).then((frame) => currentState(frame)), { timeout: 90_000 })
      .toBe('rendered');
    const chip = await (await liveComponentFrame(page)).locator('.mmd-chip').first().innerText();
    expect(chip.toLowerCase(), 'the component says what it drew').toContain('sequence');
  });

  test('the component sits in the sandbox the bridge was designed for', async ({ page }) => {
    const h = await openApp(page, 'good');
    await waitTerminal(h.comp, 'rendered');
    const facts = await h.comp.evaluate(() => ({
      origin: window.location.origin,
      href: window.location.href,
      writable: (() => {
        try {
          window.localStorage.setItem('mmd.probe', '1');
          window.localStorage.removeItem('mmd.probe');
          return 'writable';
        } catch (err) {
          return 'refused:' + String((err as Error).name);
        }
      })(),
      docKey: document.querySelector('meta[name="mmd-doc-key"]')?.content || null,
      hostAtTop: (() => {
        try {
          return !!(window.top as unknown as Record<string, unknown>).__mermaidGuiHost;
        } catch {
          return false;
        }
      })(),
    }));
    console.log('SANDBOX ' + JSON.stringify(facts));
    expect(facts.origin, 'a srcdoc document has no origin of its own').toBe('null');
    expect(facts.href).toBe('about:srcdoc');
    expect(facts.hostAtTop, 'only index.html owns storage and the address bar').toBe(true);
    expect(facts.docKey, 'the document carries a key, so the height relay can match it').toBeTruthy();
    // Whether the browser lets this frame touch storage at all is not something
    // the app may rely on, so persistence is the host's job either way.
    expect(['writable', 'refused:SecurityError'].some((word) => String(facts.writable).indexOf(word) === 0)).toBe(true);
  });
});
