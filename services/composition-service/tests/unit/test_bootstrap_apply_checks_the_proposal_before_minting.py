"""TOOLV2 LOOP #272 — a confirm card for a proposal that does not exist, on a tool that creates
real chapters.

`plan_bootstrap_apply` is confirm-gated because it WRITES: it turns a compiled plan into actual
book chapters. Measured with a fabricated but well-formed proposal UUID:

    mint     -> {"confirm_token": "...", "descriptor": "composition.bootstrap_apply",
                 "book_id": ..., "proposal_id": ...}          ← a token, no summary
    preview  -> 200 {"descriptor": ..., "resource_id": ..., "payload": {the two ids}}
    confirm  -> 400 {"detail": {"code": "action_error"}}      ← a code, no message

So the failure was discovered at the last possible moment, by the human, and the body it failed
with said nothing. The mint's own comment named the gap: `_uuid(proposal_id, "proposal_id")
# validate shape before minting` — the shape was the whole check.

Two things were missing and both are now supplied at mint:

1. EXISTENCE. `BootstrapService.get(book_id, proposal_id)` is book-scoped and the EDIT gate has
   already run one line above, so the lookup reveals nothing the caller could not already read.
2. A SUMMARY. The mint returned only the ids it was handed, so an agent had nothing to tell the
   human it was asking to approve — on a write. `plan_bootstrap_propose` already computes
   new_chapters / new_glossary_entities from the same `diff`; the apply now reports the same
   numbers rather than deriving them a second way.

Measured after the fix: the fabricated id is refused by name with the remedy, and a REAL pending
proposal still mints with `"summary": "create 0 chapter(s) + seed 8 glossary entit(ies)"`, matching
the store's diff exactly (0 and 8). The real proposal was NOT confirmed — that would have written
into a book this loop did not set up.

The message-less `{"code": "action_error"}` on the confirm side is deliberate and left alone: 60
sites in actions.py share it, and #170 kept it bare for authorization failures precisely so a 403
cannot become an existence oracle. Fixing it belongs to that pattern, not to this tool.
"""

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app" / "mcp" / "server.py"


def _handler() -> str:
    body = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")
    start = body.index("async def plan_bootstrap_apply(")
    return body[start: body.index("\n@mcp_server.tool", start)]


def test_the_mint_verifies_the_proposal_exists():
    fn = _handler()
    assert "svc.get(bid, pid)" in fn, (
        "the mint is back to shape-only validation; a fabricated UUID would again produce a "
        "confirm card for a proposal that does not exist"
    )
    assert "if rec is None:" in fn


def test_the_refusal_names_the_remedy():
    """An agent that cannot get a proposal_id has to be told where one comes from."""
    fn = _handler()
    assert "run plan_bootstrap_propose first" in fn
    assert "book-scoped" in fn, (
        "a proposal from another book will not resolve; say so, or the agent retries the same id"
    )


def test_the_mint_returns_something_a_human_can_judge():
    """It is a WRITE. Handing back only the ids the caller sent leaves the agent with nothing to
    describe on the confirm card."""
    fn = _handler()
    assert '"summary":' in fn
    assert '"new_chapters_count":' in fn
    assert '"new_glossary_entities_count":' in fn


def test_the_counts_come_from_the_proposals_own_diff():
    """Not recomputed from the plan, and not typed — the same `diff` plan_bootstrap_propose
    reports from, so the two tools cannot disagree about one proposal."""
    fn = _handler()
    assert "diff = rec.diff or {}" in fn
    assert 'diff.get("new_chapters"' in fn or "chapters = diff.get(\"new_chapters\", [])" in fn
    assert "new_glossary_entities" in fn


def test_the_edit_gate_still_runs_before_the_lookup():
    """The lookup is only safe because authorization already happened. If the gate moves below
    it, the existence check becomes the oracle it was written to avoid being."""
    fn = _handler()
    assert fn.index("_gate(tc, bid, GrantLevel.EDIT)") < fn.index("svc.get(bid, pid)")
