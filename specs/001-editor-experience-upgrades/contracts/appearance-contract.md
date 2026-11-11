# Contract: Appearance Resolution

**Owner**: `appearance.py` (Python) + `render_component.js` (consumer) · **Status**: binding for
implementation · [spec FR-001..011](../spec.md) · [data-model §4-5](../data-model.md)

This contract is what makes "the preview, the export, and the shared link show the same diagram"
a checkable property instead of an aspiration. **One resolver, three consumers.**

## 1. Inputs

### AppearanceKnobs (authoritative shape)

```json
{
  "schemeName": "neo",
  "baseColors": null,
  "textScale": "medium",
  "fontFamily": "sans",
  "density": "roomy",
  "pathEmphasis": "soft"
}
```

| Knob | Domain | Notes |
|------|--------|-------|
| `schemeName` | one of the 10 catalog names | values proven valid as Mermaid `theme` names (research R-2) |
| `baseColors` | `null` \| `{ "background": "#rrggbb", "foreground": "#rrggbb" }` | non-null switches to derived-colour mode (FR-004) |
| `textScale` | `smallest\|small\|medium\|large\|largest` | multipliers fixed in §3 |
| `fontFamily` | `sans\|serif\|mono` | web-safe stacks only (research R-2 limitation) |
| `density` | `compact\|normal\|roomy\|open` | per-type tuples in §4 |
| `pathEmphasis` | `off\|soft\|strong` | FR-007 hierarchy |

`interfaceMode`, `exportScale`, `exportBackground` are **not** part of diagram appearance
resolution: `interfaceMode` themes the chrome only (FR-036), and the export pair is consumed by
[export contract] below. Keeping them out of `ResolvedAppearance` is what prevents a UI dark-mode
switch from silently restyling a diagram in a shared link.

### Also required: `diagramType`

Derived from `mermaid.parse()`'s `ParseResult.diagramType` (research R-8), supplied by the render
component on every success. Resolution is type-aware because Mermaid's own config is per-diagram
(research R-2).

## 2. Output (ResolvedAppearance)

```json
{
  "mermaidTheme": "neo",
  "themeVariables": { "primaryColor": "#...", "lineColor": "#...", "textColor": "#..." },
  "perDiagramConfig": { "flowchart": { "nodeSpacing": 65, "rankSpacing": 60, "padding": 18 } },
  "export": { "scale": 3, "background": "white" }
}
```

Rules:

1. The object is JSON-serialisable and passed **whole** to `mermaid.initialize` (plus
   `htmlLabels: false` and `suppressErrorRendering: true`, which are fixed, not knobs — see §6).
2. Consumers may assume the output is deterministic: same `(knobs, diagramType)` ⇒ byte-identical
   output. Required for the share round-trip test.
3. Export never re-resolves from UI state; it consumes this object (FR-008).

## 3. Text size — FR-001, FR-002

