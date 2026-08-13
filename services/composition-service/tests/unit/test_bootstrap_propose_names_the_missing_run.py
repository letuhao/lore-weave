"""FRONTEND JOURNEY LOOP D-FJ-13 — the step BEFORE the one that already fixed this.

`plan_bootstrap_apply` was fixed in TOOLV2 LOOP #272 and its comment states the argument in full:
the lookup is book-scoped (`get_for_book`) and the caller has already passed the EDIT gate one line
above, "so this reveals nothing they could not already read". It refuses a fabricated proposal by
name and points at the tool that mints a real one.

`plan_bootstrap_propose` — the step immediately BEFORE it in the `autonomous-drafting` rail — was
left raising `uniform_not_accessible()` for exactly the same condition. That is the half-fix shape:
the reasoning was written down, applied at one site, and the neighbouring site left alone.

🔴 MEASURED LIVE 2026-08-12, journey `autonomous-drafting`, book 019ff497. With D-FJ-10 the rail
finally engaged and the model reached this, the rail's real first step, with:

    book_id = 019ff497-dff3-7f26-9565-7e284f7ca71c   ← CORRECT, the book
    run_id  = 019ff497-e068-77db-89f7-9d8c298fe8cd   ← the book's KNOWLEDGE PROJECT id

A well-formed UUID of the wrong entity. The answer was "not found or not accessible", which names
neither which of the two ids was wrong nor where a real run_id comes from, and the journey stopped
there with chapters=0.

D-FJ-11 deliberately does not catch this upstream: it accepts any syntactically valid id because
"whether it is the RIGHT row is the tool's question, not ours". This is the tool answering it.
"""

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "app" / "mcp" / "server.py"


def _handler() -> str:
    body = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")
    start = body.index("async def plan_bootstrap_propose(")
    return body[start: body.index("\n@mcp_server.tool", start)]


def test_a_missing_run_is_not_reported_as_an_access_failure():
    """The caller has already passed the EDIT gate on this book, so a run that is not here is a
    wrong-argument condition, not an ownership one."""
    fn = _handler()
    assert "uniform_not_accessible()" not in fn, (
        "a run_id that names nothing on a book the caller can already edit is still being reported "
        "as an access failure, which names neither the wrong argument nor a way forward"
    )


class _Row:
    """A plan_run as the refusal reads it — only `.id` and `.status` are consulted."""

    def __init__(self, rid: str, status: str) -> None:
        self.id, self.status = rid, status


def test_the_refusal_names_the_offending_id_and_the_remedy():
    """An agent that cannot get a run_id has to be told where one comes from — and naming the tool
    also ARMS it, because chat-service's recovery arm keys off catalogue names in the refusal."""
    from app.mcp.server import _missing_run_message

    msg = _missing_run_message("019ff497-e068-77db-89f7-9d8c298fe8cd", [])
    assert "no plan run 019ff497-e068-77db-89f7-9d8c298fe8cd" in msg, (
        "the refusal does not repeat the offending id, so a caller juggling several cannot tell "
        "which one it rejected"
    )
    assert "plan_propose_spec" in msg, (
        "the refusal does not name the tool that emits a run_id, so the caller has nowhere to go"
    )
    assert "book-scoped" in msg, (
        "a run from another book will not resolve here; say so, or the agent retries the same id"
    )
    assert "plan_compile" in msg, "the compile precondition is not stated, so the next call fails too"


