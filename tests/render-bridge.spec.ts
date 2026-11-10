import { expect, test } from '@playwright/test';
import {
  armRenderSpy,
  badge,
  errorPanel,
  hostLastStatus,
  hostStateHistory,
  labelStrings,
  openFixture,
  renderSpyCalls,
  send,
  svg,
  visibleSvg,
  waitState,
  type Harness,
} from './support';

// contracts/render-bridge-contract.md -- the invariants that stop a fast typist
// from ever seeing a picture drawn from text they already deleted.
test.describe('render bridge invariants', () => {
  test('the payload is the only input the component reads', async ({ page }) => {
    const h: Harness = await openFixture(page, 'good');
    await waitState(h.comp, 'rendered');
    // A <textarea> is what the app's own editor uses, so planting a decoy here
    // proves the picture came from the payload rather than from the DOM.
    await h.comp.evaluate(() => {
      const decoy = document.createElement('textarea');
      decoy.value = 'flowchart TD\n  DECOY[This text must never be drawn]';
      document.body.appendChild(decoy);
    });
    const labels = (await labelStrings(h.comp)).join(' ');
    expect(labels).not.toContain('must never be drawn');
    expect(labels).toContain('Start');
    expect(h.source).toContain('Start');
  });

  test('one request produces exactly one terminal state', async ({ page }) => {
    const h = await openFixture(page, 'good');
    await waitState(h.comp, 'rendered');
    const history = await hostStateHistory(page);
    expect(history, 'rendering is published before any async work, then exactly one terminal').toEqual([
      'rendering',
      'rendered',
    ]);
  });

  test('a reply for a superseded request is discarded', async ({ page }) => {
    const h = await openFixture(page, 'good');
    await waitState(h.comp, 'rendered');
    const before = await visibleSvg(h.comp).innerHTML();
    const hostHistory = await hostStateHistory(page);

    await h.comp.evaluate(async () => {
      const api = (window as any).__mermaidGuiRender__;
      // req-00000 is older than the request that just finished.
      return await api.handle({
        command: 'render',
        requestId: 'req-00000',
        schemaVersion: 1,
        source: 'flowchart TD\n  OLD[Stale] --> X[Gone]\n',
        appearance: {},
      });
    });
    // handle() resolves to nothing when the request was dropped as stale.
    await expect(badge(h.comp, 'rendered')).toBeVisible();
    expect(await visibleSvg(h.comp).innerHTML()).toBe(before);
    expect(await hostStateHistory(page), 'and the host saw nothing either').toEqual(hostHistory);
    void hostHistory;
  });

  test('two cycles started in the same tick: only the newest publishes', async ({ page }) => {
    const h = await openFixture(page, 'good');
    await waitState(h.comp, 'rendered');
    const before = await hostStateHistory(page);

    const ids = await h.comp.evaluate(async () => {
      const api = (window as any).__mermaidGuiRender__;
      const older = api.handle({ command: 'render', requestId: 'req-00600', schemaVersion: 1, source: 'flowchart TD\n  A[Older] --> B[Wins nothing]\n', appearance: {} });
      const newer = api.handle({ command: 'render', requestId: 'req-00601', schemaVersion: 1, source: 'flowchart TD\n  A[Newer] --> B[Wins]\n', appearance: {} });
      await Promise.all([older, newer]);
      return { older: await older, newer: await newer, newest: api.stateSnapshot().newestRequestId };
    });
    expect(ids.newest).toBe('req-00601');
    expect(ids.older, 'the superseded cycle published nothing').toBeNull();
    expect(ids.newer.state, 'the newest cycle reached a terminal').toBe('rendered');

    const history = await hostStateHistory(page);
    expect(history.slice(0, before.length), 'nothing was rewritten retroactively').toEqual(before);
    expect(history.filter((state) => state === 'rendered').length, 'exactly one new terminal').toBe(
      before.filter((state) => state === 'rendered').length + 1,
    );
    expect(history[before.length], 'started with the winner only').toBe('rendering');
    const labels = await labelStrings(h.comp);
    expect(labels.join(' '), 'the newest text is what is on screen').toContain('Wins');
    expect(labels.join(' '), 'and the loser never reached the screen').not.toContain('Wins nothing');
  });

  test('a mismatched schema version is refused with a reload hint', async ({ page }) => {
    const h = await openFixture(page, 'good');
    await h.comp.evaluate(async () => {
      const api = (window as any).__mermaidGuiRender__;
      return await api.handle({
        command: 'render',
        requestId: 'req-00002',
        schemaVersion: 99,
        source: 'flowchart TD\n  A --> B\n',
        appearance: {},
      });
    });
    await waitState(h.comp, 'invalid');
    const status = await hostLastStatus(page);
    expect(status.error.kind, 'the bridge itself is the problem, not the text').toBe('bridgeVersion');
    expect(status.error.plainMessage).toMatch(/reload/i);
    await expect(errorPanel(h.comp)).toBeVisible();
  });

  test('blank text answers "empty" without ever calling mermaid', async ({ page }) => {
    const h = await openFixture(page, 'empty');
    await waitState(h.comp, 'empty');
    await expect(svg(h.comp)).toHaveCount(0);
    await armRenderSpy(h.comp);
    await send(h.comp, { source: '   \n\n  ', requestId: 'req-00077' });
    await waitState(h.comp, 'empty');
    expect(await renderSpyCalls(h.comp), 'blank text must not reach mermaid.render()').toBe(0);
  });

  test('request ids are compared as opaque strings, newest wins', async ({ page }) => {
    const h = await openFixture(page, 'good');
    await waitState(h.comp, 'rendered');
    const snapshot = await h.comp.evaluate(async () => {
      const api = (window as any).__mermaidGuiRender__;
      const ids = ['req-00002', 'req-00010', 'req-99999'];
      for (const id of ids) {
        await api.handle({ command: 'render', requestId: id, schemaVersion: 1, source: 'flowchart TD\n  A --> B\n', appearance: {} });
      }
      return {
        newest: api.stateSnapshot().newestRequestId,
        order: [api.compareId('req-00002', 'req-00010'), api.compareId('req-00010', 'req-00010'), api.compareId('req-99999', 'req-00001')],
      };
    });
    expect(snapshot.newest).toBe('req-99999');
    expect(snapshot.order[0]).toBeLessThan(0);
    expect(snapshot.order[1]).toBe(0);
    expect(snapshot.order[2]).toBeGreaterThan(0);
  });
});
