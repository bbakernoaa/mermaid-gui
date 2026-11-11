# Tasks: Mermaid Editor Experience Upgrades

**Input**: Design documents from `specs/001-editor-experience-upgrades/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (all present)

**Tests**: INCLUDED — `quickstart.md` §4 defines the validation suites and `contracts/` §8 defines
the conformance tests (A-1..A-9); the plan treats them as binding, so every story has test tasks that
MUST be written and fail before their implementation tasks.

**Organization**: Tasks are grouped by user story so each story is an independently implementable and
testable increment.

**Constitution check**: `.specify/memory/constitution.md` is still the unfilled scaffold → **zero
gates** apply to this task list. Nothing here is blocked by governance; a ratification pass
(`/speckit-constitution`) is recommended before Phase 3 so the plan's five de-facto principles
(client-only, no build step, export fidelity, small surface, no content to servers, no silent rewrite
of user input) become enforceable rather than tribal knowledge.

**Runtime pin (applies to every task)**: site stays `@stlite/mountable` 0.73.0 / Streamlit 1.40.1.
`st.code_editor` is ABSENT from that runtime (research R-1). Do not write code against it.

---

## Phase 1: Setup (repo + dev-only tooling; deploy path stays build-step-free)

- [X] T001 Create module skeleton per plan.md §Source Code: stub `appearance.py`, `templates.py`,
      `share.py`, `render_component.js`, `export_component.js`, `preview_component.css`, plus a new
      `messages.py` (bridge payload shapes only), each carrying ONLY the single responsibility named
      for it in the plan.md module table; do not move real logic yet.
- [X] T002 [P] Add dev-only test tooling without touching the Pages workflow: `package.json` with
      `playwright` as a **devDependency only** (never used at deploy time), `playwright.config.ts`
      that serves the repo root over `http://127.0.0.1:8000` via `python3 -m http.server`, and
      `pytest.ini` restricted to `tests/` (pure-Python modules only — `appearance.py`, `share.py`,
      `templates.py` must stay import-free of `streamlit` so `pytest` works without a browser).
- [X] T003 [P] Author shared fixtures in `tests/fixtures/`: `max-size-50000.mmd` (exactly 50 000
      chars — `data-model.md` §1 `editorLimits.maxPasteChars`), `invalid-line-2.txt` (a bad arrow on
      line 2), `large-500-nodes.mmd`, `unicode-edge-cases.mmd` (accents, CJK, Cyrillic, emoji),
      `notation-edge-cases.mmd` (`<<interface>>`, labels containing `" ' { }`), `type-mismatch.txt`
      (valid sequence text while another type is selected), and `long-120-lines.mmd` — all consumed
      by V-A/V-B/V-C/V-D/V-E and by T004, T010, T011, T018.
- [X] T004 [P] Add a CI smoke job in `.github/workflows/ci.yml` (new file; do NOT alter the Pages
      deploy workflow): run `python3 -m pytest tests/ -q` — deploy stays "upload repo root to Pages".

## Phase 2: Foundational (blocking prerequisites for EVERY story)

- [X] T005 [P] Run spike **S-1** and record the outcome in `research.md` §Open Spikes: probe in the
      `http.server` run whether `localStorage` is reachable from `app.py`'s Pyodide `js` module and
      which origin it resolves to. Decide the owning module for `share.py` persistence (Python =
      chosen path, component-side = fallback). **Gates T015-T019.**
- [X] T006 [P] Run spike **S-2** and record it in `research.md` §Open Spikes: does `st.query_params`
      write back to the **real** browser URL in Stlite? If not, share links are produced only by an
      explicit Copy-link field and the live-URL path is dropped; the rest of US4 is unaffected.
      **Gates T020, T021 only.**
- [X] T007 [P] Run time-boxed spike **S-3** and record it in `research.md` §Open Spikes: migration
      branch probe from `@stlite/mountable` 0.73.0 to `@stlite/browser` (renamed package, changed
      `mount()` API, `build/wheels/` asset path, newer Streamlit). Outcome decides **only** T050.
- [X] T008 Wire the inbound bridge in `app.py` per `contracts/render-bridge-contract.md` §1: serialize
      `RenderRequest` JSON into the template, issue a strictly increasing `requestId` per change,
      debounce source sends ≥ 320 ms, and add the fixed settings `htmlLabels=false` and
      `suppressErrorRendering=true` to the initialize options.
