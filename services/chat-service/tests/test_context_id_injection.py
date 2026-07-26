"""S02 fix — deterministic context-id injection into backend tool args.

The measured live blocker: a mid-tier model (gemma-4-26b) calls glossary_*/kg_* with `{}`
because the book_id is only a prose note, never filled into args → VALIDATION-loop. The
server knows the id; `_inject_context_ids` supplies it. Pure helper, no DB.
"""

import json
from uuid import UUID

import app.services.stream_service as ss


def _tool(name, props, meta=None):
    fn = {"name": name, "parameters": {"type": "object", "properties": props}}
    if meta is not None:
        fn["_meta"] = meta
    return {"function": fn}


def test_ambient_book_tool_does_NOT_backfill_book_id():
    # Studio context binding (2026-07-22): an ambient_book tool resolves book_id from the envelope
    # (X-Book-Id) server-side, so injection must NOT fill it as an arg (else scope_source reads "arg").
    td = _tool(
        "book_structure_edit",
        {"book_id": {"type": "string"}, "op": {"type": "string"}},
        meta={"tier": "A", "scope": "book", "ambient_book": True},
    )
    args: dict = {"op": "create_part"}
    ss._inject_context_ids(args, td, book_id="B1", chapter_id="C1", project_id="P1")
    assert "book_id" not in args  # left for the envelope to resolve


def test_ambient_book_tool_STILL_backfills_project_id():
    # Only book_id is ambient; chapter_id/project_id still backfill as before.
    td = _tool(
        "book_structure_edit",
        {"book_id": {"type": "string"}, "project_id": {"type": "string"}},
        meta={"ambient_book": True},
    )
    args: dict = {}
    ss._inject_context_ids(args, td, book_id="B1", chapter_id=None, project_id="P1")
    assert "book_id" not in args
    assert args["project_id"] == "P1"


def test_ambient_project_tool_does_NOT_backfill_project_id():
    # composition: an ambient_project tool resolves project_id from the envelope (X-Project-Id).
    td = _tool(
        "composition_arc_get",
        {"project_id": {"type": "string"}, "arc_id": {"type": "string"}},
        meta={"tier": "R", "scope": "project", "ambient_project": True},
    )
    args: dict = {"arc_id": "A1"}
    ss._inject_context_ids(args, td, book_id="B1", chapter_id=None, project_id="P1")
    assert "project_id" not in args  # left for the envelope to resolve
    # book_id still backfills unless ALSO ambient_book (it's not declared here anyway)


def test_non_ambient_tool_still_backfills_book_id():
    # A tool WITHOUT the flag keeps the S02 behavior (book_id backfilled).
    td = _tool("book_chapter_save_draft", {"book_id": {"type": "string"}}, meta={"tier": "A", "scope": "book"})
    args: dict = {}
    ss._inject_context_ids(args, td, book_id="B1", chapter_id=None, project_id=None)
    assert args["book_id"] == "B1"


def test_fills_missing_book_id():
    td = _tool("glossary_propose_entities", {"book_id": {"type": "string"}, "kind": {"type": "string"}})
    args: dict = {}
    ss._inject_context_ids(args, td, book_id="B1", chapter_id=None, project_id=None)
    assert args["book_id"] == "B1"


def test_does_not_override_a_model_supplied_value():
    # A deliberate cross-book call must survive. The fixture is now a REAL uuid: the old one
    # ("OTHER") was a placeholder, and a book_id is always a uuid — so it could not actually
    # stand for the cross-book case it was written to protect, and it was the only thing
    # asserting that a MISTRANSCRIBED uuid gets passed through to a 400 (see below).
    td = _tool("x", {"book_id": {"type": "string"}})
    other = "019f0000-0000-7000-8000-000000000000"
    args = {"book_id": other}
    ss._inject_context_ids(
        args, td, book_id="019f5239-3f0d-7ad7-8fff-edd7176d056e",
        chapter_id=None, project_id=None,
    )
    assert args["book_id"] == other  # respects a deliberate cross-book call


def test_overrides_a_MALFORMED_model_supplied_id():
    # Measured 2026-07-11 (S06): gemma called glossary_propose_entities with the turn's real
    # book_id plus one extra character ("…056e6") and the tool 400'd "book_id must be a UUID"
    # — then repeated the identical corruption on a later turn. A mid-tier model cannot
    # reliably transcribe a 36-char uuid. A malformed value cannot be a deliberate cross-book
    # call, so the id the SERVER already knows wins.
    td = _tool("x", {"book_id": {"type": "string"}})
    real = "019f5239-3f0d-7ad7-8fff-edd7176d056e"
    args = {"book_id": real + "6"}
    ss._inject_context_ids(args, td, book_id=real, chapter_id=None, project_id=None)
    assert args["book_id"] == real


