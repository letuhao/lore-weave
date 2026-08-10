"""CP-5.10 — the registry is the only name source.

🔴 **MEASURED: `glossary_propose_entity_edit` was dispatched 101 TIMES across 12 SESSIONS with a
0% success rate, and it is in no catalogue.** A name the model invented, sent to the wire a hundred
times. `plan_forge.plan_propose_spec` is the same shape with a namespace prefix bolted on, and
`echo_test` is a third.

🔴 **AND THE FIRST CUT OF THIS MEASUREMENT WAS WRONG IN THE WAY THIS RUN KEEPS BEING WRONG.**
Comparing dispatched names against the FEDERATED snapshot alone reported 17 "phantom" tools —
but `workflow_load` (32 calls, 100% ok), `workflow_list` (27, 100%), `chat_search_sessions` (13,
100%), `load_skill`, `ui_navigate` and `run_subagent` are all REAL consumer-local tools, and
`book_update_meta` / `glossary_list_kinds` are RENAMED ones. A catalogue that excludes what
chat-service implements itself manufactures phantoms — the same error that briefly made the
co-writer's `compose_prose` look like a gap that had never been used.

So the check does not use a snapshot at all. It uses the two indexes the TURN itself dispatches
from, which is the only set that answers "can this actually run".
"""
from __future__ import annotations

import pathlib

STREAM = (pathlib.Path(__file__).resolve().parents[1]
          / "app" / "services" / "stream_service.py")


def src() -> str:
    return STREAM.read_text(encoding="utf-8")


class TestAnUndispatchableNameIsRefusedBeforeTheWire:

    def test_THE_CHECK_EXISTS_ON_THE_DISPATCH_PATH(self):
        assert 'if c["name"] not in cat_index and c["name"] not in plain_index:' in src(), (
            "nothing stops an invented name reaching the wire, so a tool that does not exist is "
            "still dispatched — 101 times, in the measured case"
        )

    def test_IT_IS_REFUSED_NOT_FAILED(self):
        """5.7's distinction, reused: the tool did not fail, it does not exist. Typing it as a
        failure would put it back in the corpus with the genuine ones."""
        assert '}, "unknown_tool")}' in src()
        assert '"error": "unknown_tool"' in src()

    def test_THE_REFUSAL_OFFERS_A_REAL_NAME(self):
        """`entity_id must be a UUID` was loud and unactionable; so is *"that tool does not
        exist"* on its own. The suggestion comes from the names the turn can actually dispatch."""
        assert "Did you mean" in src()
        assert "Call tool_list to see what exists" in src()

    def test_IT_SITS_BEFORE_THE_ONE_REAL_DISPATCH(self):
        """Placement is the mechanism — V-METRIC round 3 was a placement bug, not a null. A check
        after the dispatch would still burn the round trip it exists to save."""
        s = src()
        check = s.index('if c["name"] not in cat_index and c["name"] not in plain_index:')
        dispatch = s.index("envelope = await knowledge_client.mcp_execute_tool(")
        assert check < dispatch, "the name check must precede the dispatch it is meant to prevent"

    def test_IT_USES_THE_TURNS_OWN_INDEXES_NOT_A_SNAPSHOT(self):
        """🔴 The guard against the error this measurement made first. A frozen federated snapshot
        excludes every consumer-local tool, so checking against one would refuse `workflow_load`,
        `chat_search_sessions` and `run_subagent` — all real, all heavily used, several at 100%
        success. The dispatchable set is the two indexes the turn holds."""
        s = src()
        check_line = [ln for ln in s.splitlines()
                      if 'not in cat_index and c["name"] not in plain_index' in ln][0]
        assert "cat_index" in check_line and "plain_index" in check_line
        assert "snapshot" not in check_line and "baseline" not in check_line

    def test_EVERY_OTHER_DISPATCH_PATH_IS_HANDLED_EARLIER(self):
        """Frontend tools, the composer and the suspend paths all `continue` or `break` above this
        line, so the check cannot swallow a call that had somewhere else to go."""
        s = src()
        check = s.index('if c["name"] not in cat_index and c["name"] not in plain_index:')
        for earlier in ("if is_composer_tool(c[\"name\"])", "suspended_call = {"):
            assert s.index(earlier) < check, f"{earlier} must be handled before the name check"