- [X] T009 Wire the outbound bridge in `messages.py` and `preview_component.css`: `RenderStatus`
      carries `requestId` echo, `state` ∈ `rendering rendered invalid empty`, `diagramType` from Parse-
      Result, `error` (present iff invalid), `clamped` (list of adjusted colour variable names or
      empty). Inbound and outbound shapes defined in one place; a test asserts the enum is
      complete and unambiguous; every requirement's UI claim traces to one of these states.
- [X] T010 [P] Write failing state-machine tests in `tests/test_states.py` (pure) and `tests/
      render-states.spec.ts` (visual) directly from `quickstart.md` §V-B rows, including the two that
      protect SC-003: a 500-valid-node diagram must NEVER reach `invalid`, and `empty` must never
      carry an `error`.
- [X] T011 [P] Write failing appearance conformance tests A-1..A-9 from `contracts/
      appearance-contract.md` §8 in `tests/test_appearance.py` + `tests/appearance.spec.ts`:
      determinism, ≥2.0 size ratio, zero-unreported clamps at 8 000 random knob combos, the §7
      precedence table, two-colour derivation, frozen settings A-7, no-clip A-8, export-scale A-9.

**Checkpoint**: Phases 1-2 done ⇒ any user story below may be started, and stories that do not
depend on appearance can proceed in parallel with US1.

---

## Phase 3: User Story 1 — Make the diagram look the way I want (Priority: P1) 🎨 MVP-CORE

**Goal**: users control text size, colour scheme (including derive-from-two-colours), font, spacing,
and main-path emphasis, with the chosen look identical in preview, exports, and shared links.
**Independent test**: `quickstart.md` §V-A (10 checks) + §6 manual smoke step 3.
**Depends on**: T008, T009 (T010/T011 not required to start this story).

- [X] T012 [P] [US1] Implement knob domains, the ten `schemeName` values, and the multiplier tables
      (text size §3, spacing §4 of `contracts/appearance-contract.md`) in `appearance.py` as pure
      Python data; largest÷smallest MUST be ≥ 2.0.
- [X] T013 [US1] Implement the colour engine in `appearance.py`:
      `resolve(knobs, diagramType) -> ResolvedAppearance` (JSON-serialisable), mixing derived colours
      from `baseColors`. Enforce the contrast invariant (text-vs-fill ≥ 4.5:1, line-vs-panel ≥ 3:1),
      clamp-and-report, and set `sourceOf` per §7 (frontmatter > knobs > defaults).
      Add a per-diagram spacing table so each family routes through its documented keys.
      MUST NOT set `wordWrap` or `useMaxWidth` (§3).
- [X] T014 [US1] Add appearance UI in `app.py` sidebar (size, scheme, font, density, emphasis, two
      base-colour pickers, reset).
- [X] T015 [US1] Apply `ResolvedAppearance` in `render_component.js`
      (re-`initialize` + explicit `parse()`→`render()`, no `startOnLoad`), skip re-parse when only
      appearance changed, and surface the "colours
      adjusted for readability" hint when `clamped` is non-empty.
- [X] T016 [US1] Add the §7 origin chips in the component.
- [X] T017 [US1] Implement the frozen-settings
      block per §6 (htmlLabels, suppressErrorRendering, securityLevel strict).
- [X] T018 [P] [US1] Export consumption test: the `ResolvedAppearance` reaching `exportAs()` is
      deep-equal to preview's.
- [X] T019 [US1] Make T011/V-A pass and confirm the preview==export claim of §V-A check 7.

**✅ US1 independently deployable**: editor + working appearance controls; every FR-001..011 claim has
a green V-A check; a user can change and reset size/scheme/base colours, and exports match. This is
the MVP — it is what the requester explicitly asked for ("change font size etc").

---

## Phase 4: User Story 2 — Know when and why my diagram is broken (Priority: P1) 🩺

**Goal**: four honest preview states; plain-language error naming the offending line; self-clearing.
**Independent test**: §V-B table + §6 step 4.
**Depends on**: T008, T009 (and T015 from US1).

