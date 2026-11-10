import { existsSync, readdirSync } from 'node:fs';
import { homedir } from 'node:os';
import path from 'node:path';
import { defineConfig } from '@playwright/test';

// Dev-only harness. The deployed site is static and build-step-free, so nothing
// here ever runs at deploy time (constitution I.3).

/**
 * Which browser to drive. CI always uses the Chromium Playwright itself installs
 * (`npx playwright install --with-deps chromium`), so it never depends on what a
 * runner image happens to ship. Locally, Playwright's own build is preferred when
 * it is present; when it is not (the ~150 MB download is frequently unavailable),
 * the Chrome already on the machine is used instead. Set MMD_BROWSER_CHANNEL to
 * choose explicitly ('chrome', 'msedge', or unset for Playwright's Chromium).
 */
/** The browsers `npx playwright install` put in this machine's cache, if any. */
function playwrightChromiumInstalled(): boolean {
  const roots = [
    path.join(homedir(), 'Library', 'Caches', 'ms-playwright'), // macOS
    path.join(homedir(), '.cache', 'ms-playwright'), // Linux
  ];
  return roots.some((root) => {
    if (!existsSync(root)) return false;
    let names: string[] = [];
    try {
      names = readdirSync(root);
    } catch {
      return false;
    }
    return names.some((name) => name.startsWith('chromium') && existsSync(path.join(root, name)));
  });
}

const bundledChromium = playwrightChromiumInstalled();

export default defineConfig({
  testDir: './tests',
  testMatch: '**/*.spec.ts',
  timeout: 120_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  reporter: process.env.CI ? [['line']] : [['list']],
  use: {
    baseURL: 'http://127.0.0.1:8000',
    trace: 'retain-on-failure',
    viewport: { width: 1280, height: 900 },
    // GitHub Actions installs Playwright's own Chromium. Locally that download is
    // ~150 MB per version and frequently unavailable, so if it is missing we drive
    // the browser already on the machine. Set MMD_BROWSER_CHANNEL to choose.
    channel: process.env.CI
      ? undefined
      : process.env.MMD_BROWSER_CHANNEL || (bundledChromium ? undefined : 'chrome'),
  },
  webServer: {
    command: 'python3 -m http.server 8000 --bind 127.0.0.1',
    url: 'http://127.0.0.1:8000/index.html',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
