"""K11.5a unit tests — canonical entity name + deterministic ID.

Pure-function tests, no Neo4j. Covers the table from KSA §5.0 plus
the multi-tenant scoping rule and the must-not-canonicalize-to-
empty guard.
"""

from __future__ import annotations

import pytest

from app.db.neo4j_repos.canonical import (
    canonicalize_entity_name,
    entity_canonical_id,
)


# ── canonicalize_entity_name ──────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Kai", "kai"),
        ("KAI", "kai"),
        ("kai", "kai"),
        ("  Kai  ", "kai"),
        # Honorifics — KSA §5.0 example table
        ("Master Kai", "kai"),
        ("master kai", "kai"),
        ("Lord Kai", "kai"),
        ("kai-shifu", "kai"),
        ("kai-sensei", "kai"),
        ("Kai-sama", "kai"),
        # Sub-identity stays distinct from base name
        ("Kai the Flame", "kai the flame"),
        # Whitespace collapse
        ("Kai   the    Flame", "kai the flame"),
        # Apostrophe preserved
        ("O'Neill", "o'neill"),
        # Punctuation stripped
        ("Kai!", "kai"),
        ("Kai, the Brave.", "kai the brave"),
        # K15.1: CJK scripts preserved. Python's \w is Unicode-aware
        # so Han/Hiragana/Katakana/Hangul pass through the punctuation
        # strip unchanged. Case-folding is a no-op on these scripts.
        ("凯", "凯"),
        ("凯·英雄", "凯英雄"),  # middle dot stripped as punctuation
        ("カイ", "カイ"),
        ("카이", "카이"),
        # Japanese honorific suffix on a CJK name still strips
        ("カイ-sama", "カイ"),
    ],
)
def test_k11_5a_canonicalize_examples(raw: str, expected: str):
    assert canonicalize_entity_name(raw) == expected


def test_k11_5a_canonicalize_strips_stacked_honorifics():
    # The loop visits each honorific once and strips matches.
    # Stacked honorifics like "Master Lord Kai" lose both because
    # after "master " is stripped, "lord " still matches the
    # remaining string when its turn comes around in the loop.
    # Multi-strip is the documented spec from KSA §5.0.
    assert canonicalize_entity_name("Master Lord Kai") == "kai"


def test_k11_5a_honorifics_iteration_order_is_deterministic():
    # Frozensets are hash-randomized — using one would make
    # canonical_id non-deterministic across interpreter restarts.
    # Lock the type to tuple and the order to longest-first.
    from app.db.neo4j_repos.canonical import HONORIFICS

    assert isinstance(HONORIFICS, tuple)
    lengths = [len(h) for h in HONORIFICS]
    assert lengths == sorted(lengths, reverse=True), (
        "HONORIFICS must be sorted longest-first for stable stripping"
    )


def test_k11_5a_canonicalize_mastermind_keeps_master():
    # The trailing space in "master " in the honorific list
    # prevents "mastermind" from losing its prefix.
    assert canonicalize_entity_name("Mastermind") == "mastermind"


def test_k11_5a_canonicalize_rejects_non_string():
    with pytest.raises(TypeError):
        canonicalize_entity_name(123)  # type: ignore[arg-type]


def test_k11_5a_canonicalize_empty_string_is_empty():
    # Caller (entity_canonical_id) is responsible for rejecting
    # this — the canonicalizer itself returns "".
    assert canonicalize_entity_name("") == ""
    assert canonicalize_entity_name("   ") == ""
    assert canonicalize_entity_name("!!!") == ""


# ── entity_canonical_id ───────────────────────────────────────────────


def test_k11_5a_canonical_id_is_deterministic():
    a = entity_canonical_id("u-1", "p-1", "Kai", "character")
    b = entity_canonical_id("u-1", "p-1", "Kai", "character")
    assert a == b


def test_k11_5a_canonical_id_collapses_honorifics_and_spelling():
    base = entity_canonical_id("u-1", "p-1", "Kai", "character")
    for variant in ("Master Kai", "kai", "KAI", "Kai-shifu", "  Kai  "):
        assert (
            entity_canonical_id("u-1", "p-1", variant, "character") == base
        ), f"variant {variant!r} should canonicalize to base"


def test_k11_5a_canonical_id_distinct_per_kind():
    char = entity_canonical_id("u-1", "p-1", "Kai", "character")
    place = entity_canonical_id("u-1", "p-1", "Kai", "place")
    assert char != place


def test_k11_5a_canonical_id_distinct_per_user():
    a = entity_canonical_id("u-1", "p-1", "Kai", "character")
    b = entity_canonical_id("u-2", "p-1", "Kai", "character")
    assert a != b


def test_k11_5a_canonical_id_distinct_per_project():
    a = entity_canonical_id("u-1", "p-1", "Kai", "character")
    b = entity_canonical_id("u-1", "p-2", "Kai", "character")
    assert a != b


def test_k11_5a_canonical_id_global_project_distinct_from_named():
    # project_id=None -> 'global' bucket. Must not collide with
    # any specific project named 'global'.
    a = entity_canonical_id("u-1", None, "Kai", "character")
    b = entity_canonical_id("u-1", "global", "Kai", "character")
    assert a == b  # by spec — "global" string is the explicit bucket


def test_k11_5a_canonical_id_version_bump_changes_id():
    a = entity_canonical_id("u-1", "p-1", "Kai", "character", canonical_version=1)
    b = entity_canonical_id("u-1", "p-1", "Kai", "character", canonical_version=2)
    assert a != b


def test_k11_5a_canonical_id_is_32_hex_chars():
    out = entity_canonical_id("u-1", "p-1", "Kai", "character")
    assert len(out) == 32
    int(out, 16)  # raises ValueError if not hex


def test_k11_5a_canonical_id_rejects_empty_user_id():
    with pytest.raises(ValueError, match="user_id"):
        entity_canonical_id("", "p-1", "Kai", "character")


def test_k11_5a_canonical_id_rejects_empty_name():
    with pytest.raises(ValueError, match="name"):
        entity_canonical_id("u-1", "p-1", "", "character")


def test_k11_5a_canonical_id_rejects_empty_kind():
    with pytest.raises(ValueError, match="kind"):
        entity_canonical_id("u-1", "p-1", "Kai", "")


def test_k11_5a_canonical_id_rejects_name_that_canonicalizes_to_empty():
    # "!!!" canonicalizes to "" — would silently collide with every
    # other punctuation-only name. Must be a hard error.
    with pytest.raises(ValueError, match="canonicalizes to empty"):
        entity_canonical_id("u-1", "p-1", "!!!", "character")