| `textScale` | multiplier | basis (16 px default) |
|-------------|-----------|----------------------|
| `smallest` | 0.75 | 12 px |
| `small` | 0.9 | 14.4 px |
| `medium` | 1.0 | 16 px (today's look — no surprise for returning users) |
| `large` | 1.25 | 20 px |
| `largest` | 1.75 | 28 px |

Largest ÷ smallest = **2.33x ≥ the 2x minimum (SC-001/SC-003)**.

Applied through documented keys, never via injected CSS: top-level `fontSize`, plus per-diagram
`fontSize` where the type defines its own (sequence, gantt, journey, mindmap, pie — see
`mermaid` config type definitions). FR-002 (labels stay inside shapes) is guaranteed by Mermaid's
own layout measuring text after font metrics; the contract's obligation is to **not** defeat it —
so this resolver must not set `wordWrap`, `useMaxWidth`, or HTML-label options.

## 4. Spacing — FR-006

`normal` leaves the library's own values in force. Other levels multiply the documented
`nodeSpacing` / `rankSpacing` / `padding` for the flowchart family and the nearest equivalent per
other type (mindmap, class, state; sequence uses its own `messageMargin`) as follows:

| `density` | nodeSpacing × | rankSpacing × | padding × |
|-----------|---------------|---------------|-----------|
| `compact` | 0.85 | 0.85 | 0.9 |
| `normal` | 1.0 | 1.0 | 1.0 |
| `roomy` (**default**) | 1.25 | 1.2 | 1.1 |
| `open` | 1.5 | 1.4 | 1.2 |

Roomier-than-stock default implements the reviewed styling guidance that spacing improves a
diagram more than palette choice does.

## 5. Schemes and base-colour derivation — FR-003, FR-004, FR-011

- **Named schemes (≥6 required, 10 offered)**: each maps to a verified Mermaid `theme` name and,
  where needed, an explicit `themeVariables` overlay. Includes light, dark, and a high-contrast
  entry for the spec's readability requirement.
- **Derived mode**: when `baseColors` is non-null, every element colour is computed from
  `{background, foreground}` by fixed mixes mirroring the "two-colour foundation" pattern of the
  reviewed reference theme engine (text 100 %, secondary text 60 %, edge label 40 %, faint 25 %,
  connectors 50 %, arrowheads 85 %, node fill 3 %, group header 5 %, inner stroke 12 %, node stroke
  20 % — foreground mixed into background).
- **Contrast invariant (FR-011)**: after resolution, if any offered combination yields
  text-vs-fill < 4.5:1 or line-vs-panel < 3:1, the resolver **clamps** the offending variable
  towards a compliant value and sets `clamped: [variableNames]` in its report; the UI must show
  "some colours were adjusted for readability" rather than applying it silently. Contract test:
  exhaustive check over offered knobs must yield the invariant true with zero clamps for the
  stock combinations.

## 6. Fixed (non-knob) settings — regression guards

| Setting | Value | Why it is frozen |
|---------|-------|------------------|
| `htmlLabels` / `useHtmlLabels` | `false` | required for export fidelity — commit ed4bb3e |
| `suppressErrorRendering` | `true` | app owns error UI (FR-013, SC-002); verified option name in research R-3 |
| `securityLevel` | `strict` | site is public, diagrams can be pasted from anywhere |
| start-on-load | disabled; explicit `parse()`→`render()` pipeline | state machine control (§2 data-model) |

Any change to this table is a contract amendment and must re-run the §7 tests.

## 7. Precedence — FR-009

**Effective value of a key** (highest wins):

1. `%%{init}%%` / YAML front-matter in the user's `source` (readable from `ParseResult`)
2. `AppearanceKnobs`
3. named-scheme defaults

| `source` | knobs | effective |
|----------|-------|-----------|
| `%%{init: {"theme":"dark"}}%%` | `scheme:"neo"` | `dark` (1 beats 2) |
| none | `scheme:"neo"` | `neo` (2 beats 3) |
| none | none (fresh) | catalog default (`neo` + `roomy` + `soft`) |

Resolution report includes `sourceOf: { knob → 'frontmatter'|'knob'|'default' }`; the UI renders
"set by your diagram text" chips from it so the rule is discoverable, not guessed.

## 8. Conformance tests (mandatory, per user story / requirement)

| ID | Assertion | Covers |
|----|-----------|--------|
| A-1 | `resolve(knobs, type)` deterministic: equal inputs ⇒ deep-equal output | FR-008 |
| A-2 | Preview, PNG/SVG export, and link consumers each receive the identical `ResolvedAppearance` object | FR-008, SC-005 |
| A-3 | largest/smallest text ratio ≥ 2.0 | FR-001 |
| A-4 | No offered knob combination violates the §5 contrast invariant without emitting a `clamped` report | FR-011 |
| A-5 | `sourceOf` follows §7 table for the three fixture cases | FR-009 |
| A-6 | `baseColors` derivation produces all element colours from two inputs (no manual extras) | FR-004 |
| A-7 | §6 frozen settings present in every resolved output | FR-030, FR-013 |
| A-8 | For every catalog type, resolving and rendering its plain example yields **no text clipping** (bounding-box check) at `largest` text scale and `open` density on the widest and tallest example | FR-002, SC-003 |
| A-9 | Exported PNG at `print` vs `screen` has dimension ratio matching the scale difference exactly | FR-028 |

A-9 is decided by arithmetic, not by measurement: `export_component.js` rounds the picture's own
size to whole pixels **once** and every advertised scale multiplies that integer base
(`screen` ×2, `high` ×3, `print` ×4), so `print` is exactly twice `screen` in any browser and with
any font metrics. Rounding each result separately does not hold — a 252.x-px viewBox gave
506 px at `screen` and 1014 px at `print` on Linux (ratio 2.004) while the same diagram was exact
on macOS, which is why the CI assertion is `print == 2 * screen` in whole pixels.

Two export fidelity rules follow from the same measurement, and both are asserted in
`tests/export.spec.ts` by counting pixels rather than trusting the file's header: an exported PNG must
contain the drawing (`the PNG contains the drawing, not an empty plate`), and because journey draws
its labels as HTML `<foreignObject>` whatever `htmlLabels` says, a standalone file must carry them as
real `<text>` (`a journey export keeps its labels in a standalone file`).

Diagrams too long for a browser canvas (a 1 155-node spine has a 404 × 133 933 viewBox, and a
canvas over `RASTER_LIMITS` yields an *empty* data URL rather than an error) are refused before
the raster is attempted, with the highest scale that fits named, or SVG suggested when none does.

A-8 is the regression test for the spec's "largest text + tightest spacing must stay readable"
edge case, and A-2 guards the exact class of bug fixed twice already in this repo (preview and
export diverging).
