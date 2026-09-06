"""An undo you cannot reach is not an undo.

The platform ships TEN `*_restore` tools. `composition_canon_rule_restore` takes a `rule_id`, and
nothing on the tool surface could produce the id of an ARCHIVED rule — `composition_list_canon_rules`
called `list_all(pid)` and never passed `include_archived`, so an archived rule was invisible to the
agent. The only way to hold that id was to have written it down BEFORE archiving.

🔴 THE CAPABILITY WAS ALREADY THERE, which is what makes this a wiring fix rather than a feature.
`CanonRulesRepo.list_all` has taken `include_archived` all along, and its docstring says why it
exists: "so the management UI can list them under a section and offer Restore (BE-11b)". The FE
could find an archived rule to restore; the agent could not.

NOT A CATALOGUE ADDITION — one optional argument on a tool that already ships, so it costs no new
hot-set slot and decides no product question. That distinction is the whole reason this half could
be fixed here while the other five families stay with the owner: they have no lister to add a flag
to, and giving them one means adding a tool.
"""
from __future__ import annotations

import inspect

from app.mcp import server


def test_the_lister_ACCEPTS_include_archived():
    sig = inspect.signature(server.composition_list_canon_rules)
    assert "include_archived" in sig.parameters, (
        "the archived rules a restore targets are still unreachable")
    assert sig.parameters["include_archived"].default is False, (
        "archived rules must stay OUT of the default listing — this is an opt-in for a repair "
        "flow, not a change to what 'the canon rules' means")


def test_the_flag_actually_REACHES_the_repo():
    """The bug was never a missing argument — it was an argument that existed and was not passed.
    A signature that accepts it and a call site that drops it looks identical from outside."""
    src = inspect.getsource(server.composition_list_canon_rules)
    assert "list_all(pid, include_archived=include_archived)" in src, (
        "the flag is accepted and then discarded at the call site")


def test_active_only_still_WINS():
    """`active_only` means enforceable-and-not-archived. If include_archived could override it the
    tool would answer a question with its own contradiction."""
    src = inspect.getsource(server.composition_list_canon_rules)
    i = src.index("rules = await (")
    assert "canon.list_active(pid) if active_only" in src[i:i + 200]


def test_the_DESCRIPTION_says_where_the_restore_id_comes_from():
    """A flag the model cannot know to set is the same as no flag. The description is the only
    place that connects this listing to the restore path.

    🔴 IT MUST NAME THE LIVE SUCCESSOR, NOT THE RETIRED TOOL. This test pinned
    `composition_canon_rule_restore`, which was marked `visibility: legacy` and superseded by
    `composition_canon_rule_edit`. Since 2026-08-25 the superseded gate drops EVERY legacy tool
    from the wire, so the description was pointing the model at a tool it is never offered — and
    this test was holding it there. A guard that pins a name has to be re-pointed when the name
    retires, or it enforces the defect. Measured 2026-09-03: four live tools were steering at
    dropped tools, and this was one of them.
    """
    src = inspect.getsource(server)
    i = src.index('name="composition_list_canon_rules"')
    block = src[i:i + 900]
    assert "include_archived" in block
    assert "composition_canon_rule_edit" in block, (
        "nothing tells the model this listing is where a restorable id comes from")
    assert "composition_canon_rule_restore" not in block, (
        "the description names a tool the superseded gate drops from every turn; the model "
        "cannot call it, so it will invent a call or claim success")
