"""D-THE-TRANSPORT-STALL-IS-THREE-DIFFERENT-FAILURES.

    THE INVARIANT. A single error rate over several populations cannot move, and a cause that
    explains one of them looks REFUTED by the others.

"The transport stall" was treated as one phenomenon and hunted with one hypothesis at a time.
THIRTEEN were refuted for composition_motif_link_edit — not load, not eviction, not probe
contention, not service state, not turn count, not schema size, not encoding, not context
pressure, not payload size — because each was tested against a MIXED population. Its own runs
contain ReadTimeout-with-no-calls AND upstream-error-after-a-search, counted as one ~49%.

RE-DERIVED 2026-08-27 over 121 errored runs instead of 80:

    provision                    25    the SEED could not build the fixture — not the platform
    no_output_timeout            30    ReadTimeout, ZERO tool calls
    timeout_after_call            8    ReadTimeout after the turn had already called something
    upstream_silent_no_call      13    provider failed without saying why, before any call
    upstream_silent_after_call   45    provider failed without saying why, MID-turn

🔴 THE ROW'S TABLE SHOWED 5 ZERO-CALL UPSTREAM ERRORS; THERE ARE 13. The error STRING is
identical in both cells — "upstream sent 'error' with no error message (response id "", status
"") — the provider reported a failure without saying why" — and the tool-call count is the only
thing that separates them. Reading the string alone merges two populations.

The split is now DERIVED ON EVERY RUN rather than by hand once, and the report refuses to print
one number over them. On c-motiflink2, the batch the row cites:

    composition-motif-link-edit  5  3/5  5/5  4  unchanged
        ^ the errors are NOT one population: 2x no_output_timeout,
          2x upstream_silent_after_call

This does not diagnose any of them. It stops the next thirteen hypotheses being tested against
a mixture.
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import fe_runner as fr  # noqa: E402

SRC = (ROOT / "scripts" / "toolloop" / "fe_runner.py").read_text(encoding="utf-8")
SILENT = ("{'type': 'RUN_ERROR', 'message': 'upstream sent \"error\" with no error message "
          "(response id \"\", status \"\") — the provider reported a failure without saying why'}")


def test_a_clean_run_has_no_population():
    assert fr.error_population(None, 0) is None
    assert fr.error_population("", 3) is None


def test_the_TOOL_CALL_COUNT_is_what_splits_the_identical_error():
    """🔴 THE HALF THE ROW UNDER-COUNTED. Same string, two populations — 13 before any call and
    45 mid-turn. A classifier reading the message alone merges them and recreates the mixture."""
    assert fr.error_population(SILENT, 0) == "upstream_silent_no_call"
    assert fr.error_population(SILENT, 4) == "upstream_silent_after_call"


def test_a_timeout_splits_the_same_way():
    assert fr.error_population("ReadTimeout: ", 0) == "no_output_timeout"
    assert fr.error_population("ReadTimeout: ", 1) == "timeout_after_call"


def test_a_seed_failure_is_NOT_the_platform():
    """25 of 121 errored runs never tested the platform at all."""
    assert fr.error_population("PROVISION ProvisionError: seed step 0 …", 0) == "provision"
    assert fr.error_population("PROVISION MCPToolError: …", 0) == "provision"


def test_an_unknown_error_is_named_other_not_guessed_into_a_bucket():
    assert fr.error_population("ConnectionResetError: boom", 2) == "other"


def test_every_population_is_declared():
    for e, n in ((SILENT, 0), (SILENT, 2), ("ReadTimeout:", 0), ("ReadTimeout:", 2),
                 ("PROVISION x", 0), ("weird", 1)):
        assert fr.error_population(e, n) in fr.ERROR_POPULATIONS


def test_the_runner_records_it_on_BOTH_error_paths():
    """🔴 THE CALL SITES. `send_turn` swallows every httpx error into the record, while a
    provisioning failure raises past it — a label written on only one path leaves the other
    unclassified, which is the mixture again."""
    assert 'res["error_population"] = error_population(res["error"], len(called_names(res)))' in SRC
    assert 'r["error_population"] = error_population(r["error"], 0)' in SRC


def test_the_report_REFUSES_to_print_one_number_over_them():
    """🔴 RENDER IT, DO NOT GREP FOR IT. A first version asserted the two strings were present
    in the source — and `if _pops:` -> `if False:` left them present and the guard green. The
    line has to actually reach stdout."""
    import io
    from contextlib import redirect_stdout
    runs = [{"scenario": "s", "surfaces": [], "results": [], "tool_calls": [],
             "store_diff": {}, "error": "ReadTimeout: "},
            {"scenario": "s", "surfaces": [], "results": [],
             "tool_calls": [{"type": "TOOL_CALL_START", "toolCallName": "x"}],
             "store_diff": {}, "error": SILENT},
            {"scenario": "s", "surfaces": [], "results": [], "tool_calls": [],
             "store_diff": {}}]
    buf = io.StringIO()
    with redirect_stdout(buf):
        fr.report(runs, [{"id": "s", "expect_tool": "x"}], len(runs))
    out = buf.getvalue()
    assert "the errors are NOT one population" in out, out
    assert "1x no_output_timeout" in out and "1x upstream_silent_after_call" in out, out


def test_a_batch_with_ONE_population_still_says_so_plainly():
    """PRECISION. The line is about the SPLIT; when there is only one it must still print, or a
    reader cannot tell "one population" from "nobody looked"."""
    import io
    from contextlib import redirect_stdout
    runs = [{"scenario": "s", "surfaces": [], "results": [], "tool_calls": [],
             "store_diff": {}, "error": "ReadTimeout: "} for _ in range(3)]
    buf = io.StringIO()
    with redirect_stdout(buf):
        fr.report(runs, [{"id": "s", "expect_tool": "x"}], len(runs))
    assert "3x no_output_timeout" in buf.getvalue()


def test_the_MIXED_batch_the_row_cites_really_is_mixed():
    """ANTI-VACUITY against the corpus. If c-motiflink2's four errors were one population the
    row's whole argument would be gone."""
    p = ROOT / "docs" / "eval" / "toolloop" / "2026-08-14" / "c-motiflink2-raw.json"
    if not p.exists():
        import pytest
        pytest.skip("the cited batch is not on disk")
    runs = json.loads(p.read_text(encoding="utf-8"))
    pops = collections.Counter(
        fr.error_population(r.get("error"), len(fr.called_names(r)))
        for r in runs if r.get("error"))
    assert len(pops) >= 2, pops
    assert pops["no_output_timeout"] and pops["upstream_silent_after_call"], pops


def test_the_corpus_split_still_has_every_population():
    """ANTI-VACUITY on the size. A classifier that puts everything in one bucket would pass every
    test above and say nothing."""
    pops = collections.Counter()
    for f in sorted((ROOT / "docs" / "eval" / "toolloop").rglob("*-raw.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, list):
            continue
        for r in d:
            if isinstance(r, dict) and r.get("error"):
                pops[fr.error_population(r["error"], len(fr.called_names(r)))] += 1
    assert sum(pops.values()) >= 100, pops
    for p in ("provision", "no_output_timeout", "upstream_silent_no_call",
              "upstream_silent_after_call"):
        assert pops[p] >= 5, (p, dict(pops))
    assert max(pops.values()) < sum(pops.values()) * 0.6, (
        f"one bucket holds most of the corpus — the split is not discriminating: {dict(pops)}"
    )
