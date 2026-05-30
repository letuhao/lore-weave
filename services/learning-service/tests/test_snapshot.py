"""split_snapshot — privacy split (R2): structural raw + content hash, no raw text."""

from app.events.snapshot import split_snapshot


def test_entity_split_structural_kind_content_hashed():
    structural, content_hash = split_snapshot(
        "entity",
        {"name": "Elizabeth", "kind": "person", "aliases": ["Lizzy"], "short_description": "heroine"},
    )
    assert structural == {"kind": "person"}
    assert content_hash is not None
    # No raw content leaks into the structural dict.
    assert "name" not in structural and "short_description" not in structural


def test_content_hash_changes_with_name_stable_otherwise():
    _, h1 = split_snapshot("entity", {"name": "A", "kind": "person", "aliases": [], "short_description": ""})
    _, h2 = split_snapshot("entity", {"name": "B", "kind": "person", "aliases": [], "short_description": ""})
    _, h1b = split_snapshot("entity", {"name": "A", "kind": "person", "aliases": [], "short_description": ""})
    assert h1 != h2
    assert h1 == h1b  # deterministic (hashlib, not PYTHONHASHSEED-randomised)


def test_relation_has_no_content_hash():
    structural, content_hash = split_snapshot(
        "relation",
        {"subject_id": "s", "object_id": "o", "predicate": "ally_of", "confidence": 0.9, "valid_until": None},
    )
    assert structural["predicate"] == "ally_of"
    assert content_hash is None  # endpoint ids are structural, no content


def test_event_split():
    structural, content_hash = split_snapshot(
        "event",
        {"title": "The Oath", "summary": "...", "time_cue": "dawn", "event_date_iso": "0184", "participants": ["Liu"]},
    )
    assert structural == {"event_date_iso": "0184"}
    assert content_hash is not None
    assert "title" not in structural and "summary" not in structural


def test_absent_snapshot_returns_none_none():
    assert split_snapshot("entity", None) == (None, None)
