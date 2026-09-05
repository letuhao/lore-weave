"""D-THE-PERSISTED-PER-PASS-RECORDER-DROPS-A-PASS-ON-THE-SECOND-TURN — the instrument half.

    THE INVARIANT. The store's per-pass record must not be short of the wire, and the two
    counts must be compared WHILE BOTH STILL EXIST.

`chat_messages.advertised_tools` is documented as ONE ENTRY PER MODEL PASS, appended, never
replaced. On session 01a03f44 it held 13 where the log printed 14. Reading that took a
container log, and the first attempt at this class of question found the log already rotated —
so the comparison is now taken on every run, at record time, and stored as `pass_ledger`.

WHAT THE STORE ACTUALLY SHOWS for that session, read back today:

    seq 2  assistant  completed  9 entries  seg=fdf2bb6bec25  p=1..9
    seq 3  user       abandoned_by_user
    seq 5  assistant  completed  4 entries  seg=a1b98ae38254  p=1..4   <- the log printed 5

One segment per turn, pass numbers strictly increasing, no collision. The missing entry is the
TAIL of the resumed turn, not a segment overwrite.

🔴 A HYPOTHESIS REJECTED, recorded because rejecting it is most of the value here. A census of
the five `_persist_terminal_assistant` call sites found ONE — `_materialize_abandoned_suspend`,
the abandoned-suspend path — that passes no `advertised_tools` at all. That looks exactly like
the mechanism, and this session even carries `abandoned_by_user`. It is NOT the cause: the
merge expression opens `WHEN {incoming} IS NULL THEN chat_messages.{column}`, so an omitted
value KEEPS what is stored. The path cannot erase a pass.

THE CAUSE IS STILL UNKNOWN and this file does not claim otherwise. What it changes is that the
next occurrence arrives with both numbers already recorded beside it.

RE-MEASURED after the instrument existed: 0 gaps in 5 sessions (batch c-passledger1), on the
same scenario that produced the original 1-of-5. Across every session measured this way the
rate is now 1 in 15.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

import sys as _sys, pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
import live_stack  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import fe_runner as fr  # noqa: E402

SRC = (ROOT / "scripts" / "toolloop" / "fe_runner.py").read_text(encoding="utf-8")
# 🔴 WAS `docker ps`, WHICH SUCCEEDS ON EVERY GITHUB RUNNER. A guard whose proxy is
# true wherever there is no stack is not a guard: these tests ran in CI and failed with
# connection errors that read like defects. `live_stack.up()` probes the anchor
# gate-wiring-gate already uses, and fails CLOSED if the probe cannot be loaded.
_STACK = live_stack.up()
BATCH = ROOT / "docs" / "eval" / "toolloop" / "2026-08-14" / "c-passledger1-raw.json"


def test_the_runner_records_the_comparison():
    """🔴 THE CALL SITE. A comparison nothing stores is a comparison nobody will have when the
    1-in-15 happens."""
    assert 'res["pass_ledger"] = {"store"' in SRC, "the runner never records the pass ledger"
    at = SRC.index('res["pass_ledger"]')
    seg = SRC[max(0, at - 400):at + 300]
    assert "wire_log_pass_count(sid)" in seg
    assert 'res["wire_passes"] = wire_passes(sid)' in seg, (
        "the two sides are not taken from the same session in the same place"
    )


@pytest.mark.skipif(not live_stack.up(), reason=live_stack.REASON)
def test_an_unreadable_session_is_ABSENCE_not_zero():
    """🔴 A ZERO WOULD CLAIM THE SERVICE PRINTED NOTHING. This loop has already once compared
    against a silently-empty log capture and drawn a conclusion from it, so the reader returns
    None and the gap is None with it."""
    assert fr.wire_log_pass_count("00000000-0000-4000-8000-000000000000") is None


def test_it_reads_STDERR_too():
    """Python logging goes to the container's STDERR; reading stdout alone finds only the access
    log, which is exactly how a comparison silently found zero matches once already."""
    at = SRC.index("def wire_log_pass_count(")
    body = SRC[at:SRC.index("def wire_surfaced_names(", at)]
    assert "p.stdout + p.stderr" in body


def test_the_reader_never_fails_the_run_it_measures():
    at = SRC.index("def wire_log_pass_count(")
    body = SRC[at:SRC.index("def wire_surfaced_names(", at)]
    assert "except Exception" in body and "return None" in body


def test_the_LIVE_batch_agrees_and_NOT_vacuously():
    """ANTI-VACUITY, and the trap this check could most easily fall into: two counts that are
    both ZERO agree perfectly and mean nothing. Both sides must be non-trivial before their
    agreement is evidence of anything."""
    if not BATCH.exists():
        pytest.skip("the pass-ledger batch is not on disk")
    runs = json.loads(BATCH.read_text(encoding="utf-8"))
    ledgers = [r.get("pass_ledger") or {} for r in runs]
    assert ledgers and all(l.get("store") for l in ledgers), (
        "a run recorded no stored passes — the comparison has nothing to compare"
    )
    assert all((l.get("wire_log") or 0) >= 5 for l in ledgers), (
        f"the log side is trivially small: {[l.get('wire_log') for l in ledgers]}"
    )
    assert all(l.get("gap") == 0 for l in ledgers), [l for l in ledgers if l.get("gap")]


def test_the_ORIGINAL_instance_still_shows_the_gap_in_the_store():
    """The row's evidence, re-read from the live store rather than from the row. If it ever
    stops showing 4 entries where the log printed 5, the row must be re-derived, not kept."""
    if not _STACK:
        pytest.skip("needs the local stack")
    out = subprocess.run(
        ["docker", "exec", "-i", "infra-postgres-1", "psql", "-U", "loreweave",
         "-d", "loreweave_chat", "-At", "-F", "|", "-c",
         "SELECT sequence_num, jsonb_array_length(advertised_tools) "
         "FROM chat_messages WHERE session_id='01a03f44-1507-76d3-9012-7853c2befd40' "
         "AND advertised_tools IS NOT NULL ORDER BY sequence_num;"],
        capture_output=True, text=True).stdout.strip()
    if not out:
        pytest.skip("the measured session has aged out of the chat store")
    counts = {int(r.split("|")[0]): int(r.split("|")[1]) for r in out.splitlines()}
    assert counts == {2: 9, 5: 4}, counts


def test_the_omitting_persist_path_CANNOT_erase_a_pass():
    """The rejected hypothesis, pinned. `_materialize_abandoned_suspend` passes no
    `advertised_tools`, which looks like the mechanism — and the merge keeps the stored value
    when the incoming one is NULL, so it is not. If that ever changes, the rejection stops being
    true and this row's investigation restarts from the wrong place."""
    inst = (ROOT / "services" / "chat-service" / "app" / "services" / "instrument.py").read_text(
        encoding="utf-8")
    at = inst.index("def segment_merge_sql(")
    body = inst[at:at + 4000]
    assert "WHEN {incoming} IS NULL THEN chat_messages.{column}" in body, (
        "an omitted advertised_tools may now overwrite the stored value — re-open the rejected "
        "hypothesis in D-THE-PERSISTED-PER-PASS-RECORDER-DROPS-A-PASS-ON-THE-SECOND-TURN"
    )


