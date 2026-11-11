# Feature Specification: Mermaid Editor Experience Upgrades

**Feature Branch**: `001-editor-experience-upgrades`

**Created**: 2026-11-09

**Status**: Draft

**Input**: User description: "ok make a plan to improve this. also if we could have the ability to
change font size etc it could be helpful to end users"

**Inspiration reviewed**: `lukilabs/beautiful-mermaid` (a theming layer that derives a complete,
coherent diagram look from very few base colors, plus broad diagram-type support), guides on making
Mermaid diagrams look better (visual hierarchy so the main path reads first, spacing mattering more
than color, differentiating edge types, previewing at the size where the diagram will actually be
shown, and matching the surface the diagram lives on), and "beautiful diagrams" positioning for
Mermaid authoring tools.

## Why This Feature

The tool renders diagrams correctly but leaves them looking like generic default Mermaid, and the
experience around the render is rough: broken input fails without a clear message, work is lost on
reload, only three flowchart-leaning starting points exist, and the preview is a fixed-height scroll
box with no control over how the diagram looks. The requester specifically called out the ability to
change font size and similar appearance settings as the addition most helpful to end users, so
appearance control is the center of gravity for this feature.

## Scope Overview

Six independently deliverable areas, ordered by impact:

| # | Area | Priority |
|---|------|----------|
| 1 | Look and feel control (font size, colors, spacing) | P1 |
| 2 | Reliable render feedback (clear errors, visible state) | P1 |
| 3 | More diagram types with curated examples | P2 |
| 4 | Keep work between visits, plus shareable links | P2 |
| 5 | Purpose-built export (scale, background, name, clipboard) | P3 |
| 6 | Editor and preview comfort (highlighting, fit, zoom, dark mode) | P3 |

**Explicitly out of scope**: multi-user collaboration, comments or annotations on diagrams, hosted
accounts, drag-and-drop drawing, and per-element custom CSS authoring.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Make the diagram look the way I want (Priority: P1)

A user writes a diagram and wants it to fit its destination: bigger text for a projected slide,
tighter text for a dense reference chart, a palette that matches their team's docs, more breathing
room between boxes, a font that stays readable at thumbnail size. They adjust these with simple
sidebar controls, see the preview change immediately, and the same look carries into what they
export and what others see through a shared link.

**Why this priority**: Explicitly requested as the most helpful addition for end users, and the main
reason default-rendered diagrams fail to land in real destinations.

**Independent Test**: Load any example, drive each appearance control (text size, color scheme,
font, spacing, main-path emphasis), confirm the preview responds promptly, then confirm the exported
file and a shared link show exactly the same appearance.

**Acceptance Scenarios**:

1. **Given** a rendered diagram, **When** the user changes diagram text size, **Then** node labels,
   edge labels, and titles all scale, stay inside their shapes without clipping, and the layout
   adjusts so nothing overlaps.
2. **Given** appearance controls, **When** the user compares the smallest and largest offered text
   sizes, **Then** the largest is at least twice the smallest, covering both slide projection and
   dense documentation.
3. **Given** a diagram, **When** the user picks a different color scheme, **Then** the whole diagram
   adopts a coherent set of fills, lines, text, and background colors from that scheme — not one
   color swapped in isolation.
4. **Given** a user who finds default Mermaid lifeless, **When** they apply a curated scheme or pick
   their own base background and foreground colors, **Then** the result is visibly more polished and
   matches the colors they chose, without writing any styling code.
5. **Given** a diagram whose branches, retries, and loops all look identical, **When** the user
   enables main-path emphasis, **Then** the primary flow reads first and exception/retry paths
   recede visually.
6. **Given** a diagram with short labels that looks cramped, **When** the user increases spacing
   between elements, **Then** the eye gets visible rest between nodes and rows and connectors stop
   crossing pointlessly.
7. **Given** appearance choices, **When** the user exports an image, **Then** the file matches the
   preview: same text size, scheme, spacing, font, and emphasis.
8. **Given** a user who changed appearance settings, **When** they return to the site on the same
   device, **Then** the settings are still active, and one obvious action restores defaults.

---

### User Story 2 - Know when and why my diagram is broken (Priority: P1)

A user mistypes a line. Instead of the preview going blank, showing a raw library error, or silently
keeping the old picture, they get a clear indication that the current text failed, a readable
description of what is wrong, and where in their text to look. When they fix it, the message goes
away on its own.

**Why this priority**: The most damaging current flaw — right now a beginner cannot tell "still
rendering" from "syntax error" from "this tool is broken", which makes the whole tool look
untrustworthy.