- [X] T020 [P] [US2] Implement the `parse(text, { suppressErrors: true })` gate + `render()` in
      `render_component.js`, emitting `rendering` before start and exactly one terminal status
      (`rendered`/`invalid`/`empty`) per `requestId`, discarding superseded `requestId`s;
      `diagramType` from `ParseResult`; input over 50 000 chars ⇒ `inputTooLarge`, never attempted.
- [X] T021 [US2] Implement `RenderError` normalisation in `render_component.js`: kinds
      `parseError|renderError|unsupportedType|inputTooLarge`, a `plainMessage` rewrite table for
      common Jison errors, and 1-based `line`/`column`/≤120-char `snippet` extraction from the thrown
      error. `rawMessage` goes only to a "details" disclosure.
- [X] T022 [US2] Build the error panel in `render_component.js` + `preview_component.css`: message +
      line number; auto-clear with no dismiss action (FR-015).
- [X] T023 [US2] Implement the `lastGood` panel
      (a failed parse never overwrites it) and
      the `rendering`-stall upgrade at 8 000 ms ("this is slow, still working", FR-012, SC-003).
- [X] T024 [US2] Neutral `empty` state in `render_component.js` + `preview_component.css` for blank/
      whitespace source — hint styled differently from an error (US2 scenario 4).
- [X] T025 [P] [US2] Add `typeMismatch` notice driven by parsed-vs-selected type in
      `render_component.js` and `app.py` (spec Edge Case "type mismatch"; never a silent blank).

**✅ US2 independently deployable**: paste an error → see a line number, fix it → message self-clears;
`empty` looks different from `invalid`; a 500-node diagram is never falsely called broken; the last
good diagram stays visible.

---

## Phase 5: User Story 3 — Start from a diagram type I actually need (Priority: P2) 🗂️

**Goal**: nine diagram types with plain + styled showcase examples; not flowchart-labelled.
**Independent test**: §V-C + §6 step 2.
**Depends on**: T004 (pytest), T017 (frozen settings);
`share.py`/payload tests deferred to Phase 6.

- [X] T026 [P] [US3] Build `templates.py`: `typeId, label, blurb, examples[{purpose, source, shows}]`
      for `flowchart sequence class state er gantt pie journey mindmap` + a `blank`,
      with all nine `typeId`s matching `parse().diagramType`.
- [X] T027 [P] [US3] Write `tests/test_catalog.py` (uses T003) and `tests/catalog-render.spec.ts`:
      one plain + one `styled` per type; ≥3 drawable elements per example; every example renders
      under DEFAULT knobs with zero console errors (SC-002 = 100%); `<<interface>>` stereotype
      regression (commits 89bf9cc/02ae868); type-completeness; confirm `blank` exists with
      `source=''`.
- [X] T028 [US3] Extend the `appearance.py` per-type spacing/font table so all nine `typeId`s resolve
      (FR-001 "across all supported kinds"; the T027 completeness gate fails otherwise).
- [X] T029 [US3] Replace the 3-template selectbox in `app.py` with the catalog picker, carrying
      `blurb` + `shows` into the UI (FR-021).
- [X] T030 [US3] Add the
      unsaved-text guard: switching starting points never silently overwrites (FR-020).
- [X] T031 [US3] Reword `st.title` / `st.set_page_config` / README.md headings/`<title>` to general
      diagram wording (FR-021; catalog copy stays the single source of phrasing).

**✅ US3 independently deployable**: pick any of nine types → renders on first load; class diagram
shows stereotypes intact; every type carries ≥3 examples; switching starting points never silently
overwrites. Depends on US1, so ship after US1.

---

## Phase 6: User Story 4 — Keep my work and hand it to someone else (Priority: P2) 🔗

**Goal**: per-device drafts + self-contained share links; no content stored server-side.
**Independent test**: §V-D (10 checks) + §6 step 6.
**Depends on**: T005 (**blocking** — it decides where storage lives), T006 (URL path only),
T012/T013.

- [X] T032 [P] [US4] Implement `Draft` (whole working state: source+name+knobs)
      in `share.py` at the resolved location: ≥ 1000 ms coalesced writes, `mermaidGui.draft` +
      `mermaidGui.appearance` keys, and the `version` field. On S-1 failure write the component-side
      equivalent, same contract, in `render_component.js`.
