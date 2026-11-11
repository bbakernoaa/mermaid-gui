# Phase 1 Data Model: Mermaid Editor Experience Upgrades

**Date**: 2026-11-09 | [spec.md](./spec.md) · [plan.md](./plan.md) · [research.md](./research.md)

Entities use the spec's names. Storage is browser-side only; no server schema exists or is implied.
Field notation: `Type`, constraints in brackets, validation rules follow each entity.

## 1. DiagramDocument

The user's current work. One instance is live in the app at any time.

| Field | Type | Constraints / Default |
|-------|------|---------------------|
| `source` | string | Any text; max length governed by `renderState`, not storage |
| `name` | string | `""` (no name) .. 120 chars used as filename stem |
| `diagramType` | string \| null | Derived, never authored by the user — the type Mermaid detected on last successful parse (`ParseResult.diagramType`) |
| `renderState` | RenderState | `rendering` on every source change |
| `lastError` | RenderError \| null | Non-null iff `renderState = invalid` |
| `lastGoodRender` | { svg, at } \| null | Replaced on each successful `rendered` transition (FR-016) |

**Validation**

- `source` is HTML-escaped before entering the component (preserves the fix from commit 02ae868:
  `<<interface>>`-style text must not be re-interpreted as HTML).
- `source` longer than `editorLimits.maxPasteChars` (50 000 characters, pinned from spec's
  "tens of thousands" edge case) is rejected with `inputTooLarge` and the diagram is not rendered.
- `name`: strip path separators `/ \`, control chars, and characters illegal in download names; trim
  surrounding whitespace/dots; collapse repeats of `.`; empty after sanitising → fall back to
  `untitled`. Preserves non-ASCII (spec edge case: emojis / non-Latin labels in the filename).
- `diagramType` mismatch rule: if the catalog entry the user picked has a type different from the
  parsed `diagramType`, keep rendering (Mermaid decides, FR states the result must be render-or-clear
  message, never silent blank) and surface a distinct notice `typeMismatch` (spec Edge Cases).

## 2. RenderState (state machine)

Four and only four states — required by FR-013 and SC-003 (no false errors).

```text
empty ──source non-blank──▶ rendering ──parse OK + render OK──▶ rendered
  ▲                          │  │                             │
  │                          │  └──parse/render fails──────▶ invalid
  │                          │                                  │
  └──source blank── rendered │ / invalid                        │
                             ▼                                  │
                     (no state change on identical source) ◀───┘
                                source changes again ──▶ rendering
```

| State | Shown when | Preview chrome (FR-013; spec US2 scenario 4) |
|-------|-----------|----------------------------------------------|
| `empty` | source blank / whitespace only | neutral "Nothing to render yet" hint; **not** styled as an error |
| `rendering` | parse or render in flight | progress indicator; must not read as failure; after `limits.renderStallMs` (8 000 ms) upgrade to a "this is slow, still working" message (US2 scenario 5) |
| `rendered` | success | diagram; error area hidden; last good render updated |
| `invalid` | parse or render failed | `lastError` message + location; last good render still visible in a collapsible "last valid version" area (FR-016) |

**Rules**

- Every source change transitions to `rendering` first (including a change made while `invalid`), and
  `invalid` clears automatically on success — FR-015, US2 scenario 3: no manual dismiss action
  exists in the UI at all.
- A failed parse **never** overwrites `lastGoodRender`.
- Debounce of 300 ms between keystroke and parse to protect SC-009; latest keystroke wins (a stale
  in-flight render result is discarded — prevents flicker and stale-error ghosts).
- `mermaid.initialize` is set with `suppressErrorRendering: true` (verified in research R-3) so the
  library's own "Syntax error" SVG cannot leak into the preview and be mistaken for state.

## 3. RenderError

| Field | Type | Constraints |
|-------|------|-------------|
| `kind` | enum: `parseError`, `renderError`, `unsupportedType`, `inputTooLarge` | `unsupportedType` = a valid type that the shipped Mermaid build cannot draw (US2 scenario 6) |
| `rawMessage` | string | Library text, kept for detail view only |
| `plainMessage` | string | Required human-facing rewrite of `rawMessage` (FR-014: "ordinary words"); a lookup table for known patterns, a generic fallback otherwise |
| `line` | int \| null | 1-based, when known |
| `column` | int \| null | when known; null renders only the line |
| `snippet` | string \| null | the offending source line, up to 120 chars, for a "jump to line" affordance when an editor supports it |

**Validation** — `line` and `column` are set only when the library supplied them; on `renderError`
they may be null while `plainMessage` is still required (never show a stateless "something went
wrong").

## 4. Appearance (the "resolved appearance object", research R-2's core decision)

The single shape consumed by preview, export, draft, and share link. Two layers: what the user picks,
and what the system derives.

```text
AppearanceKnobs ──resolve(diagramType)──▶ ResolvedAppearance ──▶ mermaid.initialize(…)
                                                      └────────▶ exportAs(…)  (FR-008)
