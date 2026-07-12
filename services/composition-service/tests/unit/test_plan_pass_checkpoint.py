"""27 V2-D — the PASS checkpoint: accept, edit, seed-gate, roster-bind.

This is the door the human walks through. It is the only way a BLOCKING pass is ever accepted, so
every hole in it is a hole in the one guarantee PF-6 makes: that the compiler stops at the two
questions the author alone can answer.
"""

from __future__ import annotations

import inspect

from app.services import plan_forge_service as pfs
from app.services.bootstrap_service import BootstrapService

SRC = inspect.getsource(pfs)


# ── PF-7: the quarantine ─────────────────────────────────────────────────────────────────────────

def test_the_seed_kinds_are_declared_per_pass():
    """cast seeds characters; world seeds locations/factions/concepts. No other pass touches the
    glossary at all — an unlisted pass raises rather than seeding under a guessed kind."""
    assert BootstrapService.SEED_KINDS == {
        "cast": ("character",),
        "world": ("location", "faction", "concept"),
    }


def test_propose_seed_REFUSES_a_pass_that_does_not_seed_the_glossary():
    src = inspect.getsource(BootstrapService.propose_seed)
    assert "if pass_id not in self.SEED_KINDS:" in src
    assert "does not seed the glossary" in src


def test_propose_seed_CLAMPS_an_unknown_kind_rather_than_dropping_or_passing_it_through():
    """Passing an unvalidated kind_code through would push it at glossary-service; dropping the
    entity would silently lose something the LLM did propose. Clamp + log is the only option that
    loses nothing and asserts nothing false."""
    src = inspect.getsource(BootstrapService.propose_seed)
    assert "if kind not in allowed:" in src
    assert "kind = default_kind" in src
    assert "clamping" in src


def test_propose_seed_DEDUPES_against_still_active_proposals():
    """A second propose_seed before the first is applied must not double-offer — and, if both were
    applied, double-create — the same entity. Same `_glossary_item_key` mechanism `propose()` uses:
    one dedup rule, not two."""
    src = inspect.getsource(BootstrapService.propose_seed)
    assert "list_active_for_book(book_id)" in src
    assert "_glossary_item_key(" in src
    assert "if key in claimed or key in seen:" in src


def test_a_seed_proposal_never_touches_the_manuscript():
    """`new_chapters: []`. The skeleton link is the compiler's job and already happened at
    compile(); a seed proposal that also created chapters would mint them twice."""
    src = inspect.getsource(BootstrapService.propose_seed)
    assert '"new_chapters": []' in src


# ── PF-7: the gate ───────────────────────────────────────────────────────────────────────────────

def test_accepting_CAST_requires_its_seed_proposal_to_be_APPLIED():
    """THE gate. Without it a user could accept the cast, let passes 3-7 plan an entire book around
    characters that exist only inside a run artifact, and discover at bootstrap that none of them
    were ever in the glossary — with the scenes already referencing ids that resolve to nothing.

    The blocking gate (PF-6) and the mutation gate (PF-7) are the SAME gate, so they cannot
    disagree."""
    src = inspect.getsource(pfs.PlanForgeService._assert_seed_applied)
    assert 'if proposal.status != "applied":' in src
    assert "apply it first (PF-7)" in src
    # …and it is actually called on the approve path
    review = inspect.getsource(pfs.PlanForgeService._review_pass)
    assert "await self._assert_seed_applied(book_id, run, pass_id)" in review
    assert "if approved:" in review