- [X] T033 [P] [US4] Implement the
      restore-not-silent path in `share.py`/`app.py`: version migrations or clean discard (unknown
      draft versions MUST not crash — spec edge case).
- [X] T034 [P] [US4] Implement URL-fragment
      encoding in `share.py`: `v/s/k/n` (knobs, never `ResolvedAppearance`), deflate+base64url
      (research R-5), 13 000 `tooLarge` gate, and a
      total `decode` returning `ShareLinkDecodeError` reasons (`malformed|unsupportedVersion|
      truncated|emptyPayload` — throw-free) with out-of-range knobs clamped to nearest valid enum.
- [X] T035 [P] [US4] Write `tests/test_payload.py` (pure) +
      `tests/drafts-share.spec.ts`: §V-D 1 (restore notice shows `savedAt`, relative wording on clock
      skew) + check 7 (byte-identical decode(encode(x)) over all catalog sources + fixtures), check 5
      (mangled → typed error + working editor + draft untouched), check 8 (request interception: no
      non-CDN request carries `source`), §V-D 2 (`Start fresh` clears storage AND document together),
      and §V-D 6 (`storageUnavailable` notice once — SecurityError/quota — editor keeps working).
- [X] T036 [US4] Copy-link affordance in `app.py`: read/apply
      from the fragment on load; the `tooLarge` explanation offers the `.mmd` download; no server
      storage of content anywhere in this feature (FR-024, FR-025, SC-006, SC-010).
- [X] T037 [US4] Restore banner in `app.py` with exactly two actions
      ("keep editing" / "clear") from `savedAt`.
- [X] T038 [US4] Make §V-D and §V-A check 9 pass: recipient sees sender's look across browser and
      interface-theme differences.

**✅ US4 independently deployable**: reload with the same draft restores text AND look
(SC-005); a link reproduces the sender's diagram **and** appearance in another browser with no signup;
a mangled link shows a plain message; private mode says drafts aren't kept, once; nothing is ever
transmitted to a server.

---

## Phase 7: User Story 5 — Export that fits its destination (Priority: P3) 📤

**Goal**: scale / background / name / clipboard, without reopening three fixed bug classes.
**Independent test**: §V-E (7 checks) + §6 step 5.
**Depends on**: T017 (frozen settings),
and T019/T020.
**Critical**: parameterise proven code; **keep `canvg`** — do not replace it (R-7).

- [X] T039 [P] [US5] Write `tests/export.spec.ts` for §V-E 2/3:
      arrowheads/line styles present in SVG and PNG across all catalog types with the largest scale AND
      transparent background (ed4bb3e class), and `screen`→`print` dimensions exactly `4/2 = 2.0`×.
- [X] T040 [US5] Refactor `getSerializedSVG` out of `app.py`'s f-string into `export_component.js`,
      preserving xmlns/xlink repair and the `url(#id)` marker rewrite (commits ce61056/02ae868).
- [X] T041 [US5] Extend the
      inlining whitelist in `export_component.js` so hierarchy/emphasis colours survive, while keeping
      `htmlLabels:false` (research R-2).
- [X] T042 [US5] Implement the single
      `exportAs(kind, {scale, background, name})` entry point. Scales 2/3/4; `transparent` paints no
      backdrop; the existing hard-coded `scale=3` becomes `high`; **no** bespoke export path may remain.
- [X] T043 [P] [US5] Implement the shared
      `sanitize_filename` in `messages.py`: strip path separators/control chars, collapse dots, keep
      non-ASCII, empty ⇒ `untitled`; wire it into BOTH the Streamlit `.mmd` download in `app.py` and
      `export_component.js` downloads, and add `copySvg` (`clipboard.writeText`) with a graceful
      download fallback when the API is missing/refused (FR-031, FR-032).
- [X] T044 [US5] Export toolbar in `render_component.js` +
      `preview_component.css`: scale/background/name controls bound to Knobs/`ResolvedAppearance`,
      `tooLarge`/`clamped` surfaced; §V-E check 6 — export only ever captures the SVG from the newest
      terminal `requestId` (never a stale or mid-zoom render).

