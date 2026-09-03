"""The two turn-ownership signals only chat-service can compute, and the rule behind them.

The precedence table lives in the SDK (`loreweave_agent_control.harness`, pinned by
test_turn_ownership.py). What this service owns is the INPUTS — and an input that is silently
wrong or silently empty makes a correct rule dead, which this loop has now shipped twice.

🔴 THE INCIDENT, 2026-08-13, session 019ff929, editor surface, book 019ff8f5-ae59.
The author typed "Load the tool composition_list_outline by name, then use it to show me the
outline of this book." A stale `build-a-book` rail claimed the turn and drove `plan_propose_spec`
four times — every call refused, because it carried the editor's chapter_id as `book_id`.
`tool_load` was advertised in all six passes and never called once.
"""
import pytest

from app.db.tool_call_history import STUCK_TOOL_CAP, stuck_tools_from_calls
from app.services.stream_service import _tools_named_in_request

REFUSED = "Error executing tool plan_propose_spec: not found or not accessible"

CATALOG = {
    "composition_list_outline": {},
    "plan_propose_spec": {},
    "kg_add_nodes": {},
    "book_read": {},
}


class TestTheNamedToolSignal:
    def test_the_LIVE_message_names_its_tool(self):
        assert _tools_named_in_request(
            "Load the tool composition_list_outline by name, then use it to show me the outline "
            "of this book.", CATALOG,
        ) == frozenset({"composition_list_outline"})

    def test_a_message_naming_several_tools_yields_them_all(self):
        got = _tools_named_in_request("first book_read then kg_add_nodes please", CATALOG)
        assert got == frozenset({"book_read", "kg_add_nodes"})

    def test_it_is_case_insensitive(self):
        assert _tools_named_in_request("use Book_Read", CATALOG) == frozenset({"book_read"})

    @pytest.mark.parametrize("msg", [
        "write the next chapter for me",
        "ok",
        "yes please, go ahead",
        "can you look at my outline?",          # DESCRIBES a tool's job — not the same as naming it
        "",
    ])
    def test_ordinary_prose_names_nothing(self, msg):
        """A false positive here silences the rail for a turn, which is why the match requires an
        underscore and a minimum length rather than a bare substring test. Rule 5 of the contract
        depends on ordinary co-writing turns producing an empty set."""
        assert _tools_named_in_request(msg, CATALOG) == frozenset()

    def test_a_short_or_wordlike_catalog_name_can_never_fire(self):
        """Defence for a catalogue this test does not control: if a provider ever registers a tool
        called `read` or `plan`, a bare substring match would fire on half of all prose."""
        assert _tools_named_in_request(
            "please read the plan and edit it", {"read": {}, "plan": {}, "edit": {}},
        ) == frozenset()

    def test_no_catalog_means_no_claim(self):
        assert _tools_named_in_request("composition_list_outline", {}) == frozenset()


class TestTheStuckToolSignal:
    """The rule chat-service already had — (tool → error → count), tolerate 2, a success clears
    it — with the lifetime it was missing. Both the in-turn breaker's map and the rail's nudge
    counters are rebuilt per turn, so a step failing twice a turn reset forever."""

    def test_the_LIVE_defect_four_identical_failures_across_two_turns_is_stuck(self):
        """THE FALSIFIER. Nothing in the system reached this verdict before: the in-turn breaker
        saw 2 per turn (its cap is 2, so it never tripped) and the rail counted attempts, not
        errors."""
        assert stuck_tools_from_calls(
            [("plan_propose_spec", False, REFUSED)] * 4
        ) == {"plan_propose_spec"}

    def test_the_cap_matches_the_in_turn_breaker_so_the_two_agree_on_stuck(self):
        assert STUCK_TOOL_CAP == 2
        calls = [("plan_propose_spec", False, REFUSED)] * STUCK_TOOL_CAP
        assert stuck_tools_from_calls(calls) == {"plan_propose_spec"}
        assert stuck_tools_from_calls(calls[:-1]) == set()

    def test_a_success_clears_the_tool_entirely(self):
        """Mirrors the in-turn breaker: a success means the model changed something that worked,
        so the tool is demonstrably reachable and must not stay walled off for the session."""
        assert stuck_tools_from_calls([
            ("plan_propose_spec", False, REFUSED),
            ("plan_propose_spec", False, REFUSED),
            ("plan_propose_spec", True, ""),
            ("plan_propose_spec", False, REFUSED),
        ]) == set()

    def test_two_DIFFERENT_errors_are_progress_not_a_wall(self):
        """The whole point of keying on the error: a different message means the model changed
        something. Counting bare attempts would strand a tool that was being fixed."""
        assert stuck_tools_from_calls([
            ("plan_propose_spec", False, "book_id must be a UUID"),
            ("plan_propose_spec", False, REFUSED),
        ]) == set()

    def test_a_failure_with_no_error_text_is_not_evidence(self):
        """A denied or gated call records ok=false with no error. Counting those would let a
        working safety gate read as a broken tool — this loop already had to strip exactly that
        conflation out of its own failure ranking."""
        assert stuck_tools_from_calls([("plan_propose_spec", False, "")] * 5) == set()

    def test_only_the_repeatedly_failing_tool_is_named(self):
        assert stuck_tools_from_calls([
            ("plan_propose_spec", False, REFUSED),
            ("plan_propose_spec", False, REFUSED),
            ("book_read", False, "some other error"),
        ]) == {"plan_propose_spec"}

    def test_the_error_signature_is_truncated_so_a_long_payload_still_matches_itself(self):
        long_err = "not found or not accessible " + ("x" * 5000)
        assert stuck_tools_from_calls(
            [("plan_propose_spec", False, long_err)] * 2
        ) == {"plan_propose_spec"}
