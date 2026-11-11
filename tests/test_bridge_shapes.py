"""Bridge shape tests (render-bridge contract sections 1-4, data-model 2-3).

State-enum completeness/unambiguity, the two payload shapes and their defaults,
`validate_render_status` rejection cases, and the filename sanitiser.
"""

import json

import pytest

import messages

ALL_STATES = ("empty", "rendering", "rendered", "invalid")


# ---------------------------------------------------------------------------
# the state enum
# ---------------------------------------------------------------------------

def test_state_enum_is_complete_unambiguous_and_exactly_four():
    assert messages.STATE_ENUM == ("rendering", "rendered", "invalid", "empty")
    assert set(messages.STATE_ENUM) == set(ALL_STATES)
    assert len(messages.STATE_ENUM) == len(set(messages.STATE_ENUM)) == 4
    assert messages.STATES is messages.STATE_ENUM
    assert messages.STATE_EMPTY == "empty"
    assert messages.STATE_RENDERING == "rendering"
    assert messages.STATE_RENDERED == "rendered"
    assert messages.STATE_INVALID == "invalid"


def test_terminal_and_non_terminal_partition_the_enum():
    assert set(messages.TERMINAL_STATES) == {"rendered", "invalid", "empty"}
    assert set(messages.NON_TERMINAL_STATES) == {"rendering"}
    assert set(messages.TERMINAL_STATES) | set(messages.NON_TERMINAL_STATES) \
        == set(messages.STATE_ENUM)
    assert not set(messages.TERMINAL_STATES) & set(messages.NON_TERMINAL_STATES)


@pytest.mark.parametrize("state", ALL_STATES)
def test_every_state_survive_a_constructor_and_validator_round_trip(state):
    payload = messages.make_render_status("req-00001", state)
    if state == "invalid":
        payload["error"] = messages.make_render_error("parseError", "boom")
    if state == "rendered":
        payload["metrics"] = {"durationMs": 5}
    normalized = messages.validate_render_status(payload)
    assert normalized["state"] == state
    assert normalized["requestId"] == "req-00001"


def test_unknown_state_is_rejected_everywhere():
    for bad in ("Rendered", "RENDERED", "done", "success", "", None, 0, True):
        with pytest.raises(ValueError):
            messages.make_render_status("req-00001", bad)
        with pytest.raises(ValueError):
            messages.validate_render_status({"requestId": "req-00001",
                                             "state": bad})


def test_error_kinds_are_the_documented_five():
    assert set(messages.ERROR_KINDS) == {"parseError", "renderError",
                                        "unsupportedType", "inputTooLarge",
                                        "bridgeVersion"}
    for kind in messages.ERROR_KINDS:
        error = messages.make_render_error(kind, "plain words")
        assert error["kind"] == kind
        assert error["plainMessage"] == "plain words"
        assert error["rawMessage"] == "plain words"
    with pytest.raises(ValueError):
        messages.make_render_error("mystery", "plain words")
    with pytest.raises(ValueError):
        messages.make_render_error("parseError", "")


# ---------------------------------------------------------------------------
# RenderRequest
# ---------------------------------------------------------------------------

def test_render_request_shape_and_defaults():
    request = messages.make_render_request("req-00001", "flowchart TD\n  A-->B",
                                           None)
    assert sorted(request) == sorted(["schemaVersion", "requestId", "source",
                                      "appearance", "command"])
    assert request["schemaVersion"] == messages.BRIDGE_SCHEMA_VERSION == 1
    assert request["command"] == "render"
    assert request["source"] == "flowchart TD\n  A-->B"
    # empty appearance is replaced by the documented stand-in, never by {}
    assert request["appearance"]["mermaidTheme"] == "neo"
    assert request["appearance"]["frozen"] == messages.FROZEN_DEFAULTS


def test_frozen_defaults_are_the_appearance_contract_six():
    assert messages.FROZEN_DEFAULTS == {
        "htmlLabels": False, "useHtmlLabels": False,
        "suppressErrorRendering": True, "securityLevel": "strict",
        "startOnLoad": False,
    }
    appearance = messages.default_appearance()
    assert appearance["frozen"] == messages.FROZEN_DEFAULTS
    assert appearance["themeVariables"] == {"fontSize": "16px"}
    assert appearance["perDiagramConfig"] == {}
    # the default never leaks a mutable copy into another request
    appearance["themeVariables"]["primaryColor"] = "#ffffff"
    assert messages.default_appearance()["themeVariables"] == {"fontSize": "16px"}


def test_default_appearance_carries_the_operative_text_size_spelling():
    """16 px, as a unit-carrying `themeVariables.fontSize` (mermaid 11.12 read).

    ``messages`` and ``appearance`` state it independently; drift here would put
    a FR-002-less initialize object on any path that falls back to the default.
    """
    import appearance
    assert (messages.DEFAULT_THEME_VARIABLES["fontSize"]
            == appearance.TEXT_SIZE_PX["medium"] == "16px")
    assert messages.default_appearance()["themeVariables"]["fontSize"] == "16px"


def test_default_appearance_render_limits_match_the_appearance_module():
    """messages and appearance declare the raised ceilings independently; the
    two literals must not drift (appearance.RENDER_LIMITS is what actually
    reaches mermaid.initialize, messages' copy is the app-side stand-in)."""
    import appearance
    assert messages.RENDER_LIMITS_DEFAULT == appearance.RENDER_LIMITS
    default = messages.default_appearance()
    assert default["maxEdges"] == appearance.RENDER_LIMITS["maxEdges"] == 5000
    assert (default["maxTextSize"] == appearance.RENDER_LIMITS["maxTextSize"]
            == 200000)


