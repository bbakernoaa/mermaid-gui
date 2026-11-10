"""Build the browser fixtures: the real component document, and real payloads.

The suites must exercise the shipped ``render_component.js`` /
``export_component.js`` / ``preview_component.css`` exactly as the app sends
them, without waiting for Pyodide to boot on every test. So this module is the
test-side twin of the app:

* ``page_html``  - the *same* document ``app.py`` hands to ``st.components.v1.html``,
  built with the same ``preview_asset.component_document`` and the same payload
  builder (``render_bridge`` + ``appearance.resolve``). Written as one file per
  case, so a failure points at a named case.
* ``payload_patch`` - resolved appearance/source deltas for the variants a test
  wants to drive through the live component (text scales, densities, schemes,
  per-catalog-type examples). ``send()`` in tests/support.ts feeds these to the
  shipped handler, so the resolver stays the single source of truth (contract
  A-2: preview, export and share all get the identical resolved object).

Run before the browser suites::

    python3 tests/build_fixture.py     # writes tests/.generated/
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import appearance  # noqa: E402
import preview_asset  # noqa: E402
import render_bridge  # noqa: E402
import templates  # noqa: E402

OUT_DIR = os.path.join(HERE, ".generated")

GOOD = "flowchart TD\n  A[Start] --> B[Finish]\n"
BROKEN_ARROW = "flowchart TD\n  A[Start] -->\n"
GARBAGE = "this is not mermaid at all\n%%%###\n"
UNKNOWN_FIRST_WORD = "wat\n  A --> B\n"
TYPED_THEME = "%%{init: {'theme':'dark'}}%%\nsequenceDiagram\n  A->>B: hello\n"
TYPED_COLORS = "%%{init: {'themeVariables': {'primaryColor':'#330066'}}}%%\nflowchart TD\n  A[Start] --> B[Finish]\n"

FIXTURE_FILES = {
    "notation": "notation-edge-cases.mmd",
    "large": "large-500-nodes.mmd",
    "long": "long-120-lines.mmd",
}


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def text(name):
    return read(os.path.join(ROOT, name))


def build_request(source, knobs=None, diagram_type=None, command="render",
                  name=None, interface_mode="auto", autosave=True, options=None):
    """The payload for one render, assembled exactly the way ``app.py`` does it."""
    knobs = dict(appearance.DEFAULT_KNOBS) if knobs is None else dict(knobs)
    detected = diagram_type or templates.detect_diagram_type(source)
    frontmatter = templates.extract_front_matter(source)
    resolved = appearance.resolve(knobs, detected, frontmatter)
    resolved.setdefault("export", {})["scaleName"] = knobs.get("exportScale")
    resolved["export"]["background"] = knobs.get("exportBackground")
    request = render_bridge.build_render_request_dict(source, resolved, command=command)
    request["chrome"] = {
        "autosave": autosave,
        "name": name if name is not None else (templates.label_for(detected) or ""),
        "knobs": knobs,
        "selectedTypeId": detected or "",
        "interfaceMode": interface_mode,
        "storage": "available",
    }
    if options:
        request["options"] = options
    return request


def payload_patch(source, **kwargs):
    """Only the fields a test needs to override to drive one new cycle."""
    request = build_request(source, **kwargs)
    return {
        "requestId": request["requestId"],
        "source": request["source"],
        "appearance": request["appearance"],
        "chrome": request["chrome"],
    }


UNLOADABLE_URL = "/tests/.generated/unloadable.mjs"


def page_html(case, source, **kwargs):
    mermaid_url = kwargs.pop("mermaid_url", None)
    request = build_request(source, **kwargs)
    payload = render_bridge.escape_for_html(json.dumps(request, separators=(",", ":")))
    return preview_asset.component_document(ROOT, payload, doc_key="fixture-%s" % case,
                                            mermaid_url=mermaid_url or preview_asset.MERMAID_ESM_URL)


RUNNER = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"/>
<title>Component under test</title></head><body>
<div id="root"></div>
<!--
  The harness mirrors production: the component document sits in a null-origin
  srcdoc iframe, and this page is the host that owns localStorage, the address
  bar and the iframe height, through the very same host_bridge.js the app loads.
  So every fixture test also proves the relay works, not just the render.
-->
__HOST_BRIDGE_SOURCE__
<script>
window.__mermaidGuiHost.install();
window.__mmdMessages = [];
window.addEventListener("message", (event) => {
  const data = event.data;
  if (!data || typeof data !== "object" || typeof data.type !== "string") return;
  if (data.type.indexOf("mmd-") !== 0) return;
  const record = Object.assign({}, data);
  // A rendered 50 000-character diagram is a several-hundred-KB string; keeping
  // every copy of it in the host page is how the suite used to crash the shared
  // renderer. Tests assert on the metadata, so trim the markup to its length.
  if (record.payload && typeof record.payload.svg === "string") {
    record.payload = Object.assign({}, record.payload, { svgLength: record.payload.svg.length });
    delete record.payload.svg;
  }
  window.__mmdMessages.push(record);
  if (window.__mmdMessages.length > 120) window.__mmdMessages.shift();
});
const params = new URLSearchParams(window.location.search);
const wanted = (params.get("case") || "good").replace(/[^a-z0-9-]/gi, "");
fetch("/tests/.generated/" + wanted + ".html", { cache: "no-store" })
  .then((response) => {
    if (!response.ok) throw new Error(wanted + ".html -> HTTP " + response.status);
    return response.text();
  })
  .then((markup) => {
    const frame = document.createElement("iframe");
    frame.setAttribute("title", "component-" + wanted);
    frame.setAttribute("srcdoc", markup);
    frame.style.width = "100%";
    frame.style.border = "0";
    document.getElementById("root").appendChild(frame);
    window.__mmdFrame = frame;
  })
  .catch((error) => { document.getElementById("root").textContent = String(error); });
</script>
</body></html>"""