```

### 4a. AppearanceKnobs (user-authored, persisted, shareable)

| Knob | Values (pinned) | Default | Notes |
|------|-----------------|---------|-------|
| `schemeName` | `neo`, `neo-dark`, `redux`, `redux-dark`, `redux-color`, `redux-dark-color`, `default`, `neutral`, `forest`, `base` (10 offered, ≥6 required by FR-003; light/dark/high-contrast spanned) | `neo` | names are `theme` values verified from mermaid@11 types (research R-2) |
| `baseColors` | `{ background: hex, foreground: hex }` \| null | null — scheme colours win until the user picks base colours; then derivation (FR-004) overrides `themeVariables` for element tints via the R-2 mix table |
| `textScale` | `smallest`, `small`, `medium`, `large`, `largest` → multiplier `0.75 / 0.9 / 1.0 / 1.25 / 1.75` (2.33x span, satisfies FR-001's minimum 2x) | `medium` | applied through documented per-diagram `fontSize`/`fontFamily`/`FontConfig` keys |
| `fontFamily` | `sans` (system-ui stack), `serif` (Georgia/'Times New Roman' stack), `mono` (ui-monospace/Consolas/Menlo stack) — 3 options (FR-005) | `sans` | **web-safe stacks only**, per R-2 limitation; any custom stack that needs a web-font download is out of scope since it would not embed in export |
| `density` | `compact`, `normal`, `roomy`, `open` → per-type `nodeSpacing × rankSpacing × padding` tuple (normal keeps the library's own defaults; other levels apply documented multipliers, e.g. `roomy` = 1.25/1.2/1.1, `open` = 1.5/1.4/1.2) | `roomy` | FR-006: default intentionally roomier than the library's cramped default (spacing-over-colour lesson from the reviewed styling guide) |
| `pathEmphasis` | `off`, `soft`, `strong` | `soft` | FR-007 (visual hierarchy) implemented via `themeVariables` edge/line colour+stroke-width emphasis |
| `interfaceMode` | `light` \| `dark` \| `auto` | `auto` | FR-036 chrome only; **never** part of the diagram `ResolvedAppearance` — spec FR-036 requires interface dark mode to not alter diagram appearance |
| `exportScale` | `screen`, `high`, `print` → raster multiplier `2 / 3 / 4` (FR-028) | `high` | `high` = 3 preserves the current `scale = 3` behaviour as one explicit option instead of a hard-code (FR-028's "three levels") |
| `exportBackground` | `white` \| `transparent` \| `#rrggbb` custom | `white` | FR-029; white = current behaviour, transparent = do not paint backdrop at all |

**Invariants / rules**

- **Contrast (FR-011)**: every `(schemeName, baseColors)` × `textScale` × `density` combination that
  can actually be reached through the controls must satisfy ≥ 4.5:1 text-to-node-fill and ≥ 3:1
  line-to-panel contrast as rendered. Derived colours are clamped to keep that true, and clamping is
  reported to the user rather than applied silently.
