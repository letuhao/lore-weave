"""Track A / WS-1a — tool_list + tool_load + the labeled visible-set (contracts.md C1/C2).

Pure functions (no DB/port) — no xdist_group mark needed.
"""

import app.services.tool_discovery as td


def _tool(name, desc="", *, tier="R", visibility=None, superseded_by=None, parameters=None):
    meta = {"tier": tier}
    if visibility:
        meta["visibility"] = visibility
    if superseded_by:
        meta["superseded_by"] = superseded_by
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": parameters or {"type": "object", "properties": {}},
            "_meta": meta,
        },
    }


CAT = [
    _tool("glossary_propose_entities", "Add entities", tier="A"),
    _tool(
        "glossary_propose_new_entity",
        "Legacy add-entity",
        tier="A",
        visibility="legacy",
        superseded_by="glossary_propose_entities",
    ),
    _tool("book_create", "Create a book", tier="A",
          parameters={"type": "object", "properties": {"title": {"type": "string"}}}),
    _tool("lore_enrichment_auto_enrich", "Enrich lore", tier="A"),
]


class TestLoreAlias:
    def test_lore_prefix_folds_into_glossary(self):
        assert td._domain_of("lore_enrichment_auto_enrich") == "glossary"

    def test_lore_tool_lists_under_glossary(self):
        names = [t["name"] for t in td.tool_list_result(CAT, "glossary")["tools"]]
        assert "lore_enrichment_auto_enrich" in names


class TestResearchCategoryAndPaid:
    """Track D Wave 0 (CD1 + CD5 / C1 += research)."""

    _WEB = _tool("web_search", "Search the open web", tier="R")

    def test_web_prefix_folds_into_research(self):
        # `web_search` has prefix "web" — it must resolve to the `research` domain,
        # NOT `knowledge` (that is the INTERNAL KG; web search is EXTERNAL retrieval).
        assert td._domain_of("web_search") == "research"

    def test_research_is_in_the_closed_category_enum(self):
        assert "research" in td.CATEGORY_ENUM
        assert "research" in td.GROUP_DIRECTORY

    def test_web_search_lists_under_research_not_knowledge(self):
        cat = [*CAT, self._WEB]
        assert "web_search" in [t["name"] for t in td.tool_list_result(cat, "research")["tools"]]
        assert "web_search" not in [t["name"] for t in td.tool_list_result(cat, "knowledge")["tools"]]

    def test_tool_paid_reads_meta_paid(self):
        # absent ⇒ free (a tool that doesn't declare a cost is assumed free)
        assert td.tool_paid(self._WEB) is False
        paid = _tool("web_search", tier="R")
        paid["function"]["_meta"]["paid"] = True
        assert td.tool_paid(paid) is True

    def test_paid_is_orthogonal_to_tier(self):
        # CD1: a PAID READ stays tier R — spend governs money, tier governs mutation.
        paid = _tool("web_search", tier="R")
        paid["function"]["_meta"]["paid"] = True
        assert td.tool_paid(paid) is True
        assert td.tool_tier(paid) == "R"


class TestVisibleTools:
    def test_labels_legacy_not_drops(self):
        vt = {t["name"]: t for t in td.visible_tools(CAT, "glossary")}
        assert "glossary_propose_new_entity" in vt  # NOT dropped
        assert vt["glossary_propose_new_entity"]["deprecated"] is True
        assert vt["glossary_propose_new_entity"]["superseded_by"] == "glossary_propose_entities"
        # a live (non-legacy) tool carries no deprecated flag
        assert "deprecated" not in vt["glossary_propose_entities"]

    def test_include_deprecated_false_filters(self):
        names = [t["name"] for t in td.visible_tools(CAT, "glossary", include_deprecated=False)]
        assert "glossary_propose_new_entity" not in names
        assert "glossary_propose_entities" in names

    def test_carries_tier(self):
        vt = {t["name"]: t for t in td.visible_tools(CAT, "book")}
        assert vt["book_create"]["tier"] == "A"


class TestToolListResult:
    def test_category_flat_list_with_count(self):
        p = td.tool_list_result(CAT, "book")
        assert p["category"] == "book"
        assert p["count"] == 1
        assert p["tools"][0]["name"] == "book_create"

    def test_empty_category_gets_reason(self):
        p = td.tool_list_result(CAT, "jobs")
        assert p["count"] == 0
        assert "reason" in p

    def test_all_is_grouped_by_category(self):
        p = td.tool_list_result(CAT)  # omitted == all
        assert p["count"] == 4
        assert set(p["categories"]) == {"glossary", "book"}  # lore folded into glossary
        assert len(p["categories"]["glossary"]) == 3


class TestToolLoadResult:
    def test_by_name_returns_schema_and_tier(self):
        payload, names = td.tool_load_result(CAT, name="book_create")
        assert names == ["book_create"]
        t = payload["tools"][0]
        assert t["input_schema"]["properties"] == {"title": {"type": "string"}}
        assert t["tier"] == "A"

    def test_unknown_name_reported_not_dropped(self):
        payload, names = td.tool_load_result(CAT, names=["book_create", "does_not_exist"])
        assert names == ["book_create"]
        assert payload["not_found"] == ["does_not_exist"]

    def test_by_category_loads_all_including_labeled_legacy(self):
        payload, names = td.tool_load_result(CAT, category="glossary")
        assert set(names) == {
            "glossary_propose_entities",
            "glossary_propose_new_entity",  # load does NOT drop legacy (it labels it)
            "lore_enrichment_auto_enrich",
        }
        legacy = next(t for t in payload["tools"] if t["name"] == "glossary_propose_new_entity")
        assert legacy["deprecated"] is True
        assert legacy["superseded_by"] == "glossary_propose_entities"
        assert all("input_schema" in t for t in payload["tools"])


class TestCategoryEnum:
    def test_enum_is_group_directory_plus_all(self):
        assert td.CATEGORY_ENUM == sorted(td.GROUP_DIRECTORY) + ["all"]
