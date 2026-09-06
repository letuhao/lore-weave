"""T16-D1 — the right id under the wrong KEY.

`_coerce_listed_scalar_ids` fixes a wrong VALUE shape under the right key. This is the mirror
case, and it is the larger population.

MEASURED 2026-08-09/10: `book_read` refused 89 calls for a missing `book_id`. Only 33 of those
were genuinely empty. The other 56 CARRIED THE CORRECT UUID:

    {"id": "019fccd7-…"}          19 calls
    {"ids": ["019fccd7-…"]}       13 calls
    {"book_ids": ["019fccd7-…"]}   8 calls
    {"params": {"book_id": …}}    14 calls

The model had the id — it had just read it out of `book_list` — and named the field wrongly. The
runtime answered "'book_read' is missing ['book_id'], and this is NOT yours to invent", which is
true of the FIELD and false of the SITUATION.

The repair DECLINES anything it cannot reason about, the same rule the rest of this family
follows, because a wrong graft corrupts a call instead of refusing it.
"""
from __future__ import annotations

import pytest

from app.services.stream_service import _repair_aliased_required_id, _unwrap_wrapped_args

BOOK = "019fccd7-299f-709a-8f9d-19af9cd68c20"


def _spec(props: dict, required: list[str]) -> dict:
    return {"function": {"parameters": {"type": "object", "properties": props, "required": required}}}


BOOK_READ = _spec({"book_id": {"type": "string"}, "chapter_id": {"type": "string"},
                   "offset": {"type": "integer"}}, ["book_id"])


@pytest.mark.parametrize("sent", [{"id": BOOK}, {"ids": [BOOK]}, {"book_ids": [BOOK]}])
def test_the_measured_shapes_are_repaired(sent):
    assert _repair_aliased_required_id(sent, BOOK_READ)["book_id"] == BOOK


def test_the_params_envelope_is_unwrapped():
    """The fourth measured shape, fixed by the wrapper helper this repair runs after."""
    flat = _unwrap_wrapped_args({"params": {"book_id": BOOK}}, BOOK_READ)
    assert flat == {"book_id": BOOK}


def test_the_donor_key_is_removed_not_duplicated():
    out = _repair_aliased_required_id({"id": BOOK, "offset": 2}, BOOK_READ)
    assert out == {"book_id": BOOK, "offset": 2}


def test_a_genuinely_empty_call_is_still_refused():
    """CONTROL — 33 of the 89 really had nothing, and inventing an id is the one thing the
    runtime's own message rightly forbids."""
    assert _repair_aliased_required_id({}, BOOK_READ) == {}


def test_a_wellformed_call_is_untouched():
    args = {"book_id": BOOK, "chapter_id": "019ff8f5-ee89-75ef-a894-ff9462332bc0"}
    assert _repair_aliased_required_id(dict(args), BOOK_READ) == args


def test_a_tool_that_really_declares_the_donor_key_keeps_it():
    """CONTROL. `book_list` legitimately takes `kind`; a tool that legitimately takes `ids` must
    never have it eaten. The declared-property check is what makes this safe to run everywhere."""
    spec = _spec({"book_id": {"type": "string"}, "ids": {"type": "array"}}, ["book_id"])
    sent = {"ids": [BOOK]}
    assert _repair_aliased_required_id(sent, spec) == sent


def test_a_multi_element_list_is_a_real_collection():
    other = "019ff8f5-ae59-71f9-acb9-ad607b363ef7"
    sent = {"ids": [BOOK, other]}
    assert _repair_aliased_required_id(sent, spec_two()) == sent


def spec_two() -> dict:
    return BOOK_READ


def test_two_missing_required_ids_is_a_guess_and_declines():
    """With two candidates the runtime cannot know which one the donor meant, and §3a's rule is
    that a guess may not decide a correctness question."""
    spec = _spec({"book_id": {"type": "string"}, "project_id": {"type": "string"}},
                 ["book_id", "project_id"])
    sent = {"id": BOOK}
    assert _repair_aliased_required_id(sent, spec) == sent


def test_two_donor_keys_at_once_declines():
    other = "019ff8f5-ae59-71f9-acb9-ad607b363ef7"
    sent = {"id": BOOK, "ids": [other]}
    assert _repair_aliased_required_id(sent, spec_two()) == sent


@pytest.mark.parametrize("bad", [{"id": ""}, {"id": "   "}, {"id": 7}, {"id": None},
                                 {"id": {"book_id": BOOK}}, {"ids": []}])
def test_an_unusable_donor_value_declines(bad):
    assert _repair_aliased_required_id(bad, spec_two()) == bad


def test_no_tool_def_means_no_repair():
    """Schema-free paths (resume/execute) must not guess without the declaration to check."""
    sent = {"id": BOOK}
    assert _repair_aliased_required_id(sent, None) == sent


def test_a_non_id_required_param_is_not_a_target():
    """The rule is scoped to `*_id` params; a required `query` must never be filled from `id`."""
    spec = _spec({"query": {"type": "string"}}, ["query"])
    sent = {"id": BOOK}
    assert _repair_aliased_required_id(sent, spec) == sent


def test_the_repair_is_actually_WIRED_into_the_dispatch():
    """CALL-SITE guard. Every test above exercises the helper directly and would stay green if
    the dispatch never called it — the unwired-fix shape this loop has already been bitten by.
    Assert the shipped dispatch reassigns `args_obj` from this helper."""
    import ast
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[1]
           / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "args_obj" for t in node.targets):
            continue
        call = node.value
        if (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                and call.func.id == "_repair_aliased_required_id"):
            return
    raise AssertionError(
        "stream_service.py never assigns args_obj from _repair_aliased_required_id — the repair "
        "exists but the dispatch does not use it, so every measured shape still refuses (T16-D1)"
    )


def test_params_is_among_the_unwrapped_envelope_keys():
    """The 14-call shape is fixed in the sibling helper; guard it here so both halves of the
    measured population stay covered by one file."""
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[1]
           / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
    assert '"args", "arguments", "params"' in src, (
        "`params` left the envelope-key set — the 14 measured {\"params\": {...}} calls stop "
        "being unwrapped (T16-D1)"
    )