**Independent Test**: Try each of several known-bad inputs (invalid keyword, unclosed bracket, wrong
node-shape syntax, empty text, oversized valid input) and confirm a distinct, readable state and
message for each, and that validity returns without a page reload after a fix.

**Acceptance Scenarios**:

1. **Given** text with a syntax error, **When** rendering is attempted, **Then** the preview shows
   an error state instead of pretending nothing happened, while the last successful render stays
   available for reference.
2. **Given** an error state, **When** it is displayed, **Then** the message names the problem in
   ordinary words and identifies the line responsible, and the position within it where that can be
   determined.
3. **Given** an error state, **When** the user corrects the text, **Then** the message clears and
   the redrawn diagram appears with no extra action.
4. **Given** empty or whitespace-only input, **When** the preview updates, **Then** the user sees a
   neutral "nothing to render yet" hint rather than a failure message.
5. **Given** a valid but large diagram, **When** rendering takes noticeable time, **Then** the
   preview indicates it is working instead of appearing frozen, and it does not report failure
   simply because the diagram is slow.
6. **Given** a diagram type the tool does not support, **When** the user submits it, **Then** the
   feedback says the type is unsupported rather than crashing the preview.

---

### User Story 3 - Start from a diagram type I actually need (Priority: P2)

A user wants a class diagram, state machine, ER model, project schedule, pie chart, user journey, or
mind map — and finds a named starting point for it, alongside styled examples showing what that type
looks like when laid out well.

**Why this priority**: Broadens who the tool serves; the repository's own history shows users
already attempting class diagrams and hitting rough edges. Ranked below the two P1 stories because it
adds capability rather than fixing breakage.

**Independent Test**: Choose each offered type in turn and confirm its example renders successfully
with default settings, demonstrating at least three distinct visual elements of that type; confirm
type-specific notations render (class-diagram angle brackets, sequence participants, schedule dates).

**Acceptance Scenarios**:

1. **Given** the starting-point list, **When** a user opens it, **Then** at least flowchart,
   sequence, class, state, entity-relationship, schedule/timeline, pie, user journey, and mind map
   are available, each named by what the diagram is for.
2. **Given** a chosen type, **When** its example loads, **Then** it renders successfully on first
   load and reads as a realistic starter with meaningful labels rather than a placeholder skeleton.
3. **Given** offered examples, **When** a user looks for guidance on good looks, **Then** at least
   one styled showcase example is available per major type, demonstrating recommended spacing and
   hierarchy they can copy from.
4. **Given** a user mid-edit, **When** they change the starting-point selection, **Then** their
   in-progress text is not silently overwritten.
5. **Given** the finished tool, **When** a visitor reads its title and description, **Then** the
   wording reflects general diagram support, not flowcharts only.

---

### User Story 4 - Keep my work and hand it to someone else (Priority: P2)

A user closes the tab by accident and finds their diagram waiting when they return. Later they want a
colleague to see exactly what they see, so they copy a link that reproduces the diagram and its
appearance — no account, no upload to a third party.

**Why this priority**: Without persistence every session is disposable; with sharing the tool becomes
useful for team communication. Both build on the existing single-diagram flow.

**Independent Test**: Type text, reload, confirm it is restored and labelled as restored. Generate a
link, open it in a fresh private window, confirm identical diagram and appearance, and confirm the
content travels inside the link rather than through a server.

**Acceptance Scenarios**:

1. **Given** a diagram in progress, **When** the user reloads or reopens the site on the same
   device, **Then** the text and its appearance settings are restored, and the user is told the work
   was restored rather than mistaking it for a template.
2. **Given** restored state, **When** the user wants a clean start, **Then** one obvious control
   clears the saved state and resets the editor.
3. **Given** a current diagram, **When** the user requests a share link, **Then** they receive a URL
   they can copy that reproduces both the diagram and its appearance.
4. **Given** a shared URL, **When** someone else opens it, **Then** they see the same diagram and
   look with no extra steps and can keep editing from there.
5. **Given** a diagram too large to encode in a link, **When** the user requests sharing, **Then**
   the tool explains the limit and offers downloading the source file instead, rather than producing
   a link that silently fails.
6. **Given** a mangled or truncated URL, **When** it cannot be read, **Then** the user gets a plain
   explanation and a working editor instead of a blank page.
7. **Given** a browser where local storage is unavailable, **When** the user works normally, **Then**
   the tool keeps working and notes that the draft is not being kept.

---

### User Story 5 - Export that fits its destination (Priority: P3)

A user needs the same diagram as a screen image, a slide-ready image, a transparent-background asset,
and a small thumbnail — each arriving with the scale, background, and filename they chose. They can
also drop the vector form straight onto the clipboard to paste elsewhere.

