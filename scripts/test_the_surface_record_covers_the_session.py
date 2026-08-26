"""D-HARNESS-agentSurface-DISAGREES-WITH-THE-WIRE-LOG.

chat-service logs the real per-pass wire set for the WHOLE SESSION
(`agent-surface advertised (session=...): ... activated=[...]`). The harness recorded the
surfaces of the MEASURED TURN ONLY and threw the rest away, and the loop then read
"advertised in N of M snapshots" off what survived as if it covered the session. On
01a02e76 the log showed composition_arc_apply on 4 of 6 passes and the record showed it in
0 of 6 snapshots. Both numbers were right about different turns; only one was cited.

NOT A TRACKER BUG, which is where the row said to look. `advertised_pass()` and the INFO
line are built from the SAME three lists in the same block of stream_service, so their
CONTENT cannot diverge — isolated 2026-08-27 by reading the recorded run itself:

    01a02e76 rep0: snapshots=6  arc_apply in surfaces=0  prior_turns=1
                   prior turn called: composition_arc_apply, composition_arc_suggest

The tool ran in the turn whose surfaces were discarded.

THE SIZE OF THE BLIND SPOT, over every raw record on disk: 412 of 1,420 runs are
multi-turn, and in 32 of those a tool PROVEN CALLED in an earlier turn appears nowhere in
the instrument's surface set — translation_start_job 14, translation_retranslate_dirty 14,
composition_arc_apply 12, plan_bootstrap_propose 5. A floor, not the total: a tool
advertised and NOT called in an earlier turn left no trace at all to count.

The fix keeps every turn's passes and keeps the two questions apart. `surfaced_names` stays
TURN-SCOPED — the bars ask what the model could see when it chose, and unioning earlier
turns into it would be the opposite error, calling a tool surfaced that was displaced
before the measured turn ever ran.
"""
from __future__ import annotations

import ast
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import fe_runner  # noqa: E402

#: The ORIGINAL instance, on disk, in the pre-fix format.
ORIGINAL = ROOT / "docs" / "eval" / "toolloop" / "2026-08-14" / "c-arcapply2-raw.json"


def _turn(passes: list[list[str]]) -> dict:
    return {"surfaces": [{"advertised": {"activated": list(p)}} for p in passes],
            "tool_calls": [], "text": ""}


def test_the_recorder_keeps_every_pass_of_an_earlier_turn():
    rec = fe_runner.prior_turn_record("do the thing", _turn([["a_tool"], ["a_tool", "b_tool"]]))
    assert rec["surface_passes"] == [["a_tool"], ["a_tool", "b_tool"]], rec
    assert rec["prompt"] == "do the thing"


def test_a_union_cannot_date_a_choice():
    """PER PASS, not a set. A tool that arrived only on the last pass of an earlier turn is a
    different fact from one advertised throughout, and flattening loses it."""
    rec = fe_runner.prior_turn_record("x", _turn([["early"], ["early", "late"]]))
    assert "late" not in rec["surface_passes"][0]
    assert "late" in rec["surface_passes"][1]


def test_the_TURN_scoped_reader_does_NOT_union_earlier_turns():
    """PRECISION, and the error opposite to the defect. A tool displaced BEFORE the measured
    turn must not read as surfaced — that is what the bars are asking."""
    r = {"surfaces": [{"advertised": {"activated": ["measured_tool"]}}],
         "prior_turns": [fe_runner.prior_turn_record("x", _turn([["gone_by_now"]]))]}
    assert fe_runner.surfaced_names(r) == {"measured_tool"}
    assert "gone_by_now" not in fe_runner.surfaced_names(r)


def test_the_SESSION_scoped_reader_sees_the_earlier_turn():
    """RECALL — the half that was unrecoverable before, because the data was discarded."""
    r = {"surfaces": [{"advertised": {"activated": ["measured_tool"]}}],
         "prior_turns": [fe_runner.prior_turn_record("x", _turn([["gone_by_now"]]))]}
    assert fe_runner.earlier_surfaced_names(r) == {"gone_by_now"}


