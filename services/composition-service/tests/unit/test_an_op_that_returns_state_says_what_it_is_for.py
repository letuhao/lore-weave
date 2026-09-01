"""A protocol op that hands back the run's data must also say what the caller does with it.

    THE INVARIANT. Every op in a multi-call protocol returns a `next`. An op that returns state
    and no instruction leaves the caller holding the data and not the protocol.

🔴 MEASURED. composition_build_cast_and_graph is a six-op pipeline. Every op returned a `next`
EXCEPT `status` -- and `status` is the one op that hands back the worklist. op=start's `next` is
"Show the user this worklist; call op='approve_plan' when they agree", so approving has a
PRECONDITION: the caller must be holding the worklist. On the confirmation turn it is not,
because chat-service rehydrates history from `role, content` alone and turn 1's tool result is
never selected.

    op=approve_plan calls, across 95 calls and 89 recorded sessions:   ZERO
    every recorded call is `start` or a confirm card.

AND NAMING THE NEXT OP ALONE DID NOT MOVE IT. The ACTIVE_RUN refusal was already made to name
run_id and the continuing op; re-measured K=5, still zero approve_plan. That is what a caller
told to approve something it cannot show looks like.

WHAT THIS DOES NOT CLAIM: that the turn-boundary loss is fixed. It is not -- that is DQ-T88, and
it is the owner's. This makes the tool able to restore its OWN state within one turn, which needs
no platform change.
"""
from __future__ import annotations

import ast
import inspect
import pathlib

from app.services.glossary_build import service as gb


class TestEveryStateSaysWhatToDo:
    def test_the_two_gates_name_the_op_AND_the_data(self):
        """The states whose next op has a precondition. Each must name the data to show."""
        for status, op in (("plan_ready", "approve_plan"), ("edges_ready", "approve_edges")):
            s = gb.next_sentence_for(status)
            assert s, f"{status} says nothing"
            assert op in s, f"{status} does not name op='{op}': {s!r}"
            assert "show it to them" in s or "show them and call" in s, (
                f"{status} names the op but not the precondition its own protocol states: {s!r}")

    def test_a_gate_does_not_send_a_model_BACK_for_an_agreement_it_already_has(self):
        """🔴 THE WORDING WAS WRITTEN FOR TURN 1 AND READ AS "STOP" ON TURN 2.

        It said "Show it to the user, then call op='approve_plan' when they agree" -- correct
        when the plan has just been made, and wrong on the turn that RECOVERS it, because by
        then the user has already agreed.

        MEASURED (t64-protocol5, K=5): three of five runs reached op=status, received the
        worklist, the run_id AND that sentence, and called nothing further. The scenario's turn 2
        is literally "Yes, that worklist is right -- go ahead and build them".

        THE INVARIANT: an instruction returned WITH recovered state must be valid for the turn
        that recovers it. The tool cannot know which turn it is on, so it names BOTH cases."""
        for status in ("plan_ready", "edges_ready"):
            s = gb.next_sentence_for(status)
            assert "ALREADY approved" in s, (
                f"{status} assumes the user has not seen the data yet: {s!r} — on the turn that "
                "recovers it they have, and the sentence sends the model back to ask again")
            assert "NOW" in s and "do not ask again" in s, (
                f"{status} names the already-approved case without telling the model to act on "
                "it: {s!r}")

    def test_a_polling_state_says_to_poll(self):
        for status in ("planning", "building", "proposing", "kg_projecting"):
            s = gb.next_sentence_for(status)
            assert s and "status" in s, f"{status} does not tell the caller to poll: {s!r}"

    def test_a_TERMINAL_state_does_not_invent_a_next_call(self):
        """Nothing true to say is said plainly, not filled with a made-up step."""
        for status in ("done", "cancelled"):
            s = gb.next_sentence_for(status)
            assert s, f"{status} says nothing at all"
            assert "op='approve" not in s, f"{status} invents an approval step: {s!r}"

    def test_an_unknown_state_says_nothing(self):
        assert gb.next_sentence_for("no_such_status") is None
        assert gb.next_sentence_for("") is None
        assert gb.next_sentence_for(None) is None


class TestTheTwoTablesCannotDrift:
    def test_every_next_OP_has_a_next_SENTENCE(self):
        """🔴 A FIVE-OF-SIX MISMATCH BETWEEN TWO SUCH LISTS IS HOW A BOOK WAS STRANDED FOR TWO
        WEEKS -- this file's own module records it under Repo.active_run_for_book. So the two
        state tables are asserted against each other rather than trusted."""
        missing = [s for s in gb._NEXT_OP_FOR_STATUS if s not in gb._NEXT_SENTENCE_FOR_STATUS]
        assert not missing, f"{missing} name a next OP and no sentence"

    def test_a_sentence_that_names_an_op_names_the_SAME_op(self):
        for status, op in gb._NEXT_OP_FOR_STATUS.items():
            s = gb.next_sentence_for(status) or ""
            assert f"op='{op}'" in s, (
                f"{status}: the map says op={op!r} and the sentence says {s!r}")