# ── UUID-object coercion (found live 2026-07-25 — a 500 that crashed the whole turn) ──
# `session_row["project_id"]` arrives from asyncpg as a uuid.UUID OBJECT, not a str, and
# `args_obj` is JSON-serialized twice downstream (MCP wire + tool_calls_history at persist).
# An un-coerced UUID there raised `TypeError: Object of type UUID is not JSON serializable`
# and 500'd the turn (seen when the model mistranscribed project_id → the substitute branch
# put the UUID object into args). Every injected id must be a JSON-serializable string.

def test_backfilled_uuid_OBJECT_is_stringified():
    td = _tool("kg_project_entities_to_nodes", {"project_id": {"type": "string"}})
    args: dict = {}
    pid = UUID("019f99c8-52c6-7cca-ada5-f7229f9ea5a7")
    ss._inject_context_ids(args, td, book_id=None, chapter_id=None, project_id=pid)
    assert args["project_id"] == str(pid)
    assert isinstance(args["project_id"], str)
    json.dumps(args)  # must not raise (this is the exact serialization that 500'd the turn)


def test_substituted_uuid_OBJECT_over_a_mistranscription_is_stringified():
    td = _tool("kg_project_entities_to_nodes", {"project_id": {"type": "string"}})
    pid = UUID("019f99c8-52c6-7cca-ada5-f7229f9ea5a7")
    # the model mistranscribed project_id (a char short) → the substitute branch fires
    args = {"project_id": "019f99c8-52c7-cca-ada5-f7229f9ea5a7"}
    ss._inject_context_ids(args, td, book_id=None, chapter_id=None, project_id=pid)
    assert args["project_id"] == str(pid)
    assert isinstance(args["project_id"], str)
    json.dumps(args)  # must not raise


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


def test_missing_required_names_lists_the_absent_args():
    td = _tool_req("glossary_search", {"book_id": {}, "query": {}}, ["book_id", "query"])
    assert ss._missing_required_names({"book_id": "B1"}, td) == ["query"]


def test_missing_required_names_empty_when_satisfied():
    td = _tool_req("x", {"book_id": {}}, ["book_id"])
    assert ss._missing_required_names({"book_id": "B1"}, td) == []


def test_missing_required_names_unknown_tool_empty():
    assert ss._missing_required_names({}, None) == []


# ── Studio single-book override (2026-07-25, user decision) ───────────────────
# The writing studio works ONE book/Work at a time. A book-scoped tool that is NOT
# ambient_book (e.g. plan_propose_spec) still REQUIRES book_id, but the studio prompt
# tells the model not to pass one — so a weak model invents a VALID-but-WRONG book_id,
# which the tool's grant-gate then refuses ("not found or not accessible"). On a studio
# turn a book_id that differs from the studio's book is a hallucination, so it is
# overridden to the studio's book. OFF a studio turn a different valid book_id is still
# honored (a real cross-book call — see test_does_not_override_a_model_supplied_value).

_AMBIENT = "019f5239-3f0d-7ad7-8fff-edd7176d056e"
_WRONG = "019f0000-0000-7000-8000-000000000000"


def test_studio_overrides_a_mismatched_valid_book_id():
    td = _tool("plan_propose_spec", {"book_id": {"type": "string"}})
    args = {"book_id": _WRONG}
    ss._inject_context_ids(args, td, book_id=_AMBIENT, chapter_id=None, project_id=None, studio=True)
    assert args["book_id"] == _AMBIENT  # hallucinated cross-book target corrected


def test_non_studio_still_preserves_a_cross_book_id():
    td = _tool("plan_propose_spec", {"book_id": {"type": "string"}})
    args = {"book_id": _WRONG}
    ss._inject_context_ids(args, td, book_id=_AMBIENT, chapter_id=None, project_id=None, studio=False)
    assert args["book_id"] == _WRONG  # off-studio: a deliberate cross-book call survives


def test_studio_leaves_a_matching_book_id_untouched():
    td = _tool("plan_propose_spec", {"book_id": {"type": "string"}})
    args = {"book_id": _AMBIENT}
    ss._inject_context_ids(args, td, book_id=_AMBIENT, chapter_id=None, project_id=None, studio=True)
    assert args["book_id"] == _AMBIENT


def test_studio_drops_a_mismatched_book_id_on_an_ambient_book_tool():
    # ambient_book tools resolve book_id from X-Book-Id; a mismatched supplied one is dropped
    # so the envelope's ambient book wins (not the hallucinated arg).
    td = _tool("book_structure_edit", {"book_id": {"type": "string"}}, meta={"ambient_book": True})
    args = {"book_id": _WRONG, "op": "create_part"}
    ss._inject_context_ids(args, td, book_id=_AMBIENT, chapter_id=None, project_id=None, studio=True)
    assert "book_id" not in args  # dropped → envelope resolves the studio's book
