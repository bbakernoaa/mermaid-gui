import { expect, test } from '@playwright/test';
import {
  hostHeightMessages,
  labelStrings,
  MANIFEST,
  nextRequestId,
  openApp,
  send,
  svg,
  svgLabels,
  toolbar,
  visibleSvg,
  waitState,
  waitTerminal,
} from './support';

// Editing must stay reliable in a plain textarea (FR-037), and the page is the
// only place that can reach the app's own widget. These run against the shipped
// host_bridge.js in the harness host document.
test.describe('keyboard editing', () => {
  test('Tab indents, Shift-Tab outdents, and a selection indents every line', async ({ page }) => {
    // 'flowchart TD' is 12 characters, the newline is 12, so the second line
    // begins at 13. Every caret position below is stated from that layout.
    const box = await openEditor(page, 'flowchart TD\nA-->B\nC-->D');

    await caret(page, 13, 13);
    await page.keyboard.press('Tab');
    expect(await box.inputValue(), 'one Tab is two spaces').toBe('flowchart TD\n  A-->B\nC-->D');

    await caret(page, 15, 15);
    await page.keyboard.press('Tab');
    expect(await box.inputValue()).toBe('flowchart TD\n    A-->B\nC-->D');

    await caret(page, 15, 15);
    await page.keyboard.press('Shift+Tab');
    expect(await box.inputValue(), 'Shift-Tab removes exactly one level').toBe('flowchart TD\n  A-->B\nC-->D');

    // A selection indents every line it touches. The range is stated by lines so
    // this test does not depend on how many spaces each earlier step added.
    const twoLines = (await box.inputValue()).split('\n');
    const from = twoLines[0].length + 1;
    const to = (await box.inputValue()).length;
    await caret(page, from, to);
    await page.keyboard.press('Tab');
    expect(await box.inputValue(), 'every line the selection touches is indented').toBe('flowchart TD\n    A-->B\n  C-->D');

    await caret(page, 0, (await box.inputValue()).length);
    await page.keyboard.press('Shift+Tab');
    expect(await box.inputValue(), 'and Shift-Tab takes one level off each of them').toBe('flowchart TD\n  A-->B\nC-->D');

    await setText(page, 'A-->B\nC');
    await caret(page, 0, 0);
    await page.keyboard.press('Tab');
    expect(await box.inputValue(), 'Tab works from the very first character').toBe('  A-->B\nC');
    await page.keyboard.press('Shift+Tab');
    expect(await box.inputValue(), 'and Shift-Tab puts it back').toBe('A-->B\nC');
    await caret(page, 0, 0);
    await page.keyboard.press('Shift+Tab');
    expect(await box.inputValue(), 'with no indent left, Shift-Tab changes nothing').toBe('A-->B\nC');

    // A Tab that indents keeps the caret in the editor, which is the point of FR-037.
    await setText(page, 'flowchart TD');
    await caret(page, 0, 0);
    await page.keyboard.press('Tab');
    expect(await page.evaluate(() => document.activeElement?.id || ''), 'Tab stays in the editor').toBe('mmd-prose');

    // A Shift-Tab with nothing to remove is left to the browser: it fires no input
    // event, so the page's own tab order stays intact and a keyboard user can
    // always leave.
    await setText(page, 'flowchart TD');
    await caret(page, 0, 0);
    const events = await page.evaluate(() => {
      const box = document.getElementById('mmd-prose');
      (window as any).__mmdCounted = 0;
      box.addEventListener('input', () => ((window as any).__mmdCounted += 1));
      return true;
    });
    await page.keyboard.press('Shift+Tab');
    expect(events).toBe(true);
    expect(await page.evaluate(() => (window as any).__mmdCounted), 'a no-op outdent fires no input event').toBe(0);
  });

  test('the line the caret is on is stated next to the editor (FR-033)', async ({ page }) => {
    await openEditor(page, 'flowchart TD\n  A-->B\n  C-->D\n  E');
    await caret(page, 13, 13);
    await expect(page.locator('[data-testid="mmd-caret-readout"]')).toHaveText('Line 2 of 4');
    await caret(page, 30, 30);
    await expect(page.locator('[data-testid="mmd-caret-readout"]')).toHaveText('Line 4 of 4');

    // It is the Tab key that moves the caret, so the readout has to follow it.
    await caret(page, 13, 13);
    await page.keyboard.press('Tab');
    await expect(page.locator('[data-testid="mmd-caret-readout"]')).toHaveText('Line 2 of 4');
    expect(await page.locator('#mmd-prose').inputValue()).toBe('flowchart TD\n    A-->B\n  C-->D\n  E');
  });

  test('the keystroke reaches the widget Streamlit reads', async ({ page }) => {
    const box = await openEditor(page, 'flowchart TD', true);
    await caret(page, 0, 0);
    await page.keyboard.press('Tab');
    const seen = await page.evaluate(() => (window as any).__mmdInputEvent || '');
    expect(seen, 'React-based widgets only update on a real input event').toBe('  flowchart TD');
    const commit = await page.evaluate(() => (window as any).__mmdChangeEvent || '');
    expect(commit, 'and the value is offered for commit, which is how a text_area saves').toBe('  flowchart TD');
    expect(await box.inputValue()).toBe('  flowchart TD');
  });
});

