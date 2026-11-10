import { existsSync, readdirSync, statSync } from 'node:fs';
import { homedir } from 'node:os';
import path from 'node:path';
import { defineConfig } from '@playwright/test';

// Dev-only harness. The deployed site is static and build-step-free, so nothing
// here ever runs at deploy time (constitution I.3).

/**
 * Which browser to drive. `MMD_BROWSER_CHANNEL` always wins; otherwise CI uses the
 * Chromium `npx playwright install` put in the cache (the workflow drops this
 * variable to `chrome` when Playwright does not support the runner's distribution
 * yet, which is how `ubuntu-latest` moving to Ubuntu 26 broke the first attempt),
 * and a local run uses Playwright's own build when it is present, falling back to
 * the machine's Chrome when it is not (that download is ~150 MB and often
 * unavailable). Set `MMD_BROWSER_CHANNEL=chrome` to choose explicitly.
 */
/**
 * Whether `npx playwright install` actually put a usable Chromium in this
 * machine's cache. A directory alone is not proof: an interrupted download leaves
 * a folder with no executable, and launching that fails with a message nobody can
 * read. So look for the real binary inside any chromium build directory.
 */
function playwrightChromiumInstalled(): boolean {
  const roots = [
    path.join(homedir(), 'Library', 'Caches', 'ms-playwright'), // macOS
    path.join(homedir(), '.cache', 'ms-playwright'), // Linux
  ];
  const executables = [
    ['chrome-linux', 'chrome'],
    ['chrome-linux', 'headless_shell'],
    ['chrome-mac', 'Chromium.app', 'Contents', 'MacOS', 'Chromium'],
    ['chrome-mac', 'headless_shell'],
    ['chrome-mac-arm64', 'Chromium.app', 'Contents', 'MacOS', 'Chromium'],
    ['win', 'chrome.exe'],
  ];
  return roots.some((root) => {
    let builds: string[] = [];
    try {
      builds = readdirSync(root);
    } catch {
      return false;
    }
    return builds.some((build) => {
      if (!build.startsWith('chromium')) return false;
      const dir = path.join(root, build);
      return executables.some((parts) => {
        const candidate = path.join(dir, ...parts);
        if (!existsSync(candidate)) return false;
        try {
          // A "successful" download is tens of megabytes, not a stub.
          return statSync(candidate).size > 1_000_000;
        } catch {
          return false;
        }
      });
    });
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
    channel: process.env.MMD_BROWSER_CHANNEL || (process.env.CI || bundledChromium ? undefined : 'chrome'),
  },
  webServer: {
    command: 'python3 -m http.server 8000 --bind 127.0.0.1',
    url: 'http://127.0.0.1:8000/index.html',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
