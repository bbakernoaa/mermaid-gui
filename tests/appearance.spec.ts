import { expect, test } from '@playwright/test';
import { clippedLabels, component, openApp, setKnob, setSlider, setSource, svgColors, svgFontPx, waitTerminal } from './support';

// V-A: appearance control (story 1, FR-001..011) — mirrors
// contracts/appearance-contract.md §8 A-2/A-3/A-6/A-8.
test.describe('appearance', () => {
  test('text size spans at least 2x from smallest to largest (A-3)', async ({ page }) => {
    await openApp(page);
    await setSource(page, 'flowchart TD\n  A[Start] --> B{Question?}\n  B -->|yes| C[End]');
    await waitTerminal(page, 'rendered');

    await setSlider(page, 'Text size', 'left');
    await waitTerminal(page, 'rendered');
    const smallest = await svgFontPx(page);

    await setSlider(page, 'Text size', 'right');
    await waitTerminal(page, 'rendered');
    const largest = await svgFontPx(page);

    expect(largest / smallest, `largest ${largest}px / smallest ${smallest}px`).toBeGreaterThanOrEqual(2.0);
  });

  test('every scheme changes the whole diagram, not one element (FR-003)', async ({ page }) => {
    await openApp(page);
    await setSource(page, 'flowchart TD\n  A-->B\n  B-->C');
    await waitTerminal(page, 'rendered');
    const first = new Set(await svgColors(page));
    for (const scheme of ['Neutral', 'Dark', 'Forest']) {
      await setKnob(page, 'Colour scheme', scheme);
      await waitTerminal(page, 'rendered');
      const now = new Set(await svgColors(page));
      expect(now.size, `${scheme} paints the diagram with more than one colour`).toBeGreaterThan(1);
    }
    expect(new Set(await svgColors(page))).not.toEqual(first);
  });

  test('two base colours derive everything (A-6)', async ({ page }) => {
    await openApp(page);
    await setSource(page, 'flowchart TD\n  A[Text] --> B[More]');
    await waitTerminal(page, 'rendered');
    const plain = new Set(await svgColors(page));
    await setKnob(page, 'Base colours', 'light');
    await waitTerminal(page, 'rendered');
    const derived = await svgColors(page);
    expect(derived.length, 'derived colours paint the whole diagram').toBeGreaterThan(1);
    expect(new Set(derived).size, 'a derived palette has several steps').toBeGreaterThan(2);
    expect(new Set(derived), 'and it is not the stock palette').not.toEqual(plain);
  });

  test('largest text with open spacing does not clip labels (A-8)', async ({ page }) => {
    await openApp(page);
    await setSource(page, 'flowchart TD\n  A["A deliberately long label to test wrapping"] --> B["Another long label here"]');
    await setSlider(page, 'Text size', 'right');
    await setSlider(page, 'Spacing', 'right');
    await waitTerminal(page, 'rendered');
    expect(await clippedLabels(component(page)), 'no label may fall outside the drawing').toBe(0);
  });

  test('spacing changes the documented flowchart keys (FR-006)', async ({ page }) => {
    await openApp(page);
    await setSource(page, 'flowchart TD\n  A-->B\n  A-->C\n  B-->D\n  C-->D');
    await waitTerminal(page, 'rendered');
    const tight = await component(page).locator('svg').first().evaluate((node: Element) => node.getBBox().width);
    await setSlider(page, 'Spacing', 'right');
    await waitTerminal(page, 'rendered');
    const roomy = await component(page).locator('svg').first().evaluate((node: Element) => node.getBBox().width);
    expect(roomy, 'open spacing must be wider than compact').toBeGreaterThan(tight);
  });

  test('a diagram that sets its own theme wins, and says so (FR-009)', async ({ page }) => {
    // The payload for this case is resolved from the diagram's own front matter,
    // so the chip the preview shows is the resolver's own report, not a guess.
    await openApp(page, 'typed-theme');
    await waitTerminal(page, 'rendered');
    const colours = new Set(await svgColors(page));
    expect(colours.size, 'the front matter palette actually painted').toBeGreaterThan(1);
    await expect(component(page).locator('.mmd-chip[data-origin="frontmatter"]').first()).toContainText('set by your diagram text');
  });

  test('exports use the same appearance as the preview (A-2)', async ({ page }) => {
    await openApp(page);
    await setSlider(page, 'Text size', 'right');
    await setSource(page, 'flowchart TD\n  A[Exported] --> B[Same look]');
    await waitTerminal(page, 'rendered');
    const previewFont = await svgFontPx(page);
    await component(page).getByRole('button', { name: 'Export SVG' }).click();
    const captured = await component(page).locator('svg').first().evaluate((node: Element) =>
      getComputedStyle(node.querySelector('text') as Element).fontSize);
    expect(parseFloat(captured)).toBeCloseTo(previewFont, 1);
  });
});
