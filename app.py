"""Mermaid diagram editor — a client-only Streamlit app.

Runs in the browser under Stlite (``index.html``): no server, no build step,
nothing uploaded. Three runtime facts shape this file:

* ``st.components.v1.html`` is a one-way, ``srcdoc``-sandboxed iframe, so the
  preview component cannot reach ``localStorage`` or the page URL. ``index.html``
  owns both and hands a one-shot snapshot in through ``runDir`` (spikes S-1/S-2).
* Streamlit 1.40.1 (bundled with ``@stlite/mountable`` 0.73.0) has **no**
  ``st.code_editor``, so the editor stays a ``st.text_area`` with a line ruler —
  the spec's permitted FR-033 downgrade (spike S-3 not performed).
* Render state, error chrome, zoom and export live in the component. This file
  owns widgets, appearance resolution, the catalog, share payloads, downloads.

Mermaid sources are injected as JSON inside a ``<script type="application/json">``
block, which is why no HTML-escaping of the diagram text is needed here: ``<<interface>>``
survives because JSON is data, not markup (research R-5).
"""

import hashlib
import json
import os
import time

import sys

import streamlit as st
import streamlit.components.v1 as components

import appearance
import messages
import preview_asset
import render_bridge
import share
import templates

ASSET_DIR = os.path.dirname(os.path.abspath(__file__))
# Under Stlite this file is mounted as ``mermaid-gui-app/app.py`` and the
# runner does not guarantee that its directory is importable, so the sibling
# modules sitting next to it are made reachable explicitly.
if ASSET_DIR not in sys.path:
    sys.path.insert(0, ASSET_DIR)

MAX_SOURCE_CHARS = messages.MAX_PASTE_CHARS
PASTE_CEILING = MAX_SOURCE_CHARS + 1

st.set_page_config(page_title="Mermaid Diagram Editor", layout="wide")
st.title("Mermaid Diagram Editor")
st.caption("Plain diagram types, a look you control, and exports that match the preview.")


# ---------------------------------------------------------------------- boot --
def _session():
    state = st.session_state
    state.setdefault("booted", False)
    state.setdefault("knobs", dict(appearance.DEFAULT_KNOBS))
    state.setdefault("source", "")
    state.setdefault("name", "")
    state.setdefault("choice", (templates.BLANK_TYPE_ID, "plain"))
    state.setdefault("loaded_example", None)
    state.setdefault("link_error", None)
    state.setdefault("restore", None)
    state.setdefault("interface_mode", "auto")
    state.setdefault("autosave", True)
    state.setdefault("host_action", None)
    state.setdefault("storage_state", "unknown")
    state.setdefault("last_sent", None)
    state.setdefault("payload_json", None)
    state.setdefault("request_id", None)
    state.setdefault("last_change_at", 0.0)
    state.setdefault("pending_send", False)
    state.setdefault("doc_key", None)
    return state


def _apply_boot(state, boot):
    """Apply the one snapshot ``index.html`` handed in, exactly once.

    Order of precedence is link > draft > stored knobs, but a draft is always
    offered: arriving by someone else's link must not quietly discard the text
    sitting on this device (FR-022), which is why ``restore`` is set even when
    the fragment already filled the editor.
    """
    if state["booted"]:
        return
    state["booted"] = True
    state["storage_state"] = boot.get("storage") or "unavailable"

    fragment = boot.get("fragment")
    if fragment:
        decoded = share.decode_fragment(fragment)
        if share.is_decode_error(decoded):
            state["link_error"] = decoded
        else:
            _apply_document(state, decoded)

    migrated = share.migrate_document(boot.get("draft"))
    if migrated is not None and (migrated.get("source") or "") != state["source"]:
        state["restore"] = migrated
        return

    saved = boot.get("appearance")
    if isinstance(saved, dict) and saved:
        state["knobs"] = share.clamp_knobs({**appearance.DEFAULT_KNOBS, **saved})