def test_a_book_that_ALREADY_HAS_runs_is_told_which_ones():
    """🔴 MEASURED LIVE 2026-08-12, book 019ff497 — the defect this guard exists for.

    With the first form of this refusal (which named `plan_propose_spec` and nothing else) the
    model answered: "I'll find your plan: I'll look for the most recent plan we've worked on" —
    and then STOPPED and asked the author. Its instinct was right: this book holds a COMPILED run
    (019ff49a-f12b-732f-a0cf-73dd0cfcae76), so "create a run" means re-planning a planned book,
    and it declined to do that unasked. The ids are one book-scoped read away from a caller who
    has already passed the EDIT gate, so the refusal must simply say them.
    """
    from app.mcp.server import _missing_run_message

    msg = _missing_run_message(
        "019ff497-e068-77db-89f7-9d8c298fe8cd",
        [_Row("019ff49a-f12b-732f-a0cf-73dd0cfcae76", "compiled"),
         _Row("019ff333-0000-7000-8000-000000000000", "proposed")],
    )
    assert "019ff49a-f12b-732f-a0cf-73dd0cfcae76" in msg, (
        "the book's own plan run is not named, so the caller is left to guess an id the tool "
        "had in hand"
    )
    assert "compiled" in msg and "proposed" in msg, (
        "the statuses are dropped, so the caller cannot tell which run this tool will accept"
    )
    assert "NO plan runs" not in msg and "create one" not in msg, (
        "a book that ALREADY has runs is still being told to create a new one — which is what "
        "made the model stop and ask rather than proceed"
    )


def test_a_book_with_NO_runs_is_still_sent_to_the_emitter():
    """The CONTROL. Naming existing runs must not delete the only remedy a fresh book has — and a
    fresh book is the common case for this rail's first ever call."""
    from app.mcp.server import _missing_run_message

    msg = _missing_run_message("019ff497-e068-77db-89f7-9d8c298fe8cd", [])
    assert "plan_propose_spec" in msg, (
        "a book with no runs at all is no longer told how to make one"
    )


def test_the_listing_is_an_enrichment_and_never_masks_the_refusal():
    """If reading the book's runs fails, the caller must still get the real refusal. A best-effort
    read that can turn a wrong-argument answer into a 500 is worse than not reading at all."""
    fn = _handler()
    assert "rows = []" in fn and "except Exception:" in fn, (
        "the plan-run listing is not fenced, so a repo failure would replace the refusal that "
        "actually explains the caller's mistake"
    )
    assert "_missing_run_message(run_id, rows)" in fn, (
        "the handler no longer passes the book's real runs into the refusal, so the message can "
        "only ever emit the no-runs branch"
    )
    assert "list_for_book(bid" in fn, (
        "the runs are not read for THIS book, so the refusal would name another book's runs"
    )


def test_the_compiled_precondition_is_still_distinguished():
    """The 'run exists but is not compiled' path is a DIFFERENT answer and must stay that way — it
    already returns an actionable detail, and collapsing the two would lose that."""
    fn = _handler()
    assert "except ValueError as exc:" in fn and '"success": False' in fn, (
        "the not-yet-compiled branch was folded into the not-found one; they are different "
        "conditions with different remedies"
    )
    from app.mcp.server import _missing_run_message

    assert "cannot preview" in fn, "the uncompiled branch lost its own label"
    assert "cannot preview" not in _missing_run_message("x", []), (
        "the two conditions no longer have distinct labels, so a caller cannot tell a missing run "
        "from an uncompiled one"
    )


def test_a_malformed_run_id_is_a_SHAPE_error_not_a_STATE_error():
    """🔴 The second half of the same half-fix. `plan_bootstrap_apply` validates
    `_uuid(proposal_id, "proposal_id")` OUTSIDE its try, commented "validate shape before minting".
    Here `_uuid` sat INSIDE the try, so a malformed id raised ValueError and was caught by the
    not-yet-compiled arm — reporting a BAD ARGUMENT as a STATE problem.

    MEASURED LIVE 2026-08-12: called with run_id="arc_1" (an arc id), the model was told "cannot
    preview" — the sentence meaning "run has no compiled package yet". That run WAS compiled and
    had three package artifacts, so the only hint it got pointed at the one thing that was fine.
    """
    fn = _handler()
    uuid_at = fn.index('_uuid(run_id, "run_id")')
    try_at = fn.index("    try:")
    assert uuid_at < try_at, (
        "_uuid(run_id) is still inside the try, so a malformed id is reported as a compile-state "
        "problem instead of a bad argument"
    )


def test_the_reason_travels_IN_the_error_not_only_beside_it():
    """The caller received `error: "cannot preview"` with the `detail` dropped by the envelope. A
    label without its reason is the same shape as a failure emitted with no message."""
    fn = _handler()
    assert 'f"cannot preview — {str(exc)[:300]}"' in fn, (
        "the explanation lives only in `detail`, which an envelope already dropped once"
    )
