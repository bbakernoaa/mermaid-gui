import { expect, test } from '@playwright/test';
import {
  badge,
  component,
  consoleProblems,
  emptyPanelSlot,
  errorPanel,
  expectNoErrors,
  labelStrings,
  noticePanel,
  visibleSvg,
  openFixture,
  pageErrors,
  send,
  svg,
  textFontPx,
  waitState,
  waitTerminal,
} from './support';

// US1: every state is reachable, and a diagram that cannot be drawn says so in
// plain words and points at the line (FR-013..FR-018, quickstart V-B).
test.describe('preview states and messages', () => {
  test('a valid diagram reaches "Up to date" with a picture and no error', async ({ page }) => {
    await openFixture(page, 'good');
    await waitState(page, 'rendered');
    await expect(svg(page)).toBeVisible();
    await expect(badge(page, 'invalid')).toHaveCount(0);
    await expect(errorPanel(page)).toBeHidden();
    expect(await textFontPx(page)).toBeGreaterThan(8);
    expect(await component(page).locator('.mmd-snippet').count(), 'a good diagram shows no snippet').toBe(0);
    void consoleProblems; void pageErrors;
    expectNoErrors(page);
  });

  test('an unfinished arrow names a line and quotes the text', async ({ page }) => {
    await openFixture(page, 'broken-arrow');
    await waitState(page, 'invalid');
    const panel = errorPanel(page);
    await expect(panel).toBeVisible();
    const message = await panel.innerText();
    expect(message.toLowerCase(), 'no parser jargon in the headline').not.toMatch(/expecting|got '|jison|parseerror/);
    expect(message).toMatch(/line \d+/i);
    await expect(panel.locator('.mmd-snippet').first()).toBeVisible();
    await expect(panel.locator('.mmd-caret')).toBeVisible();
  });

  test('text that is not a diagram at all is reported, never a blank box', async ({ page }) => {
    await openFixture(page, 'garbage');
    await waitState(page, 'invalid');
    await expect(errorPanel(page)).toBeVisible();
    expect((await errorPanel(page).innerText()).trim().length, 'message is not empty').toBeGreaterThan(20);
    await expect(svg(page)).toHaveCount(0);
  });

  test('blank text waits for input instead of reporting an error', async ({ page }) => {
    await openFixture(page, 'empty');
    await waitState(page, 'empty');
    const slot = emptyPanelSlot(page);
    await expect(slot).toBeVisible();
    await expect(errorPanel(page)).toBeHidden();
    expect(await slot.innerText()).toMatch(/type|start|waiting/i);
  });

  test('a first word that names no diagram type says which word is wrong', async ({ page }) => {
    await openFixture(page, 'unknown-type');
    await waitState(page, 'invalid');
    const message = await errorPanel(page).innerText();
    expect(message).not.toMatch(/SyntaxError|Parse error: /);
    expect(message).toContain('wat');
    expect(message.toLowerCase()).toMatch(/not a diagram type|flowchart/);
  });

  test('a renderer that cannot be loaded is reported, not swallowed', async ({ page }) => {
    await openFixture(page, 'no-renderer');
    await waitTerminal(page, 'invalid');
    await expect(errorPanel(page)).toBeVisible();
    expect((await errorPanel(page).innerText()).toLowerCase()).toMatch(/could not draw|not draw|renderer|reload|initiali|load/);
  });

  test('the 50000-character ceiling renders', async ({ page }) => {
    await openFixture(page, 'at-limit');
    await waitState(page, 'rendered');
    await expect(svg(page)).toHaveCount(1);
    // 1155 nodes is enough to make the next navigation crash a shared renderer,
    // so the picture is released as soon as it has been proven to exist.
    await component(page).evaluate(() => {
      const host = document.querySelector('.mmd-canvas');
      if (host) host.innerHTML = '';
    });
  });

  test('one character over the ceiling is refused, visibly and without a picture', async ({ page }) => {
    await openFixture(page, 'too-large');
    // Read only the panel that is actually up: innerText() on an absent panel
    // waits for the full action timeout, which is how this test used to spend
    // two minutes before the harness killed it.
    const panel = noticePanel(page).or(errorPanel(page)).first();
    await expect(panel).toBeVisible({ timeout: 30_000 });
    const copy = await panel.innerText();
    expect(copy).toMatch(/50,?000|too large|ceiling/i);
    await expect(badge(page, 'invalid')).toBeVisible();
    await expect(svg(page)).toHaveCount(0);
  });

  test('a 500-node diagram is never called broken (SC-003)', async ({ page }) => {
    await openFixture(page, 'large');
    await waitState(page, 'rendered');
    await expect(component(page).locator('svg g.node').first()).toBeVisible();
    void consoleProblems; void pageErrors;
    expectNoErrors(page);
  });

  test('a 120-line diagram renders', async ({ page }) => {
    await openFixture(page, 'long');
    await waitState(page, 'rendered');
    await expect(svg(page)).toHaveCount(1);
  });

  test('angle-bracket notation survives the HTML parser (02ae868 / 89bf9cc)', async ({ page }) => {
    await openFixture(page, 'notation');
    await waitState(page, 'rendered');
    // Mermaid rewrites <<...>> into its own guillemet stereotype, and the note
    // text keeps the apostrophe and the literal <b> markup, which is exactly the
    // bug class these two commits introduced. A cut-off tag would show up here as
    // an HTML entity instead.
    const labels = (await labelStrings(page)).join('\n');
    expect(labels).toMatch(/«interface»|<<interface>>/);
    expect(labels).toMatch(/«enumeration»|<<enumeration>>/);
    expect(labels).toContain('Beware');
    expect(labels).toContain("dog's");
    expect(labels).toContain('<b> markup </b>');
    expect(labels).not.toMatch(/&lt;|&gt;/);
    expectNoErrors(page);
  });

  test('the last good picture survives a broken edit (FR-016)', async ({ page }) => {
    await openFixture(page, 'good');
    await waitState(page, 'rendered');
    const before = await visibleSvg(page).innerHTML();
    await send(component(page), { source: 'flowchart TD\n  A[Start] -->\n' });
    await waitState(page, 'invalid');
    await expect(errorPanel(page)).toBeVisible();
    const shown = visibleSvg(page);
    await expect(shown).toBeVisible();
    expect(await shown.innerHTML(), 'the picture must not be thrown away').toBe(before);
  });

  test('fixing the text clears the message with no extra click', async ({ page }) => {
    await openFixture(page, 'broken-arrow');
    await waitState(page, 'invalid');
    await send(component(page), { source: 'flowchart TD\n  A[Start] --> B[End]\n' });
    await waitState(page, 'rendered');
    await expect(errorPanel(page)).toBeHidden();
  });

  test('the export toolbar appears only once there is a picture', async ({ page }) => {
    await openFixture(page, 'empty');
    await waitState(page, 'empty');
    await expect(component(page).getByRole('button', { name: /Export PNG/ })).toHaveCount(0);

    await openFixture(page, 'good');
    await waitState(page, 'rendered');
    await expect(component(page).getByRole('button', { name: 'Export PNG' })).toBeVisible();
    await expect(component(page).getByRole('button', { name: 'Export SVG' })).toBeVisible();
    await expect(component(page).getByRole('button', { name: 'Copy SVG' })).toBeVisible();
    await expect(visibleSvg(page)).toBeVisible();
    expect((await labelStrings(page)).join(' ')).toContain('Start');
  });
});
