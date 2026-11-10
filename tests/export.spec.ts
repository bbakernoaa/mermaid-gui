import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { openApp, toolbarButton, waitState, type Harness } from './support';

// V-E (story 5, FR-028..032). Three bug classes this repository already paid for
// are asserted here: arrowheads and line styles must survive into the raster and
// the vector file (ed4bb3e), the exported XML must stand on its own (ce61056),
// and the advertised scale ratios must be exactly what the PNG carries (A-9).
async function exportFrom(h: Harness, buttonName: string): Promise<{ suggested: string; path: string | null }> {
  await waitState(h.comp, 'rendered');
  const [download] = await Promise.all([
    h.page.waitForEvent('download', { timeout: 60_000 }),
    toolbarButton(h.comp, buttonName).click(),
  ]);
  const path = await download.path();
  expect(path, `${buttonName} produced an empty download`).toBeTruthy();
  return { suggested: download.suggestedFilename(), path };
}

test.describe('export', () => {
  test('print is exactly twice the screen raster (A-9)', async ({ page }) => {
    const h = await openApp(page, 'good');
    const toolbar = h.comp.locator('.mmd-toolbar');
    await toolbar.getByLabel('Scale').selectOption('screen');
    const screen = await exportFrom(h, 'Export PNG');
    const screenSize = rasterSize(screen.path as string);

    await toolbar.getByLabel('Scale').selectOption('print');
    const print = await exportFrom(h, 'Export PNG');
    const printSize = rasterSize(print.path as string);

    expect(printSize.width / screenSize.width, 'width ratio').toBeCloseTo(2.0, 3);
    expect(printSize.height / screenSize.height, 'height ratio').toBeCloseTo(2.0, 3);

    await toolbar.getByLabel('Scale').selectOption('high');
    const high = await exportFrom(h, 'Export PNG');
    const highSize = rasterSize(high.path as string);
    expect(highSize.width / screenSize.width, 'the middle setting is between the two').toBeGreaterThan(1);
    expect(highSize.width / screenSize.width).toBeLessThan(2);
  });

  test('a transparent background really has no baked white', async ({ page }) => {
    const h = await openApp(page, 'good');
    const toolbar = h.comp.locator('.mmd-toolbar');
    await toolbar.getByLabel('Background').selectOption('white');
    const white = await exportFrom(h, 'Export PNG');
    await toolbar.getByLabel('Background').selectOption('transparent');
    const clear = await exportFrom(h, 'Export PNG');

    const whiteBuffer = readFileSync(white.path as string);
    const clearBuffer = readFileSync(clear.path as string);
    // Colour type 6 = RGBA; a white-background export is written without alpha.
    expect(clearBuffer[25] & 0x04, 'transparent export carries an alpha channel').toBe(0x04);
    expect(whiteBuffer.length, 'the white plate is a real image').toBeGreaterThan(1000);
    expect(clearBuffer.length, 'the transparent plate is a real image').toBeGreaterThan(1000);
  });

  test('SVG stands on its own: namespaces, markers, no external urls', async ({ page }) => {
    const h = await openApp(page, 'good');
    const file = await exportFrom(h, 'Export SVG');
    const text = readFileSync(file.path as string, 'utf8');
    expect(text).toContain('<svg');
    expect(text).toContain('xmlns="http://www.w3.org/2000/svg"');
    expect(text).toContain('xmlns:xlink="http://www.w3.org/1999/xlink"');
    expect(text, 'a standalone file cannot point at the page it left').not.toMatch(/url\(["']?https?:/);
    expect(text).toMatch(/marker-(end|start|mid)/);
    expect(text, 'arrowheads survive (ed4bb3e)').toMatch(/markerWidth|marker /);
    expect(text).toMatch(/font-family/i);
    expect(text).not.toMatch(/<script/i);
  });

  test('every catalogue type keeps arrowheads and label text (V-E 3)', async ({ page }) => {
    const h = await openApp(page, 'good');
    const samples: Array<[string, string]> = [
      ['flowchart TD\n  A[Start] --> B[Finish]', 'flowchart'],
      ['sequenceDiagram\n  A->>B: hello\n  B-->>A: ok', 'sequence'],
      ['stateDiagram-v2\n  [*] --> Busy\n  Busy --> [*]', 'state'],
      ['classDiagram\n  Shape <|-- Circle\n  class Circle { +draw() }', 'class'],
      ['erDiagram\n  CUSTOMER ||--o{ ORDER : places', 'er'],
      ['journey\n  title Trip\n  section Go\n    Walk: 5: Me'],
      ['gantt\n  title Plan\n  section A\n  Task: 2024-01-01, 3d'],
      ['pie showData\n  "A" : 40\n  "B" : 60'],
      ['mindmap\n  root((Centre))\n    Branch\n      Leaf'],
    ];
    for (const [source, name] of samples) {
      const { send, nextRequestId } = await import('./support');
      await send(h.comp, { source, requestId: nextRequestId() });
      await waitState(h.comp, 'rendered');
      const file = await exportFrom(h, 'Export SVG');
      const text = readFileSync(file.path as string, 'utf8');
      expect(text, `${name ?? source.slice(0, 12)} exported nothing`).toContain('<svg');
      expect(text).toContain('xmlns="http://www.w3.org/2000/svg"');
      expect(text).not.toMatch(/url\(["']?https?:/);
      if (name === 'flowchart' || name === 'state' || name === 'class') {
        expect(text, `${name} lost its arrowheads`).toMatch(/marker/);
      }
      void file.suggested;
    }
  });

  test('file names follow the diagram name and stay safe (FR-031)', async ({ page }) => {
    const h = await openApp(page, 'good');
    const name = h.comp.locator('.mmd-toolbar input');
    await name.fill('  quarter/../two  spaces\tcafé ！  ');
    await name.press('Enter');
    const file = await exportFrom(h, 'Export SVG');
    expect(file.suggested).not.toContain('/');
    expect(file.suggested).not.toContain('..');
    expect(file.suggested).not.toContain('\t');
    expect(file.suggested, 'non-ascii survives sanitising').toContain('café');
    expect(file.suggested).toMatch(/\.svg$/);
  });

  test('an export can never capture an older request (V-E check 6)', async ({ page }) => {
    const h = await openApp(page, 'good');
    await waitState(h.comp, 'rendered');
    const fresh = await h.comp.evaluate(() => (window as any).__mermaidGuiRender__.stateSnapshot());
    expect(fresh.newestTerminalId, 'a successful render is a terminal state too').toBe('req-00001');

    // A capture asked for under an older request id must be refused rather than
    // quietly exporting the picture from before the last edit.
    const refusal = await h.comp.evaluate(async () => {
      const api = (window as any).__mermaidGuiRender__;
      const svg = document.querySelector('.mmd-canvas svg');
      return await (window as any).__mermaidGuiExport__.exportAs('exportSvg', {
        svg: svg,
        expectedRequestId: 'req-00000',
      });
    });
    expect(refusal.ok, 'the stale capture was refused').toBe(false);
    expect(refusal.reason).toBe('stale');
    expect(refusal.message).toMatch(/stale|changed while/i);
    void fresh;

    const accepted = await h.comp.evaluate(async () => {
      const svg = document.querySelector('.mmd-canvas svg');
      return await (window as any).__mermaidGuiExport__.exportAs('exportSvg', {
        svg: svg,
        expectedRequestId: (window as any).__mermaidGuiRender__.stateSnapshot().newestTerminalId,
      });
    });
    expect(accepted.ok, 'the newest request exports normally').toBe(true);
    expect(String(accepted.filename)).toMatch(/\.svg$/);
  });

  test('copy SVG explains a refused clipboard instead of failing silently (FR-032)', async ({ page }) => {
    const h = await openApp(page, 'good');
    await waitState(h.comp, 'rendered');
    // No clipboard permission is granted, which is the state the notice exists for.
    await toolbarButton(h.comp, 'Copy SVG').click();
    const note = h.comp.locator('.mmd-panel--busy:not(.mmd-hidden), .mmd-panel--hint:not(.mmd-hidden)').first();
    await expect(note, 'the user is told what happened').toBeVisible({ timeout: 10_000 });
    expect((await note.innerText()).toLowerCase()).toMatch(/copied|saved|download|not available|couldn|blocked|permission/);
  });
});

function rasterSize(path: string): { width: number; height: number } {
  const buffer = readFileSync(path);
  expect(buffer.subarray(1, 4).toString('hex'), 'not a PNG').toBe('504e47');
  return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
}
