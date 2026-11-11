# Quickstart: Validate Mermaid Editor Experience Upgrades

**Audience**: anyone implementing or reviewing this feature · [plan.md](./plan.md) ·
[spec.md](./spec.md)

This is a **validation guide**, not implementation instructions. Everything here must be runnable
before/while the feature lands, so the contracts can be proven instead of eyeballed.

## 1. Prerequisites

- macOS/Linux/WSL with **Python 3** (`python3 -m http.server`) and **Node.js 20+** — needed only to
  run tests; the deployed site never touches Node.
- A Chromium-family browser (Playwright downloads one).
- Network access at run time: Mermaid, Stlite, and compression libraries load from CDNs by design —
  the site has no bundle; the tests assume that constraint.
- No `pip install`, no conda env, **no build step**. The current repo already works with less, and
  this feature stays within that shape.

## 2. Run it

```bash
cd /Users/barry/Documents/mermaid-gui
python3 -m http.server 8000
# open http://localhost:8000
```

## 3. Install test runner (repo root)

This step exists only for `tests/`. It adds dev-only tooling; it is not part of the deployment.

```bash
npm install --no-save playwright@latest
npx playwright install chromium
```

## 4. Validation scenarios (each maps to contracts and requirements)

`npm test` runs each scenario; the expected result is a pass, not a manual judgement call.

### V-A · Appearance control (story 1, FR-001..011) → [appearance-contract.md](./contracts/appearance-contract.md)

```bash
npx playwright test tests/appearance.spec.ts
```

1. Set text size smallest ↔ largest → preview redraws; measured SVG font size ratio ≥ 2.0 (A-3).
2. Cycle every offered scheme → whole diagram changes colour, never one element (FR-003).
3. Pick `baseColors = { background: #1a1b26, foreground: #a9b1d6 }` → all element colours derive from
   those two inputs only (A-6).
4. Set largest text + `open` spacing → no label clipped for every catalog example (A-8).
5. Increase spacing → `nodeSpacing`/`rankSpacing`/`padding` values change by the §4 multipliers
   (FR-006).
6. Toggle path emphasis → primary path reads first in the rendered SVG (FR-007).
7. Export SVG and PNG with non-default knobs → both match the preview (A-2: identical
   `ResolvedAppearance` reaching both consumers).
8. Reload → knobs persist; "reset appearance" restores defaults (FR-010).
9. Paste a source containing explicit `theme` settings → effective-value chip says who wins (FR-009,
   precedence table §7).
10. Contrast report → no combination needs clamping that the report did not surface (A-4, FR-011).

### V-B · Render feedback (story 2, FR-012..016) → [render-bridge-contract.md](./contracts/render-bridge-contract.md)

```bash
npx playwright test tests/render-states.spec.ts
```

| Input | Expected state | Assertion |
|-------|---------------|-----------|
| valid flowchart | `rendered` | diagram visible; no error node in DOM |
| `flowchart TD\n  A-->` | `invalid` | plain message + `line 2` in the error panel |
| garbage (`zzz q`) | `invalid` | `kind: parseError`, line reported, nothing blanked |
| empty / spaces | `empty` | hint present; **not** `invalid` (spec scenario 4) |
| fix a broken line | `rendered`, error gone | with no click at all (FR-015) |
| 500-node valid flowchart, no failure; show `rendering` throughout | `rendered` | SC-003 requires 0 false errors |
| valid `pie` / unsupported type (`notadiagram X`) | `invalid` + readable "not supported/readable" | `error.kind` in the contract enum |
| error then success twice quickly | last good render intact | FR-016 |

Every status shown belongs to the contract's state machine and the four-state UI in
[../data-model.md](../data-model.md) §2. This test asserts the bridge's invariants §2 (exactly one
terminal state per `requestId`, so slow renders cannot masquerade as failures; SC-002: 0 silent drops).

### V-C · Types and catalog (story 3, FR-017..021) → [template-catalog-contract.md](./contracts/template-catalog-contract.md)

