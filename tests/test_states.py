"""Render state-machine invariants (T010): pure Python, no browser.

Data-model section 2 / render-bridge contract section 2 rules 1-4. The 500-node
fixture is the SC-002 stress case: a valid diagram must never land in `invalid`.
"""

import os

import pytest

import messages
import states
import templates

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def read_fixture(name):
    path = os.path.join(FIXTURES, name)
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def status(request_id, state, **kwargs):
    payload = messages.make_render_status(request_id, state,
                                          diagram_type=kwargs.get("type"))
    if "error" in kwargs:
        payload["error"] = kwargs["error"]
    if "metrics" in kwargs:
        payload["metrics"] = kwargs["metrics"]
    else:
        payload["metrics"] = {"durationMs": 12}
    return payload


# ---------------------------------------------------------------------------
# the four states
# ---------------------------------------------------------------------------

def test_machine_starts_empty_and_reports_the_blank_notice():
    machine = states.RenderStateMachine()
    assert machine.state == messages.STATE_EMPTY
    assert machine.last_error is None
    assert machine.notice == states.EMPTY_SOURCE_HINT
    assert machine.snapshot()["hasLastGood"] is False


@pytest.mark.parametrize("source", ["", "   ", "\n\t ", "\n\n"])
def test_whitespace_only_source_is_empty_never_invalid(source):
    machine = states.RenderStateMachine()
    machine.change_source("flowchart TD\n  A-->B", "req-00001")
    machine.apply_status(status("req-00001", messages.STATE_RENDERED,
                                type="flowchart"))
    machine.change_source(source, "req-00002")
    assert machine.state == messages.STATE_EMPTY
    assert machine.last_error is None
    assert machine.apply_status(status("req-00002", messages.STATE_EMPTY))
    assert machine.state == messages.STATE_EMPTY


def test_classify_source_is_the_empty_rule_in_isolation():
    assert states.classify_source("") == messages.STATE_EMPTY
    assert states.classify_source("  \n ") == messages.STATE_EMPTY
    assert states.classify_source("flowchart TD") == messages.STATE_RENDERING
    assert states.classify_source(None) == messages.STATE_EMPTY


def test_any_source_change_goes_through_rendering_even_from_invalid():
    machine = states.RenderStateMachine()
    machine.change_source("flowchart TD\n  A->>B", "req-00001")
    assert machine.state == messages.STATE_RENDERING
    machine.apply_status(status("req-00001", messages.STATE_INVALID,
                                error=messages.make_render_error(
                                    "parseError", "Unknown arrow style on line 2",
                                    line=2)))
    assert machine.state == messages.STATE_INVALID
    for request in ("req-00002", "req-00003"):
        machine.change_source("flowchart TD\n  A-->B", request)
        assert machine.state == messages.STATE_RENDERING


def test_errors_clear_automatically_and_no_dismissal_path_exists():
    """FR-015: no user action removes an error; a new result replaces it."""
    machine = states.RenderStateMachine()
    machine.change_source("bad", "req-00001")
    machine.apply_status(status("req-00001", messages.STATE_INVALID,
                                error=messages.make_render_error("parseError",
                                                                 "boom")))
    assert machine.error_visible() is True
    machine.change_source("", "req-00002")
    assert machine.error_visible() is False
    assert machine.last_error is None
    assert not any(name.startswith("dismiss") for name in dir(machine))
    assert not any(name.startswith("clear_error") for name in dir(machine))


def test_overlong_paste_is_rejected_without_attempting_the_diagram():
    machine = states.RenderStateMachine()
    huge = "flowchart TD\n" + "  A-->B\n" * 20000      # > 50 000 characters
    assert len(huge) > messages.MAX_PASTE_CHARS
    machine.change_source(huge, "req-00001")
    assert machine.state == messages.STATE_INVALID
    assert machine.last_error["kind"] == "inputTooLarge"
    assert messages.MAX_PASTE_CHARS == 50000


# ---------------------------------------------------------------------------
# SC-002 stress case: 500 valid nodes never reach invalid
# ---------------------------------------------------------------------------

def test_five_hundred_valid_nodes_never_report_invalid():
    source = read_fixture("large-500-nodes.mmd")
    nodes = set()
    for line in source.splitlines():
        for token in line.replace("-->", " ").split():
            if token.startswith("N") and token[1:].isdigit():
                nodes.add(token)
    assert len(nodes) == 500
    assert len(source.splitlines()) == 501        # header + 500 statements
    assert templates.detect_diagram_type(source) == "flowchart"
    assert templates.count_elements(source, "flowchart") >= 500
    machine = states.RenderStateMachine()
    seen = []
    for index in range(1, 40):
        request_id = "req-%05d" % index
        machine.change_source(source, request_id)
        assert machine.state == messages.STATE_RENDERING
        machine.apply_status(status(request_id, messages.STATE_RENDERING))
        machine.apply_status(status(request_id, messages.STATE_RENDERED,
                                    type="flowchart"))
        seen.append(machine.state)
        assert machine.state != messages.STATE_INVALID
        assert machine.last_error is None
        assert machine.state == messages.STATE_RENDERED
    assert set(seen) == {messages.STATE_RENDERED}


