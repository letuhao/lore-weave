"""DQ-T76 · the ABSENT-id branch — why advising the model was measured insufficient.

🔴 THE MEASUREMENT THAT REDIRECTED THIS. Four claims died against the corpus in order:

  1. "338 live name-into-id failures"     → mostly PRE-fix history; live residual 86.
  2. "refresolve needs building"          → shipped 2026-08-10; 15.7 → 1.6 per session (~10x).
  3. "name→id resolution is the fix"      → 89% of current failures are the id ABSENT, not
                                            misspelled. That plan addressed 11%.
  4. "declare which tool supplies the id" → ALREADY DONE. `argument_emitters` covers 632 of
                                            the 723 failures (87%), and the refusal names the
                                            supplier to the model.

And then the one that decided the design: of 605 (session, tool) pairs that failed on a
missing id — supplier declared, supplier named in the refusal — only 51 (**8%**) ever
succeeded with that tool again in the same session. The count is GENEROUS; it credits
successes that happened before the failure. Telling the model where the id comes from is a
mechanism that FIRES and does not MATTER.

So this branch FETCHES. The two-branch contract is untouched: exactly one candidate
substitutes; anything else refuses WITH the rows, because the 5.3 pilot measured ambiguity
at 37.5% of contested calls and a "pick the best" arm would be a guess deciding a
correctness question.
"""

from app.agentruntime.refresolve import (
    bare_id_field, decide_absent, harvest,
)

# A real composition_motif_link_list shape, wrapping its rows one level down.
MOTIF_ONE = {"motifs": [
    {"motif_id": "e6c27ac3-08e2-5a6d-a08a-7941a4d6b90f", "name": "A Grudge Older Than the Holder"},
]}
MOTIF_MANY = {"motifs": [
    {"motif_id": "e6c27ac3-08e2-5a6d-a08a-7941a4d6b90f", "name": "A Grudge Older Than the Holder"},
    {"motif_id": "11111111-2222-4333-8444-555555555555", "name": "The Debt Unpaid"},
]}


def test_a_single_candidate_is_substituted_not_advised():
    r = decide_absent("motif_id", "composition_motif_link_list", MOTIF_ONE)
    assert r.outcome == "resolved" and r.ok
    assert r.resolved == "e6c27ac3-08e2-5a6d-a08a-7941a4d6b90f"


def test_a_role_prefix_is_not_a_different_id_type():
    """🔴 168 of the 723 failures. `composition_motif_link_edit` requires from_motif_id /
    to_motif_id; its supplier returns `motif_id`. Matching the literal parameter name scores
    the single most reliable supplier in the corpus (620/626 ok) as absent."""
    assert bare_id_field("from_motif_id") == "motif_id"
    assert bare_id_field("to_motif_id") == "motif_id"
    assert bare_id_field("motif_id") == "motif_id"
    # ...and it must not eat a field that merely starts with those letters.
    assert bare_id_field("format_id") == "format_id"
    assert bare_id_field("targeting_id") == "targeting_id"
    for p in ("from_motif_id", "to_motif_id"):
        assert decide_absent(p, "composition_motif_link_list", MOTIF_ONE).ok, p


def test_ambiguity_refuses_and_hands_back_the_rows():
    """The refusal is the POINT, not a shortfall — measured at 37.5% of contested calls.
    What makes it an improvement is the payload: today the model is handed the NAME OF A
    TOOL TO GO CALL; here it is handed the rows to choose between."""
    r = decide_absent("motif_id", "composition_motif_link_list", MOTIF_MANY)
    assert r.outcome == "ambiguous" and not r.ok
    assert r.resolved is None, "an ambiguous resolution must never carry a substituted id"
    assert len(r.candidates) == 2
    assert {c.name for c in r.candidates} == {"A Grudge Older Than the Holder", "The Debt Unpaid"}


def test_a_schema_is_not_a_supplier():
    """🔴 THE FALSE POSITIVE THAT INFLATED THE FIRST SIZING PASS. `tool_load` returns tool
    SCHEMAS, so every id parameter appears there as a property KEY. Keyed on the name alone it
    scored as a supplier of world_id/map_id/job_id. A schema describes an argument; it is not
    a value anything can pass."""
    schema_shaped = {"tool": "world_get", "inputSchema": {"properties": {
        "world_id": {"type": "string", "description": "the world's id (UUID)"}}}}
    assert harvest(schema_shaped, "world_id") == ()
    assert decide_absent("world_id", "tool_load", schema_shaped).outcome == "no_match"


def test_a_non_uuid_value_is_not_an_id():
    """Agrees with the name branch about what an id IS, rather than holding a second opinion."""
    assert harvest({"world_id": "Ember Codex"}, "world_id") == ()
    assert harvest({"world_id": "default"}, "world_id") == ()
    assert harvest({"world_id": None}, "world_id") == ()


def test_the_same_record_twice_is_one_choice_not_an_ambiguity():
    dup = {"a": [{"motif_id": "e6c27ac3-08e2-5a6d-a08a-7941a4d6b90f", "name": "X"}],
           "b": [{"motif_id": "e6c27ac3-08e2-5a6d-a08a-7941a4d6b90f", "name": "X"}]}
    r = decide_absent("motif_id", "composition_motif_link_list", dup)
    assert r.outcome == "resolved", "a duplicated row was scored as two conflicting candidates"


def test_an_unlabelled_candidate_is_still_offered():
    """An id with no human label is worse to choose between; hiding it would be worse still."""
    r = decide_absent("job_id", "jobs_list", {"jobs": [
        {"job_id": "11111111-2222-4333-8444-555555555555"},
        {"job_id": "66666666-7777-4888-8999-aaaaaaaaaaaa"}]})
    assert r.outcome == "ambiguous" and len(r.candidates) == 2
    assert all(c.name == "" for c in r.candidates)


def test_a_pathological_payload_cannot_spin():
    deep: dict = {"x": {}}
    node = deep["x"]
    for _ in range(60):
        node["x"] = {}
        node = node["x"]
    node["motif_id"] = "e6c27ac3-08e2-5a6d-a08a-7941a4d6b90f"
    assert harvest(deep, "motif_id") == (), "depth bound did not hold"
