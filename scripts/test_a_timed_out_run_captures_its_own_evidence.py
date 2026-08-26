"""D-THE-MOTIF-LINK-SCENARIO-TIMES-OUT-6-OF-10 — the instrument half.

    THE INVARIANT. A failure must capture its own evidence at the moment it happens.

The row's residual is 2 of 20 runs (10%, down from 60% after the aborted-turn sequence race was
fixed, p=0.007) and its cause is UNKNOWN — not because nobody looked, but because looking
afterwards does not work:

  * the original timed-out sessions' logs had ROTATED before they were read, so the store had
    to be asked instead;
  * two later batches were run with `docker logs -f` open specifically to catch one, and BOTH
    came back 0/5. At a 10% rate that is an expected ~10 runs per capture, and a scenario batch
    is not a cheap way to buy a lottery ticket.

The row's own next step was "a standing log filter that keeps only sessions with no assistant
row". This is that, moved one step earlier: the capture stops being something a person runs
afterwards and becomes something the FAILURE DOES TO ITSELF. It costs nothing until a run
errors, and then it costs one query and one `docker logs`.

WHAT IT CAPTURES, both readings the row itself identified as the useful ones:

  * THE STORE SIGNATURE — a timed-out session holds user rows about TURN_TIMEOUT apart (the
    runner's retry) and ZERO assistant rows. "The turn produced nothing, twice" is a different
    fact from "the tool was slow", and the counts say which.
  * THE SERVICE LOG lines for that session id.

THIS DOES NOT EXPLAIN THE RESIDUAL. It is the instrument that would let the next one explain
itself, and saying otherwise would be claiming a cause this loop does not have.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import fe_runner as fr  # noqa: E402

SRC = (ROOT / "scripts" / "toolloop" / "fe_runner.py").read_text(encoding="utf-8")
_STACK = subprocess.run(["docker", "ps"], capture_output=True).returncode == 0


def test_the_capture_is_AT_BOTH_HANDLERS_INSIDE_send_turn():
    """🔴 THE FIRST ATTEMPT HOOKED THE WRONG PATH AND A LIVE RUN PROVED IT. `run_scenario` never
    sees the exception: BOTH handlers in `send_turn` swallow every httpx error into
    `out["error"]` and return. Forced 3 genuine ReadTimeouts and got `dead_turn: null` on every
    one — a capture wired to a path the failure does not take is the same as no capture."""
    import ast as _ast
    fn = next(n for n in _ast.walk(_ast.parse(SRC))
              if isinstance(n, _ast.AsyncFunctionDef) and n.name == "send_turn")
    calls = [c for c in _ast.walk(fn) if isinstance(c, _ast.Call)
             and getattr(c.func, "id", None) == "capture_dead_turn"]
    assert len(calls) == 2, (
        f"{len(calls)} capture(s) inside send_turn — there are two error handlers (the first "
        "turn and the resume loop) and both must carry it"
    )
    assert all(getattr(a, "id", None) == "session_id" for c in calls for a in c.args)


def test_every_handler_that_sets_an_error_also_captures():
    """The general form, so a THIRD handler added later cannot quietly skip it."""
    import ast as _ast
    fn = next(n for n in _ast.walk(_ast.parse(SRC))
              if isinstance(n, _ast.AsyncFunctionDef) and n.name == "send_turn")
    for h in (n for n in _ast.walk(fn) if isinstance(n, _ast.ExceptHandler)):
        body = _ast.dump(_ast.Module(body=h.body, type_ignores=[]))
        if "'error'" in body:
            assert "capture_dead_turn" in body, (
                "a handler in send_turn records an error without capturing the evidence"
            )


def test_the_backstop_still_exists_and_never_kills_the_run():
    """`run_scenario` keeps a capture for an error that escapes some OTHER way. A capture that
    raises would replace a timeout with a harness crash and destroy the run it exists to
    explain."""
    at = SRC.index("e.dead_turn = capture_dead_turn(sid)")
    seg = SRC[at - 200:at + 200]
    assert "try:" in seg and "except Exception" in seg, seg


@pytest.mark.skipif(not _STACK, reason="needs the local stack")
def test_an_UNKNOWN_session_is_not_reported_as_a_dead_turn():
    """🔴 PRECISION, AND THE FIRST DRAFT GOT IT WRONG. A session that does not exist has no
    assistant row either, so `"assistant" not in rows` reported the dead-turn signature for a
    session id that was never created. The signature is USER ROWS WITH NO ANSWER."""
    d = fr.capture_dead_turn("00000000-0000-4000-8000-000000000000")
    assert d["rows_by_role"] == {}
    assert d["user_rows"] == 0
    assert d["no_assistant_row"] is False


@pytest.mark.skipif(not _STACK, reason="needs the local stack")
def test_a_HEALTHY_session_is_not_reported_as_a_dead_turn():
    row = subprocess.run(
        ["docker", "exec", "-i", "infra-postgres-1", "psql", "-U", "loreweave",
         "-d", "loreweave_chat", "-At", "-c",
         "SELECT session_id FROM chat_messages WHERE role='assistant' "
         "ORDER BY created_at DESC LIMIT 1;"], capture_output=True, text=True).stdout.strip()
    if not row:
        pytest.skip("no assistant row in the chat store")
    d = fr.capture_dead_turn(row, since="6h")
    assert d["user_rows"] >= 1
    assert d["no_assistant_row"] is False, d["rows_by_role"]


@pytest.mark.skipif(not _STACK, reason="needs the local stack")
def test_it_really_reads_the_LOG_and_not_just_the_store():
    """ANTI-VACUITY. The store half alone would have been available all along; the log is the
    half that rotates, and it is the half the row could never get."""
    row = subprocess.run(
        ["docker", "exec", "-i", "infra-postgres-1", "psql", "-U", "loreweave",
         "-d", "loreweave_chat", "-At", "-c",
         "SELECT session_id FROM chat_messages ORDER BY created_at DESC LIMIT 1;"],
        capture_output=True, text=True).stdout.strip()
    if not row:
        pytest.skip("no chat messages")
    d = fr.capture_dead_turn(row, since="6h")
    assert "log_error" not in d, d.get("log_error")
    assert d["log_line_count"] >= 1, (
        "no log line for the most recent session — the reader is looking at the wrong stream "
        "or the wrong container"
    )
    assert all(row in ln for ln in d["log_lines"])


def test_it_reads_STDERR_too():
    """Python logging goes to the container's STDERR. Reading stdout alone finds the access log
    and misses every INFO line — a mistake already made once against this very container, which
    cost a comparison that silently found zero matches."""
    at = SRC.index("def capture_dead_turn(")
    body = SRC[at:SRC.index("async def run_scenario(", at)]
    assert "p.stdout + p.stderr" in body, body[-400:]


@pytest.mark.skipif(not _STACK, reason="needs the local stack")
def test_a_store_failure_is_RECORDED_not_swallowed():
    """The capture is best-effort, but best-effort must still leave a trace: a silent empty
    capture is indistinguishable from a session that genuinely wrote nothing."""
    at = SRC.index("def capture_dead_turn(")
    body = SRC[at:SRC.index("async def run_scenario(", at)]
    assert 'out["store_error"]' in body and 'out["log_error"]' in body
    assert "except (RuntimeError, OSError, ValueError, IndexError)" in body, (
        "the store read swallows more than a store that would not answer"
    )


def test_the_LIVE_forced_timeout_batch_carries_its_evidence():
    """ANTI-VACUITY against a real run. Three genuine ReadTimeouts, forced by dropping the
    per-turn READ timeout below the gap between SSE chunks — which is what that knob actually
    bounds: SILENCE, not total turn length."""
    raw = ROOT / "docs" / "eval" / "toolloop" / "2026-08-14" / "c-deadturn4-raw.json"
    if not raw.exists():
        pytest.skip("the forced-timeout batch is not on disk")
    runs = json.loads(raw.read_text(encoding="utf-8"))
    errored = [r for r in runs if r.get("error")]
    assert errored, "the forced-timeout batch recorded no error"
    for r in errored:
        dt = r.get("dead_turn")
        assert dt, f"an errored run carries no capture: {r.get('error')}"
        assert dt.get("user_rows", 0) >= 1
        assert dt.get("no_assistant_row") is True, dt.get("rows_by_role")
        assert dt.get("log_line_count", 0) >= 1, "no service log line was captured"


def test_the_turn_timeout_flag_is_not_frozen_at_import():
    """🔴 `--turn-timeout` WAS INERT. `send_turn`'s default was `timeout=TURN_TIMEOUT`, which
    binds at IMPORT, so setting the module global in main() never reached the per-turn request
    that overrides the client's own timeout. The flag moved the AsyncClient and nothing else.

    That matters beyond tidiness: the row records "raising the per-turn timeout to 300s changed
    nothing" as evidence. It ran at 180 both times."""
    import inspect
    assert inspect.signature(fr.send_turn).parameters["timeout"].default is None, (
        "the default is bound at import again — the flag is inert"
    )
    body = inspect.getsource(fr.send_turn)
    assert "if timeout is None:" in body and "timeout = TURN_TIMEOUT" in body