async function openEditor(page: import('@playwright/test').Page, text: string, spy = false) {
  await page.goto('/tests/.generated/runner.html?case=good', { waitUntil: 'domcontentloaded' });
  await page.evaluate((args) => {
    const box = document.createElement('textarea');
    box.value = args.text;
    box.id = 'mmd-prose';
    document.body.appendChild(box);
    (window as any).__mermaidGuiHost.assistEditors(document);
    if (args.spy) {
      (window as any).__mmdInputEvent = '';
      (window as any).__mmdChangeEvent = '';
      box.addEventListener('input', () => ((window as any).__mmdInputEvent = box.value));
      box.addEventListener('change', () => ((window as any).__mmdChangeEvent = box.value));
    }
  }, { text, spy });
  return page.locator('#mmd-prose');
}

async function caret(page: import('@playwright/test').Page, start: number, end: number): Promise<void> {
  await page.locator('#mmd-prose').evaluate((node, range) => {
    const box = node as HTMLTextAreaElement;
    box.focus();
    box.setSelectionRange(range.start, range.end);
  }, { start, end });
}

async function setText(page: import('@playwright/test').Page, text: string): Promise<void> {
  await page.locator('#mmd-prose').evaluate((node, value) => {
    const box = node as HTMLTextAreaElement;
    box.value = value;
    box.focus();
  }, text);
}

