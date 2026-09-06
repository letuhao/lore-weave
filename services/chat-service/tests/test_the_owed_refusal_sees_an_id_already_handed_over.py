"""An `owed` refusal must not tell a model the runtime owns an id the model is holding.

    'plan_bootstrap_apply' is missing ['proposal_id'], and this is NOT yours to invent: the
    runtime supplies it from the current context or an active plan, and has none right now.

Every clause is true of the RUNTIME. None of it is true of the TURN when the value is already in
the transcript. "NOT yours to invent" is correct and load-bearing — fabricating a UUID is the
failure that text exists to prevent — but "the runtime supplies it … and has none right now" tells
a model that has just been handed the id that the id is not its business. The two clauses give
opposite instructions.

🔴 THE RECORDED INSTANCE SPANS TWO TURNS, which is why it was nearly dismissed:
    turn 1  "Create the chapters"        -> plan_bootstrap_propose ok, returns proposal_id,
                                            "Would you like me to go ahead?"
    turn 2  "Yes — create the chapters"  -> plan_bootstrap_apply {book_id} — proposal_id OMITTED
Anything scanning only turn 2 sees a model that never held the id, and the refusal reads as
correct. A first sweep did exactly that and reported ZERO cases across 1290 turns.

MEASURED PROPERLY, per SESSION over loreweave_chat.chat_messages: of 15 `owed` refusals, 4 (27%)
fired while the session had already been handed that exact id — plan_compile.run_id twice,
plan_bootstrap_apply.proposal_id twice. The row that filed this refused to ship on its own n=3,
and was right to; 27% of a message every `owed` tool shares is a different proposition.

PRECISION, measured before the code was written: in all four cases the session held EXACTLY ONE
value for the key. Where it holds more than one, this says nothing — "the" id would be a guess.
"""
from __future__ import annotations

import pathlib

import pytest

from app.services import stream_service as ss

SRC = pathlib.Path(ss.__file__).read_text(encoding="utf-8", errors="replace")
PID = "01a03042-1cdc-7637-a75c-fff992d15cc6"
OTHER = "01a03043-c4ca-71b8-871a-7bea92c186fe"
OWED = {"argument_supplier": {"proposal_id": "plan — the compiled proposal"}}


def _tool_msg(body: str) -> dict:
    return {"role": "tool", "content": body}


class TestItFindsAnIdHandedOverEarlier:
    def test_it_reads_a_tool_result_from_a_PRIOR_turn(self):
        history = [
            {"role": "user", "content": "Create the chapters"},
            _tool_msg('{"ok": true, "result": {"proposal_id": "%s", "status": "pending"}}' % PID),
            {"role": "assistant", "content": "Would you like me to go ahead?"},
            {"role": "user", "content": "Yes — create the chapters now."},
        ]
        assert ss._ids_already_returned(history, "proposal_id") == [PID]

    def test_only_TOOL_messages_count(self):
        """An id the ASSISTANT merely mentioned in prose is not one a tool returned — quoting that
        back would be laundering the model's own guess into an instruction."""
        history = [{"role": "assistant", "content": f'the proposal_id is "{PID}"'}]
        assert ss._ids_already_returned(history, "proposal_id") == []

    def test_a_different_key_is_not_borrowed(self):
        history = [_tool_msg('{"ok": true, "result": {"run_id": "%s"}}' % PID)]
        assert ss._ids_already_returned(history, "proposal_id") == []

    def test_no_history_is_survivable(self):
        assert ss._ids_already_returned(None, "proposal_id") == []
        assert ss._ids_already_returned([], "proposal_id") == []


class TestTheRefusalChangesOnlyWhenTheIdIsUNAMBIGUOUS:
    def test_it_quotes_the_id_and_drops_the_runtime_claim(self):
        msg = ss._missing_args_message(
            "plan_bootstrap_apply", ["proposal_id"], OWED,
            history=[_tool_msg('{"ok": true, "result": {"proposal_id": "%s"}}' % PID)])
        assert PID in msg, "the value must be handed back, not merely referred to"
        assert "ALREADY HAVE" in msg
        assert "has none right now" not in msg, (
            "the runtime-owns-it clause is FALSE for this turn and must not survive beside the "
            "quoted value")

    def test_TWO_values_means_it_says_nothing(self):
        """The precision guard. A session with two runs makes 'the' id a fabrication, so the
        original wording stands rather than a guess being quoted."""
        msg = ss._missing_args_message(
            "plan_bootstrap_apply", ["proposal_id"], OWED,
            history=[_tool_msg('{"ok": true, "result": {"proposal_id": "%s"}}' % PID),
                     _tool_msg('{"ok": true, "result": {"proposal_id": "%s"}}' % OTHER)])
        assert PID not in msg and OTHER not in msg
        assert "has none right now" in msg

    def test_with_NO_history_the_original_wording_is_unchanged(self):
        msg = ss._missing_args_message("plan_bootstrap_apply", ["proposal_id"], OWED)
        assert "NOT yours to invent" in msg and "has none right now" in msg
        assert "ALREADY HAVE" not in msg

    def test_it_still_forbids_inventing_one(self):
        msg = ss._missing_args_message(
            "plan_bootstrap_apply", ["proposal_id"], OWED,
            history=[_tool_msg('{"ok": true, "result": {"proposal_id": "%s"}}' % PID)])
        assert "do NOT invent one" in msg

    def test_it_tells_the_model_not_to_RE_FETCH(self):
        """The recorded failure ended with the model calling the supplier again — and that second
        call failed for its own missing argument. Re-fetching is the other wrong move."""
        msg = ss._missing_args_message(
            "plan_bootstrap_apply", ["proposal_id"], OWED,
            history=[_tool_msg('{"ok": true, "result": {"proposal_id": "%s"}}' % PID)])
        assert "do not call the supplier again" in msg

    def test_a_MODEL_supplied_argument_is_untouched(self):
        """`body` and `items` are the model's to write; this branch must not reach them."""
        msg = ss._missing_args_message(
            "book_chapter_save_draft", ["body"], {"argument_supplier": {"body": "model"}},
            history=[_tool_msg('{"ok": true, "result": {"body": "x"}}')])
        assert "ALREADY HAVE" not in msg


