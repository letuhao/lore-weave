"""27 V2-C1 — the pass registry, the fingerprint, and the DERIVED freshness view (PF-3/PF-5/PF-6).

The three laws these pin, and the bug each prevents:

  • inputs resolve BY POINTER — pass 7 emits a new `scene_plan`, so a latest-by-kind rule would
    make it its own input and it would stale itself against its own output, forever;
  • freshness is DERIVED — so re-running a pass needs ZERO invalidation writes, and there is no
    stored dirty flag to drift;
  • `model_ref` is NOT in the fingerprint — changing the default model must not silently stale a
    plan the user already reviewed and accepted.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.db.models import PASS_ORDER, PlanRun
from app.services import plan_pass_service as pps

BOOK = uuid4()


def run_with(pass_state: dict) -> PlanRun:
    return PlanRun(
        id=uuid4(), created_by=uuid4(), book_id=BOOK, mode="llm", pass_state=pass_state,
    )


def done(artifact_id, fp, decision="auto"):
    return {
        "status": "completed", "decision": decision,
        "artifact_id": str(artifact_id), "input_fingerprint": fp,
    }


# ── the registry mirrors 27 §170 ──────────────────────────────────────────────


def test_the_seven_passes_are_the_specs_closed_set_in_dependency_order():
    # The spec's names, not a paraphrase. A closed-set value that drifts from the spec is the
    # Frontend-Tool-Contract bug: the agent passes the documented value and the server 422s.
    assert PASS_ORDER == (
        "motifs", "cast", "world", "beats", "character_arcs", "scenes", "self_heal",
    )
    assert tuple(pps.PASS_REGISTRY) == PASS_ORDER


def test_blocking_is_exactly_cast_and_beats():
    """PF-6 (ratified P-8): the human blocks where the human is the ONLY oracle — who the
    characters are (pass 2) and what shape the story takes (pass 4). Everything else auto-accepts
    and stays reviewable after the fact."""
    blocking = {p for p, s in pps.PASS_REGISTRY.items() if s.checkpoint == "blocking"}
    assert blocking == {"cast", "beats"}


def test_self_heal_emits_a_scene_plan_which_is_why_pointers_exist():
    assert pps.PASS_REGISTRY["self_heal"].output_kind == "scene_plan"
    assert pps.PASS_REGISTRY["scenes"].output_kind == "scene_plan"


def test_every_dependency_names_an_EARLIER_pass():
    # A pass may never depend on a later one — the order IS the dependency order.
    for i, pid in enumerate(PASS_ORDER):
        for dep in pps.PASS_REGISTRY[pid].depends_on:
            assert PASS_ORDER.index(dep) < i, f"{pid} depends on later pass {dep}"


# ── the fingerprint (PF-3) ────────────────────────────────────────────────────


def test_fingerprint_is_stable_and_order_sensitive():
    a, b = uuid4(), uuid4()
    assert pps.fingerprint(input_artifact_ids=[a, b]) == pps.fingerprint(input_artifact_ids=[a, b])
    # ORDERED, not sorted — swapping inputs is a different plan.
    assert pps.fingerprint(input_artifact_ids=[a, b]) != pps.fingerprint(input_artifact_ids=[b, a])


def test_fingerprint_changes_when_an_input_artifact_changes():
    a, b = uuid4(), uuid4()
    assert pps.fingerprint(input_artifact_ids=[a]) != pps.fingerprint(input_artifact_ids=[b])


def test_params_are_in_the_fingerprint_but_dict_ORDER_is_not():
    f1 = pps.fingerprint(input_artifact_ids=[], params={"a": 1, "b": 2})
    f2 = pps.fingerprint(input_artifact_ids=[], params={"b": 2, "a": 1})
    assert f1 == f2  # a fingerprint that moved with dict order would stale a plan on a Py upgrade
    assert f1 != pps.fingerprint(input_artifact_ids=[], params={"a": 1, "b": 3})


def test_model_ref_is_NOT_an_input_to_the_fingerprint():
    """PF-3, explicit: changing the default model must not silently stale a plan the user already
    reviewed. The signature simply has nowhere to put it — that is the enforcement."""
    import inspect

    assert "model_ref" not in inspect.signature(pps.fingerprint).parameters


# ── freshness is DERIVED (PF-3) ───────────────────────────────────────────────


def test_a_pass_that_never_ran_is_not_fresh():
    assert pps.is_fresh(run_with({}), "cast") is False


PKG = uuid4()  # the run's current `planning_package` artifact


def test_a_completed_pass_with_a_matching_fingerprint_is_fresh():
    # `cast` has no PASS dependencies, but it DOES read the package — so the package artifact id is
    # its only input. (Before the fix its fingerprint was a constant and it was fresh forever.)
    fp = pps.fingerprint(input_artifact_ids=[str(PKG)])
    r = run_with({"cast": done(uuid4(), fp)})
    assert pps.is_fresh(r, "cast", package_artifact_id=PKG) is True


def test_a_NEW_PACKAGE_stales_the_entry_passes():
    """THE bug this fixes. `motifs`/`cast` have no pass dependencies, so with the package left out of
    the fingerprint their input set was EMPTY — a constant — and they were fresh forever, including
    after the user re-compiled with a different arc or genre and a brand-new package artifact. That
    is the "a plan silently becomes internally inconsistent" failure PF-5 exists to stop."""
    fp = pps.fingerprint(input_artifact_ids=[str(PKG)])
    r = run_with({"cast": done(uuid4(), fp)})
    assert pps.is_fresh(r, "cast", package_artifact_id=PKG) is True
    # …re-compile ⇒ a NEW package artifact ⇒ cast is stale, by derivation, with no invalidation write.
    assert pps.is_fresh(r, "cast", package_artifact_id=uuid4()) is False


def test_RE_RUNNING_a_pass_stales_its_downstream_with_ZERO_invalidation_writes():
    """THE mechanism (PF-5). `world` depends on `cast`. Re-run `cast` ⇒ new artifact id ⇒ `world`'s
    recorded fingerprint no longer matches the one its inputs produce ⇒ stale, by derivation.
    Nothing was written to `world`. This is `make`: edit a header, dependents rebuild."""
    cast_v1 = uuid4()
    cast_fp = pps.fingerprint(input_artifact_ids=[str(PKG)])
    # `world` reads the package AND depends on `cast` — in registry order: package first, then deps.
    world_fp = pps.fingerprint(input_artifact_ids=[str(PKG), str(cast_v1)])
    r = run_with({"cast": done(cast_v1, cast_fp), "world": done(uuid4(), world_fp)})
    assert pps.is_fresh(r, "world", package_artifact_id=PKG) is True

    # …re-run `cast`: a NEW artifact id, and we touch NOTHING else.
    cast_v2 = uuid4()
    r2 = run_with({"cast": done(cast_v2, cast_fp), "world": r.pass_state["world"]})
    assert pps.is_fresh(r2, "cast", package_artifact_id=PKG) is True    # cast itself is fine
    assert pps.is_fresh(r2, "world", package_artifact_id=PKG) is False  # …world staled on its own


def test_an_upstream_that_never_ran_stales_the_downstream():
    """An ABSENT upstream must change the fingerprint, or a pass that somehow ran before its
    upstream existed would look fresh forever."""
    # `world` recorded a fingerprint built over a real cast artifact…
    world_fp = pps.fingerprint(input_artifact_ids=[str(uuid4())])
    r = run_with({"world": done(uuid4(), world_fp)})  # …but `cast` is not in the ledger at all
    assert pps.is_fresh(r, "world") is False


# ── PF-5: the runner refuses to build on inputs the user has not seen ─────────


def test_assert_runnable_blocks_when_an_upstream_is_stale():
    r = run_with({})  # cast never ran
    with pytest.raises(pps.UpstreamStale) as ei:
        pps.assert_runnable(r, "world")
    assert ei.value.blockers == ["cast"]


def test_assert_runnable_blocks_when_an_upstream_is_completed_but_NOT_ACCEPTED():
    """A BLOCKING pass completes with decision 'pending'. That is the stop signal, not 'nearly
    done' — building on it would produce a plan the user never agreed to."""
    fp = pps.fingerprint(input_artifact_ids=[])
    r = run_with({"cast": done(uuid4(), fp, decision="pending")})
    with pytest.raises(pps.UpstreamStale):
        pps.assert_runnable(r, "world")