- **Precedence (FR-009)**: 1) explicit `%%{init}%%` front-matter in the user's source wins for the
  keys it names; 2) then user knobs; 3) then the shipped scheme defaults. The component compares the
  effective value's origin and labels it in the UI ("from your diagram text"). Verified achievable:
  `parse()` returns the "config passed as YAML frontmatter or directives" in `ParseResult` (R-3),
  so front-matter keys are discoverable before rendering without parsing text ourselves.
- **Round-trip**: `ResolvedAppearance` is derived, never stored. Storage/persistence holds Knobs only
  — the resolved form must be recomputable from `{knobs, diagramType}`, otherwise a saved diagram
  could render differently than the same knobs typed fresh.

## 5. ResolvedAppearance

`ResolvedAppearance = { mermaidTheme, themeVariables, perDiagramConfig, rasterScale, rasterBackground }`
— the exact shape passed to `mermaid.initialize` and consumed by `exportAs()`. Serialised once, used
by three consumers; **the same object** is what makes FR-008 (preview = export = link) a data
property rather than a duplicated-code coincidence.

## 6. DiagramCatalog → DiagramType + Example

```text
DiagramCatalog: Map<typeId, DiagramType>
DiagramType { typeId, label, family, plain: Example, styled: Example }
Example      { exampleId, purpose: 'plain' | 'styled', source,
               minElements: int, verifiedRender: bool }
```

| Field | Rules |
|-------|-------|
| `typeId` | stable slug (`flowchart`, `sequence`, `class`, `state`, `er`, `gantt`, `pie`, `journey`, `mindmap`) — all nine verified as first-class mermaid@11 configs (R-8) |
| `label` | human-facing, describes the use ("Class diagram", not a code sample); FR-021 requires the app's copy to shed "flowchart-only" wording |
| `minElements` | validation: example's `source` must yield ≥ 3 distinct drawable elements (FR-018 / US3 scenario 2) — counted on the rendered SVG |
| `verifiedRender` | CI/test asserts renders under default knobs with zero console errors (FR-018, SC-002) |
| `purpose='styled'` | must additionally pass the contrast invariant in §4a for the default scheme/size used |

Catalog content lives in `templates.py` as a data structure, not scattered inline strings, so adding a
type is a data change (R-8).

## 7. Draft

```text
Draft { version: int, savedAt: ISO8601, source, name, knobs }
```

Storage key carries a schema `version`; reading a lower/unknown version **migrates in place or is
ignored** with no crash — never throws, per spec edge case "drafts from an older version".

**Rules**