class TestTheCROSSTurnSourceIsTheOneThatCarriesTheRecordedInstance:
    """🔴 THE FIRST FIX FIRED ZERO TIMES IN TEN LIVE RUNS, and these tests exist because of it.

    It scanned the turn's own message list for role="tool" entries. Those exist only WITHIN a
    turn — appended live, not yet persisted. Across turns there is nothing to find:
    `chat_messages` holds ZERO role='tool' rows, because a tool result is stored on the ASSISTANT
    row in a `tool_calls` JSONB column. Rehydration therefore returns user/assistant text and no
    results at all. The unit tests passed, the deployed sha matched, and the branch never ran.

    So the conversation covers THIS turn and the server's record covers the PRIOR ones, and the
    defect needs both. `also_returned` is the second half.
    """

    def test_a_value_only_the_SERVER_remembers_still_changes_the_refusal(self):
        """No tool message anywhere in `history` — exactly the shape a rehydrated prior turn has."""
        msg = ss._missing_args_message(
            "plan_bootstrap_apply", ["proposal_id"], OWED,
            history=[{"role": "user", "content": "Yes — create the chapters now."}],
            also_returned={"proposal_id": [PID]})
        assert PID in msg and "ALREADY HAVE" in msg
        assert "has none right now" not in msg

    def test_the_two_sources_are_UNIONED_not_preferred(self):
        """One value from each source is TWO values, and two values must silence the branch — the
        precision guard has to see the union or it guards half the evidence."""
        msg = ss._missing_args_message(
            "plan_bootstrap_apply", ["proposal_id"], OWED,
            history=[_tool_msg('{"ok": true, "result": {"proposal_id": "%s"}}' % PID)],
            also_returned={"proposal_id": [OTHER]})
        assert PID not in msg and OTHER not in msg
        assert "has none right now" in msg

    def test_the_SAME_value_from_both_sources_is_still_one_value(self):
        """The common case once a turn is persisted: the server and the transcript agree. Deduping
        is what stops that agreement from reading as ambiguity and silencing the branch."""
        msg = ss._missing_args_message(
            "plan_bootstrap_apply", ["proposal_id"], OWED,
            history=[_tool_msg('{"ok": true, "result": {"proposal_id": "%s"}}' % PID)],
            also_returned={"proposal_id": [PID]})
        assert PID in msg and "ALREADY HAVE" in msg

    def test_a_junk_also_returned_is_survivable(self):
        for junk in (None, {}, {"proposal_id": []}, "nonsense"):
            msg = ss._missing_args_message(
                "plan_bootstrap_apply", ["proposal_id"], OWED, also_returned=junk)
            assert "has none right now" in msg


class TestItIsWiredInAtTheCallSite:
    def test_the_call_site_passes_BOTH_sources(self):
        assert "history=working, also_returned=_ma_prior)" in SRC, (
            "the conversation alone is the fix that fired 0/10 — the call must also thread the "
            "server's own record, which is where a PRIOR turn's tool result actually lives")

    def test_the_call_site_reads_the_SERVER_record(self):
        assert "from app.db.tool_call_history import ids_returned_under_key" in SRC
        assert "await ids_returned_under_key(" in SRC

    def test_only_RUNTIME_OWED_arguments_are_looked_up(self):
        """A per-argument query for `body` or `items` is waste — and the predicate deciding that
        must be the SAME one the message branches on, not a second copy free to drift."""
        assert "for _oa in _owed_args(_c_block, _missing_args):" in SRC
        assert SRC.count("def _owed_args(") == 1
        assert "owed = _owed_args(block, missing)" in SRC

    def test_the_lookup_cannot_take_the_turn_down(self):
        seg = SRC.split("from app.db.tool_call_history import ids_returned_under_key", 1)[1][:900]
        assert "except Exception" in seg and "_ma_prior = {}" in seg

    def test_the_helper_is_scoped_to_tool_messages(self):
        assert 'm.get("role") != "tool"' in SRC

    @pytest.mark.parametrize("guard", [
        "== 1",                      # exactly one value, or say nothing
    ])
    def test_the_ambiguity_guard_is_present(self, guard):
        seg = SRC.split("_held: dict[str, list[str]] = {}", 1)[1][:500]
        assert guard in seg