def test_force_is_the_only_escape():
    pps.assert_runnable(run_with({}), "world", force=True)  # does not raise


def test_a_pass_with_no_dependencies_is_always_runnable():
    pps.assert_runnable(run_with({}), "cast")
    pps.assert_runnable(run_with({}), "motifs")


# ── the derived cursor + blocked_at (never stored) ────────────────────────────


def test_pass_cursor_is_CONTIGUOUS_not_a_count():
    """A run with 1,2,3 done and 4 blocking has cursor 3 — even if someone force-ran pass 5. The
    cursor answers "how far can the compiler proceed unattended", which a total count answers
    wrongly."""
    m, c = uuid4(), uuid4()
    pkg_fp = pps.fingerprint(input_artifact_ids=[str(PKG)])
    r = run_with({
        "motifs": done(m, pkg_fp),
        "cast": done(c, pkg_fp, decision="accepted"),
        "world": done(uuid4(), pps.fingerprint(input_artifact_ids=[str(PKG), str(c)])),
        # `beats` is skipped entirely…
        # …but someone force-ran `character_arcs`:
        "character_arcs": done(uuid4(), "sha256:whatever"),
    })
    # motifs, cast, world — then it STOPS at the gap.
    assert pps.pass_cursor(r, package_artifact_id=PKG) == 3


