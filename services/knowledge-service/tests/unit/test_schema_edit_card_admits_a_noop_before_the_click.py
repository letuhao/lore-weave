"""TOOLV2 LOOP #255 — the schema-edit card promised a version bump it could not deliver.

kg_schema_edit works. Measured live, each through propose → confirm, verified in the SSOT:

    deprecate edge_type WORSHIPS_TOOLV2_252  -> applied, schema_version 3, deprecated_at set
    add       fact_type prophecy_toolv2_255  -> applied, schema_version 4, row present

Two calls that cannot succeed were also accepted, and their cards said nothing:

    deprecate a code that never existed -> card: "Deprecate edge type 'NEVER_EXISTED_255'",
                                                 destructive TRUE, "will bump to 5"
                                           confirm: "the edge_type … no longer exists"
    add a code that already exists      -> card: "Add fact type 'prophecy_toolv2_255'",
                                                 drift false, "will bump to 5"
                                           confirm: 409 "already exists in this schema"

`preview_schema_edit` is documented as a "non-consuming current-state render … so the FE can warn
before the human confirms", and it already implements that idea twice — a `drift` row whose note
is literally "confirming will be rejected", and a "no active schema" branch. This is the third way
the same confirm gets rejected, and it was the one case the card rendered as a normal, actionable
change.

The destructive flag made it worse. A deprecate with no target destroys nothing, and the card
marked it destructive:true — asking a human to weigh a loss that cannot occur.

Note on what counts as "exists": the check reads `resolve_for_project`, the same effective view
the extraction path validates against, and deprecated types are absent from it. That is the
behaviour we want in both directions — re-adding a deprecated code is a genuine add, and
re-deprecating one is a genuine no-op.
"""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app" / "ontology" / "schema_edit_effect.py"


def _body() -> str:
    return SRC.read_text(encoding="utf-8").replace("\r\n", "\n")


def _flat() -> str:
    """`_body()` with adjacent-string-literal joins collapsed — the wire form of these notes.

    Same helper as #253's benchmark guard, for the same reason: a sentence that is contiguous
    when the caller reads it is split by `" \\n "` in the source, and a naive phrase assertion
    goes red on formatting rather than on meaning.
    """
    return re.sub(r'"\s*\n\s*"', "", _body())


def test_the_card_warns_when_the_edit_is_already_done():
    body = _body()
    assert "_code_exists(" in body, "the preview no longer checks whether the code is there"
    assert '"label": "⚠ no-op"' in body, (
        "the card renders a doomed edit as a normal one again"
    )
    # Both directions, in the caller's terms, read as the caller receives them.
    wire = _flat()
    assert "already exists here — confirming will be rejected; nothing is added twice" in wire
    assert "exists here — confirming will be rejected; nothing is removed" in wire


def test_a_deprecate_with_no_target_is_not_flagged_destructive():
    body = _body()
    assert '"destructive": params.verb == "deprecate" and not conflict,' in body, (
        "a deprecate that cannot find its target is marked destructive again — the human is "
        "asked to weigh a loss that will not happen"
    )


def test_the_conflict_test_covers_both_verbs():
    """add+present and deprecate+absent are the same defect from opposite sides; a check written
    for only one of them leaves the other rendering a clean card."""
    body = _body()
    assert 'conflict = (params.verb == "add") == exists' in body


def test_the_existing_two_rejection_paths_are_untouched():
    """drift and no-active-schema already warned correctly. The new row must be added alongside
    them, not in place of either."""
    body = _body()
    assert '"label": "⚠ drift", "value": "yes"' in body
    assert '"value": "no active schema"' in body
    assert '"the schema changed since you proposed — confirming will be rejected"' in body


def test_the_existence_check_reads_the_effective_schema():
    """Reading a raw table instead would disagree with what the confirm validates against, and
    would count deprecated rows as present — turning a genuine re-add into a false 'already
    exists' warning."""
    body = _body()
    assert "resolve_for_project(project_id)" in body
    assert "edge_types if params.level ==" in body, (
        "the check must pick the pool matching `level`; testing one list for both would report "
        "a fact_type as missing whenever an edge_type of the same code exists, and vice versa"
    )


def test_apply_still_raises_on_both_conflicts():
    """The card is a warning, not the guard. If apply stopped raising, a doomed confirm would
    become a silent no-op reported as success — worse than the card that started this."""
    body = _body()
    assert "DuplicateChildError" in body
    assert "ChildNotFoundError" in body