def _apply_document(state, document):
    state["source"] = document.get("source") or ""
    if document.get("name"):
        state["name"] = document["name"]
    knobs = document.get("knobs")
    if isinstance(knobs, dict) and knobs:
        state["knobs"] = share.clamp_knobs({**appearance.DEFAULT_KNOBS, **knobs})


def _mark_change(state):
    state["last_change_at"] = time.monotonic()
    state["pending_send"] = True


# ------------------------------------------------------------------- sidebar --
def _sidebar_catalog(state):
    st.sidebar.header("Start from")
    options = templates.entries()
    choice = st.sidebar.selectbox(
        "Diagram type",
        [item["typeId"] for item in options],
        format_func=templates.label_for,
    )
    entry = templates.entry_for(choice) or {}
    if entry.get("blurb"):
        st.sidebar.caption(entry["blurb"])
    purposes = _purposes(entry)
    state["choice"] = (choice, purposes[0])

    if choice != templates.BLANK_TYPE_ID:
        pick = st.sidebar.selectbox("Example", purposes, format_func=_purpose_label)
        state["choice"] = (choice, pick)
        example = templates.example_for(choice, pick) or {}
        if example.get("shows"):
            st.sidebar.caption("Shows: %s" % example["shows"])

        key = (choice, pick)
        if key != state["loaded_example"]:
            source = example.get("source", "")
            dirty = bool(state["source"].strip()) and state["source"] != source
            if not dirty:
                _load_example(state, key, source)
            else:
                st.sidebar.warning("The editor holds text that differs from this starting point.")
                if st.sidebar.button("Replace it", key="replace_%s_%s" % key):
                    _load_example(state, key, source)
    elif state["loaded_example"] != (choice, "blank"):
        _load_example(state, (choice, "blank"), "")
    return choice


def _purposes(entry):
    seen = []
    for example in entry.get("examples", []):
        purpose = example.get("purpose") or "plain"
        if purpose not in seen:
            seen.append(purpose)
    return seen or ["plain"]


def _purpose_label(purpose):
    return {"plain": "plain", "styled": "styled"}.get(purpose, str(purpose))


def _load_example(state, key, source):
    state["loaded_example"] = key
    state["source"] = source
    _mark_change(state)


def _sidebar_appearance(state):
    knobs = state["knobs"]
    st.sidebar.header("Look")
    changed = False

    size = st.sidebar.select_slider("Text size", options=list(appearance.TEXT_SCALES), value=knobs["textScale"],
                                    help="About 12 px up to 28 px labels — over 2x of range.")
    if size != knobs["textScale"]:
        knobs["textScale"] = size
        changed = True

    names = list(appearance.SCHEMES.keys())
    scheme = st.sidebar.selectbox("Colour scheme", names,
                                  index=names.index(knobs["schemeName"]) if knobs["schemeName"] in names else 0,
                                  format_func=_scheme_label,
                                  help="Mermaid's own themes plus a readable default; low-contrast pairs are corrected.")
    if scheme != knobs["schemeName"]:
        knobs["schemeName"] = scheme
        changed = True

    fonts = list(appearance.FONT_FAMILIES)
    font = st.sidebar.selectbox("Font", fonts,
                                index=fonts.index(knobs["fontFamily"]) if knobs["fontFamily"] in fonts else 0,
                                help="Web-safe stacks only, so an exported file shows the same shapes anywhere.")
    if font != knobs["fontFamily"]:
        knobs["fontFamily"] = font
        changed = True

    density = st.sidebar.select_slider("Spacing", options=list(appearance.DENSITIES), value=knobs["density"],
                                       help="More space between nodes usually reads better than more colour.")
    if density != knobs["density"]:
        knobs["density"] = density
        changed = True

    emphasis = st.sidebar.select_slider("Line emphasis", options=list(appearance.PATH_EMPHASES), value=knobs["pathEmphasis"])
    if emphasis != knobs["pathEmphasis"]:
        knobs["pathEmphasis"] = emphasis
        changed = True

    derived = st.sidebar.checkbox("derive colours from two colours", value=knobs["baseColors"] is not None,
                                  help="One background and one foreground colour; every element colour is mixed from them.")
    base = knobs["baseColors"] or {}
    background_colour = st.sidebar.color_picker("Background colour", value=base.get("background") or "#ffffff", disabled=not derived)
    foreground_colour = st.sidebar.color_picker("Foreground colour", value=base.get("foreground") or "#101020", disabled=not derived)
    wanted_base = {"background": background_colour, "foreground": foreground_colour} if derived else None
    if wanted_base != knobs["baseColors"]:
        knobs["baseColors"] = wanted_base
        changed = True

    if st.sidebar.button("Reset appearance"):
        state["knobs"] = dict(appearance.DEFAULT_KNOBS)
        changed = True
    if changed:
        _mark_change(state)