def test_record_pass_appends_unconditionally():
    """The other half of where the pass could vanish. If the recorder ever starts dropping or
    capping, that becomes the first place to look instead of the last.

    🔴 A FIRST VERSION OF THIS ASSERTION WAS WRONG AND IS CORRECTED RATHER THAN KEPT. It read
    "no `if` anywhere before the append", which fails on `if manifest_revision is not None:` —
    an OPTIONAL FIELD, not a condition on recording. A bar that forbids legitimate code is a bar
    that gets deleted the first time it fires. The property is narrower: the append must be an
    UNCONDITIONAL statement of the function body, which AST can answer and a substring cannot.
    """
    inst = (ROOT / "services" / "chat-service" / "app" / "services" / "instrument.py").read_text(
        encoding="utf-8")
    import ast as _ast
    fn = next(n for n in _ast.walk(_ast.parse(inst))
              if isinstance(n, _ast.FunctionDef) and n.name == "record_pass")
    top = [st for st in fn.body
           if isinstance(st, _ast.Expr) and isinstance(st.value, _ast.Call)
           and getattr(st.value.func, "attr", None) == "append"]
    assert top, (
        "record_pass no longer appends unconditionally at the top level of its body — a pass "
        "can now be dropped before it is recorded"
    )
    nested = [st for st in _ast.walk(fn)
              if isinstance(st, (_ast.If, _ast.Try))
              and any(isinstance(x, _ast.Call) and getattr(x.func, "attr", None) == "append"
                      for x in _ast.walk(st))]
    assert not nested, "the append moved inside a conditional"