def test_the_GATE_runs_BEFORE_ANY_WRITE_so_a_refusal_changes_nothing():
    """The live smoke caught the other order.

    With `approved=true` AND `edits`, the edit was saved and THEN the seed gate refused — so the
    caller got a 409 for a call that had already mutated their plan. A partial success reported as a
    failure is the worst of both: the user retries, and the retry re-applies the edit on top of
    itself. A refused checkpoint must be ATOMIC — nothing happened.

    (`approved=false` + `edits` is "hold this, but keep my revisions" and must still work while the
    seed sits unapplied, so only the APPROVE path is gated.)"""
    review = inspect.getsource(pfs.PlanForgeService._review_pass)
    gate_at = review.index("await self._assert_seed_applied(")
    write_at = review.index("save_artifact(")
    assert gate_at < write_at, "the gate must refuse before anything is written"
    # …and it is checked exactly ONCE (an earlier version gated twice, the second one dead)
    assert review.count("await self._assert_seed_applied(") == 1


def test_the_seed_gate_applies_to_CAST_ONLY_because_WORLD_is_advisory():
    """Pass 3 may lag: an unapplied world seed degrades grounding, it does not corrupt the plan. A
    gate on an advisory pass would block the compiler for no correctness gain."""
    src = inspect.getsource(pfs.PlanForgeService._assert_seed_applied)
    assert 'if pass_id != "cast":' in src
    assert "return" in src.split('if pass_id != "cast":')[1][:30]


def test_a_missing_proposal_REFUSES_rather_than_silently_accepting():
    """Absent ≠ satisfied. No proposal means the cast was never offered to the glossary — which must
    read as "not yet", not as "nothing to do"."""
    src = inspect.getsource(pfs.PlanForgeService._assert_seed_applied)
    assert "if not proposal_id:" in src
    assert "before its glossary seed proposal exists" in src


# ── D2: the edit ─────────────────────────────────────────────────────────────────────────────────

def test_an_EDIT_saves_a_NEW_artifact_rather_than_mutating_in_place():
    """PF-3. The new artifact id changes every downstream fingerprint, so everything below goes
    stale BY DERIVATION — zero invalidation writes. Mutating in place would leave the downstream
    passes fresh against a plan that no longer exists: a human edits the cast and the scenes planned
    around the OLD cast keep reporting themselves as up to date."""
    src = inspect.getsource(pfs.PlanForgeService._review_pass)
    assert "merged = _deep_merge(art.content, edits)" in src
    assert "new_art = await self._runs.save_artifact(" in src
    assert "artifact_id = new_art.id" in src


def test_an_edited_pass_stays_FRESH_ITSELF_while_its_dependents_stale():
    """The human changed the OUTPUT, not the INPUTS. This pass is exactly the plan the author now
    wants, so it keeps its fingerprint; what moved is the pointer its dependents read."""
    src = inspect.getsource(pfs.PlanForgeService._review_pass)
    assert "input_fingerprint=entry.get(\"input_fingerprint\")" in src


def test_you_cannot_accept_a_pass_that_never_COMPLETED():
    """Accepting a pass with no artifact would let the compiler proceed past a blocking checkpoint
    on something that does not exist — every downstream pass would resolve its input to nothing and
    plan on air, successfully."""
    src = inspect.getsource(pfs.PlanForgeService._review_pass)
    assert 'if entry.get("status") != "completed":' in src
    assert "has not completed" in src


def test_the_SPEC_checkpoint_is_unchanged_when_no_pass_id_is_given():
    """One door, two checkpoints. The v1 spec behaviour must not have moved."""
    src = inspect.getsource(pfs.PlanForgeService.review_checkpoint)
    assert "if pass_id is not None:" in src
    assert 'status="validated" if approved else "checkpoint"' in src


# ── PF-13: roster_bindings ───────────────────────────────────────────────────────────────────────

def test_the_roster_binding_is_WRITTEN_TO_THE_SPEC_after_cast_is_accepted():
    """Otherwise `cast_plan` is a stored-but-unread blob on the spec side — the exact write-only
    bug `structure_node` was built to kill."""
    review = inspect.getsource(pfs.PlanForgeService._review_pass)
    assert 'if approved and pass_id == "cast":' in review
    assert "await self._bind_roster(created_by, book_id, run)" in review

    bind = inspect.getsource(pfs.PlanForgeService._bind_roster)
    assert '"roster_bindings"' in bind
    assert "find_by_plan_run(book_id, run.id)" in bind


