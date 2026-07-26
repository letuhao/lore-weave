"""D-ARC-TRACKS-ROSTER-SCHEMA (spec 32a §A.3) — the pure repair function is non-destructive
and idempotent. No DB — this covers the logic that would run against a dirty deployment."""
from __future__ import annotations

from app.db.repairs.arc_entry_keys import repair_entries


def test_missing_and_empty_keys_get_positional_keys_never_dropped():
    entries = [{"label": "no key"}, {"key": "", "label": "empty"}, {"key": "revenge"}]
    out, notes = repair_entries(entries, prefix="track")
    assert [e["key"] for e in out] == ["track_0", "track_1", "revenge"]
    # non-destructive: labels preserved, nothing removed
    assert len(out) == 3
    assert out[0]["label"] == "no key"
    assert len(notes) == 2


def test_within_node_duplicate_is_suffixed_not_merged():
    out, notes = repair_entries([{"key": "hero"}, {"key": "hero"}], prefix="role")
    assert [e["key"] for e in out] == ["hero", "hero_2"]
    assert len(out) == 2  # both kept — a merge would silently eat one
    assert any("duplicate" in n for n in notes)


def test_clean_input_is_a_noop_and_idempotent():
    entries = [{"key": "a", "label": "A"}, {"key": "b"}]
    out, notes = repair_entries(entries, prefix="track")
    assert out == entries
    assert notes == []
    # re-running the repaired output changes nothing (idempotent)
    out2, notes2 = repair_entries(out, prefix="track")
    assert out2 == out and notes2 == []


def test_repair_output_passes_the_write_door_schema():
    # The whole point: a repaired list must satisfy ArcTrack (non-empty unique keys).
    from app.routers.arc import validate_track_dicts

    garbage = [{"label": "x"}, {"key": ""}, {"key": "dup"}, {"key": "dup"}]
    repaired, _ = repair_entries(garbage, prefix="track")
    # would raise pydantic.ValidationError if any key were empty or duplicated
    assert validate_track_dicts(repaired) == repaired
