# Contract: Diagram Catalog and Examples

**Owner**: `templates.py` (data) · consumed by `app.py`, and by tests (render checks) ·
[spec FR-017..021](../spec.md) · [data-model §6](../data-model.md)

## Catalog shape

```json
{
  "types": [
    {
      "typeId": "class",
      "label": "Class diagram",
      "blurb": "Types, interfaces and their relationships",
      "examples": [
        { "purpose": "plain",  "source": "classDiagram\n  …" },
        { "purpose": "styled", "source": "classDiagram\n  …", "shows": "spacing and emphasis" }
      ]
    }
  ]
}
```

| Field | Rule |
|-------|------|
| `typeId` | must match a type `mermaid.parse()` reports as `diagramType` (research R-8) — no invented ids, no prefix-sniffing table |
| `label` / `blurb` | human-facing wording describing the purpose (FR-020; the app's whole vocabulary sheds "flowchart") |
| `examples[].purpose` | exactly one `plain` and at least one `styled` per type in `requiredTypes` (FR-018) |
| `examples[].shows` | required on `styled` examples: what technique it demonstrates, copied straight into the UI |

## Required minimum (FR-017)

`flowchart, sequence, class, state, er, gantt, pie, journey, mindmap`, plus a `blank` pseudo-entry
that is the "Clear my work" path from FR-023.

## Validation rules (each must fail a build, not a person)

1. **Renders**: every example, under **default** knobs, is renderable — a parse gate pass and a
   successful `render()` (SC-002 requires 100%).
2. **Real starter**: `minElements ≥ 3` drawable elements counted on the rendered SVG (FR-018), so an
   example is never a two-line toy.
3. **Notation is correct**: type-characteristic notation is present and renders — class
   `<<interface>>` stereotypes visible as stereotypes (regression for commit 89bf9cc's bug class),
   sequence actor/participant lines, gantt dates, ER cardinality symbols, journey sections.
4. **Appearance-compatible**: each type resolves with the appearance contract (§4 of
   [appearance-contract.md](./appearance-contract.md)) — spacing/font maps must have an entry for
   every required `typeId`, verified by a completeness check so a newly added type cannot ship
   without appearance support (guards SC-001's "works across diagram kinds" claim for future
   growth).
5. **No destructive switch**: selecting or switching a starting point never replaces existing user
   text without confirmation (FR-020).
6. **Wording**: app title/subtitle/description strings live in this catalog's copy or in `app.py`
   only — no hard-coded "flowchart" UI labels scattered elsewhere (FR-021).

## Extension model

Adding a type = one catalog entry + one appearance mapping row + test fixtures. No change to the
render bridge, share payload, or export path. Any change that violates that statement is scope creep
for a "more types" request and must go through a spec amendment (e.g. the types Mermaid supports that
the specification did not ask for — timeline, quadrant, xy chart, sankey, block, architecture — stay
out until requested).
