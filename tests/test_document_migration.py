"""Draft persistence + version migration tests (share contract section 2)."""

import json

import pytest

import share

SOURCE = "flowchart TD\n  A-->B\n  B-->C{decision}"
SAVED_AT = "2026-11-09T17:05:12Z"


def v0_draft(**overrides):
    """The pre-schema shape: updatedAt / text / appearance / type."""
    draft = {
        "updatedAt": SAVED_AT,
        "text": SOURCE,
        "name": "Old name",
        "appearance": {"density": "roomy", "schemeName": "neo"},
        "type": "flowchart",
    }
    draft.update(overrides)
    return draft


# ---------------------------------------------------------------------------
# storage keys and shape
# ---------------------------------------------------------------------------

def test_storage_keys_are_the_documented_names():
    assert share.STORAGE_KEY_DRAFT == "mermaidGui.draft"
    assert share.STORAGE_KEY_APPEARANCE == "mermaidGui.appearance"
    assert share.DRAFT_VERSION == 1
    share.appearance.DEFAULT_KNOBS["fontFamily"] = "sans"  # keys are pure copies


def test_current_draft_shape_is_the_data_model_seven():
    draft = share.make_draft(SOURCE, "Release flow", share.make_knobs(),
                             saved_at=SAVED_AT)
    assert sorted(draft) == sorted(["version", "savedAt", "source", "name",
                                    "knobs"])
    assert draft["version"] == 1
    assert draft["savedAt"] == SAVED_AT
    assert share.validate_draft(draft) is True
    assert share.draft_is_storable(draft) is True
    assert json.dumps(draft)                     # localStorage needs a string


def test_saved_at_is_always_a_string_and_out_of_band_values_cannot_break_it():
    draft = share.make_draft(SOURCE, saved_at=1730000000)
    assert isinstance(draft["savedAt"], str)
    assert share.validate_draft(draft) is True


def test_validate_draft_rejects_every_partial_shape():
    good = share.make_draft(SOURCE, "n", share.make_knobs(), SAVED_AT)
    assert share.validate_draft(good) is True
    for key in ("version", "savedAt", "source", "name", "knobs"):
        broken = dict(good)
        del broken[key]
        assert share.validate_draft(broken) is False, key
    for wrong in (None, "string", 5, [], {}):
        assert share.validate_draft(wrong) is False
    wrong_type = dict(good, source=None)
    assert share.validate_draft(wrong_type) is False
    wrong_knobs = dict(good, knobs="oops")
    assert share.validate_draft(wrong_knobs) is False
    wrong_version = dict(good, version="1")
    assert share.validate_draft(wrong_version) is False


# ---------------------------------------------------------------------------
# migration map
# ---------------------------------------------------------------------------

def test_version_zero_migrates_to_the_current_draft():
    migrated = share.migrate_document(v0_draft())
    assert migrated == {
        "version": 1,
        "savedAt": SAVED_AT,
        "source": SOURCE,
        "name": "Old name",
        "knobs": {"density": "roomy", "schemeName": "neo"},
    }
    assert share.validate_draft(migrated) is True
    assert "text" not in migrated and "appearance" not in migrated
    assert "updatedAt" not in migrated and "type" not in migrated


def test_migration_preserves_unicode_byte_for_byte():
    source = "classDiagram\n  <<interface>> «Café»\n  A <|-- 日本 : 🎨\n"
    migrated = share.migrate_document(v0_draft(text=source))
    assert migrated["source"] == source
    round_tripped = json.loads(json.dumps(migrated))
    assert round_tripped["source"] == source


def test_migration_falls_back_to_the_current_source_key():
    migrated = share.migrate_document({"updatedAt": SAVED_AT, "source": SOURCE,
                                       "appearance": {"density": "open"}})
    assert migrated["source"] == SOURCE
    assert migrated["knobs"] == {"density": "open"}


def test_out_of_range_knobs_are_dropped_not_trusted_by_migration():
    migrated = share.migrate_document(v0_draft(
        appearance={"density": 99, "schemeName": "bogus", "pathEmphasis": "soft"}))
    assert migrated["knobs"] == {"pathEmphasis": "soft"}


def test_unknown_version_discards_silently():
    """Contract rule 2: no migration entry means start normal, never crash."""
    for version in (2, 3, 99, -1):
        assert share.migrate_document(dict(v0_draft(), version=version)) is None
    assert share.migrate_document({"version": 7, "source": SOURCE}) is None
    # a version-less draft in the legacy shape is data, not garbage: v0 applies
    assert share.migrate_document({"updatedAt": SAVED_AT,
                                  "text": SOURCE}) is not None
    assert share.migrate_document({"version": "1", "source": SOURCE}) is None
    assert share.migrate_document({"version": True}) is None
    for garbage in (None, "string", 5, [], {}, [v0_draft()]):
        assert share.migrate_document(garbage) is None


def test_migrating_a_broken_v0_draft_discards_instead_of_crashing():
    for broken in ({"updatedAt": SAVED_AT}, {"text": 5}, {"version": 0},
                   {"text": None, "appearance": 3}):
        assert share.migrate_document(broken) is None