**Why this priority**: Export already works, and this project has needed three separate fixes in this
area; making the choices explicit improves outcomes and reduces repeat breakage.

**Independent Test**: Export the same diagram at two scales and a transparent background, verify
output dimensions, transparency, and filenames; paste a clipboard SVG into a text tool and confirm
it is usable markup.

**Acceptance Scenarios**:

1. **Given** a rendered diagram, **When** the user chooses an output scale from at least
   screen-friendly, high, and print-quality, **Then** the produced image dimensions reflect that
   choice.
2. **Given** a background choice of transparent, **When** the user exports an image, **Then** the
   background really is transparent and diagram text remains legible on whatever surface it is
   placed on.
3. **Given** a solid background choice, **When** the user exports, **Then** the diagram appearance is
   unchanged apart from the backdrop.
4. **Given** an export of any kind, **When** the diagram contains connectors with arrowheads or
   distinct line styles, **Then** those survive the export at every scale and background.
5. **Given** a diagram the user named, **When** they download source, vector, or image, **Then** the
   filename uses that name with the right extension, and awkward characters are sanitized instead of
   breaking the download.
6. **Given** a rendered diagram, **When** the user copies the vector form to the clipboard, **Then**
   pasting into a standard text tool gives usable markup, and if the browser refuses clipboard
   access the user is told plainly and offered the download.

---

### User Story 6 - Edit and inspect comfortably (Priority: P3)

A user works on a 60-line diagram with confidence: markup structure stands out, line numbers let them
talk about specific lines, the preview shows all of the diagram or any part they choose rather than a
small fixed scroll box, and everything stays readable in a dim room.

**Why this priority**: A genuine quality-of-life gain for heavy users, but they can work around it
today with an external editor; it also depends on the P1 and P2 work being in place to be worthwhile.

**Independent Test**: Load a long diagram and confirm structural highlighting plus line numbers;
confirm a diagram taller than the old fixed preview box is fully visible; check zoom in/out and
fit-to-view; switch to dark interface mode and confirm editor, controls, and preview all stay
readable.

**Acceptance Scenarios**:

1. **Given** a multi-line diagram, **When** the user edits it, **Then** keywords, node shapes, and
   arrows are visually distinguished and line numbers are available.
2. **Given** a diagram taller or wider than the old fixed preview area, **When** it renders, **Then**
   the whole diagram is visible without scrolling inside a small box, or the user can fit it with one
   control.
3. **Given** a dense diagram, **When** the user zooms, **Then** they can go from whole-diagram
   overview to label-level detail and back.
4. **Given** a low-light environment, **When** the user switches the interface to dark mode, **Then**
   editor text, controls, and preview chrome are all readable, and the diagram's own chosen
   appearance is not unexpectedly altered.
5. **Given** a very long diagram, **When** the user edits, **Then** typing stays responsive and
   indentation behaves as expected.

### Edge Cases

- **Slow render vs. broken render**: large valid diagrams must show progress, not a false error; the
  in-progress, invalid, and empty states must look different from each other.
- **Appearance settings vs. styling inside the user's text**: when the diagram source already sets
  colors or fonts, the outcome must follow a stated precedence rule the user can discover, never an
  invisible-text or unpredictable result.
- **Setting-combination extremes**: largest text with tightest spacing on a high-contrast scheme must
  still fit inside shapes and stay readable; no combination may clip text or make it vanish against
  its background.
- **Special characters**: non-Latin scripts, emoji, class-diagram angle-bracket notation, and quotes
  or braces inside labels must render, survive export, and survive sharing unchanged.
- **Huge inputs**: pasting tens of thousands of characters must either stay responsive or report the
  input is too large — never hang the page.
- **Oversized diagrams**: extremely wide or tall diagrams must remain inspectable and must not cover
  or break the rest of the page.
- **Link length ceiling**: an oversized diagram cannot fit in a link; the tool must say so and offer
  the file-download route.
- **Storage unavailable or full**: private browsing and locked-down browsers must degrade to
  "not saved" with a calm hint and no crash, and no misleading "saved" claim.
- **Type mismatch**: syntactically valid text from one diagram type chosen under another type must
  render or explain itself, never silently blank.
- **Drafts from an older version of the site**: must be read or cleanly ignored, never crash startup.
- **Export during a redraw**: export what is currently on screen and say so, rather than capturing a
  half-drawn diagram.
- **Display scaling**: browser zoom and different screen resolutions must not change diagram text in
  the exported file away from the requested size.