def test_render_request_json_is_compact_and_key_ordered():
    request = messages.make_render_request("req-00001", "A", {"m": 1})
    text = messages.render_request_json(request)
    assert json.loads(text) == request
    assert ", " not in text            # separators=(",", ":")
    assert text.index('"schemaVersion"') < text.index('"requestId"') \
        < text.index('"source"')


def test_commands_are_the_documented_seven():
    assert set(messages.COMMANDS) == {"render", "exportSvg", "exportPng",
                                     "copySvg", "zoomIn", "zoomOut", "fit"}


# ---------------------------------------------------------------------------
# validate_render_status rejection matrix (letter E)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload,expectation", [
    ({"state": "rendered", "metrics": {}}, "requestId"),
    ({"requestId": "", "state": "rendered", "metrics": {}}, "requestId"),
    ({"requestId": 7, "state": "rendered", "metrics": {}}, "requestId"),
    ({}, "state"),
    ({"requestId": "req-1", "state": "bogus"}, "state"),
    ({"requestId": "req-1", "state": "invalid"}, "error"),
    ({"requestId": "req-1", "state": "rendered", "metrics": None,
      "error": {"kind": "parseError"}}, "iff"),
    ({"requestId": "req-1", "state": "empty", "error": {"kind": "parseError"}},
     "iff"),
    ({"requestId": "req-1", "state": "rendering",
      "error": {"kind": "parseError"}}, "iff"),
    ({"requestId": "req-1", "state": "rendered"}, "metrics"),
])
def test_validator_rejects_exactly_the_documented_problems(payload, expectation):
    with pytest.raises(ValueError) as info:
        messages.validate_render_status(payload)
    assert expectation.lower() in str(info.value).lower()


@pytest.mark.parametrize("payload", [None, [], "string", 5, True])
def test_validator_rejects_non_objects(payload):
    with pytest.raises(ValueError):
        messages.validate_render_status(payload)


def test_validator_keeps_optional_keys_only_when_supplied():
    status = messages.validate_render_status({
        "requestId": "req-00001", "state": "invalid",
        "diagramType": None,
        "error": messages.make_render_error("parseError", "Unknown arrow style",
                                           line=2, column=9,
                                           snippet="  A->>B" * 40)})
    assert sorted(status) == sorted(["requestId", "state", "diagramType",
                                     "error"])
    assert status["error"]["line"] == 2
    assert len(status["error"]["snippet"]) <= messages.SNIPPET_MAX_CHARS
    with_clamp = messages.validate_render_status({
        "requestId": "req-00002", "state": "rendered",
        "metrics": {"durationMs": 9}, "clamped": ("lineColor",)})
    assert with_clamp["clamped"] == ["lineColor"]
    assert "clamped" not in messages.validate_render_status({
        "requestId": "req-00003", "state": "empty"})


def test_rendering_must_be_emitted_before_async_work_marker_exists():
    """Contract section 2 table: `rendering` is non-terminal and precedes any
    terminal status; the pure machine enforces ordering (see test_states)."""
    assert messages.NON_TERMINAL_STATES == (messages.STATE_RENDERING,)


def test_bridge_constants_are_the_documented_numbers():
    assert messages.MAX_PASTE_CHARS == 50000
    assert messages.RENDER_STALL_MS == 8000
    assert messages.PARSE_DEBOUNCE_MS == 300
    assert messages.FILENAME_MAX_CHARS == 120
    assert messages.SNIPPET_MAX_CHARS == 120
    assert messages.UNTITLED_NAME == "untitled"


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("My Diagram", "My Diagram"),
    ("../../etc/passwd", "etcpasswd"),
    ("a/b\\c:d*e?f\"g<h>i|j", "abcdefghij"),
    ("...", "untitled"),
    ("   ", "untitled"),
    ("", "untitled"),
    ("name.with.dots", "name.with.dots"),
    ("weird\u0000char", "weirdchar"),
    ("trail. ", "trail"),
    ("diagram 😺", "diagram 😺"),
    ("日本語の図", "日本語の図"),
])
def test_sanitize_filename(raw, expected):
    assert messages.sanitize_filename(raw) == expected


def test_sanitize_filename_never_escapes_the_directory():
    for raw in ("/", "..", "../..", "\\\\server\\share", "/etc/passwd",
                "../../../tmp/x"):
        clean = messages.sanitize_filename(raw)
        assert "/" not in clean and "\\" not in clean
        assert ".." not in clean
        assert clean and "\x00" not in clean


def test_sanitize_filename_respects_length_and_fallback():
    long_name = "n" * 500
    assert len(messages.sanitize_filename(long_name)) == 120
    assert messages.sanitize_filename(None) == "untitled"
    assert messages.sanitize_filename(42) == "untitled"
    assert messages.sanitize_filename("", fallback="draft") == "draft"
    assert messages.sanitize_filename("x" * 300, None, 10) == "x" * 10


def test_export_filename_composes_sanitised_name_and_extension():
    assert messages.export_filename("../my diagram", "mmd") == "my diagram.mmd"
    assert messages.export_filename(None, ".svg") == "untitled.svg"
    assert messages.export_filename("図", "png") == "図.png"
    for raw in ("", ":x:", ".."):
        name = messages.export_filename(raw, "svg")
        assert "/" not in name and ":" not in name and ".." not in name
        assert name.endswith(".svg")
