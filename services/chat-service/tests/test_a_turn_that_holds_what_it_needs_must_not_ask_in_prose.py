"""P16-PROSE-CONFIRMATION — asking for consent you already have is a turn that did not happen.

🔴 THE INVARIANT. When the user's request IS the instruction and the turn already holds every
argument the write requires, ending in prose that asks whether to proceed is not a confirmation.
The platform HAS a consent mechanism for exactly this — the Tier-A approval card — and prose asks
for consent in a channel that records nothing and gates nothing. The author answers a question
they already answered, and no card ever appears.

MEASURED, K=5, zero errored runs, identical on every run: the author said "Create the chapters —
make the plan real for this book", and the turn ran composition_package_tree ->
plan_bootstrap_propose x2 -> composition_list_outline, held a real `proposal_id`, and replied
"Would you like me to go ahead and create these chapters so we can start writing?".

WHY THE PROBLEM STAYED OPEN FOR TWELVE DAYS WITH ITS ONLY TOOL READING `proven`. The tool was made
REACHABLE; the invariant was never enforced. Its own cleared_note said so: "Nothing was built that
detects a turn holding what it needs and answering in prose. If another tool exhibits it, this
problem catches nothing." A problem emptied by re-attribution is not a problem solved.

WHAT THE DETECTOR MAY AND MAY NOT READ. Two sibling guards fire when the turn called NOTHING
(`_claimed_an_effect_without_acting`, `_rail_write_step_stalled`). This turn called four tools —
that is what makes it equipped — so the mechanical condition had to come from elsewhere, and it
comes from data the platform already declares:

    argument_emitters   plan_bootstrap_apply: {proposal_id: plan_bootstrap_propose}
    turn_succeeded      which tools actually returned a result THIS turn

"The turn holds what it needs" is therefore never inferred from the reply. The prose test decides
only whether the turn ASKED.
"""
from __future__ import annotations

from app.services.stream_service import _asked_instead_of_acting

# 🔴 `_meta` GOES INSIDE `function`, and putting it at the top level cost the first run of this
# file. `tool_meta` reads `_fn(tool_def)["_meta"]`, so a top-level block is invisible and
# `tool_tier` falls back to its safe default "R" — the guard then skipped the write correctly and
# the test read as "the detector does not work". A fixture in a shape the platform never produces
# measures the fixture. It failed loudly here, which is the good outcome; the same mistake in the
# silent direction is how a guard ships green and inert.
APPLY = {
    "type": "function",
    "function": {
        "name": "plan_bootstrap_apply",
        "description": "create the proposed chapters",
        "parameters": {"type": "object",
                       "properties": {"proposal_id": {"type": "string"}},
                       "required": ["proposal_id"]},
        "_meta": {"tier": "A"},
    },
}
READ = {
    "type": "function",
    "function": {"name": "composition_list_outline", "description": "read",
                 "parameters": {"type": "object", "properties": {}, "required": []},
                 "_meta": {"tier": "R"}},
}
#: An ambient-only write: every required argument is context the turn always has.
AMBIENT_WRITE = {
    "type": "function",
    "function": {"name": "book_update_details", "description": "edit",
                 "parameters": {"type": "object",
                                "properties": {"book_id": {"type": "string"}},
                                "required": ["book_id"]},
                 "_meta": {"tier": "A"}},
}

CATALOG = {"plan_bootstrap_apply": APPLY, "composition_list_outline": READ,
           "book_update_details": AMBIENT_WRITE}
EMITTERS = {"plan_bootstrap_apply": {"proposal_id": "plan_bootstrap_propose"}}

#: The reply, verbatim in shape, from the measured runs.
ASKED = ("I have compiled the plan and it proposes four chapters: The Salt Road, The Drowned "
         "Road, Ironhold, and The Frozen North. Would you like me to go ahead and create these "
         "chapters so we can start writing?")


def _call(text, attempted, succeeded):
    return _asked_instead_of_acting(text, attempted=attempted, succeeded=succeeded,
                                    catalog_index=CATALOG, emitters=EMITTERS)


def test_the_measured_instance_is_detected():
    """The original defect, reconstructed: equipped, did not call, asked."""
    assert _call(ASKED, {"plan_bootstrap_propose", "composition_list_outline"},
                 {"plan_bootstrap_propose"}) == "plan_bootstrap_apply"