def page_cases():
    at_limit = read(os.path.join(HERE, "fixtures", "max-size-50000.mmd"))
    cases = {
        "good": (GOOD, {}),
        "broken-arrow": (BROKEN_ARROW, {}),
        "garbage": (GARBAGE, {}),
        "empty": ("", {}),
        "unknown-type": (UNKNOWN_FIRST_WORD, {}),
        "typed-theme": (TYPED_THEME, {}),
        "typed-colors": (TYPED_COLORS, {"knobs": dict(appearance.DEFAULT_KNOBS, schemeName="sunset", baseColors=None)}),
        "dark-interface": (GOOD, {"interface_mode": "dark"}),
        # 10 characters beyond the 50000-character ceiling.
        "too-large": (at_limit + "X" * 10, {}),
        "at-limit": (at_limit, {}),
        # A renderer that cannot load must be *said* so (contract section 3): this
        # case boots against a module with no default export. The URL is swapped in
        # the boot glue, not the payload -- the RenderRequest shape is frozen.
        "no-renderer": (GOOD, {"mermaid_url": UNLOADABLE_URL}),
    }
    for case, filename in FIXTURE_FILES.items():
        cases[case] = (read(os.path.join(HERE, "fixtures", filename)), {})
    return cases


def variant_payloads():
    """Name -> the deltas ``send()`` applies, one per appearance decision.

    Keeping the variants here (rather than in TypeScript) means the contrast
    clamps, the multipliers and the frozen settings in every browser assertion
    come from ``appearance.py``, the same module the app uses.
    """
    payloads = {}
    for name, value in [
        ("smallest", "smallest"),
        ("small", "small"),
        ("medium", "medium"),
        ("large", "large"),
        ("largest", "largest"),
    ]:
        payloads["text-" + name] = payload_patch(GOOD, knobs=dict(appearance.DEFAULT_KNOBS, textScale=value))
    for name in appearance.DENSITIES:
        payloads["density-" + name] = payload_patch(GOOD, knobs=dict(appearance.DEFAULT_KNOBS, density=name))
    for name in appearance.PATH_EMPHASES:
        payloads["emphasis-" + name] = payload_patch(GOOD, knobs=dict(appearance.DEFAULT_KNOBS, pathEmphasis=name))
    for name in appearance.FONT_FAMILIES:
        payloads["font-" + name] = payload_patch(GOOD, knobs=dict(appearance.DEFAULT_KNOBS, fontFamily=name))
    for name in appearance.SCHEMES:
        payloads["scheme-" + name] = payload_patch(GOOD, knobs=dict(appearance.DEFAULT_KNOBS, schemeName=name))
    payloads["base-dark"] = payload_patch(
        GOOD,
        knobs=dict(appearance.DEFAULT_KNOBS, baseColors={"background": "#101820", "foreground": "#f8fafc"}),
    )
    payloads["base-light"] = payload_patch(
        GOOD,
        knobs=dict(appearance.DEFAULT_KNOBS, baseColors={"background": "#f8fafc", "foreground": "#101820"}),
    )
    for name in appearance.EXPORT_SCALES:
        payloads["export-" + name] = payload_patch(GOOD, knobs=dict(appearance.DEFAULT_KNOBS, exportScale=name))
    for name in appearance.EXPORT_BACKGROUND_WORDS:
        payloads["background-" + name] = payload_patch(GOOD, knobs=dict(appearance.DEFAULT_KNOBS, exportBackground=name))
    payloads["typed-theme"] = payload_patch(TYPED_THEME)
    payloads["typed-colors"] = payload_patch(TYPED_COLORS, knobs=dict(appearance.DEFAULT_KNOBS, schemeName="sunset"))
    payloads["notation"] = payload_patch(text("tests/fixtures/notation-edge-cases.mmd"))
    payloads["empty"] = payload_patch("")
    payloads["broken-arrow"] = payload_patch(BROKEN_ARROW)
    payloads["garbage"] = payload_patch(GARBAGE)
    payloads["unknown-type"] = payload_patch(UNKNOWN_FIRST_WORD)
    payloads["large"] = payload_patch(text("tests/fixtures/large-500-nodes.mmd"))
    return payloads


