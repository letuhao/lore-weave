"""TOOL DEEP-DIVE `kg_project_set_embedding_model` (T6-D1) — an id carrying its own field name.

🔴 MEASURED LIVE 2026-08-13. The tool was called with
embedding_model="user_model_id:019e7f71-0271-722f-9c9c-3f049c0b26f4" and refused "invalid
model_ref". CONTROL: the same id WITHOUT the prefix is accepted — the project then carried
embedding_model=019eeb08-8bff-75cb-8e86-700efd4033b5 with embedding_dimension=1024. So the value
was right and only its FORM was wrong. This is what blocked kg_build (cycle 5).

THE ROOT IS NOT A HALLUCINATION. `settings_list_models` — the tool this one's own refusal points the
caller to — returns each model as an object whose id sits under the KEY `user_model_id`:
{..., "user_model_id": "019ebb72-…", "provider_model_name": …}. The model read the field name and
emitted KEY:VALUE. The id was present and correct; it serialised the pair.

Fifth shape in the argument-form family after ["vi"] for a scalar, 1 for a string, and objects for
an array of strings.
"""

from app.services.stream_service import _strip_field_name_prefix_from_ids as fix

UID = "019e7f71-0271-722f-9c9c-3f049c0b26f4"


def _def(props: dict) -> dict:
    return {"function": {"name": "t", "parameters": {"type": "object", "properties": props}}}


KG = _def({
    "project_id": {"type": "string"},
    "embedding_model": {"type": "string"},
    "note": {"type": "string"},
    "count": {"type": "integer"},
    "payload": {"type": ["string", "object"]},
})


def test_the_measured_call_is_repaired():
    """🔴 The exact recorded argument."""
    args = {"project_id": "019ff8f6-2a59-7dad-bfe5-f1b2b445e75c",
            "embedding_model": f"user_model_id:{UID}"}
    assert fix(args, KG) == ["embedding_model"]
    assert args["embedding_model"] == UID
    assert args["project_id"] == "019ff8f6-2a59-7dad-bfe5-f1b2b445e75c", "a sibling was disturbed"


def test_a_bare_uuid_is_untouched():
    args = {"embedding_model": UID}
    assert fix(args, KG) == []
    assert args["embedding_model"] == UID


def test_prose_containing_a_colon_is_never_cut():
    """THE CONTROL THAT MATTERS. A colon is ordinary punctuation; only `<identifier>:<uuid>` is this
    mistake. Cutting a title in half would corrupt a write rather than refuse it."""
    for v in ("chapter 3: the flood", "https://example.com/x", "note: see " + UID,
              f"user model id:{UID}", f":{UID}", f"user_model_id:{UID}extra"):
        args = {"note": v}
        assert fix(args, KG) == [], v
        assert args["note"] == v


def test_a_prefix_whose_tail_is_not_a_uuid_is_declined():
    args = {"note": "user_model_id:not-a-uuid-at-all-really-no"}
    assert fix(args, KG) == []


def test_a_param_that_also_accepts_an_object_is_declined():
    """A union with a non-string branch is not this mistake."""
    args = {"payload": f"user_model_id:{UID}"}
    assert fix(args, KG) == []


def test_a_non_string_value_is_ignored():
    args = {"count": 5}
    assert fix(args, KG) == []


def test_an_undeclared_param_is_never_touched():
    args = {"mystery": f"user_model_id:{UID}"}
    assert fix(args, KG) == []


def test_the_repair_is_actually_WIRED_INTO_dispatch():
    """Guard the CALL SITE: every assertion above passes against a repair that is never called."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "app" / "services" / "stream_service.py"
    body = src.read_text(encoding="utf-8").replace("\r\n", "\n")
    call = "_deprefixed = _strip_field_name_prefix_from_ids(args_obj, _tool_def_for_args)"
    assert call in body, "the repair is defined but never called"
    assert body.index(call) < body.index("_missing_args ="), (
        "the repair runs after the missing-argument interception, so the call is already refused"
    )
