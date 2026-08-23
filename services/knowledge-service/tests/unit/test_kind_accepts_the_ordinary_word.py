"""`kind="person"` must reach the graph as `character`, not as a rejection.

🔴 THE RUN THIS PINS. kg_propose_edge, K=5, 2026-08-23 (p4-ctxid). Both failing runs died at the
same place: the model called kg_add_nodes with `kind="person"` for a human being — the plain
English word — and every call was rejected. The nodes were never created, so the edge could never
resolve, and the model retried FOUR times without recovering.

The rejection was already well worded: "Input should be 'character', 'location', ... (you sent
'person')". It named the value and listed the alternatives, and the model still could not act on
it. A rejection the caller cannot act on costs the turn however good the message is.

So the alias is folded at the edge and the CANONICAL value is what is stored — the graph never
sees a second vocabulary, and AUTHORABLE_KINDS stays the one home for the closed set.
"""
import pytest

from app.db.neo4j_repos.entities import AUTHORABLE_KINDS, canonical_kind
from app.tools.graph_schema_tools import KgCreateNodeArgs


def test_person_is_accepted_and_stored_as_character():
    args = KgCreateNodeArgs(name="Aldric Vane", kind="person")
    assert args.kind == "character", "the alias must be folded, not merely tolerated"
    assert args.kind in AUTHORABLE_KINDS


@pytest.mark.parametrize("raw,canonical", [
    ("person", "character"), ("PERSON", "character"), ("  Person  ", "character"),
    ("place", "location"), ("group", "organization"),
    ("idea", "concept"), ("object", "item"),
])
def test_the_ordinary_words_fold_to_the_closed_set(raw, canonical):
    assert canonical_kind(raw) == canonical
    assert KgCreateNodeArgs(name="X", kind=raw).kind == canonical


def test_a_canonical_kind_is_untouched():
    for k in AUTHORABLE_KINDS:
        assert canonical_kind(k) == k
        assert KgCreateNodeArgs(name="X", kind=k).kind == k


def test_an_unknown_kind_is_still_refused():
    """This NORMALISES; it must not widen the closed set."""
    assert canonical_kind("spaceship") == "spaceship"
    with pytest.raises(ValueError):
        KgCreateNodeArgs(name="X", kind="spaceship")


def test_every_alias_maps_into_the_canonical_set():
    """A typo in the map would invent a sixth kind that nothing downstream accepts."""
    from app.db.neo4j_repos.entities import KIND_ALIASES
    for alias, target in KIND_ALIASES.items():
        assert target in AUTHORABLE_KINDS, f"{alias} -> {target} is not an authorable kind"
        assert alias not in AUTHORABLE_KINDS, f"{alias} is canonical; aliasing it is a loop"


def test_a_retired_misnomer_is_never_aliased_back_into_existence():
    """🔴 The first draft mapped faction -> organization and this suite caught it.

    `test_kg_create_node_rejects_legacy_faction_kind` pins that "`faction` is the retired misnomer
    — the agent must not be able to mint it either". An alias map is a way to resurrect a retired
    term WITHOUT NOTICING, because the alias never appears in the canonical set anyone reviews.
    """
    from app.db.neo4j_repos.entities import KIND_ALIASES
    assert "faction" not in KIND_ALIASES
