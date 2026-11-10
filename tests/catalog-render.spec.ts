import { expect, test } from '@playwright/test';
import { MANIFEST, expectNoErrors, labelStrings, openApp, send, waitState, waitTerminal } from './support';

// V-C / SC-002: every example the app actually ships must render, with nothing
// thrown to the console. The sources and the resolved appearance both come from
// tests/.generated/manifest.json, which tests/build_fixture.py produced from
// templates.py -- so the test cannot drift from the catalogue, and each example
// is drawn with the spacing its own diagram family resolves to.
const ROWS = MANIFEST.catalog.rows;

test.describe('catalogue', () => {
  test('the catalogue covers all nine types plus a blank starting point', async () => {
    const types = new Set(ROWS.map((row) => row.typeId));
    for (const required of ['flowchart', 'sequence', 'class', 'state', 'er', 'gantt', 'pie', 'journey', 'mindmap']) {
      expect(types.has(required), `catalogue must include ${required}`).toBe(true);
    }
    expect(types.has('blank'), 'and a blank slate').toBe(true);
    expect(ROWS.length).toBeGreaterThanOrEqual(19);
    const byType: Record<string, number> = {};
    ROWS.forEach((row) => {
      byType[row.typeId] = (byType[row.typeId] || 0) + 1;
    });
    Object.keys(byType).forEach((type) => {
      if (type === 'blank') return;
      expect(byType[type], `${type} needs plain and styled examples`).toBeGreaterThanOrEqual(2);
    });
  });

  test('every example renders as a real picture (SC-002)', async ({ page }) => {
    const h = await openApp(page, 'good');
    for (const row of ROWS) {
      const key = `${row.typeId}/${row.purpose}`;
      const variant = MANIFEST.catalog.plain[key];
      expect(variant, `no resolved payload was built for ${key}`).toBeTruthy();
      await send(h.comp, {
        source: row.source,
        appearance: variant.appearance,
        chrome: variant.chrome,
      });
      // A blank starting point has nothing to draw, and must be reported as
      // waiting rather than broken (US2 scenario 4); every other example must paint.
      const expected = row.typeId === 'blank' && !row.source.trim() ? 'empty' : 'rendered';
      await waitState(h.comp, expected);
      const svg = h.comp.locator('.mmd-canvas svg');
      await expect(svg, `${key} drew nothing`).toHaveCount(expected === 'rendered' ? 1 : 0);
      const drawn = await svg.locator('path, rect, circle, polygon, ellipse, text, line, g.node').count();
      expect(drawn, `${key} is not a two-line toy`).toBeGreaterThanOrEqual(row.minElements);
      if (expected === 'rendered') {
        const labels = await labelStrings(h.comp);
        expect(labels.join(' ').length, `${key} is drawn but says nothing`).toBeGreaterThan(0);
      }
      expectNoErrors(page);
    }
  });

  // Regression guard for the bug class the two commits fixed: diagram text with
  // angle-bracket notation used to be eaten by the HTML parser.
  test('class stereotypes and generics survive (02ae868 / 89bf9cc)', async ({ page }) => {
    const h = await openApp(page, 'notation');
    await waitTerminal(h.comp, 'rendered');
    const labels = (await labelStrings(h.comp)).join('\n');
    expect(labels).toMatch(/«interface»|<<interface>>/);
    expect(labels).toMatch(/«enumeration»|<<enumeration>>/);
    expect(labels).toMatch(/Shelter<T>|Shelter~T~/);
    expect(labels, 'markup inside a note stays literal text, never an element').toContain('<b> markup </b>');
    expect(labels).not.toMatch(/&lt;|&quot;/);
  });

  test('the blank starting point is an empty editor, not a broken one', async ({ page }) => {
    const h = await openApp(page, 'empty');
    await waitState(h.comp, 'empty');
    await expect(h.comp.locator('.mmd-canvas svg')).toHaveCount(0);
    expect((await labelStrings(h.comp).catch(() => [])) as string[]).toEqual([]);
  });
});


