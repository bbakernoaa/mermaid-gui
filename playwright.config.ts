import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import path from 'node:path';
import { defineConfig } from '@playwright/test';

// Dev-only harness. The deployed site is static and build-step-free, so nothing
// here ever runs at deploy time (constitution I.3).
const bundledChromium = existsSync(
  path.join(homedir(), 'Library', 'Caches', 'ms-playwright', 'chromium_headless_shell-1187')
);

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
    channel: process.env.MMD_BROWSER_CHANNEL || (bundledChromium ? undefined : 'chrome'),
  },
  webServer: {
    command: 'python3 -m http.server 8000 --bind 127.0.0.1',
    url: 'http://127.0.0.1:8000/index.html',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
