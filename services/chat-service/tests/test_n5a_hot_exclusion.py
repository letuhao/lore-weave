# N5a (dogfood 2026-07-18 F3) — glossary_adopt_standards must not ride the domain hot-seed.
# It is a high-impact, book-wide, confirmation-gated tool; keeping it advertised let the
# co-writer proactively "set up the world" on a plain "write a chapter" turn. It stays reachable
# via find_tools/tool_load when the writer explicitly asks — just not on the default wire.
from app.services.tool_discovery import (
    hot_tool_names, DISCOVER_ONLY_HIGH_IMPACT,
    filter_intent_gated_setup_tools, INTENT_GATED_SETUP_TOOLS, SETUP_INTENT_SKILL,
)


def _cat(*names):
    return [{"function": {"name": n, "description": "x", "parameters": {}}} for n in names]


def _names(cat):
    return {c["function"]["name"] for c in cat}


def test_adopt_standards_excluded_from_glossary_hot_seed():
    cat = _cat("glossary_search", "glossary_adopt_standards", "glossary_propose_entities")
    hot = hot_tool_names(cat, {"glossary"})
    assert "glossary_search" in hot                 # normal glossary tools still hot
    assert "glossary_propose_entities" in hot
    assert "glossary_adopt_standards" not in hot     # the high-impact one is find_tools-only
    assert "glossary_adopt_standards" in DISCOVER_ONLY_HIGH_IMPACT


# N5a-FULL — the capability floor: high-impact setup tools are absent from the turn catalog
# (all three reach-paths: hot/find_tools/tool_load read this ONE list) UNLESS the turn is
# world-setup intent (glossary_shaping injected). This is the seam that closes the tool_load leak.
def test_setup_tools_filtered_out_on_a_plain_write_turn():
    cat = _cat("glossary_search", "glossary_propose_entities",
               "glossary_adopt_standards", "glossary_plan", "book_chapter_create")
    filtered = filter_intent_gated_setup_tools(cat, injected_skill_codes=["glossary", "co_write"])
    names = _names(filtered)
    # request-scoped tools + unrelated tools survive
    assert "glossary_search" in names
    assert "glossary_propose_entities" in names
    assert "book_chapter_create" in names
    # high-impact world-setup tools are GONE (unreachable via any path)
    assert "glossary_adopt_standards" not in names
    assert "glossary_plan" not in names


def test_setup_tools_present_when_setup_intent():
    cat = _cat("glossary_search", "glossary_adopt_standards", "glossary_plan")
    # glossary_shaping injected == the turn IS world-setup (pinned or intent-router match)
    filtered = filter_intent_gated_setup_tools(cat, injected_skill_codes=["glossary", SETUP_INTENT_SKILL])
    assert _names(filtered) == {"glossary_search", "glossary_adopt_standards", "glossary_plan"}


def test_gated_set_is_the_bulk_ontology_builders_not_single_entity_writes():
    # request-scoped single writes must NOT be gated (the writer's direct asks)
    assert "glossary_adopt_standards" in INTENT_GATED_SETUP_TOOLS
    assert "glossary_propose_entities" not in INTENT_GATED_SETUP_TOOLS  # "add Kaila" stays autonomous
    assert "glossary_search" not in INTENT_GATED_SETUP_TOOLS