```bash
python3 -m pytest tests/test_catalog.py -q     # pure-Python, fast
npx playwright test tests/catalog-render.spec.ts # in-browser render proof
```

- All 9 required `typeId`s + blank exist, one plain + one `styled` example each.
- In-browser render succeeds for **every** example (SC-002 is 100%, so any single failure is a red CI).
- `minElements ≥ 3` per example, counted on the rendered SVG.
- Class example shows `<<interface>>` correctly — a direct regression test for the bug fixed in
  commits 02ae868 / 89bf9cc.

### V-D · Persistence and sharing (story 4, FR-022..027) → [share-payload-contract.md](./contracts/share-payload-contract.md)

```bash
npx playwright test tests/drafts-share.spec.ts
```

1. Type, reload → `Draft restored … <time>` notice, text and knobs intact (SC-005).
2. Start new → draft gone in storage **and** editor blank; notice suppressed until next save.
3. Copy link → open in a fresh context — source, name and knobs identical.
4. Link for a source at the max size → `tooLarge` message, download offered, no broken link created.
5. Hand-mangle the link fragment (truncate, scramble the alphabet) → `malformed`, `unsupportedVersion`
   or `truncated` per contract, and a working editor (FR-026; nothing thrown).
6. Block/`localStorage`-less run → app works; the notice states "drafts are not being saved" once
   (FR-027; no fake success).
7. Round-trip property test on all catalog sources + `data/*.edge-cases`:
   `decode(encode(x)) == x` byte-identically, incl. non-ASCII, `<<>>`, quotes, braces.
8. **No server calls** other than the CDN imports: assert via request interception that the user's
   `source` never crosses the wire (FR-024, SC-010).
9. Knobs-only payload → open the link with a different interface theme — the diagram is identical to
   the sender's (SC-005).

### V-E · Export (story 5, FR-028..032) → [appearance-contract.md](./contracts/appearance-contract.md) A-9

```bash
npx playwright test tests/export.spec.ts
```

1. `screen` ↔ `print` → PNG dimensions differ by exactly the ratio the §3/§4 table promises (A-9).
2. White / dark / custom / transparent backgrounds → the alpha test is real, no baked white box; text
   contrast still holds in transparent exports (FR-029, §4a invariant).
3. Arrowheads and line styles present in SVG **and** PNG for all required types (FR-030) —
   a direct guard against the regression class fixed in ed4bb3e.
4. Custom name with `/`, spaces, control chars, unicode → sanitised, non-ASCII preserved, extension
   correct, in both download paths (FR-031).
5. Copy SVG to clipboard → paste yields serialised markup with inline styles; clipboard failure
   shows fallback (FR-032).
6. Export while the preview still shows an earlier `requestId`'s render → a new PNG/SVG from the stale
   render is **not** exported (bridge contract §1, `requestId` invariant).
7. `.mmd` download → raw source, no appearance metadata (data-model §9 invariant: `mmd` never carries
   `appearance`).

### V-F · Editor and preview comfort (story 6, FR-033..037)

```bash
npx playwright test tests/preview.spec.ts
```

1. A ~40-line catalog example, fit-to-view → zero inner scrollbars in the preview container (FR-034).
2. Zoom in / out / fit → ≤ 3 actions from whole overview to readable labels (SC-008).
3. Interface dark mode via `prefers-color-scheme` → chrome dark; diagram appearance identical to
   light mode (FR-036; the `interfaceMode` exclusion in appearance contract §1).
4. Line numbers and highlight presence depends on outcome **S-3**.

## 5. One-command suite

Two layers, both introduced by this feature. Nothing here is deployed; the site stays a
build-step-free static upload.

```bash
# 1. Python logic: catalogue completeness, appearance resolution, payload round-trips,
#    message wording, state machine, bridge shapes (no browser, no network).
python3 -m pytest tests/ -q

# 2. Browser contracts in Chromium: renders, states and messages, appearance knobs,
#    exports, zoom/fit/host relays. The pages under test are *generated* from the
#    shipped modules, so they cannot drift from what deploys.
npm run test:browser          # = fixtures + `playwright test`
#   equivalently:
python3 tests/dump_catalog.py && python3 tests/build_fixture.py
npx playwright test
```