def test_an_old_record_reports_ABSENCE_not_zero():
    """A record written before 2026-08-27 has no `surface_passes`. It must read as no
    evidence — an empty set the caller cannot mistake for a measured zero is the best this
    can do, so the docstring says so and this pins that it does not invent names."""
    old = {"surfaces": [], "prior_turns": [{"prompt": "x", "called": ["t"], "text": ""}]}
    assert fe_runner.earlier_surfaced_names(old) == set()


def test_the_ORIGINAL_instance_is_still_unreadable_and_that_is_the_point():
    """ANTI-VACUITY against the real evidence. The recorded run that the row was written from
    still shows the tool called in a discarded turn and absent from every kept snapshot. The
    fix does not repair this file — nothing can — it stops the next one being written."""
    if not ORIGINAL.exists():
        import pytest
        pytest.skip("the original batch record is not on disk")
    runs = json.loads(ORIGINAL.read_text(encoding="utf-8"))
    hits = [r for r in runs
            if "composition_arc_apply" in {c for t in (r.get("prior_turns") or [])
                                           for c in (t.get("called") or [])}]
    assert hits, "the original instance no longer shows the tool called in an earlier turn"
    for r in hits:
        assert "composition_arc_apply" not in fe_runner.surfaced_names(r), (
            "the measured turn now advertises it — this file's premise is gone"
        )
        assert not any("surface_passes" in t for t in r["prior_turns"]), (
            "the original record has been rewritten; it is evidence, not a fixture"
        )


def test_the_LOOP_uses_the_chokepoint():
    """🔴 ASSERT THE CALL SITE. The dropped field was invisible precisely because the record
    was built INLINE in the turn loop, so a helper alone proves nothing about what gets
    written. Pin that the loop calls it and builds no dict of its own."""
    src = (ROOT / "scripts" / "toolloop" / "fe_runner.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    appends = [n for n in ast.walk(tree)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr == "append"
               and isinstance(n.func.value, ast.Name) and n.func.value.id == "prior"]
    assert len(appends) == 1, f"{len(appends)} places write a prior turn — there must be one"
    arg = appends[0].args[0]
    assert isinstance(arg, ast.Call) and getattr(arg.func, "id", None) == "prior_turn_record", (
        "the turn loop builds the prior-turn record inline again"
    )


def test_the_report_separates_the_two_counts():
    """The number that was misread is a REPORTED number. Keeping the data but printing one
    conflated column would leave the defect where it was found."""
    src = (ROOT / "scripts" / "toolloop" / "fe_runner.py").read_text(encoding="utf-8")
    assert "earlier_only" in src and "EARLIER turn only" in src
    at = src.index("surfaced = sum(")
    seg = src[at:at + 700]
    assert "earlier_surfaced_names" in seg, "the report never asks the session question"
    assert "not in surfaced_names(r)" in seg, (
        "earlier-only is not exclusive of surfaced — the two counts overlap and the column "
        "means two things again"
    )


# ── the COUNT half of the row: "The counts differ AND the content differs." ───────────────
#
# The content half is above. The counts differ for a SECOND, independent reason: an
# `agentSurface` event is not a pass. It fires on every phase transition (Curated,
# SkillInjected, Activated, ToolRunning, Idle) and is SUPPRESSED on a pass whose surface did
# not change — `AgentSurfaceTracker.advertised_pass()` returns None unless something moved. So
# the snapshot count runs both above and below the pass count, and no arithmetic on it
# recovers the truth. Measured on 01a03f32: the measured turn kept 4 snapshots (phases
# Curated, SkillInjected, SkillInjected, Idle) of which only 2 changed the advertised set,
# while the session ran 6 passes.
#
# chat-service already persists the real thing — `chat_messages.advertised_tools`, one entry
# per pass, appended, from the same list the chokepoint hands the provider. The harness now
# reads it.

