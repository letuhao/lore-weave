"""TOOLV2 LOOP #252 — a precondition refusal that described its remedy without naming it.

kg_ontology_propose is correct on everything it advertises. Measured live, each op gates on
exactly its own fields and says which are missing:

    op=schema_edit    (bare) -> "op=schema_edit requires verb, level, and code"
    op=adopt_template (bare) -> "op=adopt_template requires source_schema_id"
    op=sync_apply     (bare) -> "op=sync_apply requires base_source_hash"

And the full chain works end to end. On a project with no ontology, schema_edit refused; adopting
the Fantasy template via this same tool (propose -> confirm) returned adopted=true; the retried
schema_edit minted a token whose card read "Add edge type 'WORSHIPS_TOOLV2_252' … current
schema_version 1 … will bump to 2"; confirming it returned applied=true at schema_version 2, and
kg_edge_types holds the row (WORSHIPS_TOOLV2_252 | Worships).

The gap is one sentence. The refusal said:

    this project has no adopted ontology to edit — adopt a project schema first
    (the System template is read-only and admin-managed)

"Adopt a project schema first" is the right instruction for a human reading a UI. For an agent it
is a description of a remedy, not a route to it: the operation that performs it is `op=
'adopt_template'` ON THIS SAME TOOL, and reaching it needs a source_schema_id that only
kg_list_templates supplies. Neither is named.

This service already holds itself to the opposite standard, in a sibling refusal, in a comment
that says why: kg_build's no-embedding-model error names kg_project_set_embedding_model outright,
because "an agent cannot open a dialog … this error string is the ONLY instruction a tool-calling
model gets here, so it must name the tools that unblock it, in order (F6 — Track D liveness
eval)". Same service, same rule, two refusals, one of them following it.

The text appears TWICE — the propose path and the mint path — so a fix to one copy would have left
an agent hitting the other with the old wording.
"""

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app" / "tools" / "graph_schema_tools.py"


def _body() -> str:
    return SRC.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_the_refusal_names_both_tools_needed_to_clear_it():
    body = _body()
    assert "adopt a project schema \"\n            \"first" not in body, (
        "the un-actionable wording is back — it describes the remedy without naming it"
    )
    assert "call kg_list_templates to " in body, (
        "adopt_template needs a source_schema_id; without naming where ids come from, the "
        "instruction dead-ends one step later"
    )
    assert "op='adopt_template'" in body, "the op that clears this lives on this same tool"
    assert "then retry this edit" in body, "a refusal needs its final step, or the agent stops"


def test_both_copies_were_fixed():
    """The same message guards the propose path and the mint path. One agent hits one, one hits
    the other, and a half-fix looks green from either side alone."""
    body = _body()
    assert body.count("call kg_list_templates to ") == 2, (
        "expected exactly 2 copies of the corrected refusal — a divergence here means one path "
        "still answers with the old text"
    )


def test_the_read_only_fact_survives():
    """The original said the System template is read-only and admin-managed. That is true and is
    the reason the remedy is 'adopt a copy' rather than 'edit the template' — dropping it would
    make the instruction look arbitrary."""
    body = _body()
    assert "System template is read-only " in body
    assert "cannot be edited in place" in body


def test_the_sibling_refusal_that_sets_the_standard_still_names_its_tool():
    """If kg_build's refusal ever loses its tool name, the precedent this fix cites is gone and
    the two should be re-decided together rather than drifting apart one at a time."""
    build = (SRC.parent / "build_tools.py").read_text(encoding="utf-8")
    # Matched as a bare name, not as a phrase: the sibling's message is assembled from adjacent
    # string literals, so "call kg_project_set_embedding_model first" is not contiguous in the
    # source even though it is contiguous on the wire. A phrase match here would go red on a
    # harmless re-wrap and say nothing about the standard it is guarding.
    assert "kg_project_set_embedding_model" in build, (
        "kg_build's refusal no longer names its remedy tool — the precedent #252 cites is gone "
        "and the two refusals should be re-decided together, not drift apart one at a time"
    )
