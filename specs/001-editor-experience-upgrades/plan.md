# Implementation Plan: Mermaid Editor Experience Upgrades

**Branch**: `001-editor-experience-upgrades` | **Date**: 2026-11-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-editor-experience-upgrades/spec.md`

## Summary

Upgrade the browser-only Mermaid editor from "renders a diagram" to "produces a diagram you are
willing to publish". The centre of gravity is appearance control (text size, colour scheme derived
from base colours, font, spacing, main-path emphasis), followed by trustworthy render feedback
(Mermaid's `parse()` gate with a plain-language message and line location), broader diagram-type
coverage, per-device draft persistence plus self-contained share links, purpose-built export
(scale/background/name/clipboard), and editor/preview comfort (line numbers, auto-height preview,
zoom, dark mode).

Technical approach: keep the existing zero-build static architecture (`index.html` + `@stlite/mountable`
+ `app.py` rendered through `components.html`), and split the currently monolithic inline JavaScript
into explicit source modules. Appearance control is implemented as one **resolved appearance object**
that is applied identically to preview, export, and shared links, by mapping a small set of
user-facing knobs onto Mermaid 11's documented `theme`, `themeVariables`, and per-diagram config keys
(verified against `mermaid@11` type definitions). Persistence and sharing are implemented client-side
only: drafts through Pyodide's `js` module (`localStorage`), share links as compressed payload in the
URL, so no backend is introduced and the GitHub Pages deployment model is unchanged.

## Technical Context

**Language/Version**: Python 3.12 (Pyodide/WASM runtime provided by Stlite) for the UI layer;
ECMAScript modules for the rendering/export layer (Mermaid 11 is ESM-only via CDN)

**Primary Dependencies**: `@stlite/mountable` 0.73.0 (bundles Streamlit **1.40.1** — verified from
the wheel shipped inside the package), Mermaid **11.x** (CDN ESM), `canvg` 4.0.1 (existing rasteriser),
`lz-string` or equivalent for link compression (new), all CDN-loaded; no npm install, no bundler

**Storage**: Browser `localStorage` through Pyodide's `js` module (draft + appearance prefs).
Diagram content for sharing lives inside the URL fragment. No server storage.

**Testing**: No test harness exists today (repo is two files served statically). Plan adds
`npm`-free, browser-executed checks: a lightweight Playwright-based smoke suite run in CI against the
static site, plus contract assertions for the appearance/bridge/payload shapes. See
[contracts/](./contracts/).

**Target Platform**: Modern desktop browsers (Chromium, Firefox, Safari) on GitHub Pages over HTTPS;
touch not assumed

**Project Type**: Single-page static web application (no backend, no build step)

**Performance Goals**: keystroke-to-preview feedback under ~300 ms for typical diagrams; appearance
change reflected under 3 s (SC-009); a 500-line diagram stays responsive; shared link opens to a
rendered diagram within 10 s (SC-006); false error reports = 0 for large valid diagrams (SC-003)

**Constraints**: No backend and no accounts (deployment stays GitHub Pages); no bundler/transpile
step; must keep working when `localStorage` is unavailable; Mermaid must render with `htmlLabels:
false` for export fidelity (existing constraint from the PNG-export fixes in commits ce61056 and
ed4bb3e); first paint may not block on network beyond the existing CDN imports

**Scale/Scope**: One diagram at a time; ≥9 diagram types, ≥6 curated schemes, ≥3 font choices;
37 functional requirements across 6 user stories; source size grows from ~2 files to ~8-10 small
modules, no new services

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is still the **unfilled scaffold template** — every principle,
section, and the version/ratification fields are placeholders (`[PRINCIPLE_1_NAME]`,
`[CONSTITUTION_VERSION]`, etc.). It defines no enforceable gates.

| Gate | Status | Basis |
|------|--------|-------|
| Core principles (5 placeholders) | **No constraint defined** | Template text, not project content |
| Additional constraints / security / performance section | **No constraint defined** | Placeholder `[SECTION_2_CONTENT]` |
| Development workflow / quality gates | **No constraint defined** | Placeholder `[SECTION_3_CONTENT]` |
| Governance / version / ratified date | **No constraint defined** | Placeholders, so the constitution cannot currently be cited as authority |

**Gate result: PASS with zero constitutional constraints to check.** Nothing blocks Phase 0.

Because a constitution is meant to be the project's binding rules and this one is empty, the plan
carries forward the constraints that are already **de facto** project rules, evidenced by the
repository itself, and holds every design decision against them:

| De-facto principle | Evidence | How this plan respects it |
|--------------------|----------|---------------------------|
| Runs entirely client-side, zero server | `index.html` mounts Stlite from CDN only; README "Zero Server Setup" | Persistence is `localStorage`; sharing encodes content in the URL; no new service calls a server |
| No build step, CDN-only dependencies | Repo has no `package.json`; Mermaid and canvg imported as ESM from jsDelivr | New deps (`lz-string`) added as CDN ESM imports only; no bundler introduced |
| Export fidelity is non-negotiable | Three prior fixes: ce61056 (tainted canvas), ed4bb3e (arrowheads/styles), 02ae868 (escaped class-diagram brackets) | Appearance layer must flow into exports unchanged; FR-030 regression checks in the quickstart; SVG-label rendering preserved |
| Small, few-file surface | 224-line `app.py`, 36-line `index.html` | Split into focused modules by responsibility (one clear purpose each) instead of growing the monolith; file count grows modestly, per-file size shrinks |
| Static GitHub Pages deployment | `.github/workflows` uploads the repo root as the Pages artefact | Every added file is plain static/Python; nothing requires server rendering or Node at deploy time |

**Recommended follow-up (not a blocker)**: ratify a real constitution with `/speckit-constitution`
before implementation, so that "no backend", "no build step", and "export fidelity" become stated,
checkable principles rather than tribal knowledge. This plan treats them as binding in the meantime.

## Project Structure

### Documentation (this feature)

```text
specs/001-editor-experience-upgrades/
├── spec.md              # Feature specification (input)
├── plan.md              # This file
├── research.md          # Phase 0: decisions, rationale, alternatives, open spikes
├── data-model.md        # Phase 1: entities, fields, validation, state transitions
├── quickstart.md         # Phase 1: runnable validation guide
├── checklists/
│   └── requirements.md   # Spec quality checklist (pass)
└── contracts/            # Phase 1: interface contracts
    ├── appearance-contract.md   # knobs -> Mermaid config resolution, precedence rules
    ├── render-bridge-contract.md# Python <-> component JavaScript bridge + render states
    ├── share-payload-contract.md# URL payload schema, encoding, size ceiling, decoding errors
    └── template-catalog-contract.md # diagram-type catalog + example schema