def test_it_is_silent_when_the_turn_does_not_hold_the_argument():
    """🔴 THE HALF THAT KEEPS THIS HONEST. If the emitter never ran, the turn does NOT hold the
    id, and asking is the correct thing to do — the model cannot call a tool it has no argument
    for. A guard that fired here would be punishing the right behaviour."""
    assert _call(ASKED, set(), set()) is None


def test_it_is_silent_when_the_turn_actually_called_the_tool():
    assert _call(ASKED, {"plan_bootstrap_apply", "plan_bootstrap_propose"},
                 {"plan_bootstrap_propose"}) is None


def test_it_is_silent_when_the_reply_does_not_ask():
    """A turn that acted, or that reported, is not this defect whatever else it did."""
    assert _call("I created the four chapters.", set(), {"plan_bootstrap_propose"}) is None


def test_an_offer_of_EXTRA_work_mid_reply_is_not_this_defect():
    """The regex is END-ANCHORED on purpose. "Would you like me to also add a prologue?" in the
    middle of a reply offers work the author did NOT ask for, which is a different thing from
    withholding work they did."""
    text = ("Would you like me to also add a prologue? I have created the four chapters and the "
            "outline now reflects them.")
    assert _call(text, set(), {"plan_bootstrap_propose"}) is None


def test_an_ambient_only_write_never_fires():
    """🔴 WITHOUT THIS, EVERY POLITE CLOSING QUESTION IS A DEFECT. `book_update_details` requires
    only `book_id`, which the turn always has, so it would be "equipped" on every turn that ended
    with an offer. Requiring at least one EMITTED argument is what confines this to turns that
    genuinely did the work and stopped one call short."""
    assert _asked_instead_of_acting(
        ASKED, attempted=set(), succeeded={"plan_bootstrap_propose"},
        catalog_index={"book_update_details": AMBIENT_WRITE}, emitters={}) is None


def test_a_read_tier_tool_never_fires():
    """Consent is a WRITE concern. A read the turn could have made is not a withheld action."""
    assert _asked_instead_of_acting(
        ASKED, attempted=set(), succeeded={"plan_bootstrap_propose"},
        catalog_index={"composition_list_outline": READ},
        emitters={"composition_list_outline": {"x": "plan_bootstrap_propose"}}) is None


def test_the_advertised_set_bounds_the_search():
    """A tool that was not on the wire cannot have been withheld — the model never saw it."""
    assert _asked_instead_of_acting(
        ASKED, attempted={"plan_bootstrap_propose"}, succeeded={"plan_bootstrap_propose"},
        catalog_index=CATALOG, emitters=EMITTERS,
        advertised={"composition_list_outline"}) is None


def test_the_mapping_form_of_an_emitter_entry_is_read():
    """🔴 AN ENTRY MAY BE `{tool, field}`, NOT ONLY A STRING. `declared_emitter`'s docstring
    records that reading only the string form would silently lose the pairs whose supplier returns
    the id under a different key (composition_arc_list returns nodes[].id for composition_arc_get's
    node_id). A guard that skipped those would be inert for exactly the tools that needed the
    richer declaration — silently, and only for them."""
    assert _asked_instead_of_acting(
        ASKED, attempted={"plan_bootstrap_propose"}, succeeded={"plan_bootstrap_propose"},
        catalog_index=CATALOG,
        emitters={"plan_bootstrap_apply": {
            "proposal_id": {"tool": "plan_bootstrap_propose", "field": "id"}}},
    ) == "plan_bootstrap_apply"


def test_the_guard_is_actually_CALLED_by_the_turn_loop():
    """🔴 A DETECTOR NOTHING CALLS IS A DEAD MECHANISM, and every test above would still pass if
    the wiring were deleted — they exercise the pure function. This repo has shipped that shape
    before: a helper defined, never read, and green.

    AST, not a substring search. Grepping for the name matches this file's own docstring, the
    comment beside the call, and a commented-out call — the exact class of guard that goes green
    with the fix removed. `ast` sees a CALL node or it does not.
    """
    import ast
    import inspect

    from app.services import stream_service

    tree = ast.parse(inspect.getsource(stream_service))
    called = {
        n.func.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "_asked_instead_of_acting" in called, (
        "_asked_instead_of_acting is defined but never CALLED — the P16 invariant is detected "
        "by nothing, which is the state the problem sat in for twelve days"
    )