`tests/build_fixture.py` builds every component page through
`preview_asset.component_document()` — the very function `app.py` uses — and
`tests/.generated/runner.html` hosts those pages in a null-origin `srcdoc` iframe behind the
real `host_bridge.js`, so storage, the `#p=` fragment, the height relay and the last-good
mirror are exercised rather than assumed.

### The live boot (opt-in, slower)

```bash
npm run test:live             # MMD_LIVE=1 + MMD_APP=live, boots index.html with Stlite from the CDN
```

Two flags, deliberately separate: `MMD_APP=live` makes the shared helpers drive the real app
instead of a fixture page, while `MMD_LIVE=1` is what unlocks `tests/live-app.spec.ts` itself,
so an ordinary `playwright test` never boots Pyodide by accident.

This is the only layer that runs Streamlit itself (Pyodide, the sidebar widgets, the
`boot.json` hand-off, the rerun cycle). It needs the network, takes about a minute per
scenario, and is the check behind §6 below.

## 6. Manual smoke (2 minutes, before any PR merge)

Steps 2-5 are automated (`npm run test:browser`); steps 1 and 6-7 need a human because they
involve another browser profile or an image viewer. Run `npm run test:live` first and it
covers 1-5 as well.

1. `python3 -m http.server 8000`, open the page.
2. Choose the **class diagram** example → renders, stereotypes intact. Then switch Example to
   `styled`: it loads immediately (app-loaded text is never treated as the user's own work), while
   anything you typed yourself is still protected by a confirm before it is replaced.
3. Bump text size to largest, spacing to open → legible, nothing clipped.
4. Break a line → clear error with a line number; fix it → gone by itself.
5. Export PNG with `high` scale + transparent; open in an image viewer over a dark page → correct.
   The picture has to actually be *in* the file: an empty raster carries valid dimensions, so open it
   and look (the automated check counts painted pixels, `npm run test:browser`).
6. Reload → restore notice; copy link → open in a private window → same picture.
7. Zoom out a mindmap to overview → whole diagram fits.

## 7. What "done" means here

1. Every automated assertion above passes with **every** catalog example, and each scenario's
   expected result is a pass/fail assertion, not a human "seems fine";
2. Manual smoke steps 2-7 show the expected outcome with no console errors;
3. The three spikes in [research.md](./research.md) are resolved and their outcomes recorded as
   comments/decisions in the PR (each with the fallback chosen, if a fallback got used);
5. `git diff` shows no new server dependency, no build step in the deployment path, and the
   Pages workflow files unchanged.

Both test layers run in CI (`.github/workflows/ci.yml`: a pure-Python job and a Chromium job
that builds the fixtures from the shipped modules first). `.github/workflows/deploy.yml` is
never touched by this work: it still uploads the repository root as it is, so what GitHub Pages
serves is exactly what this folder holds. The Node tooling is dev-only — `package.json` has no
dependencies that the site loads, and `npx playwright …` is never part of a deploy.

Before merging, confirm each of these against the running site (`npm run test:live` automates
1-5, and step 6 is the one a human should see):

| Gate | Check |
|---|---|
| Nothing leaves the device | The Network tab shows requests only to the CDNs and to the page's own origin; no request carries diagram text (SC-010). |
| Nothing is built | `git diff --stat .github/workflows/deploy.yml` is empty, and the served file list equals the repository root. |
| Nothing is installed at runtime | `app.py`'s imports are this folder's modules plus Streamlit; `requirements` in `stlite.mount()` is empty. |
| Storage stays local | Drafts, appearance and the share fragment are in `localStorage` / the address bar of the browser, and never in a query string. |
| The component is really sandboxed | Its frame's `location.origin` is `"null"`; the host page still relays height, storage and link messages on its behalf. |
| The look is one object | Preview, exported SVG/PNG and a shared link show the same colours and text size for the same knobs (contract A-2). |
