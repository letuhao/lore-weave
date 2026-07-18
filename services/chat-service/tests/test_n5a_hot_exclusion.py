# N5a (dogfood 2026-07-18 F3) — glossary_adopt_standards must not ride the domain hot-seed.
# It is a high-impact, book-wide, confirmation-gated tool; keeping it advertised let the
# co-writer proactively "set up the world" on a plain "write a chapter" turn. It stays reachable
# via find_tools/tool_load when the writer explicitly asks — just not on the default wire.
from app.services.tool_discovery import hot_tool_names, DISCOVER_ONLY_HIGH_IMPACT


def _cat(*names):
    return [{"function": {"name": n, "description": "x", "parameters": {}}} for n in names]


def test_adopt_standards_excluded_from_glossary_hot_seed():
    cat = _cat("glossary_search", "glossary_adopt_standards", "glossary_propose_entities")
    hot = hot_tool_names(cat, {"glossary"})
    assert "glossary_search" in hot                 # normal glossary tools still hot
    assert "glossary_propose_entities" in hot
    assert "glossary_adopt_standards" not in hot     # the high-impact one is find_tools-only
    assert "glossary_adopt_standards" in DISCOVER_ONLY_HIGH_IMPACT
