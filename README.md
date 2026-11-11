# Mermaid Diagram Editor

A browser-only editor for Mermaid diagrams: write or paste text, watch it render, make it
look the way you want, and take the picture with you as SVG, PNG or a shareable link.

It runs entirely on the client. Python (Streamlit) executes in the browser through
[Stlite](https://github.com/whitphx/stlite) and WebAssembly — there is no server, no account,
no build step, and nothing you type is ever uploaded. The site is a plain upload of this
repository's root to GitHub Pages.

## What it does

- **Nine diagram types, not just flowcharts** — flowchart, sequence, class, state,
  entity-relationship, gantt, pie, user journey and mindmap, each with a plain and a styled
  example that renders on the first load, plus a blank starting point. Pick a type in the
  sidebar; the editor loads that example and the preview follows the text, not the pick.
- **A look you control** — text size (12 px to 28 px labels, over 2× of range), colour scheme
  (Mermaid's own themes plus a higher-contrast default), web-safe font stack, spacing from
  compact to open, and main-path line emphasis. Two colour pickers let you derive the whole
  palette from one background and one foreground colour. Low-contrast pairs are corrected and
  the preview says which ones.
- **Preview that reports honestly** — four states (rendering, up to date, not drawn, waiting
  for text). A diagram that cannot be drawn names the line it stopped at, quotes the offending
  text, and keeps the last good picture on screen; the message clears itself when you fix it.
  Mermaid's jargon is rewritten into plain language. A diagram too large for the browser's own
  limits is refused with an explanation rather than silently truncated.
- **Exports that match the preview** — the same resolved appearance drives the picture, the SVG
  file, the PNG raster, and the shared link. PNG scale is screen (2×), high (3×) or print (4×),
  so a print export is exactly twice the linear size of a screen one; the background can be the
  diagram's own, white, or transparent. Arrowheads, connector styles and inline colours survive
  export, and file names are taken from your diagram name with anything unsafe removed.
- **Zoom and fit** — zoom in, zoom out, fit-to-view and 1:1 on the rendered picture itself
  (scaling the SVG, never re-rendering it), in a preview that sizes itself to the diagram
  instead of sitting in a fixed-height scroll box.
- **Nothing is lost** — your text, name and knobs are kept as a draft on your own device and
  offered back when you return, with the time it saved. "Start fresh" clears the editor and the
  device together. An interface dark theme styles the chrome only and never touches the diagram.
- **Share links** — Copy link produces a URL whose fragment carries the diagram *and* its look,
  decodable in another browser with no signup. Links are not automatic: the address is only
  written when you ask. A diagram too big for a reliable link says so and offers the `.mmd`
  download instead; a mangled link shows a plain message and still opens a working editor.

## How to use it

1. Open the site (or `python3 -m http.server 8000` and visit `http://localhost:8000`).
2. Pick a diagram type in the sidebar, or start typing in the **Mermaid text** box.
3. Turn the **Look** controls; the preview updates as you go.
4. Use the toolbar under the picture to export SVG or PNG, copy the markup, or change scale,
   background and file name.
5. Use **Share this diagram → Copy link** to send it, or **Download .mmd source** to keep it.

## Architecture, briefly

| File | Role |
|---|---|
| `index.html` | The page. Loads Stlite from a CDN, mounts `app.py` with its sibling modules in one virtual directory, owns `localStorage`, the `#p=` fragment and the preview frame height through `host_bridge.js`. |
| `app.py` | The Streamlit script: widgets, catalogue, appearance resolution, share payloads, downloads. |
| `appearance.py` | The one resolver of "how should this look", from knobs + diagram type + the diagram's own front matter. Preview, export and share all read its output. |
| `templates.py` | The diagram catalogue and type detection. |
| `render_component.js` / `preview_component.css` | The preview component: parse → render, states, error wording, zoom, chrome, export toolbar. |
| `export_component.js` | One `exportAs(kind, options)` path for SVG, PNG and clipboard copy, including the standalone-file repair. |
| `messages.py`, `render_bridge.py`, `states.py`, `share.py`, `preview_asset.py` | The contracts between those layers: payloads, status objects, request ids, the share codec, and component document assembly. |
| `host_bridge.js` | Page-side storage, fragment and iframe-height relay (the component iframe is an opaque-origin `srcdoc` sandbox, and Stlite's Python runs in a Web Worker). |

`tests/` holds the pure-Python suites and the Playwright suites, and `specs/` the
specification, plan, contracts and quickstart this code was built from. The dev-only
Node tooling (`package.json`, `playwright.config.ts`) never runs at deploy time.

## Contributing a diagram type

Add an entry to `CATALOG` in `templates.py`: `typeId` (matching the type Mermaid's `parse()`
reports), `label`, `blurb`, and at least two `examples` (`plain` and `styled`) each with three
or more drawable elements. Then run:

```bash
python3 -m pytest tests/ -q                 # catalogue completeness and every contract
npm run test:browser                         # renders, appearance, exports, states, sharing
```

Both are explained in `specs/001-editor-experience-upgrades/quickstart.md`, along with the
manual smoke steps and the opt-in live-boot suite.

## Deployment

`.github/workflows/deploy.yml` publishes the repository root to GitHub Pages unchanged —
static files only, no build, no bundler, no dependency install. `.github/workflows/ci.yml`
runs the tests on push and pull request but produces nothing that ships.