def _sidebar_output(state):
    knobs = state["knobs"]
    st.sidebar.header("Export and file")
    scales = list(appearance.EXPORT_SCALES)
    scale = st.sidebar.selectbox("PNG scale", scales,
                                 index=scales.index(knobs["exportScale"]) if knobs.get("exportScale") in scales else 1,
                                 help="2x / 3x / 4x of the preview size. SVG is vector at any setting.")
    backgrounds = list(appearance.EXPORT_BACKGROUND_WORDS)
    choice = st.sidebar.selectbox("PNG background", backgrounds,
                                  index=backgrounds.index(knobs["exportBackground"]) if knobs.get("exportBackground") in backgrounds else 0)
    name = st.sidebar.text_input("Diagram name", value=state["name"], help="Used for exported file names.")
    interface = st.sidebar.radio("Interface", ["auto", "light", "dark"],
                                 index=["auto", "light", "dark"].index(state["interface_mode"]), horizontal=True,
                                 help="Themes the editor chrome only. Never the diagram, never a shared link.")
    keep = st.sidebar.toggle("Keep a draft on this device", value=state["autosave"])

    knobs["exportScale"] = scale
    knobs["exportBackground"] = choice
    if name != state["name"]:
        state["name"] = name
        _mark_change(state)
    state["interface_mode"] = interface
    if bool(keep) != state["autosave"]:
        state["autosave"] = bool(keep)


def _scheme_label(name):
    scheme = appearance.SCHEMES.get(name) or {}
    if scheme.get("label"):
        return scheme["label"]
    return str(name).replace("-", " ").capitalize()


# ------------------------------------------------------------------- notices --
def _restore_notice(state):
    draft = state.get("restore")
    if not draft:
        return
    when = _humanise_saved(draft.get("savedAt"))
    st.info("Restored a draft from this device%s. It was never uploaded." % (" — saved %s" % when if when else ""))
    keep, clear = st.columns(2)
    if keep.button("Keep editing", key="keep_draft"):
        state["restore"] = None
        _apply_document(state, draft)
        state["loaded_example"] = ("restored", "draft")
        _mark_change(state)
    if clear.button("Clear the draft", key="clear_draft"):
        state["restore"] = None
        state["source"] = ""
        state["host_action"] = {"action": "clearStorage"}
        _mark_change(state)


def _humanise_saved(iso):
    import datetime as dt

    if not iso:
        return None
    try:
        stamp = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    delta = dt.datetime.now(dt.timezone.utc) - stamp
    if delta.total_seconds() < 0 or delta.days < 1:
        return "earlier today"
    if delta.days == 1:
        return "yesterday"
    return stamp.strftime("%d %b %Y %H:%M")


def _link_error_notice(state):
    failure = state.get("link_error")
    if not failure:
        return
    message = failure.get("message") if isinstance(failure, dict) else None
    st.error(message or share.DECODE_MESSAGES["malformed"])
    if st.button("Start a new diagram", key="dismiss_link"):
        state["link_error"] = None
        state["host_action"] = {"action": "clearStorage"}
        state["source"] = ""
        _mark_change(state)