## Requirements *(mandatory)*

### Functional Requirements

**Look and feel control**

- **FR-001**: System MUST let the user set overall diagram text size across at least a 2x range from
  smallest to largest offered setting.
- **FR-002**: System MUST keep labels inside their shapes at every offered text size, adjusting the
  layout as size changes.
- **FR-003**: System MUST offer at least 6 curated color schemes spanning light, dark, and
  high-contrast looks, each restyling the entire diagram coherently (fills, lines, text, background)
  rather than one element at a time.
- **FR-004**: System MUST let the user derive a coherent look from their own base colors (at minimum
  a background and a foreground), so a diagram can match a destination page or deck without
  hand-picking every element color.
- **FR-005**: System MUST let the user choose the diagram font from at least 3 options covering
  sans, serif, and monospace, remaining legible at small sizes and in exports.
- **FR-006**: System MUST let the user adjust spacing between diagram elements, MUST default to
  roomier spacing than the cramped out-of-the-box layout.
- **FR-007**: System MUST let the user emphasize the main flow relative to secondary and exception
  paths so visual hierarchy reads at a glance.
- **FR-008**: System MUST apply the user's appearance settings identically to preview, exports,
  saved drafts, and shared links.
- **FR-009**: System MUST define a stable precedence when the user's diagram text carries its own
  style directives, and MUST make that precedence discoverable in the interface.
- **FR-010**: System MUST remember appearance choices per device, reopen with them active, and offer
  a one-click return to defaults.
- **FR-011**: System MUST warn the user when a combination would make content hard to see, such as a
  transparent export whose text is invisible on the destination surface.

**Reliable render feedback**

- **FR-012**: System MUST re-render automatically as the user edits, with no reload or manual render
  action.
- **FR-013**: System MUST show four distinct preview states: rendering, rendered, invalid, and empty.
- **FR-014**: System MUST describe invalid diagrams in plain language and identify the offending line,
  including position within the line when determinable.
- **FR-015**: System MUST clear an invalid state automatically once the text becomes renderable.
- **FR-016**: System MUST keep the last successful render available for reference while current text
  is invalid.

**Diagram breadth**

- **FR-017**: System MUST offer at least: flowchart, sequence, class, state, entity-relationship,
  schedule/timeline, pie, user journey, and mind map.
- **FR-018**: System MUST ship at least one styled showcase example for the major diagram types,
  demonstrating recommended spacing and hierarchy, in addition to plain syntax examples.
- **FR-019**: System MUST provide examples that display each type's characteristic notation
  correctly (for example class-diagram angle-bracket stereotypes) with no escaping artifacts.
- **FR-020**: System MUST NOT overwrite existing user text when the starting point changes, without
  confirmation.
- **FR-021**: System's title, headings, and descriptions MUST reflect general diagram support rather
  than flowcharts only.

**Persistence and sharing**

- **FR-022**: System MUST save the current text and appearance on the user's device and restore them
  on return, making clear that a draft was restored.
- **FR-023**: System MUST provide an obvious control to clear the stored draft and start blank.
- **FR-024**: System MUST provide a shareable link that reproduces the current diagram and its
  appearance for any recipient, without accounts and without storing diagram content on a server.
- **FR-025**: System MUST explain when a diagram is too large to encode in a link and offer the
  source-file download instead.
- **FR-026**: System MUST show a clear message and still open a working editor when a shared link
  cannot be read.
- **FR-027**: System MUST remain fully usable when device storage is unavailable, noting that drafts
  are not being kept.

**Export**

- **FR-028**: System MUST let the user choose output scale from at least three levels and the produced
  image MUST match the choice.
- **FR-029**: System MUST let the user choose export background: light, dark, a chosen color, or
  transparent, applying it to the image only and never altering the diagram source.
- **FR-030**: System MUST preserve arrowheads, connector styles, and diagram text styling in every
  export, at every scale and background.
- **FR-031**: System MUST name downloaded source, vector, and image files from a user-supplied diagram
  name, sanitizing unsafe characters and falling back to a clear default when none is given.
- **FR-032**: System MUST offer copying vector markup to the clipboard and MUST give an explained
  download fallback when the browser refuses clipboard access.

**Editing comfort**

- **FR-033**: System MUST visually distinguish diagram markup structure while editing and show line
  numbers.
- **FR-034**: System MUST size the preview from the rendered content and available space instead of
  one fixed height.
- **FR-035**: System MUST provide zoom in, zoom out, and fit-to-view controls for the preview.
- **FR-036**: System MUST offer an interface dark mode covering editor, controls, and preview chrome
  without changing the diagram's chosen appearance.