**✅ US5 independently deployable**: PNG/SVG differ by exactly the advertised ratio; transparent
background has no baked white and stays legible; arrowheads + styles survive (regression guard for
ed4bb3e); filenames use the user's name; clipboard copy pastes, or explains why not (FR-030..032).

---

## Phase 8: User Story 6 — Edit and inspect comfortably (Priority: P3) 🔍

**Goal**: no fixed scroll box, zoom/fit, line guidance, interface dark mode; typing stays fast.
**Independent test**: §V-F (4 checks) + §6 step 7.
**Depends on**: T020 (debounce; component-owned
zoom avoids re-running Mermaid per gesture), `requestId` staleness
handling, T021 (line numbers make errors actionable).

- [X] T045 [P] [US6] Write `tests/preview.spec.ts` for §V-F 2/3 (whole 120-line example visible; ≤3
      zoom actions overview↔detail; container dark + diagram light with byte-identical SVG vs light
      mode, proving the `interfaceMode` exclusion of appearance contract §1) and §V-F 4
      (typing latency on `long-120-lines.mmd` within SC-009).
- [X] T046 [US6] Replace `components.html(..., height=600)`
      in `app.py` with a measured/auto height: component posts its content height to `window.parent`,
      a plain-JS snippet in `index.html` resizes the iframe; fallback — remove `scrolling=True` so the
      page scrolls, and pin a generous single height.
- [X] T047 [US6] Implement zoom / fit-to-view / reset
      in `render_component.js` by scaling the SVG from its `viewBox` (the same source `getSerializedSVG`
      reads — no re-render) and styling the chrome in `preview_component.css`.
- [X] T048 [US6] Implement interface dark mode in
      `preview_component.css` + Streamlit page styles: `auto` follows `prefers-color-scheme`; chrome-
      only; it MUST NOT enter `ResolvedAppearance` or a share payload (FR-036).
- [X] T049 [P] [US6] FR-033 (structure + **line numbers**)
      via the cheapest honest route on this runtime (S-3 pending): (a) S-3 passes → `st.code_editor`;
      (b) else the CodeMirror-in-iframe editor **with
      line numbers**, wired into the bridge (a real editor, not a hand-rolled one);
      (c) else FR-033's explicit **spec-permitted downgrade**: `st.text_area` + a 1-based line gutter
      derived from the caret — with the error line reference (T021, US2 scenario 2) still working.
- [X] T050 [US6] Verify keyboard editing — Tab indent/outdent, native undo, paste — after
      T049's path is chosen, and keep it intact (FR-037); do not let the editor swap break it.

## Phase 9: Polish & Cross-Cutting Concerns

- [X] T051 [P] Polish: run `quickstart.md` §5, fix all failures in `tests/` + modules.
- [X] T052 Polish: reconcile `research.md` spike
      outcomes (S-1 storage ownership, S-2 URL round-trip, S-3 editor) with what shipped, and
      replace/downgrade the affected FR claims to match — every requirement traceable.
- [X] T053 [P] Polish: update README.md — types, appearance,
      draft/share, export options; add "how to contribute a diagram type" pointing at
      `quickstart.md` §V-C.
- [X] T054 Polish: `quickstart.md` §6 pre-merge gates —
      no new server dependency, no build step in the Pages upload, Pages `.github/workflows` deploy
      file unchanged, and zero console errors on the manual smoke.

---

## Dependencies & Execution Order

```text
Phase 1 Setup ──▶ Phase 2 Foundational ──┬─▶ US1 (P1) ─┬─▶ US3 (P2)  [T028 completeness needs US1 resolved shape]
                                         │              ├─▶ US4 (P2)  [needs T005; knobs from US1]
                                         │              ├─▶ US5 (P3)  [needs T017 + US1 export object]
                                         │              └─▶ US6 (P3)  [needs T021 for lines; T049 depends on S-3]
                                         └─▶ US2 (P1)  [independent of US1; shares T008/T009 bridge]
```

- **Setup → Foundational**: hard. No story starts before T008-T011 pass.
- **US1 → US4** is **soft**: US4 needs US1's *knob shape* to share appearance. Shipping US4 without
  US1 shares a default-only payload — still valid, still testable.
- **US2 is NOT gated by US1** — bridge-only.
- **T005 (S-1) gates T032/T033/T035/T037**; T006 (S-2) gates only T036's URL path (copy-link field
  fallback keeps US4 valuable); T007 (S-3) gates only T049.
