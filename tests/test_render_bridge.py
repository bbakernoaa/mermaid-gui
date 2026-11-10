"""Render-bridge contract tests (sections 1-3), pure Python, no browser.

The clock is injected so the timing rules are asserted exactly rather than by
sleeping in a real test run.
"""

import json

import pytest

import messages
import render_bridge
from render_bridge import RenderBridge

SOURCE = "flowchart TD\n  A-->B"


class FakeClock(object):
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance_ms(self, milliseconds):
        self.now += milliseconds / 1000.0


def make_bridge(**kwargs):
    clock = FakeClock()
    bridge = RenderBridge(clock=clock, **kwargs)
    return bridge, clock


# ---------------------------------------------------------------------------
# requestId rules (section 1)
# ---------------------------------------------------------------------------

def test_request_ids_are_strictly_increasing_and_zero_padded():
    bridge, _clock = make_bridge()
    ids = [bridge.next_request_id() for _ in range(200)]
    assert ids == ["req-%05d" % i for i in range(1, 201)]
    assert all(later > earlier for earlier, later in zip(ids, ids[1:]))
    assert render_bridge.REQUEST_ID_FORMAT == "req-%05d"


def test_each_built_request_carries_a_fresh_increasing_id():
    bridge, _clock = make_bridge()
    first = bridge.build_request(SOURCE, messages.default_appearance())
    second = bridge.build_request(SOURCE, messages.default_appearance())
    assert first["requestId"] == "req-00001"
    assert second["requestId"] == "req-00002"
    assert bridge.newest_request_id == "req-00002"
    assert bridge.request_sequence("req-00042") == 42


def test_explicit_request_id_is_respected_when_supplied():
    bridge, _clock = make_bridge()
    request = bridge.build_render_request(SOURCE, messages.default_appearance(),
                                          request_id="req-00099")
    assert request["requestId"] == "req-00099"
    assert bridge.newest_request_id is None    # not issued by the bridge itself


# ---------------------------------------------------------------------------
# payload shape (section 1)
# ---------------------------------------------------------------------------

def test_payload_has_exactly_the_contract_keys():
    bridge, _clock = make_bridge()
    request = bridge.build_render_request(SOURCE, messages.default_appearance())
    assert sorted(request) == sorted(
        ["schemaVersion", "requestId", "source", "appearance", "command",
         "captureUnavailable"])
    assert request["schemaVersion"] == messages.BRIDGE_SCHEMA_VERSION == 1
    assert list(request["appearance"]) and "mermaidTheme" in request["appearance"]
    assert "frozen" in request["appearance"]
    assert request["command"] == "render"
    assert request["source"] == SOURCE      # unchanged, escapes are the caller's job


@pytest.mark.parametrize("command", messages.COMMANDS)
def test_every_documented_command_is_accepted(command):
    bridge, _clock = make_bridge()
    request = bridge.build_render_request(SOURCE, messages.default_appearance(),
                                          command=command)
    assert request["command"] == command
    assert set(messages.COMMANDS) == {"render", "exportSvg", "exportPng",
                                     "copySvg", "zoomIn", "zoomOut", "fit"}


def test_unknown_command_is_refused():
    bridge, _clock = make_bridge()
    with pytest.raises(ValueError):
        bridge.build_render_request(SOURCE, messages.default_appearance(),
                                    command="teleport")


def test_injected_string_is_json_and_html_inert():
    bridge, _clock = make_bridge()
    payload = bridge.build_render_request_json(
        "flowchart TD\n  A-->B\n  %% <script>alert(1)</script>",
        messages.default_appearance())
    assert "<" not in payload and ">" not in payload
    assert "\\u003c" in payload
    decoded = json.loads(payload.replace("\\u003c", "<").replace("\\u003e", ">")
                         .replace("\\u0026", "&"))
    assert decoded["source"].startswith("flowchart TD")
    assert decoded["requestId"] == "req-00001"


def test_template_token_is_replaced_by_the_payload():
    bridge, _clock = make_bridge()
    request = bridge.build_render_request(SOURCE, messages.default_appearance())
    html = bridge.render_template_html(
        request, template="<script>var req = %s;</script>"
        % render_bridge.DEFAULT_COMPONENT_TEMPLATE)
    assert render_bridge.DEFAULT_COMPONENT_TEMPLATE not in html
    assert '"requestId": "req-00001"' in html or '"requestId":"req-00001"' in html