def catalog_payloads():
    """One payload per catalog example, plus the A-8 stress pairing.

    A-8 is the regression for the spec's own edge case -- the largest text at the
    loosest spacing must not clip any label -- so every example is also resolved
    that way. Reading catalog.json keeps the browser suite honest about what
    actually ships instead of hard-coding diagrams twice.
    """
    rows = json.loads(read(os.path.join(HERE, "catalog.json")))
    plain = {}
    stress = {}
    for row in rows:
        key = "%s/%s" % (row["typeId"], row["purpose"])
        plain[key] = payload_patch(row["source"], diagram_type=row["typeId"])
        stress[key] = payload_patch(
            row["source"],
            diagram_type=row["typeId"],
            knobs=dict(appearance.DEFAULT_KNOBS, textScale="largest", density="open"),
        )
    return {"plain": plain, "stress": stress, "rows": rows}


UNLOADABLE_MODULE = ("/** Fixture only: a module with no default export, so the loader rejects "
                     "it (contract section 3, rendererUnavailable). */\nexport const nope = 1;\n")


def main():
    pages = page_cases()
    if os.path.isdir(OUT_DIR):
        # Stale pages would let a deleted case keep passing.
        for name in os.listdir(OUT_DIR):
            if name.endswith(".html") or name == "manifest.json":
                os.remove(os.path.join(OUT_DIR, name))
    else:
        os.makedirs(OUT_DIR)
    for case, (source, options) in pages.items():
        with open(os.path.join(OUT_DIR, "%s.html" % case), "w", encoding="utf-8") as handle:
            handle.write(page_html(case, source, **options))
    print("pages: %s" % ", ".join(sorted(pages)))
    host_source = text("host_bridge.js").replace("</scri" + "pt", "<\\/scri" + "pt")
    with open(os.path.join(OUT_DIR, "runner.html"), "w", encoding="utf-8") as handle:
        handle.write(RUNNER.replace("__HOST_BRIDGE_SOURCE__", "<script>" + host_source + "</script>"))
    with open(os.path.join(OUT_DIR, "unloadable.mjs"), "w", encoding="utf-8") as handle:
        handle.write(UNLOADABLE_MODULE)

    baked = {}
    for case, (source, options) in pages.items():
        request = build_request(source, **{k: v for k, v in options.items() if k != "mermaid_url"})
        baked[case] = {"source": request["source"], "appearance": request["appearance"],
                       "chrome": request["chrome"]}
    scheme_labels = {}
    for name, scheme in appearance.SCHEMES.items():
        scheme_labels[name] = (scheme or {}).get("label") or name
    manifest = {
        "mermaidUrl": preview_asset.MERMAID_ESM_URL,
        "schemeLabels": scheme_labels,
        "cases": sorted(pages),
        "sources": {case: source for case, (source, _options) in pages.items()},
        "baked": baked,
        "payloads": variant_payloads(),
        "catalog": catalog_payloads(),
    }
    with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, separators=(",", ":"), sort_keys=True)
    print("wrote %d pages, %d payloads and %d catalog examples to %s"
          % (len(pages), len(manifest["payloads"]["payloads"]) if False else len(variant_payloads()),
             len(manifest["catalog"]["rows"]), OUT_DIR))


if __name__ == "__main__":
    main()