- Written debounced (≥1 s after the last change) — SC-009's responsiveness target while editing.
- Restore is **not** silent: the first thing the restored user sees is a notice ("Draft restored from
  <time>") with `Start fresh` and `Keep editing` (FR-022/023, US4 scenario 1).
- When storage is unavailable (private mode, quota), the app sets `storageError` once, continues
  working, and never claims a save (FR-027).
- `Start fresh` clears storage and the live `DiagramDocument` together; clearing only one is invalid.
- The stored unit is the **whole working state** (source + name + knobs), because SC-005 requires
  appearance to come back too.

## 8. ShareLink

```text
ShareLink { payload: SharePayload, encoding, url, tooLarge: bool }
SharePayload { v: 1, source, knobs, name? }
```

- **Location**: URL fragment (`#`) only — a fragment is not sent to GitHub Pages' servers, which is
  what makes SC-006's "0 bytes of diagram content stored server-side" structural.
- **Round-trip guarantee**: `decode(encode(payload)) == payload` for every source the editor can
  render, verified by a per-type property test over all catalog examples. Non-ASCII, emoji, angle
  brackets, quotes and braces must survive (spec Edge Case "special characters", same class of bug as
  commit 02ae868).
- `tooLarge = len(url) > limits.shareUrlMaxBytes` (13 000) → the link action explains the limit and
  points at `.mmd` download (US4 scenario 5 / FR-025); it never silently produces a broken link.
  13 000 is chosen as the lowest widely-documented browser URL limit; the task list must confirm it
  against the target browsers before release.
- `decode` **returns `ShareLinkDecodeError`, never throws** (FR-026). The UI then shows a plain
  message and a working editor, and the user's current draft is left untouched.
- `v` (schema version) is mandatory so future payload changes can be handled or rejected cleanly.
- Appearance is carried **as Knobs, not ResolvedAppearance** (§4 invariant) so a shared link cannot
  render differently than the same knobs typed fresh.

## 9. ExportArtifact

```text
ExportArtifact { kind: 'svg' | 'png' | 'mmd', filename,
                 appearance: ResolvedAppearance, scale?, background?, bytes }
```

- **`filename = sanitize(name || 'untitled') + '.' + ext`** — the single sanitiser is used by both
  Streamlit's download button and component-side downloads (FR-031, R-7); §1 rules define it.
- `svg` / `png` are taken from the serialized SVG. PNG additionally applies `scale` + `background`.
  `mmd` never gains `appearance` (§4 invariant: `.mmd` remains raw, portable user text).
- `background='transparent'` ⇒ no fill rect is painted at all. With `htmlLabels: false` (R-2) text
  lives in SVG `<text>`, so transparent exports need no extra font embedding — and the contrast
  invariant of §4a guarantees the text is readable on a transparent background too.
- **Invariant**: exports use the **same** `ResolvedAppearance` as the live preview (FR-008)
  — single `exportAs()` entry point, no bespoke paths (R-7).

## 10. Relationships

```text
DiagramCatalog ──1───▶ DiagramType ──1───▶ Example[]            # plain + styled per type
DiagramDocument ──n:1──▶ DiagramType        # detected, not chosen
DiagramDocument ──1───▶ AppearanceKnobs     # knobs live on the document
AppearanceKnobs ──▶ ResolvedAppearance      # = f(knobs, diagramType); derived, never stored
DiagramDocument ──1───▶ Draft               # serialized subset: source + name + knobs
Draft / SharePayload ──▶ source + name? + AppearanceKnobs
ResolvedAppearance ──▶ ExportArtifact       # preview and export share this one shape
```

**Storage footprint**: `Draft` + `AppearanceKnobs` are the only persisted things; `ResolvedAppearance`
is always recomputed — the invariant that makes FR-008 (preview = export = link) data-verifiable.

## 11. Validation matrix (rules traced to the spec's requirements)

| Rule | Source requirement |
|------|--------------------|
| Four explicit render states, auto-clearing errors, no false errors on slow renders | FR-012..016, SC-002, SC-003 |
| Contrast invariant across size × scheme × density; clamp-and-report | FR-001, FR-003, FR-006, FR-011, US1 scenario 1..3 |
| Precedence order front-matter > knobs > defaults; origin labelled | FR-009, US5 (appearance vs in-text styling), spec Edge Cases |
| Resolved shape shared by preview/export/link; link carries knobs only | FR-008, FR-024, SC-005, SC-007 |
| Type detection from parse result; `unsupportedType` error kind | FR-017, US2 scenario 6, spec Edge Case "type mismatch" |
| Filename sanitiser shared by both download paths | FR-031, US5 scenario 5 |
| Share-URL byte cap with explained download fallback | FR-025, US4 scenario 5 |
| Decode returns error value, never throws; draft untouched | FR-026, US4 scenario 6 |
| Draft schema versioning; migrate or ignore, never crash | FR-022, spec Edge Case "older-version drafts" |
| Input size rejection `inputTooLarge` above `maxPasteChars` = 50 000 characters | SC-009, spec Edge Case "tens of thousands of chars" |
| Storage-unavailable notice, silent no-op otherwise | FR-027, US4 scenario 7 |
