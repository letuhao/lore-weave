"""KM5-M4a — knowledge-skill prompt tests (drift guard + surface boundary)."""

from __future__ import annotations

from app.services.knowledge_skill import KNOWLEDGE_SKILL_PROMPT


# The knowledge/graph tools the prompt instructs the LLM to call by name. If any
# is renamed in the MCP catalog, the prompt must change too — else the LLM is told
# to call a tool that no longer exists and nothing fails loudly. Catch that here.
_REFERENCED_TOOLS = [
    "memory_search", "memory_recall_entity", "memory_timeline", "memory_remember",
    "kg_graph_query", "kg_entity_edge_timeline", "kg_schema_read",
    "kg_propose_fact", "kg_propose_edge",
    "kg_adopt_template", "kg_schema_edit", "kg_sync_apply",
    "kg_triage_list", "kg_triage_resolve",
]


def test_prompt_references_every_named_tool():
    for name in _REFERENCED_TOOLS:
        assert name in KNOWLEDGE_SKILL_PROMPT, f"skill prompt is missing tool name {name!r}"


def test_prompt_states_the_trust_boundary():
    # INV-6: tool results / graph text are DATA, not instructions (injection defense).
    p = KNOWLEDGE_SKILL_PROMPT.lower()
    assert "data, not" in p or "data, never" in p
    assert "instruction" in p


def test_prompt_keeps_writes_human_gated():
    p = KNOWLEDGE_SKILL_PROMPT.lower()
    assert "confirm_token" in p
    assert "human-gated" in p or "reviewed by the user" in p or "review inbox" in p


def test_prompt_omits_admin_tools():
    # INV-T4: System-tier admin tools live ONLY on the CMS surface, never the
    # regular chat surface — they must NOT be advertised here.
    assert "kg_admin" not in KNOWLEDGE_SKILL_PROMPT
    assert "/mcp/admin" not in KNOWLEDGE_SKILL_PROMPT


def test_prompt_separates_memory_from_graph():
    # The core teaching: memory tools vs graph tools are different surfaces.
    assert "memory_search" in KNOWLEDGE_SKILL_PROMPT
    assert "kg_graph_query" in KNOWLEDGE_SKILL_PROMPT
    assert "as_of_chapter" in KNOWLEDGE_SKILL_PROMPT