def test_blocked_at_names_the_pass_waiting_on_a_human():
    fp = pps.fingerprint(input_artifact_ids=[])
    r = run_with({"cast": done(uuid4(), fp, decision="pending")})
    assert pps.blocked_at(r) == "cast"


def test_blocked_at_is_None_when_nothing_awaits_a_human():
    fp = pps.fingerprint(input_artifact_ids=[])
    assert pps.blocked_at(run_with({"cast": done(uuid4(), fp, decision="accepted")})) is None


def test_an_ADVISORY_pass_pending_does_not_block():
    # Only a BLOCKING pass's `pending` is a stop signal; advisory passes auto-accept.
    fp = pps.fingerprint(input_artifact_ids=[])
    r = run_with({"motifs": done(uuid4(), fp, decision="pending")})
    assert pps.blocked_at(r) is None


def test_default_decision_is_pending_for_blocking_and_auto_for_advisory():
    assert pps.default_decision("cast") == "pending"
    assert pps.default_decision("beats") == "pending"
    assert pps.default_decision("motifs") == "auto"
    assert pps.default_decision("scenes") == "auto"


# ── derive_view: the DERIVED fields are computed, never columns ───────────────


def test_derive_view_reports_every_pass_with_its_derived_freshness():
    fp = pps.fingerprint(input_artifact_ids=[str(PKG)])
    v = pps.derive_view(
        run_with({"cast": done(uuid4(), fp, decision="accepted")}), package_artifact_id=PKG,
    )
    assert [p["pass_id"] for p in v["passes"]] == list(PASS_ORDER)
    cast = next(p for p in v["passes"] if p["pass_id"] == "cast")
    assert cast["fresh"] is True and cast["decision"] == "accepted"
    world = next(p for p in v["passes"] if p["pass_id"] == "world")
    assert world["fresh"] is False and world["blockers"] == []  # cast IS accepted+fresh
    # …but the CURSOR is 0, not 1: `motifs` (pass 1) never ran, and the cursor is CONTIGUOUS from
    # the start. "How far can the compiler proceed unattended" is 0 here — a count would say 1 and
    # be wrong.
    assert v["pass_cursor"] == 0
    assert v["blocked_at"] is None