- **FR-037**: System MUST keep editing reliable — including tab and indent behavior — alongside the
  editor enhancements.

### Key Entities

- **Diagram Document**: the user's current work — source text, a human name used for file naming, and
  the render status (rendering / rendered / invalid / empty).
- **Appearance Settings**: presentation choices applied to a diagram — text size, color scheme, base
  colors, font family, spacing, path emphasis, export scale and background.
- **Color Scheme**: a named coherent set of diagram element colors; user-chosen base colors derive an
  equivalent scheme automatically.
- **Diagram Type**: a supported kind of diagram with a human-readable name and expected notation.
- **Starting Example**: a starter tied to a Diagram Type, either plain (correct syntax) or styled
  (a showcase of recommended appearance).
- **Saved Draft**: the on-device copy of a Diagram Document plus Appearance Settings, with
  restoration acknowledgement and a clear discard action.
- **Shared Link**: a self-contained representation of a Diagram Document and its Appearance Settings
  that any recipient can open, with content carried inside the link rather than on a server.
- **Export Artifact**: a produced source, vector, or image output carrying the diagram's appearance
  and the user's chosen name.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A first-time user can increase a diagram's text size, change its color scheme, and see
  both applied in the preview in under 15 seconds, without editing the diagram source at all.
- **SC-002**: 100% of invalid diagrams produce a plain-language explanation with a location hint, and
  in testing at least 8 of 10 users can identify the line to fix on their first try.
- **SC-003**: No large-but-valid diagram is ever reported as an error: 0 false failures when a test
  set of 10 large valid diagrams is rendered.
- **SC-004**: Users can choose from at least 9 diagram types and at least 6 color schemes, and at
  least 80% of testers rate a styled example as clearly better looking than the plain default render.
- **SC-005**: After an unplanned reload, 100% of recoverable drafts reopen with text and appearance
  intact, and at least 9 of 10 users correctly recognize their work was restored.
- **SC-006**: A shared link reproduces the sender's diagram and appearance for a recipient in a
  different browser within 10 seconds, with 0 sign-ups and 0 bytes of diagram content stored
  server-side.
- **SC-007**: Exported images match the user's chosen scale and background 100% of the time, use the
  user's chosen filename, and lose no arrowheads, line styles, or text styling across 20 sample
  exports.
- **SC-008**: A diagram exceeding the previously fixed preview area can be seen whole using
  fit-to-view, and an overview-to-label inspection of a dense diagram needs no more than 3 zoom
  actions.
- **SC-009**: Editing a 500-line diagram stays responsive, with any single appearance or text change
  reflected on screen within 3 seconds on ordinary hardware.
- **SC-010**: 0 user diagram contents are sent to or kept on a server, and no user reports losing
  work because of saving, sharing, or exporting.

## Assumptions

- **Audience**: engineers, analysts, and students who already write or paste diagram text, working in
  a browser, mostly on desktop or laptop; touch-specific authoring is not assumed.
- **Interpretation of "font size etc"**: read as diagram text size plus the closely related
  appearance knobs (color scheme, font family, spacing, emphasis, export background and scale). Full
  per-element theme authoring and custom CSS are excluded — they are a different, larger feature.
- **Same deployment model**: the tool stays a static site with no backend and no accounts, so
  persistence is per-device and links carry content in the link itself.
- **Derived-color default**: choosing base colors derives the remaining element colors
  automatically (as the theming inspiration does), rather than requiring the user to set each.
- **Hierarchy assistance is coarse**: the user indicates main-path emphasis; the tool does not
  semantically infer which branch is the happy path.
- **One diagram at a time**: the editor remains single-document; a document library or tabs is out of
  scope for this feature.
- **Built-in resources**: offered schemes, fonts, and examples ship with the site (no downloads or
  AI generation), consistent with the static deployment.
- **Defaults preserve today's feel**: text size, spacing, and scheme default to values close to the
  current look so returning users are not startled, with roomier spacing as the one intentional
  change.
- **Tooling dependency**: in-browser syntax highlighting, live re-render, and richer editor behavior
  depend on capabilities available in the browser-based runtime already in use. If a capability is
  not available there, the requirement downgrades to the nearest achievable form (for example plain
  text plus line numbers) rather than blocking the feature — this must be confirmed early in
  planning.
- **No AI-assisted diagram rewriting**: nothing in this feature changes the meaning of a user's
  diagram text automatically, since silent redesign or rewording by a tool is a known risk when
  diagrams document real systems.
- **Non-goals carried forward**: no collaboration, no comments, no hosted storage, no version
  history, no visual drag-and-drop node placement.
