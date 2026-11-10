# Phase 0 Research: Mermaid Editor Experience Upgrades

**Date**: 2026-11-09 | **Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)

All findings below were **verified against actual shipped artifacts** (downloading the Stlite
package's bundled Streamlit wheel and the `mermaid@11` TypeScript definitions), not against docs
memory. Evidence lines are included so each decision can be re-checked cheaply during implementation.

---

## R-1. Runtime identity and the editor-widget constraint

**Question**: What Streamlit version does the site actually run, and can it provide a
syntax-highlighted editor with line numbers (FR-033)?

**Verified evidence**:
- `index.html` loads `@stlite/mountable@0.73.0`.
- Stlite v0.73.0 release notes: "Dev/streamlit 1.40.1" (PR #1887) → maps to **Streamlit 1.40.1**.
- Downloaded `@stlite/mountable@0.73.0/build/pypi/streamlit-1.40.1-cp312-none-any.whl` and listed its
  contents (296 entries, compiled `.pyc` only).
- `streamlit/elements/widgets/` in that wheel contains: `audio_input, button, button_group,
  camera_input, chat, checkbox, color_picker, data_editor, file_uploader, multiselect, number_input,
  radio, select_slider, selectbox, slider, text_widgets, time_widgets`. **No `code_editor`.**
- No `CodeBlock_pb2.pyc` in the wheel either (the widget's message type), so it is not merely the
  Python side being stripped.
- The newest `@stlite/mountable` is **0.75.0**, and it also bundles **streamlit-1.40.1** — so this is
  not fixed by a minor bump on the current package.
- `st.query_params` modules **are** present (`query_params.pyc`, `query_params_proxy.pyc`,
  `experimental_query_params.pyc`), as are `DownloadButton_pb2.pyc` and `IFrame_pb2.pyc`.

**Decision**: FR-033 (highlighting + line numbers) will **not** be delivered through a Streamlit
widget. The editor either stays a plain `st.text_area` (spec-permitted downgrade) or gains a
CodeMirror-based editor hosted in the component iframe, driven by the bridge in R-4. It is **not** a
separate hand-rolled syntax-highlighting widget.

**Rationale**: The spec explicitly allows the downgrade path
("if a capability cannot be provided, the requirement degrades to plain text editing with line
numbers rather than blocking the feature"). Attempting `st.code_editor` on this runtime fails at
import, so this is a hard constraint rather than a preference.

**Alternatives considered**:
1. **Upgrade to `@stlite/browser`** (the renamed successor, first version 0.76.0 shipping Streamlit
   1.41.0; current 1.12.1 ships Streamlit 1.65.0, which does have `st.code_editor`). Rejected *for
   this feature*: it renames the package, changes the `mount()` API and asset paths (`build/wheels/`
   instead of `build/pypi/`), and moves Pyodide/Python versions. That is a platform migration whose
   blast radius (all existing Stlite behaviour, the export fixes, first-load size) exceeds this
   feature's scope, and doing it silently inside an "improvements" change would make regressions
   impossible to attribute. Tracked as spike **S-3** and recommended as a separate follow-up.
2. **Ship a stub/shim implementing the missing widget**: impossible — the widget needs a matching
   frontend React component and protobuf message, neither present.
3. **Accept no line numbers at all**: rejected, because line numbers are what make FR-014's
   "points at the line" error message actionable for the user.

---

## R-2. Appearance control maps onto supported Mermaid 11 config, not CSS hacks

**Question**: Can a user-facing "font size / colours / spacing" panel be implemented through the
library's real configuration surface (FR-001, FR-003..007), and what are the exact knobs?

**Verified evidence** (from `mermaid@11/dist/config.type.d.ts`, 62 KB):

| Need | Verified config surface |
|------|-------------------------|
| Colour scheme | `theme?: 'default' \| 'base' \| 'dark' \| 'forest' \| 'neutral' \| 'neo' \| 'neo-dark' \| 'redux' \| 'redux-dark' \| 'redux-color' \| 'redux-dark-color' \| 'null'` |
| Per-element colours | `themeVariables?: any` (the documented variable bag, e.g. `primaryColor`, `lineColor`, ` textColor`, `primaryBorderColor`) |
| Global text size | top-level `fontSize?: number` (also `CSSFontSize = string \| number` used by `FontConfig`) |
| Global text family | top-level `fontFamily?: string` |
| Flowchart spacing | `flowchart?: FlowchartDiagramConfig` → `nodeSpacing?: number`, `rankSpacing?: number`, `padding?: number` |
| Spacing in other types | `padding`, `nodeSpacing`, `rankSpacing`, `fontSize` repeat across per-diagram config interfaces (sequence, gantt, journey, mindmap, class/state, pie, sankey, packet, block…) |
| Font per-diagram overrides | `FontConfig { fontSize, fontFamily, fontWeight }` |
| Error rendering control | `suppressErrorRendering?: boolean` — documented as "Suppresses inserting 'Syntax error' diagram in the DOM. This is useful when you want to control how to handle syntax errors in your application." |

**Decision**: Introduce **one resolved appearance object** (see
[contracts/appearance-contract.md](./contracts/appearance-contract.md)) produced by
`appearance.py`, which maps the small user-facing knob set onto `theme`, `themeVariables`,
top-level `fontSize`/`fontFamily`, and a **per-diagram-type spacing table**. The same object is
serialised once and consumed by preview, export, and share links (FR-008). Spacing defaults are
raised above Mermaid's own (FR-006), informed by the reviewed styling guide's point that spacing
improves a diagram more than colour does.

**Amendment - appearance spellings (verified in Chromium, `mermaid@11.12.0`)**: two rows of the
R-2 table above are necessary but not sufficient — Mermaid reads *other* spellings at paint time:

| Need | Table above said | What `mermaid@11.12.0` actually honours |
|------|------------------|------------------------------------------|
| Global text size | top-level `fontSize` | top-level `fontSize` only becomes Mermaid's derived base (28 in → 14 px on the label). The rendered flowchart label follows **`themeVariables.fontSize` as a unit-carrying string** (`"28px"`). `primaryFontSize` etc. are accepted by the config type but never size labels. |
| Per-element colours | `themeVariables` (`primaryColor`, `lineColor`, …) | The base keys move the node fill/border; the generated CSS reads Mermaid's **derived** variables — `nodeTextColor`/`primaryTextColor`, `defaultLinkColor` (← `lineColor`), `nodeBorder`/`tertiaryBorderColor`, `titleColor`, `edgeLabelBackground` (else "calculated from secondaryColor"). Emitting only base keys left link stroke, edge-label plate and label text on library stock (`#9370DB`, `#ECECFF`) for *every* named theme, so FR-003 held for 2 of 5 roles. |
| Scheme knob vocabulary | — | The offered `schemeName` list is exactly the catalog key set (**11**: `neo`, `neo-dark`, `redux`, `redux-dark`, `redux-color`, `redux-dark-color`, `default`, `neutral`, `forest`, `base`, `dark`). Keeping `dark` in the palette table but out of `SCHEME_NAMES` meant `schemeName="dark"` failed domain validation and silently rendered `neo`. The name is appended last so share-link numeric indexing of the first ten is unchanged (contract §1 "the 10 catalog names" becomes 11 offered names, §5's "≥6 required" still satisfied). |

`appearance.py` therefore emits the numeric and string spellings side by side, fills
`PALETTE_ALIASES` from the palette's own values *before* the contrast pass (so an aliased spelling
clamps and is reported exactly like the variable it mirrors), and derives `SCHEME_NAMES` from the
catalog keys. FR-002 and A-3 keep their numbers: 12/14/16/20/28 px, 28 ÷ 12 = 2.333× ≥ 2.0.


**Rationale**:
- Per-diagram-type tables are mandatory, not optional, because the type definitions show spacing and
  font keys duplicated across separate diagram config interfaces — a single global setting is not
  honoured uniformly. `themeVariables.fontSize` in particular is not a universal lever across all
  diagram types; the top-level `fontSize` plus per-type configs are.
- `suppressErrorRendering` is the documented, purpose-built mechanism for taking over error display,
  which means FR-013 does not require scraping Mermaid's own error SVG out of the DOM.
- Using the library's config surface keeps appearance in the exported SVG (Mermaid writes
  `themeVariables` into its generated CSS). A CSS-override approach would render correctly on screen
  but be lost on serialisation, directly violating FR-008 and repeating the class of bug that caused
  commits ed4bb3e and ce61056.

**Amendment - render ceilings (verified in Chromium, `mermaid@11.12.0`)**: the resolved object
handed to `mermaid.initialize()` must also carry Mermaid's own **input ceilings**, raised above their
defaults — `maxEdges: 5000` (default 500) and `maxTextSize: 200000` (default 50 000). Without them a
500-edge diagram and the 50 000-character boundary fixture are rejected by the library with an
"Edge limit exceeded" / text-size error, i.e. SC-003 ("a 500-node diagram is never reported broken")
is unsatisfiable through appearance/`diagram_config` alone. Both keys are *secure* configuration:
Mermaid reads them only from the initialize object and refuses to set them from in-diagram
`%%{init}%%` text, so raising them cannot weaken the frozen `securityLevel: 'strict'` story, and a
diagram cannot lower them back. They live on the initialize-boundary object
(`appearance.RENDER_LIMITS`, re-applied last in `build_mermaid_config_output`) and are mirrored onto
the resolver output, because that payload — not a Python-built initialize object — is what streams
to the component and feeds `mermaid.initialize` in `render_component.js`.

**Alternatives considered**:
1. **Inject a `<style>` block after render and override colours with CSS**: rejected — invisible to
   `getSerializedSVG()`, so exports would diverge from the preview.
2. **Rewrite the user's diagram text with front-matter/`%%{init}%%` directives**: rejected — mutates
   the user's source, breaks FR-009's precedence clarity, and the spec's Assumptions forbid silent
   automatic rewriting of user content.
3. **`look: 'classic' | 'neo'` only, no derived colours**: rejected — cannot satisfy FR-004
   (user's own base colours) or the "match the destination surface" need.
4. **Per-element colour pickers**: rejected as out of scope per spec Assumptions (different, larger
   feature).

**Known limitation to design around**: the existing app forces `htmlLabels: false` for export
fidelity. With SVG `<text>` labels, `fontFamily` applies, but **web fonts loaded only by the page are
not embedded in serialised SVG**, so exported files fall back to system fonts unless the chosen fonts
are web-safe stacks. Therefore FR-005's three offered fonts are **web-safe stacks only** (system
sans, system serif, monospace) — no custom web font — so preview and export agree. This is a
deliberate scope reduction, recorded here so `/speckit-tasks` does not reintroduce a web font.

---

## R-3. Parse/render status can be determined programmatically with a typed API

**Question**: How does the app know a diagram is invalid, and which line is at fault (FR-012..016)?

**Verified evidence**:
- `mermaid@11/dist/types.d.ts`:
  ```ts
  export interface ParseOptions { suppressErrors?: boolean; }   // true => returns false instead of throwing
  export interface ParseResult { diagramType: string; /* + config from frontmatter/directives */ }
  ```
- `mermaid@11/dist/mermaidAPI.d.ts`:
  ```ts
  declare function parse(text, parseOptions: ParseOptions & { suppressErrors: true }): Promise<ParseResult | false>;
  declare function parse(text, parseOptions?: ParseOptions): Promise<ParseResult>;
  ```
  Documented: "returns `ParseResult` otherwise `false` if `suppressErrors` is `true`; **throws Error**
  if the diagram is invalid and `suppressErrors` is false or not set."
- `mermaid.render(id, text)` is the documented render path (`const { svg, bindFunctions } = await
  mermaid.render('graphDiv', graphDefinition)`).
- `mermaid.d.ts` exposes `setParseErrorHandler((err, hash) => void)` and a deprecated `parseError`
  property — a supported hook for capturing error details including position, and `parse()`'s thrown
  `Error` carries the Jison `loc` info (`hash`/error location) for line hints.

**Decision**: Preview pipeline becomes **validate-then-render**: `parse(text, { suppressErrors: true
})` to classify, then `render()` only when valid, with `suppressErrorRendering: true` so Mermaid's
built-in "Syntax error" diagram never appears. Emit exactly one of four states (`rendering`,
`rendered`, `invalid`, `empty`) to the parent (FR-013), and derive the message plus line number from
the parse failure (FR-014) through a small normaliser, so the raw library error text is never shown
unfiltered. The last successful SVG stays in memory and is re-shown in a "last valid" panel (FR-016).

**Rationale**: `suppressErrors: true` returning `false` would give only a boolean, so it is
insufficient alone for FR-014 (needs line info). Combining the boolean gate with the documented error
handler gives both a reliable classification and the position, and matches the library's intended
"control how to handle syntax errors in your application" pattern. `deterministicIds` exists in the
config, which makes repeated renders safe to diff/replace without id churn.

**Alternatives considered**:
1. **`startOnLoad` + scraping Mermaid's error text out of the DOM**: rejected — fragile across
   versions, cannot distinguish slow render from failure (SC-003 requires zero false errors), and
   shows an ugly library-rendered error by default.
2. **`on error` event on the iframe**: rejected — cannot express line/position, and cannot tell
   invalid from in-progress.
3. **Own a Mermaid-grammar validator in Python**: rejected — massive duplicated effort with no
   guarantee of matching the real parser.

---

## R-4. Component-to-parent direction is the one-way door

**Question**: Can JavaScript inside `components.html` tell Python about the render state, so the
Streamlit area can show a banner (FR-013 needs a persistent, non-iframe-visible state)?

**Verified evidence and reasoning**:
- Streamlit's `components.html` (the `IFrame` path, whose `IFrame_pb2` exists in the bundled wheel) is
  **parent → iframe only**: a static HTML string, no return channel. Two-way values require a declared
  custom component (`components.declare_component`) using the component-repository iframe API
  (`Streamlit.setComponentValue` / `window.parent.postMessage` envelope), and custom components under
  Stlite need their assets provided in the app file map — no CDN-hosted component server.
- Stlite's own README "known issues" documents behavioural gaps in this runtime (e.g. `st.spinner()`
  does not work with blocking calls, because it is a single-threaded Pyodide environment) — evidence
  that relying on Streamlit re-run semantics around a component is risky in this runtime.

**Decision**: Put render state, errors, zoom, appearance application, and export **entirely inside the
component iframe**, in `render_component.js` / `export_component.js`. The iframe draws its own status
bar, error panel, and preview toolbar (a thin HTML/JS chrome, not a Streamlit widget). Python's job is
to collect widgets, resolve appearance, and pass one serialised message in. The state machine and the
message shape are specified in [contracts/render-bridge-contract.md](./contracts/render-bridge-contract.md).

**Rationale**: The spec's acceptance criteria for feedback and preview control are all satisfiable
inside the iframe, and this removes the only capability in this feature that the runtime cannot
provide. It also makes the component side independently testable with Playwright against
`contracts/`, without a Python test harness.

**Alternatives considered**:
1. **Declared custom component with `setComponentValue`** for state → Python: rejected — needs a
   component build/serve path that conflicts with the repo's no-build constraint, and Stlite support
   for that path is unverified; it buys only the ability to render a *second* copy of the state in
   Streamlit chrome.
2. **Re-run the Streamlit script to read state back through a hidden widget or query param**: rejected
   — write path from the iframe into the parent's URL is subject to the unknown of spike S-2, and a
   re-run per keystroke in a single-threaded WASM runtime risks the responsiveness target in SC-009.
3. **Polling from Python into the iframe**: rejected — no supported read channel from Python into a
   `components.html` iframe.

**Consequence**: FR-022 (draft restore notice) and FR-021 (retitle) live on the Python side and are
fully supported; FR-013/014/016 and all preview chrome live iframe-side. No requirement is lost by
this split.

---

## R-5. Persistence and sharing are achievable without a server

**Question**: Where do drafts live, and how does a link carry a diagram (FR-022..026, FR-027)?

**Verified evidence**:
- Stlite uses Pyodide, whose runtime exposes the browser's `js` module to Python — so `localStorage`
  and `location` are reachable from `app.py`. (Confirmed the runtime is Pyodide-based from
  `index.html` + stlite README: "runs on Pyodide … WebAssembly-ported Python"; the specific iframe
  scope question is tracked as **S-1**.)
- `streamlit/runtime/state/` and `query_params` modules exist in the bundled wheel, so
  `st.session_state` and `st.query_params` are available. Stlite's README documents no restrictions on
  them, but it also does not promise URL round-tripping — hence **S-2**.
- Diagram content must travel inside the URL, matching the widely used pattern of self-contained
  diagram-editor links (compressed fragment payload), because no backend may be introduced
  (README "Zero Server Setup", and the Pages workflow uploads the repo root as static content).

**Decisions**:
- **Drafts**: `localStorage` writes from `app.py` via the `js` module, debounced, storing `{ source,
  name, appearance, type, updatedAt }`. Restore is opt-in with a visible banner and a clear discard
  control (FR-022/023). Unavailable storage degrades to an explicit "not being saved" notice
  (FR-027) rather than a silent failure.
- **Share links**: diagram + appearance compressed and base64-ish encoded into the URL **fragment**
  (`#`), not the query string — the fragment is never transmitted to a host, which keeps GitHub Pages
  logs clean and is the standard approach for self-contained editor links. Decoding never throws: it
  returns a typed error value that maps to FR-026's message.
- **Size ceiling**: links have a practical length limit; the app pre-computes payload size and switches
  to "too large to link — download the source instead" (FR-025). Threshold pinned in
  [contracts/share-payload-contract.md](./contracts/share-payload-contract.md).
- **Compression**: `lz-string` (or equivalent) via CDN ESM, encode in the component/JS layer or a tiny
  Pyodide-side equivalent — decided in favour of doing it **in `share.py`** using a pure-Python
  deflate-free scheme only if size tests pass; see alternatives.

**Rationale**: Fragment-based, content-in-URL sharing satisfies SC-006 ("0 bytes of diagram content
stored server-side") structurally rather than by policy. Doing persistence in Python keeps one owner
for state, since Python already owns widgets and the diagram text.

**Alternatives considered**:
1. **IndexedDB instead of `localStorage`**: rejected — no benefit at this data size (a diagram is
   text; a few KB), and it adds an async API to a sync-feeling flow.
2. **Gist/paste service for sharing**: rejected outright — it stores user content on a third-party
   server, violating SC-010 and the spec's Assumptions.
3. **`st.session_state` alone for drafts**: rejected — it is per-session and does not survive a reload,
   which is exactly the failure FR-022 fixes.
4. **`pako`/deflate instead of `lz-string`**: viable, kept as the fallback if the payload budget is not
   met; `lz-string` chosen first for its compactness on text and single-function API.

---

## R-6. Preview sizing, zoom, and dark mode are component-side

**Question**: How to remove the fixed-height scroll box (FR-034/035) and add interface dark mode
(FR-036)?

**Verified evidence**:
- `app.py` currently calls `components.html(mermaid_html, height=600, scrolling=True)` — the fixed box
  users are stuck with; and `st.set_page_config(layout="wide")` is already used.
- `IFrame` protobuf supports only a static height in this architecture; there is no supported way for
  the Streamlit script to grow after render without a re-run.

**Decisions**:
- The component measures its own content and resizes its hosting iframe by posting a sized message to
  `window.parent` (the iframe element is reachable from `index.html`-side code, which is already
  under this project's control — a plain JS snippet, no build step). Fallback when measurement is
  unavailable: keep a single generous height with the preview scrolled at the page level instead of
  inside the box.
- Zoom in / out / **fit** are implemented by scaling the rendered SVG inside the preview chrome (FR-035
  with SC-008's "no more than 3 zoom actions" requirement), with fit computed from the SVG's
  `viewBox` and the available width — the same `viewBox` reading the export code already performs.
- Interface dark mode is a CSS custom-property theme for the component chrome + Streamlit's own
  page-style colours for the surrounding app; it must **not** alter the diagram's chosen appearance
  object (FR-036), which is why appearance and interface theme are kept as separate concepts in
  [data-model.md](./data-model.md).

**Rationale**: The project controls `index.html`, so resize-by-postMessage costs no dependency and
stays inside the no-build rule. Keeping zoom client-side avoids re-running Mermaid on every gesture
(performance target: appearance/zoom changes reflected within 3 s, SC-009).

**Alternatives considered**:
1. **Re-render at each zoom level**: rejected — wasteful, causes label flicker, and complicates export
   (an export could capture a mid-zoom SVG).
2. **Drop the iframe entirely and render into the parent DOM**: rejected — Mermaid lives in the
   component's module scope; reaching the parent DOM means a cross-origin/module problem and forfeits
   the isolation that keeps Mermaid's global CSS from leaking into Streamlit's.
3. **`st.columns` + a taller fixed height**: rejected — still a fixed box; does not satisfy FR-034's
   "whole diagram visible" criterion for the tail of the range of diagram sizes.

---

## R-7. Export: keep the proven path, add the knobs

**Question**: How to add scale/background/name/clipboard (FR-028..032) without regressing the fixes
already made?

**Verified evidence**: The current chain is `getSerializedSVG()` (clone → inline computed styles from a
property whitelist → strip internal `<style>` → fix `url(#…)` marker references → add xmlns) then
`canvg` for PNG. Its history is the specification for what must not break: ce61056 (tainted canvas),
ed4bb3e (arrowheads/style loss from HTML labels), 02ae868 (angle-bracket notation eaten by the HTML
parser before Mermaid sees it).

**Decisions**:
- Keep `canvg` as the rasteriser. It is already proven to avoid the tainted-canvas failure in this
  exact content-encoding situation; replacing it re-opens a closed bug class. An
  `createImageBitmap` fast path may be added *behind* the existing behaviour, never instead of it.
- Scale, background, and filename become parameters of one `exportAs(kind, { scale, background,
  name })` entry point in `export_component.js`, so there is exactly one code path from
  "diagram on screen" to "file" (FR-030). `background: 'transparent'` means "do not paint the
  backdrop", which the current code hard-codes to white.
- The style whitelist gains the properties needed to keep hierarchy/emphasis styling (FR-007) in
  exports; every export scenario in the quickstart asserts arrowheads and line styles survive.
- Clipboard uses `navigator.clipboard.writeText` for SVG markup with an explicit explained fallback to
  download when the browser refuses or the API is missing (FR-032).
- Filenames are sanitised to remove path separators and control characters while preserving non-ASCII,
  and the sanitiser is shared with `.mmd` download so the Streamlit side and component side agree
  (FR-031).

**Rationale**: This area has needed three fixes; the safest route is to parameterise the existing
serialisation rather than swap libraries. Requiring a single export entry point is what keeps
"preview equals export" (FR-008) checkable.

**Alternatives considered**:
1. **`html-to-image` / `dom-to-image`**: rejected — operates on DOM elements including HTML labels,
   which reintroduces the exact label problem ed4bb3e fixed, and they inline resources by fetching
   (tainting/CORS exposure).
2. **Server-side rasterisation**: rejected — would introduce the backend the project forbids.
3. **Offering SVG-in-`<img>` PNG via canvas `drawImage` of a data URL**: kept only as a possible fast
   path, not the default, because the tainted-canvas history shows the encoding details matter here.

---

## R-8. Diagram-type breadth is available as shipped feature data

**Question**: Which additional diagram types can genuinely be offered (FR-017)?

**Verified evidence**: The `MermaidConfig` interface in `mermaid@11` lists first-class per-diagram
configs for, among others, `flowchart`, `sequence`, `class`, `state`, `er`, `gantt`, `journey`,
`timeline`, `pie`, `mindmap`, `quadrantChart`, `xyChart`, `requirement`, `architecture`, `sankey`,
`packet`, `block`, `treeView`, `radar`, `venn`, `gitGraph`, `c4`, `kanban`, `ishikawa`, `cynefin`,
`railroad`, `swimlane`, `eventmodeling`. Anything with a config interface is a supported type in the
version this site loads. The nine required by FR-017 are all in that list.

**Decision**: Implement all nine FR-017 types, each with a plain example plus a styled showcase, and
catalogue them as data (`templates.py`) with a documented extension route, so a future type is a data
change rather than a code change. Type detection for the empty/mismatch cases uses
`ParseResult.diagramType` (verified in R-3), not string-prefix sniffing.

**Rationale**: Using `diagramType` from the parse result gives an authoritative, version-stable way to
detect a type mismatch (edge case in the spec) instead of maintaining a prefix table.

**Alternatives considered**:
1. **Offer every type Mermaid supports**: rejected — 25+ examples to maintain and verify exceeds the
   spec's stated scope; more types would dilute the curation the styling inspiration asks for.
2. **Sniff the first token of the source for type detection**: rejected — breaks on `%%{init}%%`
   directives, blank leading lines, and comments, which a class-diagram-with-angle-brackets style
   input already demonstrated as a real trap (commit 02ae868).
3. **Defer non-flowchart types behind a feature flag**: rejected — the requester's stated goal is
   breadth, and R-2 shows appearance is per-type work that cannot be punted one type at a time.

---

## Spike Outcomes (resolved during implementation, 2026-11-09)

| ID | Outcome | Evidence | Shipped as |
|----|---------|----------|------------|
| **S-1** | **Failed as designed — moved to the fallback.** `localStorage` is unreachable from both places the design had considered. (a) `app.py` runs in a Pyodide **Web Worker**, and `WorkerGlobalScope` has no `localStorage` (HTML spec). (b) `st.components.v1.html` renders through a **`srcdoc` iframe**: the bundled protobuf `Html` message carries `src`/`srcdoc` fields (verified in `@stlite/mountable@0.73.0/build/stlite.js`: `e.prototype.srcdoc=null`, `case 2:r.srcdoc=e.string()`), and a `srcdoc` document is a fresh null-origin context. | `grep -oE "srcdoc\|URLSearchParams" stlite.js` on the shipped build. | `index.html` (the only same-origin, real-DOM context in the app) owns `localStorage` + the URL fragment. It hands `boot.json` to Python *at mount time* through `stlite.mount({files})` — Stlite's `files` map is the documented same-origin handoff, and `fetch` cannot serve files the mount has not registered. The component talks back over `postMessage` (`mmd-store`, `mmd-clear-storage`, `mmd-link`, `mmd-height`, `mmd-host`). Drafts: `mermaidGui.draft` / `mermaidGui.appearance`. |
| **S-2** | **Unreliable — not used for state.** The bundle contains no app URL syncer; every `URLSearchParams`/`search`/`hash` hit in `stlite.js` belongs to bundled third-party libraries (axios' `URLSearchParams` polyfill, dayjs parsing). Streamlit's `AppUrlSyncer` lives in the websocket/frontend layer that Stlite does not ship, so `st.query_params` writes cannot be relied on to move the real browser address. | same bundle, `grep -oE "replaceState|URLSearchParams"` — no `history.replaceState` call site. | Share links are produced by an explicit **Copy link** action in the sidebar, and the page address is updated only on request (the component asks `index.html` to `history.replaceState`). FR-019's "page's own address" is therefore *opt-in*, not automatic — recorded as a deliberate downgrade, not a silent one. |
| **S-3** | **Not performed** (verified as unnecessary for this feature's scope, and confirmed as the only route available for FR-033). Migration `@stlite/mountable@0.73.0` → `@stlite/browser` changes the package name, `mount()` API and asset paths and moves Streamlit from 1.40.1 to ≥1.41, which is where `st.code_editor` first exists. It gates only FR-033. | `@stlite/mountable@0.73.0` bundles Streamlit 1.40.1 (`grep -o "1\.40\.1" stlite.js`), where `st.code_editor` is absent; `dir(streamlit)` in the mounted runtime has no `code_editor`. | FR-033 ships the spec's documented downgrade plus the one part that *is* caret-derived: `app.py` states the line range under the editor, every failure message names the line it stopped at, and `host_bridge.js` reads the live caret from the app's own textarea (a `Line N of M` readout that updates on click, keystroke and scroll). Python cannot see a caret -- Streamlit exposes no caret or scroll position to the script -- so that half is done where the caret actually lives. Migration to `@stlite/browser` (where `st.code_editor` exists) stays a follow-up for full structural highlighting.

FR-037 holds: paste and native undo are the browser's textarea behaviour, and `host_bridge.js` adds the indent behaviour a textarea does not have -- Tab inserts two spaces at the caret and indents every line a selection touches, Shift-Tab removes one level the same way, and both fire a real `input` event plus a `change`, which is how Streamlit's widget sees the edit and how it commits on blur. A Shift-Tab with nothing to remove is deliberately left to the browser, so the page's tab order stays a way out of the editor. |

Consequence for the render bridge: because the component document is **replaced on every
rerun**, it cannot remember the last good picture or the zoom level by itself. `index.html`
holds those in a host-side store (`mmd-host` get/set) so FR-016 and FR-035 survive a keystroke.

### Runtime facts measured in Chromium while building this feature (2026-11-09)

Each of these was found by driving the shipped artifacts in a real browser, not by reading
documentation, and each one changed the implementation. They are recorded here because every
one of them is a way the design could have been silently wrong.

| Observation | Evidence | Consequence |
|---|---|---|
| Mermaid sizes diagram labels from the **px string** in the theme; a numeric top-level `fontSize` is only the base it derives other sizes from, and `primaryFontSize`/`secondaryFontSize` do not size flowchart labels. | `getComputedStyle(<text>)` after `initialize({themeVariables:{fontSize:'28px'}})` → 28 px; `{fontSize:28}` alone → 14 px; `{primaryFontSize:'28px'}` → 16 px. | `appearance.resolve()` emits `themeVariables.fontSize = "28px"` (and keeps the numeric alias for consumers). |
| `mermaid.initialize()` reads each family's settings from a **top-level key named after the family**. A nested `diagram_config`/`perDiagramConfig` object is an unknown key and is dropped without complaint. | viewBox width of one fixed flowchart across densities: 258 / 273 / 302 / 322 after the expansion; identical 273 px before it. | `configureOptions()` expands the per-family object and excludes the resolver's report keys (`sourceOf`, `clamped`, `frozen`, `family`, `export`, …) from `initialize`. |
| `securityLevel` ceilings `maxEdges` (500) and `maxTextSize` (50 000) reject the largest documents this app must handle ("Edge limit exceeded…"), and a diagram's own `%%{init}` block cannot raise them — they are secure settings. | Mermaid 11.12 error text on `tests/fixtures/max-size-50000.mmd` (1 155 edges). | `appearance.RENDER_LIMITS` raises them on the initialize object only, re-applied last, so front matter cannot lower them (SC-003). |
| Mermaid 11's `parse()` is a promise API, and `parse(text, {suppressErrors:true})` resolves `false` with no details at all. | Calling it synchronously produced an unhandled rejection and no message. | Details come from `await mermaid.parse(source)` in a rejection path, and the parse's position lives in `error.hash.loc`, not `error.loc`. |
| Every parse error puts its position only in `error.hash` = `{text, token, line, loc:{first_line,…}, expected}`; an EOF error names a line *past* the last line. | Probed against `flowchart TD\n A -->\n` → `first_line` 4 in a 2-line file. | `normalizeError()` reads `hash.loc.first_line` (1-based) and worded the "before the first line" and "past the end" cases. |
| A `srcdoc` component frame reports `location.origin === "null"` **and** can still reach `localStorage` in Chromium (the storage partition resolves through the embedding document). | `live-app.spec.ts` sandbox probe: `origin: null`, write and read succeeded from inside the component. | Host ownership of storage and the address bar is kept as a **determinism and privacy** choice, not a capability workaround: it gives one writer, survives the component being replaced on every rerun, and does not depend on per-browser srcdoc behaviour. |
| Stlite runs the script in a Web Worker, so `app.py` has no `window` at all; `st.components.v1.html` arrives as a *fresh* srcdoc document on each rerun. | Worker scope has no `localStorage`/`document`; the Html protobuf message carries `srcdoc`. | `index.html` hands a one-shot `boot.json` in through `stlite.mount({files})` and mirrors the stateful bits (`lastGood`, zoom) for the component. |
| **A component that is not re-emitted on a rerun disappears from the page.** `components.html()` is not "leave it alone if nothing changed". | Live boot: after the unsaved-text guard (a rerun that changed no text) the iframe count went 1 → 0 and the preview was gone. | `_preview()` emits the document on *every* rerun and reuses the unchanged payload and request id; the 320 ms debounce governs new sends, not element upkeep (contract §1 rule 2). |
| `@stlite/mountable`'s UMD build defines the global `stlite` only when its script finishes, and it exposes exactly `{ mount }`. | Booting `index.html` with the script tag after the boot code → "Cannot read properties of undefined (reading 'mount')". | `stlite.js` is loaded in `<head>` and `index.html` still waits for `stlite.mount` to exist before mounting. |
| `host_bridge.js` must install itself on load: the boot snapshot is read *before* anything else runs, and an un-probed store reports `storage: "unavailable"`, which makes the app tell users drafts cannot be kept when they can. | Live app showed the private-mode warning while `localStorage` was perfectly writable. | Loading the file installs the bridge (`if (!root.__mermaidGuiBoot) install()`), and `index.html` calls `install()` defensively. |
| Mermaid emits one **empty** `<text>` element per diagram, and labels are plain `<text>` because `htmlLabels` is frozen off. | `locator('svg text').first()` was invisible in Playwright. | Selections filter `hasText: /\S/`; the export CSS inlining whitelist stays in force (research R-2). |
| The component sits **two** frames deep (`index.html` → app iframe → component `srcdoc`), so `window.parent` is a frame running none of our code. | `mmd-status`/`mmd-height` posted to `window.parent` never arrived. | Relays address `window.top`, and height replies resize only the frame whose document carries the matching `<meta name="mmd-doc-key">`. |

## Decision Summary

| # | Decision | Rationale (short) | Rejected alternatives |
|---|----------|-------------------|-----------------------|
| R-1 | No `st.code_editor` on current runtime; degrade or component-side editor | Widget absent from bundled Streamlit 1.40.1 wheel | Upgrade stlite mid-feature; hand-rolled highlighter |
| R-2 | One resolved appearance object mapped onto Mermaid `theme`/`themeVariables`/`fontSize`/`fontFamily`/per-type spacing; web-safe fonts only | Exports must match preview; per-type configs are not uniform | Post-render CSS injection; mutating user text with directives; per-element pickers |
| R-3 | `parse({suppressErrors:true})` gate + `suppressErrorRendering` + error handler for line info; four explicit states; keep last good render | Built for application-owned error UI; no DOM scraping | Scraping library error from DOM; owning a Mermaid grammar in Python |
| R-4 | All render state, status chrome, zoom, export live in the component iframe | `components.html` is one-way; avoids unsupported custom-component path | `setComponentValue` custom component; iframe→parent URL writes; Python polling |
| R-5 | `localStorage` drafts (opt-in restore notice); URL **fragment** links carrying content; size ceiling with download fallback | No backend allowed; structurally guarantees no server storage | IndexedDB; third-party paste/gist services; `session_state` alone |
| R-6 | iframe self-resize via postMessage to `index.html`; SVG-scale zoom/fit from `viewBox`; interface dark mode separate from diagram appearance | Project owns `index.html`; no re-render per gesture | Fixed taller box; re-rendering per zoom; parent-DOM rendering |
| R-7 | Keep `canvg`; single parameterised `exportAs()` entry; expanded style whitelist; clipboard with explained fallback; shared filename sanitiser | Parameterise the proven path rather than reopen a thrice-fixed bug class | `html-to-image`; server rendering; replacing canvg wholesale |
| R-8 | Ship FR-017's nine types as data-driven catalog with plain + styled examples; detect type via `ParseResult.diagramType` | Config interfaces confirm support; data change extends it | All ~25 types; prefix sniffing; feature-flagging types in |
