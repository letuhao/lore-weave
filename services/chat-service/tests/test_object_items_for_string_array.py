"""TOOL DEEP-DIVE `glossary_propose_curation` — objects where the schema declares strings.

🔴 MEASURED LIVE 2026-08-12 (journey `entity-triage`, book 019ff4cf) and reproduced deliberately on
2026-08-13 against the deployed catalogue: the tool was called with op='status_change',
status='active' and `entity_ids` holding OBJECTS —

    [{"entity_id": "019ff551-…", "status": "active"}, …]

— where the schema declares an array of STRINGS. The validator refuses it before the tool runs, and
the journey ended with all 11 entities still `draft`.

Third repair in the same family: D-FJ-7 unwrapped ["vi"] for a scalar, T2-D3 stringified 1 for a
string, this one unwraps a single-meaningful-key object for an array-of-strings. Every one of them
DECLINES anything it cannot reason about, because a wrong unwrap corrupts a write instead of
refusing it.
"""

from app.services.stream_service import _unwrap_object_items_for_string_array as fix

EID = "019ff551-5000-7000-8000-000000000001"
EID2 = "019ff551-5000-7000-8000-000000000002"


def _def(props: dict) -> dict:
    return {"function": {"name": "t", "parameters": {"type": "object", "properties": props}}}


CURATION = _def({
    "op": {"type": "string"},
    "status": {"type": "string"},
    "entity_ids": {"type": ["null", "array"], "items": {"type": "string"}},
    "winner_id": {"type": "string"},
    "loser_ids": {"type": ["null", "array"], "items": {"type": "string"}},
})


def test_the_measured_call_is_repaired():
    """🔴 The exact recorded payload, including the redundant `status` echo."""
    args = {"op": "status_change", "status": "active",
            "entity_ids": [{"entity_id": EID, "status": "active"},
                           {"entity_id": EID2, "status": "active"}]}
    assert fix(args, CURATION) == ["entity_ids"]
    assert args["entity_ids"] == [EID, EID2]
    assert args["status"] == "active", "a sibling argument was disturbed"


def test_a_CONTRADICTING_echo_is_declined():
    """🔴 THE CONTROL THAT MATTERS. The measured payload echoed the sibling's value, which is
    harmless. An object that DISAGREES with its sibling is a real ambiguity about what the caller
    meant, and silently dropping the object's copy would pick one at random — on a status write."""
    args = {"op": "status_change", "status": "active",
            "entity_ids": [{"entity_id": EID, "status": "rejected"}]}
    assert fix(args, CURATION) == []
    assert args["entity_ids"] == [{"entity_id": EID, "status": "rejected"}]


def test_the_merge_arm_repairs_by_its_own_singular():
    """`loser_ids` -> `loser_id`, so the rule is not hard-coded to one parameter."""
    args = {"op": "merge", "winner_id": EID, "loser_ids": [{"loser_id": EID2}]}
    assert fix(args, CURATION) == ["loser_ids"]
    assert args["loser_ids"] == [EID2]


def test_an_object_without_the_singular_key_is_declined():
    """No singular key means this rule cannot tell which field is the id."""
    args = {"entity_ids": [{"id": EID, "status": "active"}]}
    assert fix(args, CURATION) == []


def test_a_MIXED_list_is_declined():
    """Half strings, half objects is a shape the rule cannot reason about."""
    args = {"entity_ids": [EID, {"entity_id": EID2}]}
    assert fix(args, CURATION) == []


def test_a_plain_string_array_is_untouched():
    """The correct call must pass through byte-identical."""
    args = {"entity_ids": [EID, EID2]}
    assert fix(args, CURATION) == []
    assert args["entity_ids"] == [EID, EID2]


def test_an_array_of_OBJECTS_by_schema_is_never_unwrapped():
    """When the schema really wants objects, unwrapping them would destroy the payload."""
    spec = _def({"items_": {"type": "array", "items": {"type": "object"}}})
    args = {"items_": [{"item_": "x"}]}
    assert fix(args, spec) == []


def test_an_empty_or_blank_id_is_declined():
    args = {"entity_ids": [{"entity_id": "   "}]}
    assert fix(args, CURATION) == []


def test_the_repair_is_actually_WIRED_INTO_dispatch():
    """Guard the CALL SITE: every assertion above passes against a repair that is never called."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "app" / "services" / "stream_service.py"
    body = src.read_text(encoding="utf-8").replace("\r\n", "\n")
    call = "_objs = _unwrap_object_items_for_string_array(args_obj, _tool_def_for_args)"
    assert call in body, "the repair is defined but never called"
    assert body.index(call) < body.index("_missing_args ="), (
        "the repair runs after the missing-argument interception, so the call is already refused"
    )