class TestTheRequiredIdNamesItsOwnDiscoveryRoute:
    """A required id whose ONLY supplier is a refusal must say so.

    🔴 MEASURED, batch t64-protocol3, K=5: 20 of 24 calls were `op=start`, and on a book that
    already has a run every one is refused ACTIVE_RUN. The run_id description said "if you have
    no run_id, the op you want is `start`" -- correct about the only available route, and silent
    about what taking it produces. So the refusal read as a dead end.

    THERE IS NO LISTING OP. The six are start | approve_plan | status | project_kg |
    approve_edges | cancel, and none finds an existing run, so `start` genuinely IS the discovery
    step and its refusal carries the id.
    """

    def _run_id_description(self) -> str:
        import app.mcp.server as srv

        f = srv._GlossaryBuildArgs.model_fields["run_id"]
        return " ".join(str(getattr(f, "description", "") or "").split())

    def test_it_names_ACTIVE_RUN_as_where_the_id_comes_from(self):
        d = self._run_id_description()
        assert "ACTIVE_RUN" in d, (
            "the run_id description does not name the refusal that carries the id, so a model "
            "that has no run_id is told to call an op guaranteed to be refused and nothing more")

    def test_it_says_the_refusal_is_NOT_a_dead_end(self):
        d = self._run_id_description()
        assert "dead end" in d or "discovery" in d, (
            "it names the refusal without saying the refusal is the answer")

    def test_it_still_forbids_inventing_one(self):
        """The half that was already right must survive the rewrite: this tool has been called
        with fabricated ids before, and 'never invent one' is why that stopped."""
        assert "Never invent one" in self._run_id_description()

    def test_no_listing_op_exists_which_is_WHY_start_is_the_route(self):
        """🔴 THE FIX RESTS ON AN ABSENCE, so the absence is asserted. If a listing op is ever
        added, this description should point at IT rather than at a refusal."""
        import typing

        import app.mcp.server as srv

        ops = set(typing.get_args(
            srv._GlossaryBuildArgs.model_fields["op"].annotation))
        assert "list" not in ops and "runs" not in ops, (
            f"a listing op now exists ({sorted(ops)}) — the run_id description should name it "
            "instead of sending the caller through a refusal")


class TestTheCallSitesUseIt:
    def test_the_status_op_CALLS_the_sentence_map(self):
        """🔴 THIS GUARD WAS VACUOUS AND ITS OWN FALSIFIER CAUGHT IT. The first version asserted
        `"next_sentence_for" in ast.unparse(fn)` — and the tool imports that name INSIDE the
        function, so the string was present with the call deleted. It passed with the fix
        removed. A substring test over a body that contains its own import list is measuring the
        import.

        So this walks for an actual CALL node."""
        src = pathlib.Path(inspect.getfile(
            __import__("app.mcp.server", fromlist=["x"]))).read_text(encoding="utf-8")
        fn = next((n for n in ast.walk(ast.parse(src))
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and n.name == "composition_build_cast_and_graph"), None)
        assert fn is not None, "the tool has been renamed — this guard is blind"
        calls = [n for n in ast.walk(fn)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == "next_sentence_for"]
        assert calls, (
            "the status op never CALLS next_sentence_for — it still returns the worklist with "
            "no instruction, whatever the import line says")
        subs = [n for n in ast.walk(fn) if isinstance(n, ast.Subscript)
                and isinstance(n.slice, ast.Constant) and n.slice.value == "next"]
        assert subs, "nothing assigns a `next` key into the status result"

    def test_the_ACTIVE_RUN_refusal_USES_the_restore_hint(self):
        """🔴 THE SAME VACUITY, THE OTHER SHOE. The first version asserted `"op='status'" in
        source` — true of the hint STRING even when nothing selects it. Its falsifier passed too.

        So this asserts the hint is chosen by a CONDITIONAL, which is what makes it reach the
        caller, and that the condition is scoped to the states whose next op has a precondition."""
        fn = next((n for n in ast.walk(ast.parse(inspect.getsource(gb)))
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and n.name == "_active_run_refusal"), None)
        assert fn is not None, "_active_run_refusal has been renamed — this guard is blind"
        names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
        assert "_restore" in names and "_needs_data" in names, (
            "the refusal does not select a restore hint at all")
        chosen = [n for n in ast.walk(fn) if isinstance(n, ast.IfExp)
                  and any(isinstance(x, ast.Name) and x.id == "_restore"
                          for x in ast.walk(n))]
        assert chosen, (
            "the restore hint is never chosen by a condition, so it cannot reach the caller — "
            "which is the dead-string shape this guard was rewritten to catch")
        src = ast.unparse(fn)
        assert "plan_ready" in src and "edges_ready" in src, (
            "the restore hint is not scoped to the states whose next op has a precondition")


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