# ---------------------------------------------------------------------------
# debounce (section 1 rule 2): >= 320 ms after the last keystroke
# ---------------------------------------------------------------------------

def test_debounce_constant_is_at_least_320_milliseconds():
    assert render_bridge.DEBOUNCE_MIN_MS == 320
    assert render_bridge.DEBOUNCE_MIN_SECONDS == 0.32
    # bridge send waits are 320 ms: the 300 ms parse debounce plus headroom
    assert messages.PARSE_DEBOUNCE_MS == 300
    assert render_bridge.DEBOUNCE_MIN_MS > messages.PARSE_DEBOUNCE_MS
    with pytest.raises(ValueError):
        RenderBridge(debounce_ms=319)


def test_changes_inside_the_window_coalesce_into_one_request():
    bridge, clock = make_bridge()
    assert bridge.note_change("flowchart TD\n  A", {}) is None
    for character in "BCDE":
        clock.advance_ms(40)                # keystrokes every 40 ms
        assert bridge.note_change("flowchart TD\n  A" + character, {}) is None
    assert bridge.pending() is True
    assert bridge.time_until_due_ms() > 0
    assert bridge.flush() is None           # too early: nothing may be sent
    clock.advance_ms(320)
    request = bridge.flush()
    assert request is not None
    assert request["source"] == "flowchart TD\n  AE"   # newest text wins
    assert request["requestId"] == "req-00001"         # exactly one send
    assert bridge.flush() is None                      # nothing pending anymore
    assert bridge.pending() is False


def test_first_change_after_idle_is_sent_at_the_trailing_edge():
    bridge, clock = make_bridge()
    bridge.note_change(SOURCE, {})
    clock.advance_ms(319)
    assert bridge.flush() is None
    clock.advance_ms(1)
    assert bridge.flush()["requestId"] == "req-00001"


def test_appearance_only_change_ships_the_same_source():
    """Section 1 rule 2 as data: appearance rides as its own render request."""
    bridge, clock = make_bridge()
    bridge.note_change(SOURCE, {"mermaidTheme": "neo"})
    clock.advance_ms(320)
    source_request = bridge.flush()
    appearance = {"mermaidTheme": "dark", "themeVariables": {}}
    follow_up = bridge.appearance_change_request(appearance)
    assert follow_up["command"] == "render"
    assert follow_up["source"] == source_request["source"]
    assert follow_up["appearance"] == appearance
    assert int(follow_up["requestId"][4:]) > int(source_request["requestId"][4:])


def test_shared_bridge_helpers_drive_the_default_bridge():
    bridge = RenderBridge(clock=FakeClock())
    render_bridge._DEFAULT_BRIDGE = bridge
    try:
        first = render_bridge.next_request_id()
        payload = render_bridge.build_render_request(SOURCE,
                                                     messages.default_appearance())
        assert isinstance(payload, str)
        assert first == "req-00001"
        assert json.loads(payload)["requestId"] == "req-00002"
        assert render_bridge.next_request_id() == "req-00003"
    finally:
        render_bridge._DEFAULT_BRIDGE = None


# ---------------------------------------------------------------------------
# status handling (section 2)
# ---------------------------------------------------------------------------

def valid_status(request_id="req-00001", state="rendered", **extra):
    payload = {"requestId": request_id, "state": state,
               "diagramType": "flowchart", "metrics": {"durationMs": 12}}
    payload.update(extra)
    if state == "invalid":
        payload["error"] = messages.make_render_error("parseError", "boom", line=2)
    return payload


def test_handle_status_accepts_a_dict_or_a_json_string():
    bridge, _clock = make_bridge()
    applied, status = bridge.handle_status(valid_status())
    assert applied is True and status["state"] == "rendered"
    applied, status = bridge.handle_status(json.dumps(
        valid_status("req-00002", "empty")))
    assert applied is True and status["requestId"] == "req-00002"


def test_handle_status_accepts_bytes_from_the_bridge():
    bridge, _clock = make_bridge()
    applied, status = bridge.handle_status(
        json.dumps(valid_status()).encode("utf-8"))
    assert applied is True