def test_an_UNRESOLVABLE_cast_name_is_LOGGED_and_left_UNBOUND_not_bound_to_nothing():
    """Absent ≠ empty. A role we could not bind must be visibly absent, not silently equivalent to
    "this role has no character"."""
    bind = inspect.getsource(pfs.PlanForgeService._bind_roster)
    assert "unbound.append(name)" in bind
    assert "absent, not empty" in bind


def test_two_characters_claiming_one_ROLE_do_not_silently_overwrite():
    """First writer wins, deliberately. Two protagonists is the PLAN's problem to surface; resolving
    it by overwriting would hide it."""
    bind = inspect.getsource(pfs.PlanForgeService._bind_roster)
    assert "bindings.setdefault(role, str(entity_id))" in bind


def test_the_ids_come_from_the_APPLIED_proposal_not_from_glossary_directly():
    """INV-KAL: composition reads cast through the knowledge-gateway roster, never glossary. The
    apply step is what MINTED the ids, and it recorded them in `applied_results`."""
    src = inspect.getsource(pfs.PlanForgeService._roster_ids_by_name)
    assert "proposal.applied_results" in src
    assert 'proposal.status != "applied"' in src


def test_binding_onto_an_ARCHIVED_arc_is_impossible():
    """The partial unique index that arbitrates the linker's upsert carries `NOT is_archived`, so an
    archived arc is a tombstone the linker has already re-created past. Writing the symbol table
    into it would put it in a node nothing reads."""
    from app.db.repositories.structure import StructureRepo

    src = inspect.getsource(StructureRepo.find_by_plan_run)
    assert "NOT is_archived" in src


def test_the_bind_is_DEGRADE_SAFE_on_an_unlinked_run():
    """A run that never compiled has no arc to bind onto. That must not fail an otherwise valid
    acceptance."""
    bind = inspect.getsource(pfs.PlanForgeService._bind_roster)
    assert "if arc is None:" in bind
    assert "return" in bind.split("if arc is None:")[1][:500]


# ── PF-13's EFFECT test (BA12 discipline) ────────────────────────────────────────────────────────
#
# Every test above reads SOURCE. That is self-report: it proves the code SAYS the right thing, not
# that the right thing HAPPENS. The spec is explicit that PF-13 needs the other kind — "a test
# asserts the packer's PROMPT CHANGES when the binding changes" — because the whole reason
# roster_bindings exists is to stop `cast_plan` being a stored-but-unread blob. A binding nothing
# reads is the write-only bug wearing a passing test.

import pytest


class _FakeStructureRepo:
    """The reads `gather_arc` makes, and nothing else."""

    def __init__(self, bindings: dict[str, str]) -> None:
        self._bindings = bindings

    async def ancestor_chain(self, node_id):
        class _N:
            kind = "arc"
            title = "The Iron Court"
            id = node_id
        return [_N()]

    async def resolve_tracks(self, node_id):
        return {}

    async def resolve_roster_bindings(self, node_id):
        return self._bindings

    async def span(self, node_id):
        return {}  # an unplaced span ⇒ no pacing line; irrelevant to the binding


@pytest.mark.asyncio
async def test_THE_BINDING_REACHES_THE_PROMPT_and_changing_it_CHANGES_the_prompt():
    """PF-13's reason for existing, proven by effect.

    Bind protagonist→A: the packed arc frame must NAME that entity. Rebind it to B: the frame must
    change. If both prompts were identical, `roster_bindings` would be a column the compiler writes
    and nothing reads — and every source-inspection test above would still be green.
    """
    from uuid import uuid4

    from app.packer.lenses import gather_arc

    node = uuid4()
    ha, bao = str(uuid4()), str(uuid4())

    frame_a = await gather_arc(_FakeStructureRepo({"protagonist": ha}), node, story_order=None)
    frame_b = await gather_arc(_FakeStructureRepo({"protagonist": bao}), node, story_order=None)

    assert "Cast bindings:" in frame_a
    assert ha in frame_a and bao not in frame_a
    assert bao in frame_b and ha not in frame_b
    assert frame_a != frame_b          # THE assertion: the binding is LOAD-BEARING on the prompt


