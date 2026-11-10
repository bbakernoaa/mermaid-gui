"""T003 fixture validation: each file must contain what its name promises.

These assertions are what makes the browser suites (T010, T015, T023) trust
their inputs, and they are checkable in pure Python.
"""

import os

import appearance
import messages
import templates

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
MAX_PASTE = 50000


def load(name):
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as handle:
        return handle.read()


def test_all_seven_fixtures_exist():
    expected = {"max-size-50000.mmd", "invalid-line-2.txt", "large-500-nodes.mmd",
                "unicode-edge-cases.mmd", "notation-edge-cases.mmd",
                "type-mismatch.txt", "long-120-lines.mmd"}
    assert set(os.listdir(FIXTURES)) == expected


def test_max_size_fixture_is_exactly_50000_characters():
    """Built by construction, not truncated: it must be a *complete* diagram.

    T010 loads this file in the browser; a file cut off mid-line is a parse
    failure, which is a different (and much worse) test than a big diagram.
    """
    text = load("max-size-50000.mmd")
    assert len(text) == MAX_PASTE
    assert len(text) == messages.MAX_PASTE_CHARS
    assert len(text.encode("utf-8")) == MAX_PASTE      # ASCII: bytes == chars
    lines = text.splitlines()
    assert lines[0].startswith("flowchart")
    assert templates.detect_diagram_type(text) == "flowchart"
    assert text.endswith("\n")                         # nothing cut mid-line
    for line in lines:                                 # every line is whole
        assert line.count("[") == line.count("]"), line
    assert lines[-1].lstrip().startswith("%%")         # the tail is a comment pad
    assert sum(1 for line in lines if "-->" in line) >= 3
    # It stays inside the ceilings ``appearance.RENDER_LIMITS`` raises, so the
    # biggest document we ship examples for is renderable, not "invalid".
    edges = sum(line.count("-->") for line in lines if not line.lstrip().startswith("%%"))
    assert edges <= appearance.RENDER_LIMITS["maxEdges"]
    assert len(text) <= appearance.RENDER_LIMITS["maxTextSize"]
    assert templates.count_elements(text, "flowchart") >= 3


def test_invalid_fixture_has_its_bad_arrow_on_line_two():
    lines = load("invalid-line-2.txt").splitlines()
    assert lines[0].startswith("flowchart")
    assert "-->" not in lines[1]
    assert lines[1].strip() == "A->>B"          # a sequence arrow in a flowchart
    assert len(lines) >= 3
    # line numbers are 1-based, so the error the UI shows is line 2
    assert lines[1].strip().startswith("A")
    assert lines[2].strip() == "B-->C"


def test_large_fixture_is_valid_and_has_500_nodes():
    text = load("large-500-nodes.mmd")
    lines = text.splitlines()
    assert lines[0] == "flowchart LR"
    assert len(lines) == 501
    assert templates.detect_diagram_type(text) == "flowchart"
    assert templates.count_elements(text, "flowchart") >= 500
    assert len(text) < MAX_PASTE          # renderable, just big


def test_unicode_fixture_covers_accents_cjk_cyrillic_and_emoji():
    text = load("unicode-edge-cases.mmd")
    assert any(ord(char) > 0x7F for char in text)
    assert "Caf" in text and any(0x00C0 <= ord(char) <= 0x017F for char in text)
    assert any(0x4E00 <= ord(char) <= 0x9FFF for char in text)      # CJK
    assert any(0x0400 <= ord(char) <= 0x04FF for char in text)      # Cyrillic
    assert any(0x1F300 <= ord(char) <= 0x1FAFF for char in text)    # emoji
    assert templates.detect_diagram_type(text) in templates.REQUIRED_TYPE_IDS


def test_notation_fixture_is_a_parseable_mermaid11_class_diagram():
    """Regression fixture for the `<<interface>>`-eaten-by-HTML bug class
    (commits 02ae868 / 89bf9cc): the stereotype must survive verbatim, in the
    position mermaid 11 actually accepts it.

    In mermaid 11 a classDiagram stereotype annotation may NOT sit on the
    class-declaration line (`class Animal<<interface>> { ... }` throws
    `got 'ANNOTATION_START'`); it must be on its own line inside the body.
    The real parse proof runs in the browser suite; here we assert the
    structural facts that make that parse possible plus every notation we
    care about being present.
    """
    text = load("notation-edge-cases.mmd")
    lines = text.splitlines()
    assert len(lines) <= 25                                  # small enough to eyeball
    assert templates.detect_diagram_type(text) == "class"
    assert templates.count_elements(text) >= 8               # a real diagram, not a stub
    # the notation we care about, present verbatim
    assert "<<interface>>" in text
    assert "<<enumeration>>" in text
    assert "~T~" in text                                     # generics
    assert "#quot;" in text                                  # quotes use the entity
    assert "'" in text                                       # apostrophes too
    assert "<b>markup</b>" in text                           # must stay literal
    assert "(" in text and ")" in text                       # parentheses
    assert any(line.strip().startswith("note for") for line in lines)
    # annotations are body-only: never glued onto a class declaration line
    for index, line in enumerate(lines):
        stripped = line.strip()
        if "<<" in stripped:
            assert stripped.startswith("<<"), (index + 1, stripped)
            assert "{" not in stripped, (index + 1, stripped)
        if stripped.startswith("class "):
            assert "<<" not in stripped, (index + 1, stripped)
    # class bodies open and close the same number of times
    assert sum(1 for line in lines if line.rstrip().endswith("{")) == \
        sum(1 for line in lines if line.strip() == "}")
    assert "{" in text and "}" in text


def test_type_mismatch_fixture_hides_a_sequence_diagram():
    """Selected flowchart, parsed sequence: the notice case (FR-019)."""
    text = load("type-mismatch.txt")
    assert text.splitlines()[0].startswith("sequenceDiagram")
    assert templates.detect_diagram_type(text) == "sequence"
    assert templates.label_for("sequence") != templates.label_for("flowchart")


def test_long_fixture_has_120_numbered_lines():
    lines = load("long-120-lines.mmd").splitlines()
    assert lines[0] == "flowchart TD"
    body = lines[1:]
    assert len(body) == 120
    for index, line in enumerate(body, start=1):
        assert ("line %d]" % index) in line, (index, line)
    assert "[line 120]" in body[-1]
    assert len("\n".join(lines)) < MAX_PASTE
