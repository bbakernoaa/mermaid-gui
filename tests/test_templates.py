"""Template-catalog contract checks (pure Python half of the validation rules).

Rule 1 (renders) needs a browser; here every example is checked to *detect* as
its own typeId by the documented prefix rules and to carry at least three
drawable elements (rule 2), correct notation (rule 3), label length, and one
plain + one styled example per required type.
"""

import json

import appearance
import templates

MIN_LABEL_ELEMENTS = 3
MAX_LABEL = templates.MAX_LABEL_CHARS


def test_required_type_ids_are_the_contract_nine_plus_blank():
    assert templates.REQUIRED_TYPE_IDS == (
        "flowchart", "sequence", "class", "state", "er", "gantt", "pie",
        "journey", "mindmap")
    assert templates.BLANK_TYPE_ID == "blank"
    assert set(templates.type_ids()) == set(templates.REQUIRED_TYPE_IDS) | {"blank"}
    assert len(templates.entries()) == 10


def test_catalog_is_json_serialisable_with_contract_shape():
    catalog = json.dumps(json.loads(json.dumps(templates.catalog())))
    data = json.loads(catalog)
    assert set(data) == {"types"}
    assert len(data["types"]) == 10
    for entry in data["types"]:
        assert {"typeId", "label", "blurb", "examples"} <= set(entry)
        for example in entry["examples"]:
            assert {"purpose", "source"} <= set(example)
            if example["purpose"] == "styled":
                assert example.get("shows")


def test_labels_within_length_limit_and_nonempty():
    for entry in templates.entries():
        assert entry["label"]
        assert len(entry["label"]) <= MAX_LABEL, entry["typeId"]
        assert "flowchart" not in entry["label"] or entry["typeId"] == "flowchart"


def test_purposes_and_shows_per_type():
    for type_id in templates.REQUIRED_TYPE_IDS:
        entry = templates.entry_for(type_id)
        purposes = [example["purpose"] for example in entry["examples"]]
        assert purposes.count("plain") == 1, type_id
        assert "styled" in purposes, type_id
        for example in entry["examples"]:
            if example["purpose"] == "styled":
                assert example["shows"].strip(), type_id


def test_blank_pseudo_entry_is_the_clear_path():
    blank = templates.entry_for("blank")
    assert blank["examples"][0]["purpose"] == "plain"
    assert templates.first_example("blank") == ""


def test_every_example_detects_as_its_own_type():
    for type_id in templates.REQUIRED_TYPE_IDS:
        entry = templates.entry_for(type_id)
        for example in entry["examples"]:
            assert templates.detect_diagram_type(example["source"]) == type_id, (
                type_id, example["purpose"])


def test_every_example_has_at_least_three_elements():
    for type_id in templates.REQUIRED_TYPE_IDS:
        entry = templates.entry_for(type_id)
        for example in entry["examples"]:
            count = example.get("minElements", MIN_LABEL_ELEMENTS)
            assert count >= MIN_LABEL_ELEMENTS, (type_id, example["purpose"])
            counted = templates.count_elements(example["source"], type_id)
            assert counted >= min(count, MIN_LABEL_ELEMENTS), (
                type_id, example["purpose"], counted)


def test_type_characteristic_notation_is_present():
    """Contract rule 3, checked in text (the render half is the browser suite)."""
    source = {t: templates.example_for(t)["source"]
              for t in templates.REQUIRED_TYPE_IDS}
    assert "<<interface>>" in source["class"]
    assert "<|--" in source["class"]               # inheritance arrow
    for token in ("participant", "->>"):
        assert token in source["sequence"]
    assert "dateFormat" in source["gantt"]
    assert "2026-11-09" in source["gantt"]           # real dates, not placeholders
    assert "section" in source["gantt"]
    assert any(cardinality in source["er"] for cardinality in
               ("||--|{", "}o--||", "|o--|}", "||--o{"))
    assert "section" in source["journey"]
    assert ": 3:" in source["journey"] or ": 3" in source["journey"]
    assert source["flowchart"].splitlines()[0].startswith("flowchart")
    assert "-->" in source["flowchart"]
    assert "[*]" in source["state"]
    assert source["pie"].splitlines()[0].startswith("pie")
    assert '"' in source["pie"]
    assert source["mindmap"].count("\n    ") >= 2    # hierarchy by indentation


def test_appearance_contract_supports_every_required_type():
    """Catalog rule 4: a type cannot ship without an appearance mapping row."""
    for type_id in templates.REQUIRED_TYPE_IDS:
        assert type_id in appearance.DIAGRAM_FAMILIES, type_id
        resolved = appearance.resolve(appearance.DEFAULT_KNOBS, type_id)
        assert list(resolved["perDiagramConfig"]) == [type_id]
        assert resolved["family"] == type_id
        assert isinstance(resolved["fontSize"], int)


def test_helper_lookups_agree_with_catalog():
    for entry in templates.entries():
        type_id = entry["typeId"]
        assert templates.label_for(type_id) == entry["label"]
        assert templates.blurb_for(type_id) == entry["blurb"]
        assert templates.entry_for(type_id) is entry
    assert templates.entry_for("nonsense") is None
    assert templates.label_for("nonsense") is None
    assert templates.select_options()[0] == (
        templates.REQUIRED_TYPE_IDS[0],
        templates.entry_for(templates.REQUIRED_TYPE_IDS[0])["label"])


def test_stripping_front_matter_leaves_diagram_body():
    styled = templates.example_for("flowchart", "styled")["source"]
    body = templates.strip_front_matter(styled)
    assert body.lstrip().startswith("flowchart")
    assert "---" not in body


def test_first_example_prefers_the_showcase_example():
    source = templates.first_example("class")
    assert source == templates.example_for("class", "styled")["source"]