@pytest.mark.asyncio
async def test_NO_binding_means_NO_cast_line_rather_than_an_empty_one():
    """Absent ≠ empty. An unbound arc must not ship a `Cast bindings:` header with nothing after it —
    that reads to the model as "this story has no cast", which is a stronger and falser claim than
    saying nothing."""
    from uuid import uuid4

    from app.packer.lenses import gather_arc

    frame = await gather_arc(_FakeStructureRepo({}), uuid4(), story_order=None)
    assert "Cast bindings:" not in frame


# ── B-R2 · /review-impl findings ─────────────────────────────────────────────────────────────────

def test_the_AGENT_CANNOT_FORCE_PAST_A_BLOCKING_CHECKPOINT():
    """HIGH. The MCP tool's own description promises the model that `cast` and `beats` are
    checkpoints "a human must accept" — and the first version of the tool then handed it `force`.

    An agent that hits a 409 listing its blockers does not stop. Being helpful is what it is FOR, and
    retrying with `force=true` is the obvious next move. PF-6 exists so the AUTHOR decides who the
    characters are and what shape the story takes; a bypass the model can reach for on its own is
    not a checkpoint, it is a speed bump.

    The gate is enforced by ABSENCE — not by a prompt asking the model to behave. A human at the GUI
    still has `force` (the service and the HTTP route both take it); the agent does not.
    """
    import inspect

    from app.mcp import server

    tool_src = inspect.getsource(server.plan_run_pass)
    assert "force:" not in tool_src, "`force` is exposed to the AGENT — PF-6 is bypassable"
    assert "force=False" in tool_src, "the tool must pin force=False, not pass a caller value"

    # …and the human's surface DOES keep it (this is not a capability removal)
    from app.services.plan_forge_service import PlanForgeService

    assert "force" in inspect.signature(PlanForgeService.run_pass).parameters


def test_plan_run_pass_declares_that_it_SPENDS_MONEY():
    """[MCP Tool `_meta` Completeness Law] `paid` governs MONEY; `tier` governs mutation. A pass is a
    full LLM call. A spender that does not declare it looks FREE to every consumer that reads the
    catalog to decide whether a call needs the user's say-so."""
    import inspect

    from app.mcp import server

    src = inspect.getsource(server)
    block = src[src.index('name="plan_run_pass"') : src.index("async def plan_run_pass")]
    assert "paid=True" in block


def test_a_RERUN_of_cast_does_NOT_open_an_EMPTY_seed_proposal():
    """HIGH. `list_active_for_book` counts APPLIED proposals as claiming their entities, so
    re-running `cast` after its seed was applied dedups to ZERO new entities.

    An empty proposal would then (1) overwrite `bootstrap_proposal_id`, so (2) accepting cast
    REFUSES — its new proposal is `pending` — and the author has to approve and apply an EMPTY diff
    to proceed, after which (3) its `applied_results` is `{}`, the roster join resolves no ids, and
    every scene silently loses its cast.

    Re-running a pass is this compiler's entire selling point. It must not be the thing that breaks
    it."""
    import inspect

    from app.services.bootstrap_service import BootstrapService

    src = inspect.getsource(BootstrapService.propose_seed)
    assert "if not new_glossary_entities:" in src
    assert "return None" in src
    # …and the caller leaves the prior pointer alone (record_pass ignores a None field)
    from app.worker import job_consumer

    hook = inspect.getsource(job_consumer._propose_pass_seed)
    assert "if proposal is None:" in hook
    assert "keeping the" in hook


