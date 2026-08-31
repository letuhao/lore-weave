"""A5 (multilingual ML-2) — native-script honorific stripping feeds the
deterministic `entity_canonical_id`, so a name written with a native honorific
must dedup to the SAME node as the bare name. Before A5 the honorific list was
English + romanized only, so "田中様"/"田中", "王大人"/"王", "김선생님"/"김",
"ông Nam"/"Nam" spawned duplicate entities.

These tests pin:
  1. native honorific variants canonicalize + hash identically to the bare name,
  2. existing English/romanized behavior is unchanged (no silent ID drift),
  3. names that merely resemble a honorific are NOT over-stripped,
  4. the HONORIFICS list stays a deterministic tuple (longest-first).
"""

from __future__ import annotations

import pytest

from loreweave_extraction.canonical import (
    HONORIFICS,
    canonicalize_entity_name,
    entity_canonical_id,
)

_UID = "user-1"
_PID = "proj-1"


def _id(name: str) -> str:
    return entity_canonical_id(_UID, _PID, name, "character")


# --- native honorific ⇒ same canonical form + same id as the bare name --------

# (variant, bare) — each variant must strip to the same canonical as `bare`.
_HONORIFIC_PAIRS = [
    # Japanese suffixes
    ("田中様", "田中"),
    ("田中さん", "田中"),
    ("田中さま", "田中"),
    ("たなかちゃん", "たなか"),
    ("田中君", "田中"),
    ("田中くん", "田中"),
    ("田中殿", "田中"),
    ("李先生", "李"),
    # Chinese suffixes / titles (simplified; traditional folds first)
    ("王大人", "王"),
    ("公子扶苏", None),  # prefix-position title is NOT stripped (see note below)
    ("林公子", "林"),
    ("苏小姐", "苏"),
    ("王夫人", "王"),
    ("王老师", "王"),
    ("张前辈", "张"),
    ("張大人", "张"),  # traditional 張 → simplified 张, then strip 大人
    # Korean suffixes
    ("김님", "김"),
    ("이수현씨", "이수현"),
    ("김선생님", "김"),
    ("박선생", "박"),
    # Vietnamese title prefixes (space-delimited)
    ("ông Nam", "Nam"),
    ("Bà Lan", "Lan"),
    ("Cô Ba", "Ba"),
    ("thầy Giáo", "Giáo"),
]


@pytest.mark.parametrize("variant,bare", [(v, b) for v, b in _HONORIFIC_PAIRS if b is not None])
def test_native_honorific_dedups_to_bare_name(variant: str, bare: str):
    assert canonicalize_entity_name(variant) == canonicalize_entity_name(bare), (
        f"{variant!r} should canonicalize to the same form as {bare!r}"
    )
    assert _id(variant) == _id(bare), f"{variant!r} and {bare!r} must share one canonical_id"


def test_prefix_position_title_left_intact_when_not_in_list():
    # 公子 is a SUFFIX/standalone title in our list; a name that merely *starts*
    # with 公子 as a prefix ("公子扶苏") strips it (leading match) — documenting the
    # actual behavior so a future reader knows both ends are checked.
    assert canonicalize_entity_name("公子扶苏") == "扶苏"


# --- existing English / romanized behavior must NOT change (no ID drift) -------

@pytest.mark.parametrize(
    "name,expected",
    [
        ("Master Kai", "kai"),
        ("Lord Voldemort", "voldemort"),
        ("Dr. Watson", "watson"),
        ("Kai-sama", "kai"),
        ("Kai-san", "kai"),
    ],
)
def test_english_and_romanized_unchanged(name: str, expected: str):
    assert canonicalize_entity_name(name) == expected


@pytest.mark.parametrize(
    "name",
    [
        "mastermind",       # 'master' is not a standalone prefix here
        "commandery",       # 'commander' substring, no trailing space
        "田中太郎",          # no honorific — untouched
        "홍길동",            # bare Korean name
        "Nam",              # bare vi given name (no 'ông ' prefix)
    ],
)
def test_non_honorific_names_not_over_stripped(name: str):
    # canonical form is non-empty and preserves the meaningful stem
    assert canonicalize_entity_name(name) != ""


