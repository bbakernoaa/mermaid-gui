# Contract: Python ⇄ Render Component Bridge

**Owners**: `app.py` → (`source`, `ResolvedAppearance`, catalog metadata, requested scale/fit/export
commands) → `render_component.js` → one `RenderStatus` message back per cycle.

**Type**: internal UI boundary. Python → component is the supported direction of
`st.components.v1.html`; the component side owns rendering state, export, and its own chrome
(research R-4). The reverse direction is deliberately **out** of this contract: the user-visible
surface that must react to render state is the component chrome itself.

## 1. Inbound message (`RenderRequest`)

```json
{
  "schemaVersion": 1,
  "requestId": "req-00042",
  "source": "flowchart TD\n  A-->B",
  "appearance": { "mermaidTheme": "neo", "themeVariables": {}, "perDiagramConfig": {}, "export": {} },
  "command": "render"
}
```

| Field | Rule |
|-------|------|
| `schemaVersion` | bumped together with the component; unknown version ⇒ component reports `error: { kind: "bridgeVersion" }` and keeps its previous picture (no crash) |
| `requestId` | monotonically issued by Python; the component **must** echo it and **must** discard results older than the newest request it has started (stale-render prevention) |
| `source` | already HTML-escaped as it enters the iframe (preserves the fix from commit 02ae868); unchanged otherwise |
| `appearance` | exactly [ResolvedAppearance](./appearance-contract.md) — shared identity is what binds FR-008 |
| `command` | `render \| exportSvg \| exportPng \| copySvg \| zoomIn \| zoomOut \| fit` |

Rules:

1. Python never guesses the render state. Components do not re-read the widgets themselves and
   Python does not inspect the iframe DOM (research R-4).
2. Python debounces sending `source` (≥320 ms after the last keystroke, matching the data-model's
   300 ms parse debounce with headroom) to protect SC-009.
3. `appearance` changes ship as their own `render` request with the same `source`; the component may
   skip re-parsing when `source` is unchanged and only appearance changed.

## 2. Outbound status (`RenderStatus`)

The exact single state machine of [data-model §2](../data-model.md) is what the component reports:

```json
{
  "requestId": "req-00042",
  "state": "invalid",
  "diagramType": null,
  "error": { "kind": "parseError", "plainMessage": "Unknown arrow style on line 2",
             "rawMessage": "Parse error on line 2: ...", "line": 2, "column": 9,
             "snippet": "  A->>B" },
  "metrics": { "durationMs": 41 }
}
```

| Field | Rule |
|-------|------|
| `state` | `rendering \| rendered \| invalid \| empty` |
| `diagramType` | from `ParseResult.diagramType`; drives Python's appearance re-request for the correct type and `typeMismatch` notice |
| `error` | present **iff** `state = invalid`; shape per [data-model §3](../data-model.md) |
| `metrics` | required for `rendered`; used for the responsiveness budget of SC-009 |
| `rendering` | must be emitted before any async work starts, so the UI cannot appear frozen |

Invariants:

1. **Every** inbound `render` produces exactly one terminal status (`rendered`, `invalid` or
   `empty`) — no silent drops. This enforces **SC-002**.
2. `state = invalid` ⇒ the previously `rendered` diagram remains in the `lastGood` panel; a failed
   parse **never** clears it (FR-016). No user action dismisses an error (FR-015).
3. Only one terminal status per `requestId` may exist, and no terminal status for a superseded
   `requestId` may reach the UI (prevents stale-error or stale-diagram ghosts).
4. `empty` is reserved for blank/whitespace source and must never carry an `error`.

## 3. Component-owned UI (out of Python's control by design)

The preview chrome renders, and only the component renders: state badge, error panel with
line/column and snippet, `lastGood` disclosure, zoom/fit controls, export buttons and filename echo,
plus the "clamped colours" hint when [§5 of the appearance contract](./appearance-contract.md)
reports clamping.

Python-owned UI: widget layout, scheme/size/spacing/font selectors, start-fresh control, draft
notice, share-link field.

Requirement→side map: FR-012..016 component; FR-017..021, FR-022..027 Python; FR-028..032
component; FR-033..037 split (Chrome: component, widgets: Python).

## 4. Errors crossing the bridge

| `error.kind` | meaning |
|--------------|---------|
| `parseError` / `renderError` | diagram-level failures (surfaced in the component's error panel) |
| `unsupportedType` | valid grammar for a type this build cannot draw (SC-002) |
| `inputTooLarge` | above `editorLimits.maxPasteChars` (data-model §1); diagram is not attempted |
| `bridgeVersion` | schema mismatch (defensive) |

Bridge errors are **values**, never thrown across the boundary: a thrown exception inside the
component kills the preview silently — the exact failure mode this feature exists to remove.

## 5. Non-goals

- No requirement that the browser URL be updated from the component (see research S-2).
- No streaming/typing simulation, no per-keystroke round trip.
- No Python-side access to the component's DOM or the SVG, and no component-side access to
  Streamlit widget state: single-direction by design.