def test_the_id_JOINS_union_across_ALL_applied_proposals():
    """HIGH (the other half). An entity id is a fact about the BOOK, not about the proposal that
    happened to mint it.

    Re-run `cast` and the LLM adds one new character: that re-run's proposal contains only the NEW
    one. Reading it alone would leave every character from the first batch unresolved — the scenes
    would quietly lose the cast that was already correctly seeded, and the roster would SHRINK on a
    re-run."""
    import inspect

    from app.services.plan_forge_service import PlanForgeService
    from app.worker.operations import _resolve_cast_entity_ids

    for src in (
        inspect.getsource(_resolve_cast_entity_ids),
        inspect.getsource(PlanForgeService._roster_ids_by_name),
    ):
        assert "list_active_for_book(book_id)" in src
        assert 'proposal.status != "applied"' in src   # …and only APPLIED ones have minted ids
        assert "get_for_book(book_id, UUID(str(proposal_id)))" not in src   # not the single pointer


def test_the_variable_parser_is_CAPPED():
    """MED. `source_markdown` has no max_length, and `_var_deltas` runs every declared code against
    every line of every event — O(lines × codes). A document declaring thousands of `CODE = …` lines
    turns a compile into a CPU sink."""
    from app.engine.plan_forge.propose import _MAX_VARIABLES, _variable_defs

    body = "\n".join(f"V{i} = Var{i}   [0 -> 10]" for i in range(_MAX_VARIABLES + 40))
    assert len(_variable_defs(body)) == _MAX_VARIABLES


def test_ENQUEUEING_a_pass_marks_it_RUNNING_so_the_ledger_describes_the_PRESENT():
    """HIGH. A RE-RUN was invisible, and it silently ate the author's acceptance.

    Nothing wrote to the pass entry between "job enqueued" and "finalize hook lands" ~30s later. So
    for the whole duration of a re-run the ledger still reported the PREVIOUS run's `completed` +
    `accepted`, while the artifact it named was being replaced.

    The live smoke showed the cost. A caller polls `status`, sees `completed` immediately (it never
    changed), and ACCEPTS — then the re-run's finalize hook writes `decision: pending` on top,
    because a new cast has not been reviewed by anyone. The acceptance is silently discarded, `world`
    then refuses with `blockers: ['cast']`, and the ledger shows cast `completed` + `pending` with no
    account of how it got there. Two 200s from the accept endpoint, and the human's decision gone.

    `running` fixes all three lies at once: the poll sees the truth, `is_fresh` (which requires
    `completed`) keeps anything downstream from running against a pass mid-flight, and `_review_pass`
    refuses to accept it."""
    import inspect

    from app.services.plan_forge_service import PlanForgeService

    src = inspect.getsource(PlanForgeService.run_pass)
    enqueue = src.index("await enqueue_job(")
    mark = src.index('record_pass(run, pass_id, status="running"')
    assert mark < enqueue, "the pass must be marked running BEFORE the job can be picked up"
    assert "job_id=job.id" in src


def test_a_RUNNING_pass_cannot_be_ACCEPTED_and_nothing_downstream_can_run():
    """The two consequences that make `running` load-bearing rather than cosmetic."""
    from uuid import uuid4

    from app.db.models import PlanRun
    from app.services import plan_pass_service as pps

    pkg = uuid4()
    run = PlanRun(
        id=uuid4(), created_by=uuid4(), book_id=uuid4(), status="compiled", mode="rules",
        pass_state={"cast": {"status": "running", "decision": "accepted",
                             "artifact_id": str(uuid4()), "input_fingerprint": "sha256:x"}},
    )
    # a pass being re-run is NOT fresh, whatever its decision says
    assert pps.is_fresh(run, "cast", package_artifact_id=pkg) is False
    # …so nothing that depends on it may run
    assert "cast" in pps.blockers_for(run, "world", package_artifact_id=pkg)
    # …and the checkpoint refuses it (status != completed)
    src = inspect.getsource(
        __import__("app.services.plan_forge_service", fromlist=["x"]).PlanForgeService._review_pass,
    )
    assert 'if entry.get("status") != "completed":' in src
