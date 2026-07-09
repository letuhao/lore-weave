"""S02 fix — deterministic context-id injection into backend tool args.

The measured live blocker: a mid-tier model (gemma-4-26b) calls glossary_*/kg_* with `{}`
because the book_id is only a prose note, never filled into args → VALIDATION-loop. The
server knows the id; `_inject_context_ids` supplies it. Pure helper, no DB.
"""

import app.services.stream_service as ss


def _tool(name, props):
    return {"function": {"name": name, "parameters": {"type": "object", "properties": props}}}


def test_fills_missing_book_id():
    td = _tool("glossary_propose_entities", {"book_id": {"type": "string"}, "kind": {"type": "string"}})
    args: dict = {}
    ss._inject_context_ids(args, td, book_id="B1", chapter_id=None, project_id=None)
    assert args["book_id"] == "B1"


def test_does_not_override_a_model_supplied_value():
    td = _tool("x", {"book_id": {"type": "string"}})
    args = {"book_id": "OTHER"}
    ss._inject_context_ids(args, td, book_id="B1", chapter_id=None, project_id=None)
    assert args["book_id"] == "OTHER"  # respects a deliberate cross-book call


def test_only_injects_keys_the_tool_declares():
    td = _tool("x", {"book_id": {"type": "string"}})  # chapter_id/project_id NOT in schema
    args: dict = {}
    ss._inject_context_ids(args, td, book_id="B1", chapter_id="C1", project_id="P1")
    assert args == {"book_id": "B1"}  # never hand a tool an arg it would reject


def test_project_id_injected_for_kg_tool():
    td = _tool("kg_graph_query", {"project_id": {"type": "string"}})
    args: dict = {}
    ss._inject_context_ids(args, td, book_id="B1", chapter_id=None, project_id="P1")
    assert args == {"project_id": "P1"}


def test_no_tool_def_is_a_noop():
    args: dict = {}
    ss._inject_context_ids(args, None, book_id="B1", chapter_id=None, project_id=None)
    assert args == {}


def test_blank_string_arg_is_filled():
    td = _tool("x", {"book_id": {"type": "string"}})
    args = {"book_id": ""}
    ss._inject_context_ids(args, td, book_id="B1", chapter_id=None, project_id=None)
    assert args["book_id"] == "B1"


def _tool_req(name, props, required):
    td = _tool(name, props)
    td["function"]["parameters"]["required"] = required
    return td


def test_missing_required_true_when_a_required_arg_absent():
    # glossary_search needs book_id + query; book_id injected but query still absent.
    td = _tool_req("glossary_search", {"book_id": {}, "query": {}}, ["book_id", "query"])
    assert ss._missing_required_args({"book_id": "B1"}, td) is True


def test_missing_required_false_when_all_satisfied():
    # ontology_read needs only book_id — a valid call must NOT be cap-blocked.
    td = _tool_req("glossary_book_ontology_read", {"book_id": {}}, ["book_id"])
    assert ss._missing_required_args({"book_id": "B1"}, td) is False


def test_missing_required_unknown_tool_never_blocks():
    assert ss._missing_required_args({}, None) is False