@pytest.mark.parametrize("raw", ["", "not json", "{", "[]", "null", "5",
                                 {"state": "rendered"},
                                 {"requestId": "req-1", "state": "done"},
                                 {"requestId": "req-1", "state": "invalid"},
                                 {"requestId": "req-1", "state": "rendered",
                                  "error": {"kind": "parseError"}}])
def test_invalid_payloads_raise_value_error(raw):
    bridge, _clock = make_bridge()
    with pytest.raises(ValueError):
        bridge.handle_status(raw)


def test_out_of_order_status_is_ignored():
    bridge, _clock = make_bridge()
    bridge.next_request_id()                     # req-00001
    bridge.next_request_id()                     # req-00002
    applied, _status = bridge.handle_status(valid_status("req-00001"))
    assert applied is False                      # superseded => never reaches UI
    applied, _status = bridge.handle_status(valid_status("req-00002"))
    assert applied is True
    assert bridge.newest_request_id == "req-00002"


def test_only_one_terminal_status_per_request_id():
    bridge, _clock = make_bridge()
    request_id = bridge.next_request_id()
    first, _s = bridge.handle_status(valid_status(request_id, "rendered"))
    second, _s = bridge.handle_status(valid_status(request_id, "invalid"))
    assert first is True
    assert second is False


def test_rendering_state_is_not_terminal_and_may_repeat():
    bridge, _clock = make_bridge()
    request_id = bridge.next_request_id()
    for _ in range(3):
        applied, _status = bridge.handle_status(valid_status(request_id,
                                                             "rendering"))
        assert applied is True
    applied, _status = bridge.handle_status(valid_status(request_id, "rendered"))
    assert applied is True
    applied, _status = bridge.handle_status(valid_status(request_id, "rendered"))
    assert applied is False


def test_module_level_handle_status_returns_none_for_stale():
    bridge = RenderBridge(clock=FakeClock())
    render_bridge._DEFAULT_BRIDGE = bridge
    try:
        newest = render_bridge.next_request_id()
        render_bridge.next_request_id()
        assert render_bridge.handle_status(valid_status(newest)) is None
        applied = render_bridge.handle_status(
            valid_status("req-00002", "rendered"))
        assert applied["state"] == "rendered"
        with pytest.raises(ValueError):
            render_bridge.handle_status({"state": "rendered"})
    finally:
        render_bridge._DEFAULT_BRIDGE = None


# ---------------------------------------------------------------------------
# capture-unavailable flag (clipboard fallback, FR-033)
# ---------------------------------------------------------------------------

def test_capture_unavailable_defaults_to_true_and_can_be_overridden():
    assert render_bridge.PARSE_CAPTURE_UNAVAILABLE_DEFAULT is True
    assert render_bridge.parse_capture_unavailable(None) is True
    assert render_bridge.parse_capture_unavailable("") is True
    assert render_bridge.parse_capture_unavailable(False) is False
    assert render_bridge.parse_capture_unavailable("false") is False
    assert render_bridge.parse_capture_unavailable("0") is False
    assert render_bridge.parse_capture_unavailable("no") is False
    assert render_bridge.parse_capture_unavailable(True) is True
    assert render_bridge.parse_capture_unavailable("true") is True
    assert render_bridge.parse_capture_unavailable("1") is True
    assert render_bridge.parse_capture_unavailable("nonsense") is True
    assert render_bridge.parse_capture_unavailable(0) is False
    assert render_bridge.parse_capture_unavailable(1) is True


def test_setter_lands_in_the_injected_payload():
    bridge = RenderBridge(clock=FakeClock())
    render_bridge._DEFAULT_BRIDGE = bridge
    try:
        assert render_bridge.get_capture_unavailable() is True
        payload = json.loads(render_bridge.build_render_request(
            SOURCE, messages.default_appearance()))
        assert payload["captureUnavailable"] is True
        assert render_bridge.set_capture_unavailable(False) is False
        payload = json.loads(render_bridge.build_render_request(
            SOURCE, messages.default_appearance()))
        assert payload["captureUnavailable"] is False
    finally:
        render_bridge._DEFAULT_BRIDGE = None


def test_escape_helper_is_what_the_component_template_needs():
    escaped = render_bridge.escape_for_html('{"s": "<b>&amp</b>"}')
    assert "<" not in escaped and ">" not in escaped and "&" not in escaped
    assert "\\u003c" in escaped and "\\u003e" in escaped and "\\u0026" in escaped