```

`tasks.md` is produced by `/speckit-tasks`, not by this command.

### Source Code (repository root)

The feature is delivered inside the existing static, no-build layout. Files are grouped by
responsibility so that each module can be understood and changed on its own — the current `app.py`
mixes UI, rendering JavaScript, and export logic in one 224-line file, which is precisely what has
made the export path need three separate fixes.

```text
index.html              # Stlite bootstrap; extended to fetch the Python modules below
app.py                  # Entrypoint: layout, widget wiring, state orchestration
appearance.py           # Knob definitions, curated schemes, base-colour derivation, validation
templates.py            # Diagram-type catalog + plain and styled examples (data only)
share.py                # Draft persistence (js.localStorage) + share URL encode/decode
render_component.js     # Component-side: parse/render/status/appearance application
export_component.js     # Component-side: SVG serialise, PNG rasterise, clipboard, filename
preview_component.css   # Preview chrome, zoom/fit, dark-mode surfaces
tests/
├── smoke.spec.js       # Playwright: render, error state, appearance, export, share link
└── contract.spec.js    # Appearance resolution, payload round-trip, state transitions
package.json            # Dev-only (Playwright runner); NOT used at deploy time
```

**Structure Decision**: Keep the single-app, client-only shape (`app.py` + component assets at repo
root, served straight by GitHub Pages) rather than introducing `src/`, a bundler, or a build step.
Python modules exist because Stlite's `files` map can carry them, and splitting is justified by the
three recurring export regressions: appearance resolution, render-status handling, and export
serialisation each get one owner module instead of living inline in one f-string. Dev-only tooling
(`package.json`, Playwright) never participates in the deployed site, which preserves the "zero build,
zero server" property.

### Module responsibilities and boundaries

| Module | Does exactly one thing | Depends on | Consumed by |
|--------|------------------------|------------|-------------|
| `appearance.py` | Turns user knob values into a concrete, validated Mermaid config/theme-variable object; owns scheme data and base-colour derivation | Mermaid 11 documented config keys | `app.py`, `render_component.js` (via serialized config), `share.py` |
| `templates.py` | Holds the diagram-type catalog and its plain/styled examples | None | `app.py`, `share.py` (type lookup) |
| `share.py` | Encode/decode the URL payload; read/write `localStorage` draft; report failures as values, never exceptions | `appearance.py` (shape), `templates.py` | `app.py` |
| `app.py` | Composes the four above into widgets and layout; owns what the user sees in Streamlit | `appearance.py`, `templates.py`, `share.py` | `index.html` |
| `render_component.js` | Parses, renders, applies appearance, emits exactly one render state + error detail; keeps last good render | Message from Python | `export_component.js` (current SVG) |
| `export_component.js` | Serialises SVG with inlined styles; rasterises to PNG at chosen scale/background; clipboard write; filename sanitising | Current SVG from render layer | Preview toolbar buttons |

Public surface of the Python/JavaScript boundary is defined in
[contracts/render-bridge-contract.md](./contracts/render-bridge-contract.md); the two sides may be
changed independently as long as that shape holds.

## Phase 0 outcome

All interface-level unknowns that mattered to the design are resolved in
[research.md](./research.md), including three findings that change the implementation plan:

1. `st.code_editor` **is not available** in the Streamlit version bundled by any `@stlite/mountable`
   release (0.73.0 and 0.75.0 both ship Streamlit 1.40.1; the wheel contains no code-editor module).
   FR-033 therefore cannot be satisfied by a Streamlit widget on the current runtime.
2. Mermaid 11 exposes real, typed knobs for exactly what the user asked for: `theme`,
   `themeVariables` (including `fontSize`, `fontFamily`), and per-diagram `nodeSpacing`,
   `rankSpacing`, `padding` — so appearance control is achievable with the library's supported
   surface rather than CSS hacks.
3. `mermaid.parse()` returns a typed `ParseResult` and throws `Error`s carrying position info, and
   `suppressErrors: true` gives a non-throwing boolean-style check — a clean basis for FR-013/014
   without scraping Mermaid's own error rendering out of the DOM.

Three items are left as **verification spikes** with explicit fallbacks already chosen
(S-1 iframe `localStorage` scope, S-2 `st.query_params` behaviour under Stlite, S-3 custom
editor/highlight path). None of them can invalidate the feature; each changes only which module owns
the work. See [research.md](./research.md) §Spikes.

## Post-Design Constitution Re-Check

*Required by the plan workflow: re-evaluate after Phase 1 design.*

| De-facto principle | Re-check result against the designed artifacts |
|--------------------|-----------------------------------------------|
| Runs entirely client-side, zero server | **PASS** — all state lives in `localStorage`/`AppearanceKnobs`/URL fragment; [share-payload-contract.md](./contracts/share-payload-contract.md) §1 forces the fragment (not query string) specifically so content is never transmitted; V-D test 8 asserts no request carries `source` |
| No build step, CDN-only dependencies | **PASS with one note** — the only new dependency is a compression library loaded as CDN ESM (research R-5). `package.json`/Playwright are dev-only and outside the Pages workflow; `quickstart.md` §3 marks it as such |
| Export fidelity is non-negotiable | **PASS** — [appearance-contract.md](./contracts/appearance-contract.md) §6 freezes `htmlLabels: false` as a non-knob regression guard, A-2 forces one resolved object to reach preview and export, and V-E test 3 re-tests the arrowhead/`.mmd` purity bug classes (ed4bb3e, 02ae868, ce61056) rather than trusting them |
| Small, few-file surface | **PASS** — module table in plan.md gives one responsibility per file; `app.py`'s inline JavaScript is *removed*, not grown, and the two largest current pain points (export serialisation, appearance guessing) each gain a single owner. File count grows from 2 to ~10; every file has a stated boundary and consumer |
| Static GitHub Pages deployment | **PASS** — Pages workflow untouched; nothing in the contracts requires a server route; V-D test 8 covers this at runtime |

**Gate status after Phase 1: PASS.** No complexity-tracking entries are required, and the two
deliberate simplifications (no per-element pickers, no stlite major migration) are recorded in
plan.md §Complexity Tracking as rejections rather than violations.

**Residual risk, owned by tasks**: the three spikes (S-1 storage scope, S-2 URL round-trip,
S-3 editor widget) were resolved to *decisions with fallbacks*, not to verified facts, because the
upstream documentation is silent. Each fallback is already chosen in
[research.md](./research.md) and none can invalidate the design — only which module owns the work.
`/speckit-tasks` must schedule S-1 and S-2 as first-day checks since they can change file ownership.

## Complexity Tracking

No constitutional gate failed, so no justified violations are required. Two simplifications were
deliberately taken to keep this feature small:

- **Rejected**: per-element colour pickers and custom CSS theming. Excluded by the spec
  (Assumptions) and unnecessary once base-colour derivation exists.
- **Rejected**: moving to `@stlite/browser` (which ships a much newer Streamlit and would unlock
  `st.code_editor`) as part of this feature. It changes the package name, mount API, and Python/
  Pyodide versions — a platform migration with its own risk, wider than this feature. Recorded as
  S-3 option in [research.md](./research.md) and proposed as a separate follow-up rather than a
  silent dependency of these improvements.
