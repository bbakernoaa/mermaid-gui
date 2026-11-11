"""render_bridge.py — app-side half of the Python <> render component bridge.

Contract: specs/001-editor-experience-upgrades/contracts/render-bridge-contract.md
sections 1-3 (app/inbound direction, requestId rules, debounce, staleness).
Import-light and app-independent: it never touches Streamlit, so
``python3 -m pytest tests/ -q`` exercises the timing and identity rules for
real. ``app.py`` (owned by another agent) wires these calls to its widgets.
"""

import json
import time

import messages

# ---------------------------------------------------------------------------
# Contract constants
# ---------------------------------------------------------------------------

DEBOUNCE_MIN_MS = 320          # >= 320 ms after the last keystroke (section 1)
DEBOUNCE_MIN_SECONDS = DEBOUNCE_MIN_MS / 1000.0
REQUEST_ID_FORMAT = "req-%05d"  # section 1's example shape: req-00042
SCHEMA_VERSION = messages.BRIDGE_SCHEMA_VERSION
DEFAULT_COMPONENT_TEMPLATE = "MERMAID_BRIDGE_PAYLOAD_JSON"
# captureUnavailable: browser capture APIs (clipboard/download) may be absent or
# refused; the component must know, and default to assuming they are not usable.
PARSE_CAPTURE_UNAVAILABLE_DEFAULT = True


def parse_capture_unavailable(value, default=PARSE_CAPTURE_UNAVAILABLE_DEFAULT):
    """Coerce app.py's value into the boolean the component receives.

    Truthy in, boolean out; anything unrecognisable falls back to the default
    (``True``), which is the safe assumption — the component then shows the
    download fallback instead of silently failing a clipboard write.
    """
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("1", "true", "yes", "on"):
            return True
        if text in ("0", "false", "no", "off"):
            return False
        return bool(default)
    return bool(value)


def escape_for_html(raw_json):
    """Keep the payload inert inside an inline <script> block (commit 02ae868's
    bug class): ``<`` and ``>`` never appear raw in the injected document."""
    return (raw_json.replace("&", "\\u0026")
            .replace("<", "\\u003c")
            .replace(">", "\\u003e"))


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------