// V-F (story 6, FR-033..037): the preview gets out of the way, the interface
// theme never touches the picture, and typing stays responsive on heavy text.
test.describe('preview comfort', () => {
  test('a long diagram gets the height it needs and reports it to the host', async ({ page }) => {
    const h = await openApp(page, 'long');
    await waitState(h.comp, 'rendered');

    // FR-034: the component measures itself and index.html sizes the frame, so the
    // relay has to arrive carrying the document it belongs to.
    const heights = await hostHeightMessages(page);
    expect(heights.length, 'the component never reported a height').toBeGreaterThan(0);
    const last = heights[heights.length - 1];
    expect(String(last.docKey || last.key || ''), 'height travels with its document').not.toBe('');
    expect(Number(last.height), 'a 120-line diagram is not squeezed into a small box').toBeGreaterThan(400);

    // There must be no nested scroll area: the content fits its own document.
    const overflow = await h.comp.evaluate(() => {
      const scrollers = Array.from(document.querySelectorAll('.mmd-viewport, .mmd-canvas, body, html')).filter((node) => {
        const element = node as HTMLElement;
        return element.scrollHeight - element.clientHeight > 4 || element.scrollWidth - element.clientWidth > 4;
      });
      return { scrollers: scrollers.map((node) => String(node.className || node.tagName)) };
    });
    expect(overflow.scrollers, 'the preview must not need its own scroll bar').toEqual([]);
    await expect(toolbar(h.comp)).toBeVisible();
  });

  test('overview to readable labels in three zoom actions (SC-008)', async ({ page }) => {
    const h = await openApp(page, 'good');
    await waitTerminal(h.comp, 'rendered');
    const bar = h.comp.locator('.mmd-zoom');
    await expect(bar.getByRole('button', { name: 'Zoom in' })).toBeVisible();

    // Height of a real label on screen: zoom is applied as CSS `zoom`, which
    // changes the layout box without touching the font-size declaration.
    const labelHeight = () => svgLabels(h.comp).first().evaluate((node) => Math.round(node.getBoundingClientRect().height * 100) / 100);
    const pictureWidth = () => visibleSvg(h.comp).evaluate((node) => Math.round(node.getBoundingClientRect().width));
    const zoomStyle = () => h.comp.evaluate(() => (document.querySelector('.mmd-canvas .mmd-render-host') as HTMLElement).style.zoom || 'fit');

    await bar.getByRole('button', { name: /Fit/ }).click();
    const fitted = await labelHeight();
    expect(fitted, 'the preview opens fitted, so nothing needs scrolling').toBeGreaterThan(6);

    // The overview: as small as it goes.
    for (let i = 0; i < 4; i += 1) await bar.getByRole('button', { name: 'Zoom out' }).click();
    const overview = await labelHeight();
    expect(overview, 'zooming out really shrinks the picture').toBeLessThan(fitted);
    const startWidth = await pictureWidth();

    // And back to readable in at most three actions (SC-008).
    let actions = 0;
    while (actions < 3) {
      await bar.getByRole('button', { name: 'Zoom in' }).click();
      actions += 1;
      if ((await labelHeight()) >= overview * 2) break;
    }
    expect(actions, 'readable within three zoom-ins from the overview').toBeLessThanOrEqual(3);
    expect(await labelHeight(), 'the labels actually grew').toBeGreaterThanOrEqual(overview * 2);
    expect(await pictureWidth(), 'and the picture grew with them').toBeGreaterThan(startWidth);

    await bar.getByRole('button', { name: /Fit/ }).click();
    await expect(h.comp.locator('.mmd-zoom-label')).toHaveText(/fit/i);
    expect(await zoomStyle(), 'fit leaves no zoom transform behind').toBe('fit');
    await bar.getByRole('button', { name: 'Reset zoom' }).click();
    const resetLabel = await h.comp.locator('.mmd-zoom-label').innerText();
    expect(resetLabel, '1:1 returns to one hundred percent').toBe('100%');
    expect(await zoomStyle(), 'and it leaves an explicit zoom behind').not.toBe('fit');
  });

  test('the interface theme changes the chrome and byte-for-byte nothing else (FR-036)', async ({ page }) => {
    const light = await openApp(page, 'good');
    await waitState(light.comp, 'rendered');
    const strip = (text: string) => text.replace(/mmd-[\w-]+/g, 'X');
    const lightMarkup = strip(await svg(light.comp).evaluate((node) => node.outerHTML));

    // A second page, not a second navigation: reusing the first page detaches the
    // frame under test and the comparison then proves nothing.
    const dark = await openApp(await page.context().newPage(), 'dark-interface');
    await waitState(dark.comp, 'rendered');
    const darkMarkup = strip(await svg(dark.comp).evaluate((node) => node.outerHTML));

    const chromeOf = (target: typeof light.comp) => target.evaluate(() => {
      const root = document.querySelector('#mmd-root') as HTMLElement;
      const status = document.querySelector('.mmd-status') as HTMLElement;
      const plate = document.querySelector('.mmd-viewport') as HTMLElement;
      return {
        interface: root.getAttribute('data-interface') || '',
        rootBackground: getComputedStyle(root).backgroundColor,
        statusColour: getComputedStyle(status).color,
        plateBackground: getComputedStyle(plate).backgroundColor,
      };
    });
    const lightChrome = await chromeOf(light.comp);
    const darkChrome = await chromeOf(dark.comp);

    expect(MANIFEST.baked.good.source, 'both cases draw the same text').toBe(MANIFEST.baked['dark-interface'].source);
    expect(darkMarkup, 'the diagram is identical bytes in either interface mode').toBe(lightMarkup);
    expect(darkChrome.interface, 'the component knows which interface it is in').toBe('dark');
    expect(lightChrome.interface).toBe('auto');
    expect(darkChrome.rootBackground, 'the chrome follows the interface theme').not.toBe(lightChrome.rootBackground);
    expect(darkChrome.statusColour, 'and so does the chrome text').not.toBe(lightChrome.statusColour);
    // The plate behind the picture stays light in both: the picture is the user's,
    // not the interface's, and the appearance contract forbids mixing them.
    expect(darkChrome.plateBackground, 'the diagram plate is untouched by the interface theme').toBe(lightChrome.plateBackground);
    expect((await labelStrings(dark.comp)).join(' ')).toContain('Start');
  });

  // SC-009's own bound: "any single appearance or text change reflected on screen
  // within 3 seconds on ordinary hardware". CI runners are slower than a laptop, so
  // the assertion is the spec's number rather than a locally-measured one; the value
  // is printed either way, so a regression is visible before it becomes a failure.
  test('a text change on a 120-line diagram is on screen within 3 seconds (SC-009)', async ({ page }) => {
    const h = await openApp(page, 'long');
    await waitState(h.comp, 'rendered');
    const source = MANIFEST.baked.long.source + '\n';

    const started = Date.now();
    await send(h.comp, { source, requestId: nextRequestId() });
    await waitState(h.comp, 'rendered');
    const elapsed = Date.now() - started;
    console.log(`SC-009 keystroke round trip: ${elapsed} ms`);
    expect(elapsed, `${elapsed} ms from keystroke to picture on a 120-line diagram`).toBeLessThan(3000);

    // The debounce is a floor, not a queue: a second change right away must still
    // land promptly rather than waiting behind the first.
    const again = Date.now();
    await send(h.comp, { source: source + '\n', requestId: nextRequestId() });
    await waitState(h.comp, 'rendered');
    const second = Date.now() - again;
    console.log(`SC-009 second edit: ${second} ms`);
    expect(second, 'back-to-back edits stay responsive').toBeLessThan(3000);
  });

  test('zoom never re-renders the diagram (FR-035, cost check)', async ({ page }) => {
    const h = await openApp(page, 'good');
    await waitState(h.comp, 'rendered');
    const snapshot = () => h.comp.evaluate(() => {
      const node = document.querySelector('.mmd-canvas svg');
      const api = (window as any).__mermaidGuiRender__;
      return { id: node ? node.getAttribute('id') : null, seq: api.stateSnapshot().renderSeq };
    });
    const before = await snapshot();
    expect(before.id, 'the picture must carry an id from the render that made it').toBeTruthy();
    await h.comp.locator('.mmd-zoom').getByRole('button', { name: 'Zoom in' }).click();
    await h.comp.waitForTimeout(250);
    const after = await snapshot();
    expect(after.seq, 'zooming did not ask mermaid to draw again').toBe(before.seq);
    expect(after.id, 'the same <svg> was scaled, not replaced').toBe(before.id);
  });
});