def test_derive_view_surfaces_bootstrap_proposal_id_for_the_client(monkeypatch):
    """BE-20/PF-7 — `cast` cannot be accepted until its glossary seed proposal is `applied`, and the
    ONLY route to that proposal needs its id. If the ledger omits `bootstrap_proposal_id` the approve
    button 409s forever with no way to clear it. So the derived view MUST return it."""
    prop = uuid4()
    entry = done(uuid4(), pps.fingerprint(input_artifact_ids=[str(PKG)]), decision="pending")
    entry["bootstrap_proposal_id"] = str(prop)
    v = pps.derive_view(run_with({"cast": entry}), package_artifact_id=PKG)
    cast = next(p for p in v["passes"] if p["pass_id"] == "cast")
    assert cast["bootstrap_proposal_id"] == str(prop)
    # a pass with no proposal reports None, not a missing key (the FE reads it either way)
    motifs = next(p for p in v["passes"] if p["pass_id"] == "motifs")
    assert motifs["bootstrap_proposal_id"] is None
    assert "decided_by" in cast and "decided_at" in cast


# ── record_pass merges; it never clobbers the pointer downstream passes resolve through ──


def test_record_pass_leaves_untouched_fields_ALONE():
    """A status write must not wipe the artifact pointer a previous write recorded — that pointer
    is what every downstream pass resolves through, and losing it silently un-links the plan."""
    aid = uuid4()
    r = run_with({"cast": done(aid, "sha256:x")})
    state = pps.record_pass(r, "cast", status="running")
    assert state["cast"]["artifact_id"] == str(aid)      # preserved
    assert state["cast"]["input_fingerprint"] == "sha256:x"
    assert state["cast"]["status"] == "running"          # updated


def test_record_pass_does_not_mutate_the_run_in_place():
    r = run_with({"cast": done(uuid4(), "sha256:x")})
    before = pps.derive_view(r)
    pps.record_pass(r, "cast", status="failed")
    assert pps.derive_view(r) == before  # pure — the caller persists


# ── params live on the ENTRY, not on the caller ──────────────────────────────


def test_a_param_carrying_pass_stays_FRESH_across_a_derivation():
    """The bug: freshness took `params` from the CALLER, but `derive_view`/`pass_cursor` have none
    to give — so they recomputed with `params=None`, no param-carrying pass ever matched its own
    recorded fingerprint, and every one of them read as permanently STALE, blocking everything
    downstream. The params a pass ran with are a property of THAT PASS, so they live on its entry."""
    params = {"k_ceiling": 3}
    fp = pps.fingerprint(input_artifact_ids=[str(PKG)], params=params)
    e = done(uuid4(), fp)
    e["params"] = params
    r = run_with({"cast": e})
    assert pps.is_fresh(r, "cast", package_artifact_id=PKG) is True
    # …and the derivation agrees, because it reads the params off the entry.
    v = pps.derive_view(r, package_artifact_id=PKG)
    assert next(p for p in v["passes"] if p["pass_id"] == "cast")["fresh"] is True


def test_changing_a_passs_params_stales_it():
    params = {"k_ceiling": 3}
    fp = pps.fingerprint(input_artifact_ids=[str(PKG)], params=params)
    e = done(uuid4(), fp)
    e["params"] = {"k_ceiling": 9}   # it ran with different params than the fingerprint says
    assert pps.is_fresh(run_with({"cast": e}), "cast", package_artifact_id=PKG) is False


def test_record_pass_stores_the_params_it_ran_with():
    r = run_with({})
    state = pps.record_pass(r, "cast", status="completed", params={"k": 1})
    assert state["cast"]["params"] == {"k": 1}


def test_record_pass_supports_a_DECISION_ONLY_write():
    """`status` was REQUIRED, while the docstring promised "fields left None are UNTOUCHED".

    That contradiction made a decision-only write impossible: accepting a pass at its checkpoint
    changes the DECISION, not the status, and there was no honest value to pass for `status` — so
    the accept path 500'd. The live smoke found it; no unit test could, because every existing
    caller happened to be writing a status anyway.

    A decision write must leave status, the artifact pointer, and the fingerprint exactly as they
    were — that pointer is what every downstream pass resolves through.
    """
    aid = uuid4()
    r = run_with({"cast": done(aid, "sha256:abc")})
    state = pps.record_pass(r, "cast", decision="accepted", decided_by="user")
    e = state["cast"]
    assert e["decision"] == "accepted"
    assert e["decided_by"] == "user"
    assert e["status"] == "completed"                 # untouched
    assert e["artifact_id"] == str(aid)              # untouched — downstream resolves through it
    assert e["input_fingerprint"] == "sha256:abc"    # untouched
