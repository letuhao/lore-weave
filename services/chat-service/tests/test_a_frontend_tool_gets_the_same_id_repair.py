"""A FRONTEND tool must get the same non-identifier repair the backend dispatch gives.

🔴 MEASURED 2026-08-23. composition_entity_override_edit at K=5: the model called
`glossary_propose_entity_edit` with entity_id="Aldric Vane" — a NAME — on all five runs, and the
name-repair sentence fired ZERO times in the entire batch. That tool is a FRONTEND tool, and the
frontend branch returns ABOVE the backend dispatch where the whole argument-repair chain lives.

This is the third time the same divergence has been paid for, and the file already records the
other two: the context-id injector missed this branch (D-FE-TOOL-CONTEXT-IDS), and CP-5.3's
resolver became unreachable through it (DQ-5). Each repair has been hand-ported the run after it
was found missing — wrap-repair, then context ids, then schema validation. This is the next arm.
"""
from app.services.stream_service import _invented_supplier_ids, _name_like_dropped_ids

# glossary_propose_entity_edit's shape: an *_id the model is meant to have looked up.
_FE_PROPS = {"entity_id": {"type": "string", "description": "the glossary entity's id"}}


def test_a_name_in_a_frontend_tools_id_is_dropped():
    args = {"entity_id": "Aldric Vane"}
    assert _invented_supplier_ids(args, None, _FE_PROPS) == ["entity_id"]


def test_the_dropped_name_comes_back_as_the_query():
    msg = _name_like_dropped_ids({"entity_id": "Aldric Vane"})
    assert "Aldric Vane" in msg
    assert "NAME" in msg


def test_a_real_uuid_on_a_frontend_tool_is_untouched():
    args = {"entity_id": "019ebb72-27a2-72f3-a42d-d2d0e0ded179"}
    assert _invented_supplier_ids(args, None, _FE_PROPS) == []


def test_a_context_id_on_a_frontend_tool_is_still_exempt():
    """The runtime injects book_id into frontend tools too — it must not be dropped from under it."""
    assert _invented_supplier_ids({"book_id": "Ashfall"}, None,
                                  {"book_id": {"type": "string"}}) == []
