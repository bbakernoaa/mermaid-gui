"""Runtime asset reader — the static-site compatibility layer.

The Streamlit app ships as plain files on GitHub Pages (no server, no build
step). ``st.components.v1.html`` is a one-way, self-contained HTML component:
its content is *not* served from the site origin, so the preview component
cannot ``<script type="module" src="./render_component.js">``. We therefore
read the component sources at runtime and inline them into the document we
hand to the component, and give each module a stable ``globalThis`` identity so
the Python glue can address them.

This module is imported by ``app.py`` inside Pyodide, and by tests under plain
CPython — it must stay free of Streamlit imports so the pure logic is testable
without a browser (constitution: client-only, no build step).
"""

import hashlib
import json
import os

ASSET_ERROR_TYPE = "assetUnavailable"
REQUIRED_ASSETS = ("render_component.js", "export_component.js", "preview_component.css", "host_bridge.js")


class AssetError(RuntimeError):
    """A component asset could not be read. The message is user-facing."""


def base_dir(entrypoint_file):
    return os.path.dirname(os.path.abspath(entrypoint_file))


def read_asset(name, directory):
    """Return the text of asset ``name`` in ``directory`` or raise AssetError.

    Two routes are tried because Stlite may expose the app folder as a real
    filesystem or keep it virtual: a plain ``open`` first, then the Pyodide JS
    filesystem bridge.
    """
    path = os.path.join(directory, name)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        pass
    text = _read_via_js(path)
    if text:
        return text
    raise AssetError(
        "Could not load %s from the site files. Make sure %s was deployed next to "
        "app.py, then reload." % (name, name)
    )


def missing_assets(directory):
    """Return the required assets that cannot be read (UI shows a plain notice)."""
    missing = []
    for name in REQUIRED_ASSETS:
        try:
            read_asset(name, directory)
        except AssetError:
            missing.append(name)
    return missing


def _read_via_js(path):
    try:
        import js  # provided by Pyodide/Stlite; absent under CPython  # noqa: F401
    except Exception:
        return None
    try:
        from js import API  # type: ignore[attr-defined]

        data = API.fs.readFileSync(path, "utf-8")
        return data if isinstance(data, str) else None
    except Exception:
        return None


def json_payload(obj):
    """Serialise ``obj`` for a ``<script type="application/json">`` block.

    ``</script>`` inside the JSON text would close the element early, and the
    JS-invalid line separators must be escaped; diagram sources can contain
    both (a sequence label may legitimately include ``</``).
    """
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return text.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


# --------------------------------------------------------------- the document --
# The renderer is pinned to one absolute CDN URL, exactly as the app did before
# this feature: inside a ``srcdoc`` component document, relative imports resolve
# against the *site* URL, which would break the module graph.
MERMAID_ESM_URL = "https://cdn.jsdelivr.net/npm/mermaid@11.12.0/dist/mermaid.esm.min.mjs"

CSS_NAME = "preview_component.css"
RENDER_NAME = "render_component.js"
EXPORT_NAME = "export_component.js"


def boot_script(mermaid_url=MERMAID_ESM_URL, attach_host=True):
    """The glue that runs inside the component document.

    ``attach_host`` is off only for the fixture pages, which have no host page
    and therefore no localStorage or address bar to relay to.
    """
    lines = [
        "const el = document.getElementById('mmd-payload');",
        "let payload = { command: 'render', source: '' };",
        "try { payload = el ? JSON.parse(el.textContent) : payload; } catch (err) { payload = { command: 'render', source: '' }; }",
        "const render = globalThis.__mermaidGuiRender__;",
        "render.boot({",
        "  document: document,",
        "  attachHost: %s," % ("true" if attach_host else "false"),
        "  interfaceMode: (payload.chrome || {}).interfaceMode,",
        "  mermaidUrl: (payload.options && payload.options.mermaidUrl) || %r," % (mermaid_url,),
        "});",
        "render.handle(payload);",
    ]
    return "\n".join(lines)


def document_key(source, knobs_json):
    """Stable for one visible document; changes when the picture must change.

    ``index.html`` uses it to resize only the component frame that produced a
    given height report, never the frame that hosts the whole app.
    """
    digest = hashlib.sha1(("%s|%s" % (source, knobs_json)).encode("utf-8")).hexdigest()[:12]
    return "mmd-%s" % digest


def component_document(directory, payload_json, doc_key=None, mermaid_url=MERMAID_ESM_URL,
                       attach_host=True):
    """The self-contained document handed to ``st.components.v1.html``.

    ``payload_json`` must already be HTML-inert (``render_bridge.escape_for_html``
    on the serialised RenderRequest). Both modules are inlined -- there is no
    bundler and no ``src`` that a srcdoc document could resolve -- and each
    ``<script type="module">`` tag is its own scope, so each one ends by
    publishing its public API on ``globalThis``. The tag order is the contract:
    render module, export module, then the glue that reads both.
    """
    css = read_asset(CSS_NAME, directory)
    render_js = read_asset(RENDER_NAME, directory)
    export_js = read_asset(EXPORT_NAME, directory)
    key = doc_key or document_key(payload_json, "")
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"/>'
        '<meta name="viewport" content="width=device-width, initial-scale=1"/>'
        '<title>Diagram preview</title>'
        '<meta name="mmd-doc-key" content="%s"/><style>%s</style></head>'
        '<body class="mmd-chrome"><div id="mmd-root" class="mmd-root" data-interface="auto"></div>'
        '<script type="application/json" id="mmd-payload">%s</script>'
        '<script type="module">%s\n__selfRegister__();</script>'
        '<script type="module">%s\n__selfRegister__();</script>'
        '<script type="module">%s</script>'
        '</body></html>'
        % (
            key,
            css.replace("</style", "<\\/style"),
            payload_json,
            render_js.replace("</script", "<\\/script"),
            export_js.replace("</script", "<\\/script"),
            boot_script(mermaid_url, attach_host),
        )
    )
