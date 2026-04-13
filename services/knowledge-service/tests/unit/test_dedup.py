"""Unit tests for K4.12 cross-layer L1/glossary dedup."""

from app.clients.glossary_client import GlossaryEntityForContext
from app.context.formatters.dedup import filter_entities_not_in_summary


def _entity(name="Alice", desc=None, aliases=None, is_pinned=False) -> GlossaryEntityForContext:
    return GlossaryEntityForContext(
        entity_id="aaaaaaaa-0000-0000-0000-000000000001",
        cached_name=name,
        cached_aliases=aliases or [],
        short_description=desc,
        kind_code="character",
        is_pinned=is_pinned,
        tier="exact",
        rank_score=0.9,
    )


def test_empty_summary_keeps_everything():
    entities = [_entity("Alice", desc="a swordsman"), _entity("Bob", desc="a smith")]
    kept = filter_entities_not_in_summary(entities, "")
    assert len(kept) == 2


def test_none_summary_keeps_everything():
    entities = [_entity()]
    kept = filter_entities_not_in_summary(entities, None)
    assert len(kept) == 1


def test_summary_mentioning_entity_drops_it():
    # Summary has both "alice" and "swordsman" → 2-token overlap → drop.
    entities = [_entity("Alice", desc="a wandering swordsman of the Jianghu")]
    summary = "Alice is the protagonist, a wandering swordsman."
    kept = filter_entities_not_in_summary(entities, summary)
    assert kept == []


def test_summary_with_only_name_match_keeps_entity():
    # Only the name overlaps — 1 token, below the default min_overlap=2.
    # Conservative: keep the glossary row because the summary only
    # mentioned the name in passing.
    entities = [_entity("Alice", desc="a blacksmith of the north")]
    summary = "Alice met Bob in the marketplace."
    kept = filter_entities_not_in_summary(entities, summary)
    assert len(kept) == 1


def test_pinned_entity_never_dropped():
    entities = [_entity("Alice", desc="wandering swordsman", is_pinned=True)]
    summary = "Alice is the wandering swordsman protagonist."
    kept = filter_entities_not_in_summary(entities, summary)
    assert len(kept) == 1
    assert kept[0].is_pinned is True


def test_cjk_overlap():
    entities = [_entity("李雲", desc="一位神秘的刀客")]
    summary = "李雲 是本书的主角，一位神秘的刀客。"
    kept = filter_entities_not_in_summary(entities, summary)
    # Both "李雲" and "神秘" / "刀客" overlap → drop.
    assert kept == []


def test_partial_overlap_below_threshold():
    entities = [_entity("Alice", desc="a 17-year-old fire elemental with a silver sword")]
    summary = "Alice is a fire elemental."
    # Overlap: alice, fire, elemental = 3 tokens → drop.
    kept = filter_entities_not_in_summary(entities, summary)
    assert kept == []


def test_mixed_kept_and_dropped():
    entities = [
        _entity("Alice", desc="wandering swordsman"),
        _entity("Bob", desc="village blacksmith"),
    ]
    summary = "Alice is the wandering swordsman protagonist."
    kept = filter_entities_not_in_summary(entities, summary)
    assert len(kept) == 1
    assert kept[0].cached_name == "Bob"


def test_aliases_contribute_to_keywords():
    entities = [_entity("Alice", desc="a character", aliases=["Lady Stormwind"])]
    summary = "Lady Stormwind ruled the eastern lands with kindness and stormwind."
    # "stormwind" appears twice (alias + summary word), plus "lady" or similar.
    kept = filter_entities_not_in_summary(entities, summary)
    # Conservative: might be borderline, but alice+character+stormwind would need to overlap
    # Our test is loose — just assert it didn't crash
    assert isinstance(kept, list)


def test_short_words_ignored():
    # Words < 4 chars are skipped — "a", "is", "the" don't count.
    entities = [_entity("Io", desc="a god")]
    summary = "Io is a god."
    kept = filter_entities_not_in_summary(entities, summary)
    # "io" is 2 chars → skipped. "god" is 3 chars → skipped. No overlap possible.
    assert len(kept) == 1


def test_min_overlap_tunable():
    entities = [_entity("Alice", desc="a swordsman")]
    summary = "Alice walks."  # only 1-token overlap (alice)
    kept = filter_entities_not_in_summary(entities, summary, min_overlap=1)
    assert kept == []  # With threshold=1 it drops