def _stack():
    import subprocess
    return subprocess.run(["docker", "ps"], capture_output=True).returncode == 0


def test_the_store_reader_reproduces_the_wire_log():
    """LIVE, against the session the fix was verified on. 4 passes in turn 1 + 2 in turn 2 = 6,
    which is exactly what `docker logs infra-chat-service-1 | grep agent-surface` printed."""
    if not _stack():
        import pytest
        pytest.skip("needs the local stack")
    ps = fe_runner.wire_passes("01a03f32-3a21-7401-a14e-bf4bc0453b2c")
    if not ps:
        import pytest
        pytest.skip("the verification session has aged out of the chat store")
    assert len(ps) == 6, [p["pass"] for p in ps]
    assert sorted({p["turn"] for p in ps}) == [2, 4], "the reader is not covering both turns"
    assert "catalog_get_book" in fe_runner.wire_surfaced_names({"wire_passes": ps})


def test_the_reader_is_not_dead():
    """🔴 ANTI-VACUITY, and the exact trap a sibling counter fell into: the oracle is imported
    INSIDE the function, so a stale import raises NameError, and a wide `except` would turn a
    dead reader into an honest-looking empty. An unknown session must return [] by finding no
    rows — not by failing."""
    if not _stack():
        import pytest
        pytest.skip("needs the local stack")
    assert fe_runner.wire_passes("00000000-0000-4000-8000-000000000000") == []
    # Read from the AST, not from the text: this function's own COMMENT quotes the bare
    # `except Exception` it exists to avoid, and a substring check happily fails on prose.
    src = pathlib.Path(fe_runner.__file__).read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "wire_passes")
    caught = set()
    for h in (n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)):
        t = h.type
        parts = t.elts if isinstance(t, ast.Tuple) else [t]
        caught |= {getattr(x, "id", "?") for x in parts if x is not None}
        assert h.type is not None, "a bare `except:` in the reader"
    assert caught <= {"RuntimeError", "OSError", "ValueError", "TypeError"}, (
        f"the reader swallows more than a store that would not answer: {sorted(caught)}"
    )
    assert "RuntimeError" in caught


def test_a_snapshot_is_not_a_pass():
    """The premise of the whole count half. If the SSE snapshots ever became one-per-pass this
    file's second half would be pointless — so pin that they are not, from a real record."""
    raw = ROOT / "docs" / "eval" / "toolloop" / "2026-08-14" / "c-surfrec3-raw.json"
    if not raw.exists():
        import pytest
        pytest.skip("the verification batch is not on disk")
    runs = json.loads(raw.read_text(encoding="utf-8"))
    r = next((x for x in runs if x.get("wire_passes")), None)
    if r is None:
        import pytest
        pytest.skip("recorded before wire_passes existed")
    snaps = len(r.get("surfaces") or []) + sum(
        len(t.get("surface_passes") or []) for t in (r.get("prior_turns") or []))
    assert snaps != len(r["wire_passes"]), (
        "snapshots and passes now agree — re-derive whether the suppression still exists"
    )
    # Live, 5 runs: 26-31 snapshots against 13-15 passes. Roughly double, and not by a constant
    # factor — phase transitions and advertise-changes are two unrelated event streams.
    assert snaps > len(r["wire_passes"])


def test_the_runner_records_the_wire_passes():
    """🔴 THE CALL SITE AGAIN. A reader nothing calls is the same defect by another route, and
    this loop has shipped that exact shape twice."""
    src = (ROOT / "scripts" / "toolloop" / "fe_runner.py").read_text(encoding="utf-8")
    assert 'res["wire_passes"] = wire_passes(sid)' in src, (
        "the runner never records the authoritative per-pass set"
    )
    assert "ON THE WIRE (store, every turn)" in src, (
        "the report never quotes the pass-based figure, so the misread number stays the only "
        "one on offer"
    )
