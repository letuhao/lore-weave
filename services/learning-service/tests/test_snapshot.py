"""split_snapshot — privacy split (R2): structural raw + content hash, no raw text.
FD-19/052: short_description is hashed SEPARATELY (description_hash), not in content_hash.
"""

from app.events.snapshot import split_snapshot


def test_entity_split_structural_kind_content_hashed():
    structural, content_hash, description_hash = split_snapshot(
        "entity",
        {"name": "Elizabeth", "kind": "person", "aliases": ["Lizzy"], "short_description": "heroine"},
    )
    assert structural == {"kind": "person"}
    assert content_hash is not None
    assert description_hash is not None  # short_description → its own hash
    # No raw content leaks into the structural dict.
    assert "name" not in structural and "short_description" not in structural


def test_content_hash_changes_with_name_stable_otherwise():
    _, h1, _ = split_snapshot("entity", {"name": "A", "kind": "person", "aliases": [], "short_description": ""})
    _, h2, _ = split_snapshot("entity", {"name": "B", "kind": "person", "aliases": [], "short_description": ""})
    _, h1b, _ = split_snapshot("entity", {"name": "A", "kind": "person", "aliases": [], "short_description": ""})
    assert h1 != h2
    assert h1 == h1b  # deterministic (hashlib, not PYTHONHASHSEED-randomised)


def test_description_change_keeps_content_hash_stable():
    """FD-19/052: a description-only edit must NOT move content_hash (else it's
    mis-classed as a `boundary`/rename signal); it moves description_hash instead.
    The description is hashed, never stored raw (privacy)."""
    s1, c1, d1 = split_snapshot("entity", {"name": "A", "kind": "person", "aliases": [], "short_description": "old"})
    s2, c2, d2 = split_snapshot("entity", {"name": "A", "kind": "person", "aliases": [], "short_description": "new"})
    assert c1 == c2          # name/alias unchanged → content_hash stable
    assert d1 != d2          # description changed → its own hash moves
    assert s1 == s2 == {"kind": "person"}
    assert "short_description" not in (s1 or {})  # never raw


def test_relation_has_no_content_or_description_hash():
    structural, content_hash, description_hash = split_snapshot(
        "relation",
        {"subject_id": "s", "object_id": "o", "predicate": "ally_of", "confidence": 0.9, "valid_until": None},
    )
    assert structural["predicate"] == "ally_of"
    assert content_hash is None  # endpoint ids are structural, no content
    assert description_hash is None  # relations have no description class


def test_event_split():
    structural, content_hash, description_hash = split_snapshot(
        "event",
        {"title": "The Oath", "summary": "...", "time_cue": "dawn", "event_date_iso": "0184", "participants": ["Liu"]},
    )
    assert structural == {"event_date_iso": "0184"}
    assert content_hash is not None
    assert description_hash is None  # events fold title/summary into content, no separate description
    assert "title" not in structural and "summary" not in structural


def test_absent_snapshot_returns_none_none_none():
    assert split_snapshot("entity", None) == (None, None, None)