- US5/US6 are last: they build on infrastructure other stories already need.

## Parallel Opportunities

| Batch | Parallel-safe because | Tasks |
|-------|-----------------------|-------|
| **Foundational** | different files, no shared state | T010 ‖ T011 |
| **US1 vs US2** (after T017) | US1 = `appearance.py`/`app.py`; US2 = `render_component.js` | phases 3 ‖ 4 |
| **Within US1** | pure `appearance.py` vs UI vs component | T012 ‖ (T013 → T015/T016/T017); T018 ‖ T019 |
| **Within US3** | catalog data vs tests vs app wiring | T026 ‖ T027 ‖ T029 |
| **Within US4** | `share.py` draft ‖ `share.py` link, then both test files | T032 ‖ T033 ‖ T034 → T035 |
| **Within US5** | test vs serialise refactor; filename sanitiser | T039 ‖ T040; T043 ‖ T042 |
| **Within US6** | spec writing before implementations | T045 ‖ T046; T048 ‖ T049/T050 |
| **Polish** | suite run first, then independent docs | T051 → (T052 ‖ T053 ‖ T054) |
| **Feature-branch workflow** | S-3 is a separate branch; S-1/S-2 are one-page probes in the main branch | T005 ‖ T006 ‖ T007 |

## Implementation Strategy

- **MVP = Phases 1-2 (mandatory)** + **US1 (P1)**, which
  satisfies the requester's explicit ask (font size etc.)
  and is independently valuable (a better-looking diagram, and identical in preview/export/link).
  **US2 is MVP-adjacent**: it shares only the bridge, so it is the natural second increment.
- Incremental order: MVP (US1) → US2 → US1+US2 stability pass → US3 → US4 → US5 → US6.
- **Skip US1?** Not possible: T008/T009 are shared by every story.
- **Independent test criteria**: each ✅ block above is the pass/fail gate for that story (V-A..V-F);
  a story may ship the moment its own suite and §5 pass.
- **Recommended branch strategy**: one PR per phase-group — `spikes` (T005-T007), `bridge`
  (T008-T011), `us1-appearance`, `us2-feedback`, `us3-types`, `us4-persistence`, `us5-export`,
  `us6-comfort`, `polish` — keeps the export-fidelity guards reviewable (constitution note:
  T039-T044 are the regression-sensitive ones).
- **Delivery constraint check** (from plan.md post-design re-check): no task adds a server, build step,
  or Pages-workflow change; dev-only Node usage is confined to **T002**.

## Format Validation

- **Total tasks: 54** (`T001`-`T054`), no gaps or duplicates; every reference between tasks resolves
  to an ID defined in this file (verified by scan).
- **Per phase**: Setup 4 · Foundational 7 · US1 8 · US2 6 · US3 6 · US4 7 · US5 6 · US6 6 · Polish 4.
- **Per user story**: US1 8 · US2 6 · US3 6 · US4 7 · US5 6 · US6 6 = 39 story-scoped tasks, each
  labelled `[US1]`..`[US6]`; Setup/Foundational/Polish tasks carry **no** story label, as required.
- **`[P]` markers**: 24 tasks. Each is paired in the Parallel Opportunities table with tasks working
  in different files; where a `[P]` task may still touch the same file as an earlier task in its own
  story (e.g. T042 edits `export_component.js` after T039-T041), the marker means "parallel-safe once
  that story's preceding task is merged", not "start concurrently with it".
- **Checklist format**: every line is `- [ ]` + `Txxx` + optional `[P]` + optional `[US*]` + a
  description naming at least one real path (`app.py`, `appearance.py`, `templates.py`, `share.py`,
  `messages.py`, `render_component.js`, `export_component.js`, `preview_component.css`, `index.html`,
  `tests/*`, `README.md`, `.github/workflows/ci.yml`). No task lacks a file path.
- **Independence**: each story phase ends with a ✅ block stating its own pass/fail gate mapped to
  `quickstart.md` V-A..V-F, so a story can ship alone once Phases 1-2 are in.
- **Constraints honoured**: no task introduces a server, a build step in the deployment path, or a
  change to the Pages deploy workflow; dev-only Node usage is confined to T002.