class RenderBridge(object):
    """Instance API; the module-level helpers below wrap a shared default."""
    """Strictly increasing request ids, debounced sends, stale-status dropping."""

    def __init__(self, debounce_ms=DEBOUNCE_MIN_MS, clock=None,
                 capture_unavailable=PARSE_CAPTURE_UNAVAILABLE_DEFAULT,
                 template_token=DEFAULT_COMPONENT_TEMPLATE):
        if debounce_ms < DEBOUNCE_MIN_MS:
            raise ValueError("debounce must be >= %d ms per contract section 1"
                             % DEBOUNCE_MIN_MS)
        self.debounce_ms = debounce_ms
        self._clock = clock or time.monotonic
        self.capture_unavailable = parse_capture_unavailable(capture_unavailable)
        self.template_token = template_token
        self._counter = 0
        self._last_source = None
        self._last_appearance_json = None
        self._pending = None            # (kind, payload) newest change wins
        self._last_change_ms = None
        self._newest_issued = None      # newest request id issued
        self._terminal_seen = set()     # at most one terminal per requestId

    # ---- identity -------------------------------------------------------

    def next_request_id(self):
        """Monotonically issued ``req-000NN`` id (contract section 1)."""
        self._counter += 1
        request_id = REQUEST_ID_FORMAT % self._counter
        self._newest_issued = request_id
        return request_id

    @property
    def newest_request_id(self):
        return self._newest_issued

    @staticmethod
    def request_sequence(request_id):
        digits = "".join(ch for ch in str(request_id) if ch.isdigit())
        return int(digits) if digits else -1

    # ---- debouncing -----------------------------------------------------

    def note_change(self, source, appearance):
        """Call on every keystroke/appearance change; sends are debounced.

        Returns the payload dict when a request is due now (first change after
        an idle gap), else ``None``; ``flush()`` covers the trailing edge.
        """
        now_s = self._clock()
        source_json = json.dumps(source)
        appearance_json = json.dumps(appearance, sort_keys=True)
        appearance_only = (self._last_source == source_json
                           and self._last_appearance_json != appearance_json)
        self._last_source = source_json
        self._last_appearance_json = appearance_json
        self._pending = {"kind": "appearance" if appearance_only else "source"}
        self._last_change_ms = now_s
        if self._counter == 0:
            return self.flush()
        return None

    def pending(self):
        return self._pending is not None

    def time_until_due_ms(self):
        """Whole remaining wait; float noise at the boundary counts as due."""
        if self._pending is None or self._last_change_ms is None:
            return 0
        elapsed_ms = (self._clock() - self._last_change_ms) * 1000.0
        remaining = self.debounce_ms - elapsed_ms
        if remaining < 1e-6:
            return 0
        return remaining

    def flush(self):
        """Issue the debounced request when the interval has fully elapsed."""
        if self._pending is None:
            return None
        if self.time_until_due_ms() > 0:
            return None
        self._pending = None
        return self.build_request()

    # ---- request building ----------------------------------------------

    def build_request(self, source=None, appearance=None, command="render",
                      request_id=None):
        """RenderRequest dict with a fresh strictly increasing id (section 1)."""
        if command not in messages.COMMANDS:
            raise ValueError("unknown command %r" % (command,))
        if source is None:
            source = json.loads(self._last_source) if self._last_source else ""
        resolved = appearance
        return messages.make_render_request(
            request_id or self.next_request_id(),
            source,
            resolved,
            command=command,
            schema_version=SCHEMA_VERSION,
        )

    def build_render_request(self, source, appearance, command="render",
                             request_id=None, schema_version=SCHEMA_VERSION):
        """The exact payload to inject into the component template."""
        if command not in messages.COMMANDS:
            raise ValueError("unknown command %r" % (command,))
        request = messages.make_render_request(
            request_id or self.next_request_id(),
            source,
            appearance,
            command=command,
            schema_version=schema_version,
        )
        request["captureUnavailable"] = self.capture_unavailable
        return request

    def component_script(self, request):
        """Serialise a RenderRequest for the component's HTML template."""
        return escape_for_html(messages.render_request_json(request))

    def build_render_request_json(self, source, appearance, command="render",
                                   request_id=None,
                                   schema_version=SCHEMA_VERSION):
        """Same payload, serialised (the string app.py injects)."""
        return self.component_script(
            self.build_render_request(source, appearance, command, request_id,
                                      schema_version))

    def render_template_html(self, request, template=None):
        """Replace the template token with the payload JSON (app integration)."""
        text = template if template is not None else self.template_token
        return text.replace(self.template_token, self.component_script(request))

    def appearance_change_request(self, appearance, request_id=None):
        """Appearance-only change ships as its own render request (section 1
        rule 2) with the same source."""
        source = json.loads(self._last_source) if self._last_source else ""
        return self.build_render_request(source, appearance, request_id=request_id)

    # ---- status handling -----------------------------------------------

    def handle_status(self, raw):
        """Parse/validate one RenderStatus message and apply the staleness rule.

        Accepts a dict or a JSON string; raises ValueError on any invalid
        payload (contract section 2's invariants enforced in Python). Returns
        ``(applied, status)``: ``applied`` is False when the status is stale
        (older requestId than the newest issued) or a duplicate terminal.
        """
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        if isinstance(raw, str):
            try:
                payload = json.loads(raw)
            except ValueError as failure:
                raise ValueError("RenderStatus is not valid JSON") from failure
        else:
            payload = raw
        messages.validate_render_status(payload)
        request_id = payload["requestId"]
        sequence = self.request_sequence(request_id)
        newest = (self.request_sequence(self._newest_issued)
                  if self._newest_issued is not None else None)
        if newest is not None and sequence < newest:
            return False, payload          # superseded: never reaches the UI
        if payload["state"] in messages.TERMINAL_STATES:
            if request_id in self._terminal_seen:
                return False, payload      # one terminal status per requestId
            self._terminal_seen.add(request_id)
        return True, payload


# ---------------------------------------------------------------------------
# Module-level API used by app.py (single shared bridge per page session)
# ---------------------------------------------------------------------------

_DEFAULT_BRIDGE = None


def default_bridge():
    """The shared RenderBridge the app's calls go through."""
    global _DEFAULT_BRIDGE
    if _DEFAULT_BRIDGE is None:
        _DEFAULT_BRIDGE = RenderBridge()
    return _DEFAULT_BRIDGE


def set_capture_unavailable(value):
    """Clearly named setter: app.py passes its capture-availability value here."""
    _DEFAULT_BRIDGE = default_bridge()
    _DEFAULT_BRIDGE.capture_unavailable = parse_capture_unavailable(value)
    return _DEFAULT_BRIDGE.capture_unavailable


def get_capture_unavailable():
    return default_bridge().capture_unavailable


def next_request_id():
    """Strictly increasing request id for the shared bridge."""
    return default_bridge().next_request_id()


def build_render_request(source, appearance, command="render", request_id=None,
                         schema_version=SCHEMA_VERSION):
    """The exact JSON payload string to inject into the component template."""
    return default_bridge().build_render_request_json(
        source, appearance, command, request_id, schema_version)


def build_render_request_dict(source, appearance, command="render",
                              request_id=None, schema_version=SCHEMA_VERSION):
    """The same payload as a dict (for tests and session_state bookkeeping)."""
    return default_bridge().build_render_request(
        source, appearance, command, request_id, schema_version)


def note_change(source, appearance):
    """Feed one keystroke/appearance change; None until the debounce elapses."""
    return default_bridge().note_change(source, appearance)


def flush_render_request():
    """Issue the debounced request when at least 320 ms have elapsed."""
    return default_bridge().flush()


def time_until_due_ms():
    return default_bridge().time_until_due_ms()


def handle_status(raw):
    """Status message (dict or JSON string) -> normalized dict, or None if stale.

    Raises ValueError on an invalid payload; stale or duplicate-terminal
    statuses are ignored (contract section 2 invariant 3) and return None.
    """
    applied, status = default_bridge().handle_status(raw)
    return status if applied else None
