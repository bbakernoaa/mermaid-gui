# Contract: Share Payload (Draft + Link)

**Owner**: `share.py` (encode/decode) · consumed by `app.py` · [data-model §7-8](../data-model.md) ·
[spec FR-018, FR-022..027](../spec.md)

Two related formats with **one** shared content unit: the whole working state
(`source` + `name` + `AppearanceKnobs`).

## 1. SharePayload (inside a URL)

```json
{ "v": 1, "s": "<diagram source>", "k": { "...AppearanceKnobs" : "" }, "n": "optional name" }
```

| Field | Rule |
|-------|------|
| `v` | integer schema version; **mandatory** — decode rejects unknown versions rather than guessing |
| `s` | the user's source, byte-for-byte; unescape rules must preserve non-ASCII, emoji, `<<interface>>`, quotes and braces **exactly** (round-trip property test; same bug class as commits 02ae868 / 89bf9cc) |
| `k` | `AppearanceKnobs`, **not** `ResolvedAppearance` — a link must recomputes from knobs identically to fresh input (data-model §4 invariant, SC-005) |
| `n` | optional; omitted when the user never named the diagram |

### Encoding rules

- Written to the **URL fragment** (`…/mermaid-gui/#p=…`), never the query string: the fragment is
  not sent to the hosting server, which is what makes "0 bytes stored server-side" (SC-006)
  structural instead of policy.
- Compression required before encoding (research R-5: `lz-string`-class compression via CDN ESM, or a
  Pyodide equivalent — chosen at implementation), then a URL-safe alphabet with no `+`, `/`, `=`
  characters needing further escaping.
- **Size ceiling**: `len(url) <= 13000` bytes; beyond that encode returns `tooLarge: true` and the UI
  explains the limit and offers the `.mmd` download (FR-025, spec Edge Case "link length ceiling").
  It must never emit a link known to be unreliable.
- Decoding is **pure and total**: for any string input (empty, truncated, random text, valid-prefix
  + garbage) it returns either a `SharePayload` or a `ShareLinkDecodeError` with a reason. It never
  throws, never partially mutates app state, and never clears the user's live document or draft
  (FR-026, US4 scenario 6).

### `ShareLinkDecodeError` reasons

`malformed` · `unsupportedVersion` · `truncated` · `emptyPayload` — each maps to a fixed plain-language
message plus one obvious dismissal path ("start a new diagram"; the bad link stays in the address
until the user navigates away or clears it).

## 2. Draft (inside localStorage)

```json
{ "version": 1, "savedAt": "2026-11-09T17:05:12Z",
  "source": "…", "name": "…", "knobs": { "…AppearanceKnobs" } }
```

| Key | value |
|-----|-------|
| `mermaidGui.draft` | the Draft JSON above |
| `mermaidGui.appearance` | last-applied ` AppearanceKnobs`, independent of any diagram, so a "New" diagram inherits the user's look (spec US2 scenario 4 / FR-009 per-device preference retention) |

### Rules

1. Writes are debounced ≥ 1 000 ms after the last change, and coalesced — never per keystroke
   (SC-009 target: typing stays responsive).
2. Read path: valid + current version ⇒ restore candidate, **not** silently loaded as the template:
   the UI must present the restored state and its `savedAt` (FR-022). Older/unknown version ⇒ run
   the version migration map if one exists, else discard silently and start normal — never crash,
   never surface a stack trace (spec Edge Case "drafts from an older version").
3. Storage failure modes are **detected, not guessed**: `localStorage` access throwing
   (`SecurityError`), or quota exceeded after a retry ⇒ set `storageUnavailable` once, keep the app
   fully working, and state plainly that the draft is not being kept (FR-027). No fake success, no
   repeated prompting.
4. `Start fresh` removes `mermaidGui.draft` **and** resets the live document together — one
   transaction; leaving storage populated while the editor is blank is an invalid state (FR-023).
5. The user's diagram text is never sent anywhere: no analytics payload, no error reporting, no
   third-party call may include `source` (SC-010). Draft/link content stays on-device or in the URL.
6. Restored state is labelled with `savedAt`, and the notice offers exactly two actions: keep editing
   or clear (US4 scenario 1).
7. The restore notice is rendered as a dismissible banner by the Python layer — not by the preview
   component (research R-4). That keeps the draft path independent of spike S-1's outcome: whether
   Python or the component reaches storage, same banner shape, same actions.

## 3. Behaviour required of both formats

| Case | Required outcome |
|------|------------------|
| Source with non-ASCII / emoji / `<<…>>` / quotes / braces | byte-identical round-trip in both formats |
| Source at max size (50 000 chars, data-model §1) | Draft stores it; link route takes the `tooLarge` path |
| Unknown diagram type in a payload | decode succeeds; render reports `unsupportedType` via the render bridge — decode is not a validator |
| Payload with no `k` key | decode fills catalog default knobs, explicitly marked as defaulted in UI |
| Two tabs, same draft key | last write wins, no locking — acceptable, but both tabs must show the notice correctly (spec has no multi-session requirement) |
| `savedAt` in the future (clock skew) | notice uses relative time ("earlier today") instead of a nonsense timestamp |
| Knobs with out-of-range values in a hand-edited URL | clamped to nearest valid enum value; an invalid `density: 99` must not render at all (SC-003: never a false error state) |