def test_current_version_is_passed_through_and_validated():
    good = share.make_draft(SOURCE, "n", saved_at=SAVED_AT)
    assert share.migrate_document(good) is good
    broken = dict(good)
    del broken["knobs"]
    assert share.migrate_document(broken) is None


def test_migration_is_idempotent_and_leaves_the_input_untouched():
    original = v0_draft()
    snapshot = json.dumps(original, sort_keys=True)
    once = share.migrate_document(original)
    twice = share.migrate_document(once)
    assert once == twice
    assert json.dumps(original, sort_keys=True) == snapshot


# ---------------------------------------------------------------------------
# localStorage read path
# ---------------------------------------------------------------------------

def test_parse_draft_json_handles_the_real_storage_strings():
    draft = share.make_draft(SOURCE, "n", share.make_knobs(), SAVED_AT)
    assert share.parse_draft_json(json.dumps(draft)) == draft
    assert share.parse_draft_json(json.dumps(v0_draft()))["version"] == 1


@pytest.mark.parametrize("raw", ["", "{", "null", "[]", '"text"', "not json",
                                 '{"version": 9}', "{}", None, 5])
def test_parse_draft_json_never_raises_and_discards_bad_data(raw):
    assert share.parse_draft_json(raw) is None


def test_draft_start_fresh_is_a_single_transaction_shape():
    """FR-023: clearing removes the draft and resets the document together."""
    cleared = share.make_draft("", "", share.make_knobs(), "")
    assert share.validate_draft(cleared) is True
    assert cleared["source"] == "" and cleared["name"] == ""
    assert share.draft_is_storable(cleared) is True   # writable, so storage empties


# ---------------------------------------------------------------------------
# write scheduling: debounced >= 1 000 ms and coalesced (rule 1)
# ---------------------------------------------------------------------------

class FakeClock(object):
    def __init__(self, start=10_000):
        self.now_ms = start

    def __call__(self):
        return self.now_ms

    def advance(self, milliseconds):
        self.now_ms += milliseconds


def test_interval_constant_is_at_least_one_second():
    assert share.DRAFT_MIN_INTERVAL_MS == 1000
    assert share.DRAFT_DEBOUNCE_MS == 1000
    with pytest.raises(ValueError):
        share.DraftScheduler(min_interval_ms=500)


def test_rapid_keystrokes_produce_exactly_one_write():
    clock = FakeClock()
    scheduler = share.DraftScheduler(clock_ms=clock)
    writes = []
    for index in range(200):
        draft = share.make_draft("flowchart TD\n  A" + "x" * index, saved_at="t")
        scheduler.note_change(draft)
        clock.advance(5)                       # a keystroke every 5 ms
        pending = scheduler.flush()
        if pending is not None:
            writes.append(pending)
    clock.advance(1000)
    final = scheduler.flush()
    if final is not None:
        writes.append(final)
    assert len(writes) == 1
    assert writes[0]["source"].endswith("x" * 199)   # newest text survived
    assert scheduler.flush() is None


def test_pending_write_waits_out_the_full_interval():
    """The debounce is measured from the last change, not from the last write."""
    clock = FakeClock()
    scheduler = share.DraftScheduler(clock_ms=clock)
    draft = share.make_draft(SOURCE, saved_at=SAVED_AT)
    assert scheduler.due_ms() is None          # idle: nothing to write
    assert scheduler.flush() is None
    scheduler.note_change(draft)
    assert scheduler.due_ms() == 1000
    for elapsed in (0, 1, 500, 999):
        clock.now_ms = 10_000 + elapsed
        assert scheduler.due_ms() == 1000 - elapsed
        assert scheduler.flush() is None
    clock.advance(1)
    assert scheduler.due_ms() == 0
    assert scheduler.flush() == draft
    assert scheduler.due_ms() is None          # nothing pending any more


def test_note_change_only_replaces_the_pending_value():
    clock = FakeClock()
    scheduler = share.DraftScheduler(clock_ms=clock)
    first = share.make_draft("A", saved_at="1")
    second = share.make_draft("B", saved_at="2")
    assert scheduler.note_change(first) == first
    assert scheduler.pending() == first
    clock.advance(400)
    assert scheduler.note_change(second) == second   # debounce restarts
    assert scheduler.due_ms() == 1000
    clock.advance(1000)
    assert scheduler.flush()["source"] == "B"
    assert scheduler.pending() is None


def test_scheduler_coalesces_across_the_whole_session():
    """Typing a 5 000 character paste one character at a time stays one write."""
    clock = FakeClock()
    scheduler = share.DraftScheduler(clock_ms=clock)
    text = ""
    for index in range(5000):
        text += "x"
        scheduler.note_change(share.make_draft(text, saved_at="t"))
        if index % 20 == 0:
            scheduler.flush()                  # the app tries on every rerender
            clock.advance(1)
    clock.advance(1000)
    written = scheduler.flush()
    assert written is not None and len(written["source"]) == 5000
