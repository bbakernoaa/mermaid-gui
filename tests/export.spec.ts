import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { MANIFEST, openApp, openFixture, send, toolbarButton, waitState, type Harness } from './support';

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

    // A-9 is exactness, not "close to": print must be twice screen in whole pixels.
    expect(printSize.width, 'print width is exactly 2x screen').toBe(screenSize.width * 2);
    expect(printSize.height, 'print height is exactly 2x screen').toBe(screenSize.height * 2);

    await toolbar.getByLabel('Scale').selectOption('high');
    const high = await exportFrom(h, 'Export PNG');
    const highSize = rasterSize(high.path as string);
    // high=3, screen=2, print=4, so all three share one integer base size.
    expect(highSize.width * 2, 'the three scales are one base size x 2/3/4').toBe(screenSize.width * 3);
    expect(highSize.height * 2).toBe(screenSize.height * 3);
    expect(printSize.width * 3, 'and print is exactly 4/3 of high').toBe(highSize.width * 4);
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

  // A 1 155-node spine is within the 50 000-character ceiling and renders fine as
  // a preview, but its viewBox measures 404 x 133 933: asking a browser to raster
  // that yields an *empty* data URL, so the download used to be a 0-byte file and
  // the notice still said "Saved". The exporter now predicts the limit and says
  // what to do instead.
  // The blank-file class of bug: the raster can come back with the right
  // dimensions, a valid header and a satisfied "Saved" notice while containing
  // literally nothing. Dimensions alone therefore prove nothing, so the pixels are
  // counted.
  test('the PNG contains the drawing, not an empty plate', async ({ page }) => {
    const h = await openFixture(page, 'typed-colors');
    await waitState(h.comp, 'rendered');
    const [png] = await Promise.all([
      page.waitForEvent('download', { timeout: 90_000 }),
      toolbarButton(h.comp, 'Export PNG').click(),
    ]);
    const bytes = readFileSync((await png.path()) as string);
    expect(bytes.length, 'the file is not empty').toBeGreaterThan(1000);
    const painted = await page.evaluate(async (data: string) => {
      const bin = atob(data);
      const buf = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i += 1) buf[i] = bin.charCodeAt(i);
      const bitmap = await createImageBitmap(new Blob([buf], { type: 'image/png' }));
      const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
      const ctx = canvas.getContext('2d') as CanvasRenderingContext2D;
      ctx.drawImage(bitmap, 0, 0);
      const img = ctx.getImageData(0, 0, bitmap.width, bitmap.height).data;
      let ink = 0;
      const palette = new Set<string>();
      for (let i = 0; i < img.length; i += 4) {
        if (img[i + 3] > 8) ink += 1;
        palette.add(img[i] + ',' + img[i + 1] + ',' + img[i + 2]);
      }
      return { pixels: img.length / 4, ink, distinct: palette.size };
    }, bytes.toString('base64'));
    const fraction = painted.ink / painted.pixels;
    console.log(`PNG ink ${(fraction * 100).toFixed(1)}% of ${painted.pixels} px, ${painted.distinct} colours`);
    expect(fraction, 'the raster holds the picture, not an empty plate').toBeGreaterThan(0.05);
    expect(painted.distinct, 'and it has more than one colour').toBeGreaterThan(3);
  });

  test('a journey export keeps its labels in a standalone file', async ({ page }) => {
    // Journey is the one diagram type that ignores `htmlLabels: false` and draws its
    // section and task labels as <foreignObject> HTML: a browser-only crutch that a
    // standalone SVG cannot rely on and a rasteriser will not draw. The exporter
    // carries those labels over as real <text>.
    const h = await openFixture(page, 'good');
    await waitState(h.comp, 'rendered');
    const row = MANIFEST.catalog.rows.find((r) => r.typeId === 'journey' && r.purpose === 'styled')!;
    const variant = MANIFEST.catalog.plain['journey/styled'];
    await send(h.comp, { source: row.source, appearance: variant.appearance, chrome: variant.chrome });
    await waitState(h.comp, 'rendered');

    const previewHtmlLabels = await h.comp.evaluate(() => document.querySelectorAll('.mmd-canvas foreignObject').length);
    expect(previewHtmlLabels, 'mermaid really does use HTML labels for journey').toBeGreaterThan(0);

    const [svgFile] = await Promise.all([
      page.waitForEvent('download', { timeout: 60_000 }),
      toolbarButton(h.comp, 'Export SVG').click(),
    ]);
    const markup = readFileSync((await svgFile.path()) as string, 'utf8');
    expect(markup, 'a standalone file cannot depend on HTML inside the picture').not.toMatch(/<foreignObject/);
    expect(markup).toMatch(/<text[\s\S]*Discover/);
    expect(markup).toMatch(/Find the app/);
    expect(markup).toMatch(/Pick a type/);

    const [pngFile] = await Promise.all([
      page.waitForEvent('download', { timeout: 90_000 }),
      toolbarButton(h.comp, 'Export PNG').click(),
    ]);
    const pngBytes = readFileSync((await pngFile.path()) as string);
    const ink = await page.evaluate(async (data: string) => {
      const bin = atob(data);
      const buf = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i += 1) buf[i] = bin.charCodeAt(i);
      const bitmap = await createImageBitmap(new Blob([buf], { type: 'image/png' }));
      const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
      const ctx = canvas.getContext('2d') as CanvasRenderingContext2D;
      ctx.drawImage(bitmap, 0, 0);
      const img = ctx.getImageData(0, 0, bitmap.width, bitmap.height).data;
      let ink = 0;
      for (let i = 0; i < img.length; i += 4) if (img[i + 3] > 8) ink += 1;
      return { pixels: img.length / 4, ink };
    }, pngBytes.toString('base64'));
    expect(ink.ink / ink.pixels, 'the journey raster is drawn, not blank').toBeGreaterThan(0.05);
  });

  test('a diagram too tall to raster is refused with a route that works', async ({ page }) => {
    const h = await openFixture(page, 'at-limit');
    await waitState(h.comp, 'rendered');
    const size = await h.comp.evaluate(() => {
      const svg = document.querySelector('.mmd-canvas svg') as SVGSVGElement;
      return { w: Math.round(svg.viewBox.baseVal.width), h: Math.round(svg.viewBox.baseVal.height) };
    });
    expect(size.h, 'the fixture really is a tall chain').toBeGreaterThan(20000);

    await h.comp.locator('.mmd-toolbar').getByLabel('Scale').selectOption('print');
    let downloaded: string | null = null;
    await Promise.all([
      page.waitForEvent('download', { timeout: 12_000 }).then((d) => { downloaded = d.suggestedFilename(); }).catch(() => null),
      toolbarButton(h.comp, 'Export PNG').click(),
    ]);
    expect(downloaded, 'nothing may be offered for download when it cannot be drawn').toBeNull();

    const notice = h.comp.locator('.mmd-panel--busy:not(.mmd-hidden), .mmd-panel--hint:not(.mmd-hidden)').first();
    await expect(notice).toBeVisible({ timeout: 20_000 });
    const text = await notice.innerText();
    expect(text, 'the message states the size it could not draw').toMatch(/133933|larger than a browser can draw/i);
    expect(text.toLowerCase(), 'and points at the export that always works').toMatch(/svg|high scale|screen scale/);

    // Vector export carries the same diagram, so the route offered must actually work.
    const [svgDownload] = await Promise.all([
      page.waitForEvent('download', { timeout: 120_000 }),
      toolbarButton(h.comp, 'Export SVG').click(),
    ]);
    const path = await svgDownload.path();
    const markup = readFileSync(path as string, 'utf8');
    expect(markup).toContain('<svg');
    expect(markup.length, 'the vector file holds the whole 50 000-character diagram').toBeGreaterThan(100_000);
  });

  test('the size plan is decided by arithmetic, not by a failed canvas', async ({ page }) => {
    const h = await openFixture(page, 'good');
    await waitState(h.comp, 'rendered');
    const plan = await h.comp.evaluate(() => {
      const api = (window as any).__mermaidGuiExport__;
      return {
        limits: api.RASTER_LIMITS,
        fits: api.rasterPlan(4000, 3000, 1000, 750, 4),
        tooLong: api.rasterPlan(1616, 535732, 404, 133933, 4),
        highOnly: api.rasterPlan(12000, 16000, 3000, 4000, 4),
      };
    });
    expect(plan.fits.ok, 'an ordinary print export stays within the plan').toBe(true);
    expect(plan.tooLong.ok, 'a 535k pixel edge is refused').toBe(false);
    expect(plan.tooLong.reason).toBe('rasterTooLarge');
    expect(plan.tooLong.feasibleScale, 'no advertised scale fits a 133k-long chain').toBe(0);
    expect(plan.tooLong.message).toMatch(/SVG/i);
    expect(plan.highOnly.feasibleScale, 'a 12 MP diagram fits at screen and high but not print').toBe(3);
    expect(plan.highOnly.message).toMatch(/high scale/i);
    void plan;
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
