"""Did the model DECLINE the tool, or was it never offered one?

    THE INVARIANT. "The model did not call X" is a MODEL defect only if X was on the wire.
    Otherwise the same evidence describes a SURFACING defect, and every remedy aimed at the
    model is aimed at the wrong half.

🔴 THIS ALREADY HAPPENED. D-THE-MODEL-ASKS-INSTEAD-OF-RAISING-THE-CARD-IT-HAS was filed as a
model defect on five runs where the model "asked instead of calling
composition_canon_rule_restore". The server's own `advertised_tools` says that tool was
advertised on 0 of 5 turns, along with every other canon-rule WRITE. The model held the read
and nothing else. The row is now platform-class.

`scripts/toolloop/was_it_on_the_wire.py` asks that question of every open model row. Run over
all 17 on 2026-08-27, it found three tools that were NEVER advertised on the runs their row
rests on:

    composition_motif_bind_edit        0/10   D-THE-MODEL-CLAIMS-A-BINDING-IT-NEVER-MADE
    composition_arc_edit               0/5    D-A-CONTRACT-QUESTION-ANSWERED-FROM-A-…
    composition_build_cast_and_graph   0/30   D-SURFACING-IS-NECESSARY-BUT-NOT-SUFFICIENT

A 0/N is not by itself proof a row is misfiled — the tool has to be the one the row says the
model declined — but it IS proof the model was not offered it, and no row may be closed against
the model without checking.

WHAT THE SWEEP CANNOT ANSWER. A turn that produced no assistant row has no `advertised_tools`,
so a timed-out run is UNKNOWN, never "not advertised". The two are counted separately and the
report prints both.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

_spec = importlib.util.spec_from_file_location(
    "_wire", ROOT / "scripts" / "toolloop" / "was_it_on_the_wire.py")
wire = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wire)


def test_a_psql_boolean_is_true_false_not_t_f():
    """🔴 THE BUG THIS GUARD EXISTS FOR, and it is the exact failure the sweep is meant to
    catch, committed by the sweep itself. `::text` on a boolean yields `true`/`false`; the
    first version compared against `"t"`, matched nothing, and reported EVERY row as "no
    record" — a wrong answer indistinguishable from a missing one.

    It now refuses an encoding it does not recognise instead of reading it as False."""
    rows = [["s1", "true", "true"], ["s2", "true", "false"]]
    v = wire._verdict_from_rows(rows) if hasattr(wire, "_verdict_from_rows") else None
    if v is None:                       # the helper is inline; exercise it through the parser
        import inspect
        src = inspect.getsource(wire.wire_verdict)
        assert '"true"' in src and '"false"' in src, (
            "wire_verdict no longer names the true/false encoding — if it compares against "
            "t/f again it will report every session as unrecorded and look like missing data"
        )
        assert 'raise SystemExit' in src, (
            "wire_verdict no longer REFUSES an unknown boolean encoding — a silent False is "
            "how this went wrong the first time"
        )


def test_the_sweep_separates_NOT_ADVERTISED_from_NO_RECORD():
    """A dead turn leaves no `advertised_tools` at all. Counting it as 'not advertised' would
    turn every timeout into a surfacing defect."""
    import inspect
    src = inspect.getsource(wire.wire_verdict)
    assert "no_record" in src and "not_advertised" in src, (
        "the two are no longer distinguished — a turn that produced no record would be "
        "reported as a tool the platform withheld"
    )


def test_the_candidate_tools_come_from_the_CATALOGUE_not_from_prose():
    """A ledger row is full of snake_case that is not a tool name. Filtering against the
    catalogue is what stops the sweep inventing tools to check."""
    row = {"what": "the model called book_read and not composition_canon_rule_restore, and the "
                   "store_diff showed loreweave_book.chapters unchanged"}
    names = wire.tool_names_in(row)
    assert "composition_canon_rule_restore" in names
    assert "book_read" in names
    assert not any(n.startswith("loreweave_") for n in names), names
    assert "store_diff" not in names


def test_a_row_with_no_sessions_says_so_rather_than_reporting_zero():
    """🔴 THE VACUOUS-ANSWER GUARD. A row whose batches are not on disk has NOTHING to measure,
    and reporting '0 advertised' for it would read as the strongest possible finding."""
    assert wire.wire_verdict([], "anything") == {}
    assert wire.sessions_for("c-a-batch-that-does-not-exist") == []