def _storage_notice(state):
    if state.get("storage_state") in ("denied", "unavailable") and state.get("autosave"):
        st.warning("This browser will not keep drafts (private mode, or storage is blocked). Everything else works — download a .mmd file to keep your text.")


def _mismatch_notice(state, selected_type, source):
    if selected_type == templates.BLANK_TYPE_ID or not source.strip():
        return
    detected = templates.detect_diagram_type(source)
    if detected and detected != selected_type:
        st.warning("The chosen starting point is a %s, but this text is a %s. The preview follows the text."
                   % (str(templates.label_for(selected_type)).lower(), str(templates.label_for(detected)).lower()))
        return detected
    return detected


# -------------------------------------------------------------------- editor --
def _editor(state):
    text = st.text_area("Mermaid text", value=state["source"], height=280, max_chars=PASTE_CEILING,
                        placeholder="flowchart TD\n  A[Start] --> B{Decision?}", key="editor")
    if text != state["source"]:
        state["source"] = text
        _mark_change(state)
    if len(text) > MAX_SOURCE_CHARS:
        st.error("This diagram has %d characters, above the %d limit for live preview. Download the .mmd file and split it up."
                 % (len(text), MAX_SOURCE_CHARS))
    else:
        total = max(1, len(text.splitlines()))
        st.caption("Lines 1–%d. When a diagram cannot be drawn, the message names the line it stopped at." % total)


# ------------------------------------------------------------------- preview --
def _resolved(state, diagram_type):
    # Section 7 precedence: what the *diagram text* sets for itself beats the
    # sidebar, and the resolver reports that as sourceOf="frontmatter" so the
    # preview can say "set by your diagram text" instead of silently ignoring it.
    frontmatter = templates.extract_front_matter(state["source"])
    resolved = appearance.resolve(state["knobs"], diagram_type, frontmatter)
    resolved.setdefault("export", {})
    resolved["export"]["scaleName"] = state["knobs"].get("exportScale")
    resolved["export"]["background"] = state["knobs"].get("exportBackground")
    return resolved


def _chrome(state):
    return {
        "autosave": bool(state["autosave"]) and state.get("storage_state") != "denied",
        "name": state["name"],
        "knobs": state["knobs"],
        "selectedTypeId": state["choice"][0],
        "interfaceMode": state["interface_mode"],
        "storage": state.get("storage_state"),
        "host": state.get("host_action") or None,
    }


def _boot_snapshot():
    """``boot.json`` is mounted by index.html: URL fragment + storage + draft.

    Stlite's ``runDir`` is a *virtual* filesystem, so the snapshot is handed over
    as an in-memory file rather than read from disk. The plain ``open`` path is
    kept for the Streamlit CLI and the Single Column Model style runners.
    """
    for path in (os.path.join(ASSET_DIR, "boot.json"), "boot.json"):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            continue
    return {}


def _send_due(state):
    """Contract §1 rule 2: no source send more often than every 320 ms."""
    fingerprint = "%s|%s|%s|%s" % (
        state["source"], json.dumps(state["knobs"], sort_keys=True), state["name"], state["host_action"] and "host")
    unchanged = state["last_sent"] == fingerprint and not state.get("host_action")
    if unchanged:
        return False
    elapsed_ms = (time.monotonic() - state["last_change_at"]) * 1000.0
    if state["pending_send"] and elapsed_ms < render_bridge.DEBOUNCE_MIN_MS:
        time.sleep(min((render_bridge.DEBOUNCE_MIN_MS - elapsed_ms) / 1000.0, 0.6))
    state["last_sent"] = fingerprint
    state["pending_send"] = False
    return True


