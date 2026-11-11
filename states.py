"""states.py — the Python side of the render state machine (data-model section 2).

Pure, standard library only. ``RenderStateMachine`` is what ``app.py`` mirrors to
decide notices (type mismatch, stall upgrade, lastGood retention); the component
owns drawing. It exists so the invariants — five hundred valid nodes never reach
``invalid``, ``empty`` never carries an ``error``, a failed parse never clears
the last good render, latest request wins — are checkable without a browser
(T010, SC-002, SC-003, FR-016).
"""

import messages

EMPTY_SOURCE_HINT = "Nothing to render yet"
STALL_UPGRADE_MS = messages.RENDER_STALL_MS


def classify_source(source):
    """``empty`` for blank/whitespace, otherwise the input state for a change."""
    if not isinstance(source, str) or not source.strip():
        return messages.STATE_EMPTY
    return messages.STATE_RENDERING


class RenderStateMachine(object):
    """Four states, auto-clearing errors, last-good retention, staleness."""

    # invariants asserted by tests/test_states.py
    TERMINAL_STATES = messages.TERMINAL_STATES
    STATES = messages.STATES

    def __init__(self):
        self.state = messages.STATE_EMPTY
        self.diagram_type = None
        self.last_error = None
        self.last_good = None          # {"svg": ..., "at": ...} (FR-016)
        self.current_request_id = None
        self.type_mismatch = False
        self.source = ""
        self.notice = EMPTY_SOURCE_HINT

    # ------------------------------------------------------------------
    # source path
    # ------------------------------------------------------------------

    def change_source(self, source, request_id):
        """Any source change (even from ``invalid``) goes through ``rendering``.

        Blank/whitespace source resolves straight to ``empty`` with no error —
        it is never styled as a failure (data-model section 2, US2 scenario 4).
        """
        if not isinstance(source, str):
            raise ValueError("source must be a string")
        self.source = source
        self.current_request_id = request_id
        self.type_mismatch = False
        if len(source) > messages.MAX_PASTE_CHARS:
            # over the ceiling: rejected without attempting the diagram
            self.state = messages.STATE_INVALID
            self.last_error = messages.make_render_error(
                "inputTooLarge",
                "This diagram is longer than the editor can render "
                "(limit %d characters)." % messages.MAX_PASTE_CHARS,
                line=None, column=None, snippet=None)
            self.notice = None
            return self.state
        if classify_source(source) == messages.STATE_EMPTY:
            self.state = messages.STATE_EMPTY
            self.last_error = None      # errors clear automatically (FR-015)
            self.diagram_type = None
            self.notice = EMPTY_SOURCE_HINT
            return self.state
        self.state = messages.STATE_RENDERING
        self.notice = None
        return self.state

    # ------------------------------------------------------------------
    # component status path
    # ------------------------------------------------------------------

    def apply_status(self, status):
        """Feed one RenderStatus; stale ones are ignored, not applied."""
        messages.validate_render_status(status)
        request_id = status["requestId"]
        if self.current_request_id is not None and \
                _sequence_of(request_id) < _sequence_of(self.current_request_id):
            return False          # superseded request never reaches the UI
        if status["state"] == messages.STATE_RENDERING:
            if request_id != self.current_request_id:
                return False
            self.state = messages.STATE_RENDERING
            return True
        if request_id != self.current_request_id:
            return False          # terminal status for a superseded request
        state = status["state"]
        self.diagram_type = status.get("diagramType")
        if state == messages.STATE_RENDERED:
            self.state = messages.STATE_RENDERED
            self.last_error = None      # invalid clears automatically (FR-015)
            self.last_good = {"svg": status.get("svg"),
                              "at": status.get("at")}
            self.notice = None
        elif state == messages.STATE_INVALID:
            self.state = messages.STATE_INVALID
            self.last_error = status["error"]
            self.notice = None
            # last_good deliberately untouched: a failed parse never clears it
        elif state == messages.STATE_EMPTY:
            self.state = messages.STATE_EMPTY
            self.last_error = None
            self.diagram_type = None
            self.notice = EMPTY_SOURCE_HINT
        else:
            raise ValueError("unreachable state %r" % (state,))
        return True

    # ------------------------------------------------------------------
    # derived UI facts
    # ------------------------------------------------------------------

    def stalled(self, elapsed_ms):
        """"This is slow, still working" upgrade (US2 scenario 5)."""
        return self.state == messages.STATE_RENDERING and elapsed_ms > STALL_UPGRADE_MS

    def error_visible(self):
        return self.state == messages.STATE_INVALID and self.last_error is not None

    def type_mismatch_notice(self, selected_type_id):
        """Selected catalog type vs the parser's type: surfaced, never silent.

        Returns the parsed type name when the two differ (so the UI can name
        what it actually found), otherwise ``None``.
        """
        parsed = self.diagram_type
        mismatch = (self.state in (messages.STATE_RENDERED, messages.STATE_INVALID)
                    and selected_type_id is not None and parsed is not None
                    and selected_type_id != parsed)
        self.type_mismatch = mismatch
        return parsed if mismatch else None

    def snapshot(self):
        return {
            "state": self.state,
            "diagramType": self.diagram_type,
            "lastError": self.last_error,
            "hasLastGood": self.last_good is not None,
            "currentRequestId": self.current_request_id,
            "notice": self.notice,
            "typeMismatch": self.type_mismatch,
            "stalled": False,
        }


def _sequence_of(request_id):
    """Integer tail of a ``req-00042`` style id (unparseable sorts last)."""
    digits = "".join(ch for ch in str(request_id) if ch.isdigit())
    return int(digits) if digits else -1
