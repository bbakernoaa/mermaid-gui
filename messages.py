"""messages.py — the two bridge payload shapes, defined in one place.

Contracts: specs/001-editor-experience-upgrades/contracts/render-bridge-contract.md
(sections 1-4) and data-model.md sections 2-3. Standard library only, no
Streamlit, so pytest can validate the shapes with no browser. ``app.py`` and
``render_component.js`` both build/read exactly these shapes (T008/T009).
"""

import copy
import json

# ---------------------------------------------------------------------------
# Schema / identity
# ---------------------------------------------------------------------------

BRIDGE_SCHEMA_VERSION = 1
REQUEST_ID_TOKEN_BYTES = 16
FILENAME_MAX_CHARS = 120
SNIPPET_MAX_CHARS = 120
UNTITLED_NAME = "untitled"

# ---------------------------------------------------------------------------
# RenderStatus.state — the exact single state machine of data-model section 2.
# Four states and only four: the enum here is its authoritative Python copy.
# ---------------------------------------------------------------------------

STATE_EMPTY = "empty"
STATE_RENDERING = "rendering"
STATE_RENDERED = "rendered"
STATE_INVALID = "invalid"
STATES = (STATE_RENDERING, STATE_RENDERED, STATE_INVALID, STATE_EMPTY)
# Authoritative enum alias for callers that spell it the contract way.
STATE_ENUM = STATES
TERMINAL_STATES = (STATE_RENDERED, STATE_INVALID, STATE_EMPTY)
NON_TERMINAL_STATES = (STATE_RENDERING,)

# ---------------------------------------------------------------------------
# RenderRequest commands (contract section 1)
# ---------------------------------------------------------------------------

COMMANDS = ("render", "exportSvg", "exportPng", "copySvg", "zoomIn", "zoomOut",
            "fit")

# ---------------------------------------------------------------------------
# Error kinds crossing the bridge as values, never thrown (contract section 4)
# ---------------------------------------------------------------------------

ERROR_KINDS = ("parseError", "renderError", "unsupportedType", "inputTooLarge",
               "bridgeVersion")

# ---------------------------------------------------------------------------
# Frozen defaults every request carries (appearance contract section 6)
# ---------------------------------------------------------------------------

FROZEN_DEFAULTS = {
    "htmlLabels": False,
    "useHtmlLabels": False,
    "suppressErrorRendering": True,
    "securityLevel": "strict",
    "startOnLoad": False,
}

# data-model section 1: input ceiling and render stall budget
MAX_PASTE_CHARS = 50000
RENDER_STALL_MS = 8000
PARSE_DEBOUNCE_MS = 300

# appearance contract section 1/2: a ResolvedAppearance always has these three
# parts; the frozen pair is what the component must merge before initialize.
# Mermaid's own input ceilings, raised to the same values as
# ``appearance.RENDER_LIMITS`` (maxEdges 500 / maxTextSize 50 000 by default
# would reject the largest diagrams this app handles). They are secure settings:
# read only from the initialize object, never from diagram text. Tested against
# appearance.RENDER_LIMITS in tests/test_bridge_shapes.py so they cannot drift.
RENDER_LIMITS_DEFAULT = {"maxEdges": 5000, "maxTextSize": 200000}

# The size a label is drawn at when nothing decided one. Mermaid's own default
# is 16 px, and `themeVariables.fontSize` -- a string with the unit -- is the
# only spelling that reaches a flowchart label in 11.12 (the numeric top-level
# `fontSize` becomes a derived base instead), so the stand-in carries that key
# explicitly: every initialize path sets the operative key. Mirrors
# `appearance.TEXT_SIZE_PX["medium"]`; tested against it so it cannot drift.
DEFAULT_THEME_VARIABLES = {"fontSize": "16px"}

RESOLVED_APPEARANCE_DEFAULT = {
    "mermaidTheme": "neo",
    "themeVariables": dict(DEFAULT_THEME_VARIABLES),
    "perDiagramConfig": {},
    "export": {},
    "rasterScale": 3,
    "rasterBackground": "white",
    "maxEdges": RENDER_LIMITS_DEFAULT["maxEdges"],
    "maxTextSize": RENDER_LIMITS_DEFAULT["maxTextSize"],
}


def default_appearance():
    """A safe ResolvedAppearance stand-in, with the frozen defaults attached."""
    out = copy.deepcopy(RESOLVED_APPEARANCE_DEFAULT)
    out["frozen"] = copy.deepcopy(FROZEN_DEFAULTS)
    return out


# ---------------------------------------------------------------------------
# RenderRequest
# ---------------------------------------------------------------------------