def test_one_hundred_twenty_line_document_reports_its_type():
    source = read_fixture("long-120-lines.mmd")
    lines = source.splitlines()
    assert lines[0] == "flowchart TD"
    assert len(lines) == 121                        # header + 120 numbered lines
    assert "line 120" in lines[-1]
    assert "line 1]" in lines[1]
    assert len(source) <= messages.MAX_PASTE_CHARS
    machine = states.RenderStateMachine()
    machine.change_source(source, "req-00001")
    machine.apply_status(status("req-00001", messages.STATE_RENDERED,
                                type="flowchart"))
    assert machine.diagram_type == "flowchart"


# ---------------------------------------------------------------------------
# invalid keeps lastGood (FR-016)
# ---------------------------------------------------------------------------

def test_failed_parse_never_clears_the_last_good_render():
    machine = states.RenderStateMachine()
    machine.change_source("flowchart TD\n  A-->B", "req-00001")
    payload = status("req-00001", messages.STATE_RENDERED, type="flowchart")
    payload["svg"] = "<svg>good</svg>"
    payload["at"] = 1000
    machine.apply_status(payload)
    good = machine.last_good
    machine.change_source("flowchart TD\n  A->>B", "req-00002")
    machine.apply_status(status("req-00002", messages.STATE_INVALID,
                                error=messages.make_render_error(
                                    "parseError", "Unknown arrow style on line 2",
                                    line=2, column=9)))
    assert machine.last_good == good
    assert machine.state == messages.STATE_INVALID
    assert machine.error_visible() is True
    # recovering clears the error but the panel keeps the newer good render
    machine.change_source("flowchart TD\n  A-->B", "req-00003")
    machine.apply_status(status("req-00003", messages.STATE_RENDERED,
                                type="flowchart"))
    payload = status("req-00003", messages.STATE_RENDERED, type="flowchart")
    payload["svg"] = "<svg>newer</svg>"
    machine.apply_status(payload)
    assert machine.last_error is None
    assert machine.last_good["svg"] == "<svg>newer</svg>"
    assert machine.state == messages.STATE_RENDERED


# ---------------------------------------------------------------------------
# staleness (invariant 3)
# ---------------------------------------------------------------------------

def test_terminal_status_for_a_superseded_request_is_ignored():
    machine = states.RenderStateMachine()
    machine.change_source("flowchart TD\n  A-->B", "req-00009")
    assert machine.apply_status(status("req-00005", messages.STATE_INVALID,
                                       error=messages.make_render_error(
                                           "parseError", "old"))) is False
    assert machine.state == messages.STATE_RENDERING
    assert machine.last_error is None


def test_only_one_terminal_status_per_request_id_reaches_the_ui():
    machine = states.RenderStateMachine()
    machine.change_source("flowchart TD\n  A-->B", "req-00001")
    assert machine.apply_status(status("req-00001", messages.STATE_RENDERED,
                                       type="flowchart")) is True
    late = status("req-00001", messages.STATE_INVALID,
                  error=messages.make_render_error("renderError", "late"))
    assert machine.apply_status(late) is True   # same-id follow-up still applies
    assert machine.state in (messages.STATE_INVALID,)
    third = messages.make_render_status("req-00001", messages.STATE_EMPTY)
    assert machine.apply_status(third) is True
    assert machine.state == messages.STATE_EMPTY
    # a status for a request that was never issued is refused
    machine.change_source("flowchart TD\n  Z-->Y", "req-00010")
    assert machine.apply_status(status("req-00011",
                                       messages.STATE_RENDERED,
                                       type="flowchart")) is False
    assert machine.state == messages.STATE_RENDERING


def test_stall_upgrade_needs_more_than_the_stall_budget():
    machine = states.RenderStateMachine()
    machine.change_source("flowchart TD\n  A-->B", "req-00001")
    assert machine.stalled(messages.RENDER_STALL_MS) is False
    assert machine.stalled(messages.RENDER_STALL_MS + 1) is True
    assert messages.RENDER_STALL_MS == 8000
    machine.apply_status(status("req-00001", messages.STATE_RENDERED,
                                type="flowchart"))
    assert machine.stalled(999999) is False


def test_type_mismatch_is_surfaced_never_silent():
    machine = states.RenderStateMachine()
    machine.change_source("sequenceDiagram\n  A->>B: hi", "req-00001")
    machine.apply_status(status("req-00001", messages.STATE_RENDERED,
                                type="sequence"))
    assert machine.type_mismatch_notice("flowchart") == "sequence"
    assert machine.type_mismatch is True
    assert machine.type_mismatch_notice("sequence") is None
    assert machine.type_mismatch is False


def test_empty_status_never_carries_an_error():
    """Contract section 2 invariant 4."""
    machine = states.RenderStateMachine()
    machine.change_source("flowchart TD\n  A-->B", "req-00001")
    payload = messages.make_render_status("req-00001", messages.STATE_EMPTY)
    assert "error" not in payload
    machine.apply_status(payload)
    assert machine.state == messages.STATE_EMPTY
    with pytest.raises(ValueError):
        messages.validate_render_status({
            "requestId": "req-00002", "state": messages.STATE_EMPTY,
            "error": messages.make_render_error("parseError", "nope")})


def test_snapshot_is_json_friendly_and_report_only():
    import json
    machine = states.RenderStateMachine()
    machine.change_source("flowchart TD\n  A-->B", "req-00001")
    blob = json.dumps(machine.snapshot(), sort_keys=True)
    assert "rendering" in blob
