"""The vector-specific hit mapper, and the cost of forking it (plan T25b).

The PO's call was to FORK `passage_to_hit` rather than widen it, because it is shared with the
CJK lexical leg — not a vector search, never coming through this port — and widening it would
rewrite a retrieval path this migration has no business touching.

Forking has a price: two mappers can drift into two output shapes, and the consumer (the raw
search API, and the FE reading `location.blockIndex`) would see one shape from the semantic leg
and another from the lexical one. These tests are that price, paid: they pin the two mappers to
one shape so the duplication stays honest.
"""

from __future__ import annotations

from app.ports.vector_store import EntityVectorRecord, VectorHit
from app.search.retriever import passage_to_hit, vector_hit_to_raw_hit


def _passage_attrs(**over):
    a = {
        "text": "the sect elder turned",
        "source_id": "chapter-1",
        "source_type": "chapter",
        "chunk_index": 2,
        "chapter_index": 5,
        "canon": True,
        "source_lang": "zh",
        "block_index": 11,
        "is_hub": False,
    }
    a.update(over)
    return a


def _hit(**over):
    return VectorHit(
        record_id="passage-1", score=0.87, scope="passage", attributes=_passage_attrs(**over),
    )


class _FakePassage:
    """The Neo4j-shaped model `passage_to_hit` consumes. Built here rather than imported so
    the shape comparison below is between the two MAPPERS, not between two constructors."""

    def __init__(self, a):
        self.source_id = a["source_id"]
        self.chapter_index = a["chapter_index"]
        self.canon = a["canon"]
        self.source_lang = a["source_lang"]
        self.text = a["text"]
        self.chunk_index = a["chunk_index"]
        self.block_index = a["block_index"]


class _FakeSearchHit:
    def __init__(self, a, score):
        self.passage = _FakePassage(a)
        self.raw_score = score


def test_the_two_mappers_agree_field_for_field():
    """The whole justification for forking rests on this.

    If the vector mapper drifts, the semantic leg and the lexical leg start answering the same
    API with different shapes — and the FE reads `location.blockIndex` to jump to a block, so
    the drift shows up as a reader landing in the wrong place, not as an error.
    """
    attrs = _passage_attrs()
    vector = vector_hit_to_raw_hit(_hit())
    lexical = passage_to_hit(_FakeSearchHit(attrs, 0.87), match_type="semantic")

    assert vector.keys() == lexical.keys(), (
        f"the mappers produce different top-level fields:\n"
        f"  vector={sorted(vector)}\n  lexical={sorted(lexical)}"
    )
    assert vector["location"].keys() == lexical["location"].keys(), (
        "the mappers produce different `location` fields — the FE reads this to jump"
    )
    for k in vector:
        assert vector[k] == lexical[k], f"the mappers disagree on {k!r}: {vector[k]!r} != {lexical[k]!r}"


def test_block_index_survives_the_port():
    """The gap the plan named. `block_index` is what turns a hit into a PRECISE jump; without
    it every semantic hit lands at the top of the chapter — degraded in a way nothing errors
    on, because the hit is otherwise perfectly well formed."""
    assert vector_hit_to_raw_hit(_hit())["location"]["blockIndex"] == 11
    # And an adapter that omits it degrades rather than raising — `attributes` is a plain
    # mapping by design, so a missing scope-specific key must not take out the search.
    bare = VectorHit(record_id="p", score=0.1, scope="passage", attributes={})
    assert vector_hit_to_raw_hit(bare)["location"]["blockIndex"] is None


def test_a_draft_passage_reports_its_surface():
    """`canon` gates the spoiler window. A vector hit that reported a draft as canon would
    leak unpublished text into a reader-facing answer."""
    assert vector_hit_to_raw_hit(_hit(canon=False))["surface"] == "draft"
    assert vector_hit_to_raw_hit(_hit(canon=True))["surface"] == "canon"
    # Absent reads as canon, matching `Passage.canon`'s default for legacy nodes.
    bare = VectorHit(record_id="p", score=0.1, scope="passage", attributes={})
    assert vector_hit_to_raw_hit(bare)["surface"] == "canon"


def test_match_type_still_distinguishes_the_two_legs():
    """Both legs read the same passages, so without this they both report "semantic" — the
    cosmetic mislabel the lexical mapper already carries a note about."""
    assert vector_hit_to_raw_hit(_hit())["matchType"] == "semantic"
    assert vector_hit_to_raw_hit(_hit(), match_type="lexical")["matchType"] == "lexical"


def test_missing_attributes_degrade_rather_than_raise():
    """A backend that omits a scope-specific key must produce a degraded hit, not a KeyError
    that takes out the whole search for every other result too."""
    out = vector_hit_to_raw_hit(VectorHit(record_id="p", score=0.5, scope="passage"))
    assert out["chapterId"] is None
    assert out["sortOrder"] == 0
    assert out["snippet"] is None
    assert out["score"] == 0.5


def test_entity_record_carries_lifecycle_with_safe_defaults():
    """T25b reopened T14 for these two. `project_id` scopes the search (the glossary FK is
    unique per (user, project)); `archived` keeps a retired entity out of retrieval.

    The default for `archived` is FALSE on purpose: a vector that forgot to say it was
    archived must be visible and wrong in a way somebody notices, not silently absent.
    """
    r = EntityVectorRecord(
        user_id="u", entity_id="e", embedding=[0.1],
        embedding_dim=1, embedding_model="m", embedding_version=1,
    )
    assert r.project_id is None
    assert r.archived is False

    scoped = EntityVectorRecord(
        user_id="u", entity_id="e", embedding=[0.1],
        embedding_dim=1, embedding_model="m", embedding_version=1,
        project_id="p-1", archived=True,
    )
    assert (scoped.project_id, scoped.archived) == ("p-1", True)