def _preview(state, diagram_type):
    """Emit the component on *every* rerun, and change its payload only when due.

    Streamlit rebuilds the page each rerun: an element that is not re-created
    simply disappears, and st.components.v1.html is no exception -- the earlier
    "skip the send and keep the iframe" shortcut meant that any rerun which
    changed nothing else (say, the unsaved-text guard) took the whole preview
    with it. So the document is always emitted; the debounced fingerprint decides
    whether the request id and text inside it are new, and an unchanged rerun
    re-issues the identical payload under the request id the component already
    knows (contract section 1 rule 2 is about *sends*, not about element upkeep).
    """
    fingerprint = "%s|%s|%s|%s" % (
        state["source"], json.dumps(state["knobs"], sort_keys=True), state["name"], "host" if state.get("host_action") else "")
    if _send_due(state) or not state.get("payload_json"):
        request = render_bridge.build_render_request_dict(state["source"], _resolved(state, diagram_type), command="render")
        request["requestId"] = state["request_id"] = render_bridge.next_request_id()
        request["chrome"] = _chrome(state)
        state["doc_key"] = preview_asset.document_key(state["source"], json.dumps(state["knobs"], sort_keys=True))
        state["payload_json"] = render_bridge.escape_for_html(messages.render_request_json(request))
    document = preview_asset.component_document(ASSET_DIR, state["payload_json"], doc_key=state["doc_key"])
    st.subheader("Preview")
    components.html(document, height=_estimated_height(state["source"]), scrolling=False)


def _estimated_height(text):
    # A starting point only: index.html re-sizes this iframe to the component's
    # measured height as soon as the component reports one (FR-034).
    lines = max(1, len(str(text or "").splitlines()))
    return int(min(1600, max(460, 170 + lines * 9)))


# ------------------------------------------------------------- share/download --
def _page_url(boot):
    href = boot.get("href")
    return href.split("#", 1)[0] if isinstance(href, str) and href else ""


def _share_panel(state, boot):
    with st.sidebar.expander("Share this diagram", expanded=False):
        encoded = share.encode_document(state["source"], state["knobs"], state["name"], _page_url(boot))
        if encoded.get("tooLarge"):
            st.info("This diagram is %s bytes — above the %s-byte ceiling for a reliable link, so no link was made. Download the .mmd file instead."
                    % (encoded.get("sizeBytes"), share.SHARE_URL_MAX_BYTES))
        else:
            st.text_input("Link (carries the diagram *and* its look)", value=encoded.get("url", ""), key="share_link")
        if st.button("Also put it in the page address", key="host_link", disabled=bool(encoded.get("tooLarge"))):
            state["host_action"] = {"action": "link", "payload": share.fragment_of(encoded.get("url", "")), "copy": True}
        st.caption("The link sits after `#` in the address, which a browser never sends to a server.")


def _download_panel(state):
    filename = messages.sanitize_filename(state["name"], fallback=messages.UNTITLED_NAME) + ".mmd"
    st.sidebar.download_button("Download .mmd source", data=state["source"], file_name=filename, mime="text/plain", key="mmd_download")
    if st.sidebar.button("Start fresh", key="start_fresh"):
        state["source"] = ""
        state["name"] = ""
        state["restore"] = None
        state["link_error"] = None
        state["loaded_example"] = None
        state["host_action"] = {"action": "clearStorage"}
        _mark_change(state)


# ------------------------------------------------------------------------ ui --
def main():
    state = _session()
    boot = _boot_snapshot()
    _apply_boot(state, boot)

    missing = preview_asset.missing_assets(ASSET_DIR)
    if missing:
        st.error("The preview component is missing from the site: %s. Deploy the repository root, including these files."
                 % ", ".join(missing))
        return

    _link_error_notice(state)
    _storage_notice(state)
    _restore_notice(state)

    selected_type = _sidebar_catalog(state)
    _sidebar_appearance(state)
    _sidebar_output(state)
    _share_panel(state, boot)
    _download_panel(state)

    _editor(state)
    detected = _mismatch_notice(state, selected_type, state["source"])
    diagram_type = detected or (selected_type if selected_type != templates.BLANK_TYPE_ID else "flowchart")
    _preview(state, diagram_type)
    state["host_action"] = None


main()
