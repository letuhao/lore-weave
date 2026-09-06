"""P6-DESCRIBE-NOT-RECORD — when the request names an artefact the platform can STORE, prose
about it is not an answer.

🔴 MEASURED 2026-08-23, K=5, zero errored runs, identical every run. Asked "Make the opening line
of this chapter darker — SHOW ME THE CHANGE before it goes in", the model called `book_read` and
then wrote THREE ALTERNATIVE REWRITES OUT IN THE REPLY. `propose_edit` declares "show me the
change" verbatim, and `answerable_tools` returns EXACTLY that one tool for the sentence. Nothing
else was called. What beat the tool was the model's own prose — always available, always cheaper,
and it looks like an answer.

WHY THE PROBLEM SAT OPEN WITH 3 OF 3 TOOLS `proven`. Its own status: "the problem is emptied by
RE-ATTRIBUTION rather than by enforcement ... nothing was built that DETECTS a turn answering in
prose where it could have recorded. If another tool exhibits it, this problem catches nothing."
The goal's clause is EMPTY IS NOT CLEARED, and this is the guard that closes it.

🔴 THE DANGEROUS NEIGHBOUR, AND HOW THIS STAYS AWAY FROM IT. The read-side guard
`_unanswered_data_question_reads` says in as many words that "nudging a write from a question
would be this loop's own worst defect". It is right, so the separation here is the sentence's own
grammar rather than a judgement about intent: this fires ONLY on an instruction — no trailing
question mark, no interrogative opener. "How should I make this darker?" is a question and none of
this guard's business. "Make it darker and show me the change" is an instruction naming a tool
that exists to record exactly that.
"""
from __future__ import annotations

from app.services.stream_service import _instruction_names_a_recorder

PROSE = (
    "Here are three ways the opening could land darker. First: 'The storm came down on Hollow "
    "Keep like a fist, and Aldric felt the stones shudder beneath him.' Second: 'Rain arrived "
    "with the sound of something breaking, and the Keep answered in kind.' Third: 'Aldric "
    "watched the sky close over Hollow Keep and understood, too late, what the quiet had been "
    "for.' Any of these would set a heavier tone for the chapter that follows, and I can adapt "
    "whichever you prefer to the surrounding paragraphs."
)


def _td(name, *, synonyms, tier="A"):
    return {"type": "function",
            "function": {"name": name, "description": f"{name} does a thing.",
                         "parameters": {"type": "object", "properties": {}, "required": []},
                         "_meta": {"synonyms": list(synonyms), "tier": tier}}}


CATALOG = {
    "propose_edit": _td("propose_edit",
                        synonyms=["show me the change", "suggest an edit", "rewrite this"]),
    "book_read": _td("book_read", synonyms=["read the chapter"], tier="R"),
}
INSTRUCTION = "Make the opening line of this chapter darker - show me the change before it goes in."


def _call(request, attempted=frozenset(), reply=PROSE, catalog=None):
    return _instruction_names_a_recorder(
        request, catalog_index=catalog if catalog is not None else CATALOG,
        attempted=set(attempted), reply_text=reply)


def test_the_measured_instance_is_detected():
    """The original defect: an instruction naming the recorder, nothing called, prose returned."""
    assert _call(INSTRUCTION) == ["propose_edit"]


def test_a_QUESTION_naming_the_same_tool_is_never_this_guard_s_business():
    """🔴 THE ARM THAT KEEPS THIS SAFE. The read-side guard's docstring calls nudging a write from
    a question this loop's own worst defect. A question that happens to match a recorder's
    vocabulary must produce NOTHING here."""
    assert _call("How would you show me the change to make this darker?") == []
    assert _call("Can you show me the change before it goes in?") == []
    assert _call("What change would make the opening line darker?") == []


def test_a_turn_that_called_something_is_left_alone():
    """Successes AND failures both count, exactly as the sibling guards count them: a model that
    tried and got a real error already has honest feedback."""
    assert _call(INSTRUCTION, attempted={"propose_edit"}) == []
    assert _call(INSTRUCTION, attempted={"book_read"}) == []


def test_a_short_reply_is_not_the_artefact():
    """Without a length floor, every brief reply on an instruction turn reads as this defect. A
    refusal or a clarifying sentence is not 'prose instead of the record'."""
    assert _call(INSTRUCTION, reply="I can do that — which chapter?") == []


def test_a_READ_tool_matched_by_the_same_words_is_not_reported():
    """Recording is a WRITE concern. A read the turn could have made is the other guard's."""
    only_read = {"book_read": _td("book_read", synonyms=["show me the change"], tier="R")}
    assert _call(INSTRUCTION, catalog=only_read) == []


def test_an_instruction_naming_no_recorder_reports_nothing():
    """The surface may only be judged where the platform has declared the vocabulary. An
    instruction matching nothing is not a defect."""
    assert _call("Make me a sandwich, and be quick about it, because I am extremely hungry.") == []


def test_the_guard_is_actually_CALLED_by_the_turn_loop():
    """🔴 A DETECTOR NOTHING CALLS IS A DEAD MECHANISM, and every test above would pass with the
    wiring deleted. AST, not a substring search: grepping the name matches this docstring and the
    comment beside the call site."""
    import ast
    import inspect

    from app.services import stream_service

    tree = ast.parse(inspect.getsource(stream_service))
    called = {n.func.id for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "_instruction_names_a_recorder" in called, (
        "_instruction_names_a_recorder is defined but never CALLED — P6's invariant is detected "
        "by nothing, which is the state its own cleared_note described"
    )
