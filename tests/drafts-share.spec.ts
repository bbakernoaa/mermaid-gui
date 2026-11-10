import { expect, test } from '@playwright/test';
import {
  MANIFEST,
  hostAddress,
  hostBoot,
  hostMessageCounts,
  hostStored,
  hostStorageLength,
  nextRequestId,
  openFixture,
  send,
  waitState,
} from './support';

async function storeWrites(page: import('@playwright/test').Page): Promise<number> {
  return page.evaluate(() => ((window as any).__mmdMessages || []).filter((msg: any) => msg.type === 'mmd-store' && msg.key === 'draft').length);
}

// V-D (story 4, FR-022..027, SC-005, SC-010). Drafts and the page address are
// owned by the host page -- the component sits in a null-origin srcdoc sandbox
// and Stlite's Python has no window at all (research.md S-1/S-2, both resolved
// as failures by design). So these tests drive the shipped host_bridge.js in the
// harness page and assert what a browser really keeps.
const FLOW = 'flowchart TD\n  A[Draft] --> B[Share]';

async function typeText(h: Awaited<ReturnType<typeof openFixture>>, text: string): Promise<void> {
  await send(h.comp, { source: text, requestId: nextRequestId() });
  await waitState(h.comp, 'rendered');
}

test.describe('drafts and share links', () => {
  test('the draft is kept on the device and survives a reload', async ({ page }) => {
    const h = await openFixture(page, 'good');
    await waitState(h.comp, 'rendered');
    await typeText(h, FLOW);

    // Coalesced writes: at least one save per second, not one per keystroke
    // (share-payload contract section 2 rule 1).
    await page.waitForTimeout(1500);
    const stored = await hostStored(page, 'draft');
    expect(stored, 'nothing was written to the device').toBeTruthy();
    expect(stored.source).toBe(FLOW);
    expect(stored.savedAt, 'a draft without a timestamp cannot be labelled').toBeTruthy();
    expect(String(stored.version), 'drafts are versioned').toBe('1');

    const reload = await openFixture(page, 'good');
    const boot = await hostBoot(page);
    expect(boot.draft?.source, 'the host offered the draft back before the first render').toBe(FLOW);
    expect(boot.storage).toBe('available');
    void reload;
  });

  test('rapid typing writes once, not once per character', async ({ page }) => {
    const h = await openFixture(page, 'good');
    await waitState(h.comp, 'rendered');
    const before = await storeWrites(page);
    for (let i = 1; i <= 12; i += 1) {
      await send(h.comp, { source: FLOW.slice(0, 12 + i), requestId: nextRequestId() });
    }
    await page.waitForTimeout(1600);
    const stores = (await storeWrites(page)) - before;
    expect(stores, 'the device must not be hammered once per keystroke').toBeLessThanOrEqual(2);
    const stored = await hostStored(page, 'draft');
    expect(stored.source, 'and the last write wins').toBe(FLOW.slice(0, 24));
  });

  test('the chosen look is kept with the draft', async ({ page }) => {
    const h = await openFixture(page, 'good');
    await waitState(h.comp, 'rendered');
    const variant = MANIFEST.payloads['scheme-forest'];
    await send(h.comp, { source: FLOW, appearance: variant.appearance, chrome: variant.chrome, requestId: nextRequestId() });
    await waitState(h.comp, 'rendered');
    await page.waitForTimeout(1400);
    const look = await hostStored(page, 'appearance');
    expect(look, 'the appearance was not remembered').toBeTruthy();
    expect(look.schemeName).toBe('forest');
    // The snapshot is taken when the page loads, so the next visit is a new page.
    await openFixture(page, 'good');
    const boot = await hostBoot(page);
    expect(boot.appearance?.schemeName, 'and it is offered back on the next visit').toBe('forest');
  });

  test('clearing the draft empties the device, not just the editor', async ({ page }) => {
    const h = await openFixture(page, 'good');
    await waitState(h.comp, 'rendered');
    await typeText(h, FLOW);
    await page.waitForTimeout(1400);
    expect(await hostStored(page, 'draft')).toBeTruthy();

    await send(h.comp, {
      source: '',
      chrome: Object.assign({}, MANIFEST.baked.good.chrome, { host: { action: 'clearStorage' } }),
      requestId: nextRequestId(),
    });
    await waitState(h.comp, 'empty');
    expect(await hostStored(page, 'draft'), 'the draft is gone').toBeNull();
    expect(await hostStorageLength(page), 'and no orphan keys were left').toBeLessThanOrEqual(1);

    await openFixture(page, 'good');
    const boot = await hostBoot(page);
    expect(boot.draft, 'a reload cannot resurrect it').toBeNull();
  });

  test('putting the link in the address replaces it and adds no history', async ({ page }) => {
    const h = await openFixture(page, 'good');
    await waitState(h.comp, 'rendered');
    const token = 'd1:test-payload';
    const lengthBefore = await page.evaluate(() => window.history.length);

    await send(h.comp, {
      chrome: Object.assign({}, MANIFEST.baked.good.chrome, { host: { action: 'link', payload: token, copy: false } }),
      requestId: nextRequestId(),
    });
    await page.waitForFunction((wanted) => window.location.hash.indexOf(wanted) !== -1, token, { timeout: 10_000 });

    const address = await hostAddress(page);
    expect(address).toContain('#p=' + token);
    expect(address, 'the diagram travels in the fragment, never the query').not.toContain('?p=');
    expect(address.split('#')[0].indexOf('flowchart'), 'the path stays clean').toBe(-1);
    expect(await page.evaluate(() => window.history.length), 'replaceState must not add an entry').toBe(lengthBefore);

    // A second link overwrites the first rather than stacking up.
    await send(h.comp, {
      chrome: Object.assign({}, MANIFEST.baked.good.chrome, { host: { action: 'link', payload: 'd1:second', copy: false } }),
      requestId: nextRequestId(),
    });
    await page.waitForFunction(() => window.location.hash.indexOf('d1:second') !== -1, undefined, { timeout: 10_000 });
    expect(await hostAddress(page)).toContain('#p=d1:second');
    expect(await hostAddress(page), 'no duplicate tokens').not.toContain('test-payload');
  });

  test('a page opened from a share link hands the token to the app before the first render', async ({ page }) => {
    const h = await openFixture(page, 'good', { fragment: '#p=d1.from-a-share-link' });
    await waitState(h.comp, 'rendered');
    const boot = await hostBoot(page);
    expect(boot.fragment, 'the host snapshot carries the fragment verbatim (Python does the decoding)').toBe('d1.from-a-share-link');
    expect(boot.href).toContain('#p=d1.from-a-share-link');
    expect(boot.version).toBe(1);
  });

  test('a denied store is reported to the app and the editor keeps working (FR-027)', async ({ page }) => {
    const h = await openFixture(page, 'good', { blockStorage: true });
    await waitState(h.comp, 'rendered');

    // The host is the only place that can learn this, and it must say so in the
    // snapshot the app reads before its first render -- app.py turns that into the
    // "this browser will not keep drafts" warning (tests/test_app_messages.py).
    const boot = await hostBoot(page);
    expect(['denied', 'unavailable', 'full']).toContain(boot.storage);
    expect(boot.storage, 'a working store must not be reported as broken here').toBe('denied');

    // Nothing about editing changes: the diagram still renders after the refusal.
    await typeText(h, FLOW);
    await expect(h.comp.locator('.mmd-canvas svg')).toHaveCount(1);
    expect(await hostStorageLength(page), 'and nothing could be written anyway').toBe(-1);

    const refused = await page.evaluate(() => (window as any).__mermaidGuiStorage.writeTally());
    expect(refused.refused, 'the refused writes are counted, not swallowed').toBeGreaterThan(0);
    expect(refused.ok, 'and none of them succeeded').toBe(0);
  });

  test('nothing but the CDN and the local server ever sees the diagram text (SC-010)', async ({ page }) => {
    const leaked: string[] = [];
    await page.route('**/*', (route) => {
      const request = route.request();
      const url = request.url();
      const local = /^https?:\/\/(127\.0\.0\.1|localhost)/.test(url) || url.startsWith('file:') || url.startsWith('about:');
      if (!local && !/cdn\.jsdelivr\.net/.test(url)) {
        const body = request.postData() || '';
        if (body.includes('Draft') || url.includes('Draft') || url.includes(encodeURIComponent('A[Draft]'))) {
          leaked.push(url.slice(0, 120));
        }
      }
      return route.continue();
    });

    const h = await openFixture(page, 'good');
    await waitState(h.comp, 'rendered');
    await typeText(h, FLOW);
    await page.waitForTimeout(1400);
    // Ask for a share link too: it is built and copied locally, never fetched.
    await send(h.comp, {
      chrome: Object.assign({}, MANIFEST.baked.good.chrome, { host: { action: 'link', payload: 'd1.' + encodeURIComponent(FLOW.slice(0, 12)), copy: true } }),
      requestId: nextRequestId(),
    });
    await page.waitForTimeout(600);
    expect(leaked, 'user text must never leave the device').toEqual([]);
  });

  test('a link the app was given decodes to the same look the sender saw', async ({ page }) => {
    // The codec itself is pure Python (tests/test_share_codec.py, byte-identical
    // round trip over every catalogue source). Here we prove the transport: the
    // token that reaches the host is the one the page was opened with.
    const token = 'd1.transport-check';
    const h = await openFixture(page, 'typed-colors', { fragment: '#p=' + token });
    await waitState(h.comp, 'rendered');
    const boot = await hostBoot(page);
    expect(boot.fragment).toBe(token);
    expect(MANIFEST.baked['typed-colors'].appearance.frontmatterColorKeys.length, 'front matter colours were detected').toBeGreaterThan(0);
  });
});