def make_render_request(request_id, source, appearance, command="render",
                        schema_version=BRIDGE_SCHEMA_VERSION):
    """RenderRequest dict inbound to the component (contract section 1).

    ``source`` arrives already HTML-escaped by the caller (commit 02ae868's
    fix); this helper does not re-escape or otherwise alter it.
    """
    return {
        "schemaVersion": schema_version,
        "requestId": request_id,
        "source": source,
        "appearance": copy.deepcopy(appearance) if appearance
        else default_appearance(),
        "command": command,
    }


def render_request_json(request):
    """The exact JSON string injected into the component template."""
    return json.dumps(request, separators=(",", ":"), sort_keys=False)


# ---------------------------------------------------------------------------
# RenderStatus
# ---------------------------------------------------------------------------

def make_render_error(kind, plain_message, raw_message=None, line=None,
                      column=None, snippet=None):
    """RenderError dict (data-model section 3): kinds, plain words, position."""
    if kind not in ERROR_KINDS:
        raise ValueError("unknown error kind %r" % (kind,))
    if not plain_message:
        raise ValueError("plainMessage is required (FR-014)")
    error = {
        "kind": kind,
        "plainMessage": plain_message,
        "rawMessage": raw_message if raw_message is not None else plain_message,
        "line": line,
        "column": column,
        "snippet": snippet[:SNIPPET_MAX_CHARS] if isinstance(snippet, str)
        else snippet,
    }
    return error


def make_render_status(request_id, state, diagram_type=None, error=None,
                       metrics=None, clamped=None):
    """RenderStatus dict outbound from the component (contract section 2)."""
    if state not in STATES:
        raise ValueError("unknown state %r" % (state,))
    status = {
        "requestId": request_id,
        "state": state,
        "diagramType": diagram_type,
    }
    if error is not None:
        status["error"] = error
    if metrics is not None:
        status["metrics"] = metrics
    if clamped is not None:
        status["clamped"] = list(clamped)
    return status


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_render_status(payload):
    """Check a RenderStatus against the contract; raise ValueError if invalid.

    Accepts a dict. Rejects: unknown/missing ``state``, missing ``requestId``,
    ``invalid`` without ``error`` (invariant: error present iff invalid),
    ``rendered`` carrying ``error``, ``empty`` carrying ``error`` (invariant 4),
    and ``rendered`` without ``metrics``.
    """
    if not isinstance(payload, dict):
        raise ValueError("RenderStatus must be an object")
    state = payload.get("state")
    if state not in STATES:
        raise ValueError("unknown state %r (allowed: %s)"
                         % (state, ", ".join(STATES)))
    request_id = payload.get("requestId")
    if not isinstance(request_id, str) or not request_id:
        raise ValueError("requestId is required and must be a non-empty string")
    if state == STATE_INVALID and payload.get("error") is None:
        raise ValueError("state invalid requires an error")
    if state != STATE_INVALID and payload.get("error") is not None:
        raise ValueError("error is present iff state is invalid (got %s)" % state)
    if state == STATE_RENDERED and payload.get("metrics") is None:
        raise ValueError("metrics is required for rendered")
    return normalize_render_status(payload)


def normalize_render_status(payload):
    """The status with the contract's optional keys present only when supplied."""
    status = {
        "requestId": payload["requestId"],
        "state": payload["state"],
        "diagramType": payload.get("diagramType"),
    }
    if payload.get("error") is not None:
        status["error"] = payload["error"]
    if payload.get("metrics") is not None:
        status["metrics"] = payload["metrics"]
    if payload.get("clamped") is not None:
        status["clamped"] = list(payload["clamped"])
    return status


# ---------------------------------------------------------------------------
# Filename sanitiser (data-model section 1 / FR-031) — shared by both download
# paths: Streamlit's .mmd button and the component's exports.
# ---------------------------------------------------------------------------

_CONTROL_CHARS = "".join(chr(code) for code in range(32)) + chr(127)
_ILLEGAL_FILENAME_CHARS = '<>:"/\\|?*'
_STRIP_CHARS = _CONTROL_CHARS + _ILLEGAL_FILENAME_CHARS


def sanitize_filename(name, fallback=UNTITLED_NAME, max_length=FILENAME_MAX_CHARS):
    """Strip path separators, control chars and illegal download-name characters.

    Collapses repeated dots, trims surrounding whitespace/dots, preserves
    non-ASCII (emojis and non-Latin labels stay), and falls back to ``untitled``
    when nothing usable remains.
    """
    if not isinstance(name, str):
        return fallback
    cleaned = "".join(ch for ch in name if ch not in _STRIP_CHARS)
    # collapse runs of dots (including "..") down to one
    while ".." in cleaned:
        cleaned = cleaned.replace("..", ".")
    cleaned = " ".join(cleaned.split())
    cleaned = cleaned.strip(" .")
    if not cleaned:
        return fallback
    return cleaned[:max_length]


def export_filename(name, extension):
    """``sanitize(name or 'untitled') + '.' + ext`` (data-model section 9)."""
    ext = extension.lstrip(".")
    return "%s.%s" % (sanitize_filename(name), ext)