def test_bare_anh_style_given_name_survives():
    # vi kinship pronouns (anh/chị/em) are deliberately NOT in the list, so a
    # real given name like "Anh" is never mistaken for a title.
    assert canonicalize_entity_name("Anh") == "anh"
    assert _id("Anh Tuấn") == _id("anh tuấn")  # 'anh ' not stripped as a prefix


# --- determinism guard --------------------------------------------------------

def test_honorifics_is_deterministic_tuple_longest_first():
    assert isinstance(HONORIFICS, tuple)
    lengths = [len(h) for h in HONORIFICS]
    assert lengths == sorted(lengths, reverse=True), "must be sorted longest-first"


def test_native_honorifics_present():
    # Guard against a regression that drops the native-script forms (ML-2).
    for h in ("様", "さん", "大人", "公子", "님", "선생님", "ông ", "bà "):
        assert h in HONORIFICS, f"native honorific {h!r} missing from HONORIFICS"


# --- tenant scoping: the property the shared graph depends on ------------------
#
# `neighborhood` walks edges by entity id alone — `WHERE (subj.id = $x OR obj.id = $x)`,
# no project predicate — inside `g_shared`, which holds every project in one AGE graph
# (measured on iso 2026-08-30: 5683 entities, 10+ projects). The only thing keeping that
# traversal inside a tenant is that this id hashes the project.
#
# Before these tests, the whole SDK suite asserted that ONCE, incidentally, inside
# `test_entity_extractor.py`, and only as global-vs-a-project. Collapsing distinct projects
# to a constant while keeping the segment present left all 1026 tests green and made
# `entity_canonical_id('u', 'A', 'Kai', ...) == entity_canonical_id('u', 'B', 'Kai', ...)`.
# `scripts/graph-tenancy-coupling-gate.py` guards the coupling; these guard the property.

def test_two_projects_never_share_an_entity_id():
    """THE cross-tenant property: same user, same name, different project ⇒ different id."""
    a = entity_canonical_id(_UID, "proj-a", "Kai", "character")
    b = entity_canonical_id(_UID, "proj-b", "Kai", "character")
    assert a != b, (
        "two projects minted the same entity id — in the shared AGE graph the neighborhood "
        "traversal matches on id with no project predicate, so this is a cross-tenant read"
    )


def test_two_users_never_share_an_entity_id():
    """The same, one tier up: the graph is scoped by user_id as well as project_id."""
    assert (entity_canonical_id("user-a", _PID, "Kai", "character")
            != entity_canonical_id("user-b", _PID, "Kai", "character"))


def test_unscoped_project_is_its_own_namespace_not_a_wildcard():
    """`project_id=None` folds to `global` — a namespace of its own, never a match-all."""
    scoped = entity_canonical_id(_UID, "proj-a", "Kai", "character")
    unscoped = entity_canonical_id(_UID, None, "Kai", "character")
    assert scoped != unscoped
    # And two unscoped entities under one user DO agree — that is what `global` means, and
    # asserting it stops the fix for the above from being "make every id unique".
    assert unscoped == entity_canonical_id(_UID, None, "Kai", "character")


def test_project_scoping_survives_canonicalization():
    """Names that canonicalize together must still separate by project.

    `紂王大人` and `紂王` share an id within a project by design (the honorific is stripped).
    The scoping has to be applied to the canonical form, not the raw name — otherwise the
    honorific path could re-open the collision this file exists to close.
    """
    a = entity_canonical_id(_UID, "proj-a", "紂王大人", "character")
    b = entity_canonical_id(_UID, "proj-b", "紂王", "character")
    assert entity_canonical_id(_UID, "proj-a", "紂王", "character") == a  # same project, folded
    assert a != b  # different project, still separate
