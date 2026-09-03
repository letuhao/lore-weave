"""D-IDEMPOTENCY-PROBE-COUNTS-ROWS-NOT-LIFECYCLE.

The probe decided by comparing ROW COUNTS either side of the second call. A tool that
SOFT-archives the prior rows and writes replacements grows the table, so it was reported
"🔴 NOT IDEMPOTENT — the second call DUPLICATED: outline_node 3->5" — which is false. The old
rows were archived, exactly as the tool's description promises. Measured on
composition_motif_bind_edit, 2026-08-23.

A later pass softened that to "⚠ INCONCLUSIVE" and NAMED the check that would settle it
("count ACTIVE rows only"), deliberately not running it. This runs it.

🔴 `status` MEANS FOUR DIFFERENT THINGS ACROSS THE SIX SOFT-ARCHIVING TABLES, and the obvious
predicate would have been wrong on the very table the defect was measured on. Read from the
store 2026-08-26:

    arc_template / composition_work / motif   active | archived                <- lifecycle
    outline_node                              done | drafting | empty | outline
    structure_node                            drafting | outline
    glossary_entities                         active | draft | inactive | rejected

So `status <> 'archived'` is a lifecycle test for three of them and a WORKFLOW state for the
rest. outline_node's archive flag is `is_archived` (65 of 640 rows true) and
glossary_entities' is `deleted_at` (34 set). One column name, four meanings — the predicate is
per-table and read from the data.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import idempotency_probe as ip  # noqa: E402

pytestmark = pytest.mark.skipif(
    subprocess.run(["docker", "ps"], capture_output=True).returncode != 0,
    reason="needs the local stack",
)


def _sql(db: str, q: str) -> str:
    return subprocess.run(
        ["docker", "exec", "-i", "infra-postgres-1", "psql", "-U", "loreweave", "-d", db, "-At", "-c", q],
        capture_output=True, text=True,
    ).stdout.strip()


def test_every_soft_archiving_table_has_a_predicate():
    """A table in the soft-archiving set with no predicate would silently fall out of the count
    and take the verdict back to INCONCLUSIVE for that tool."""
    assert set(ip._SOFT_ARCHIVING_TABLES) == set(ip._ACTIVE_PREDICATE)
    assert len(ip._ACTIVE_PREDICATE) >= 6


def test_the_predicate_is_NOT_status_for_the_measured_table():
    """The trap. outline_node is the table the defect was measured on, and its `status` is a
    workflow state — `done|drafting|empty|outline` — with no 'archived' among them. A
    status-based predicate would count every row as active and the verdict would never fire."""
    db, pred = ip._ACTIVE_PREDICATE["outline_node"]
    assert "is_archived" in pred, pred
    assert "status" not in pred, pred
    statuses = _sql(db, "SELECT string_agg(DISTINCT status, ',') FROM outline_node;")
    assert "archived" not in (statuses or ""), (
        f"outline_node.status now contains 'archived' ({statuses}) — re-check this predicate"
    )


def test_each_predicate_actually_runs():
    """🔴 THE FIRST DRAFT RETURNED {} FOREVER. `oracle` is imported inside functions in that
    file, so the new counter raised NameError on every table and a bare `except Exception:
    continue` turned it into "no counts" — which the verdict reads as INCONCLUSIVE. It would
    have shipped dead and looked exactly like the defect it replaced."""
    book = _sql("loreweave_composition",
                "SELECT book_id FROM outline_node WHERE book_id IS NOT NULL LIMIT 1;")
    if not book:
        pytest.skip("no book with outline nodes")
    counts = ip._active_counts(list(ip._ACTIVE_PREDICATE), book)
    assert set(counts) == set(ip._ACTIVE_PREDICATE), (
        f"a table produced no count at all — the reader is dead for it: {sorted(counts)}"
    )
    assert all(isinstance(v, int) for v in counts.values())


def test_the_active_count_differs_from_the_total_where_rows_are_archived():
    """The discrimination itself. If active == total everywhere, the new count carries no
    information the old one did not."""
    book = _sql("loreweave_composition",
                "SELECT book_id FROM outline_node GROUP BY book_id "
                "HAVING count(*) FILTER (WHERE is_archived) > 0 LIMIT 1;")
    if not book:
        pytest.skip("no book with archived outline nodes to discriminate on")
    total = int(_sql("loreweave_composition",
                     f"SELECT count(*) FROM outline_node WHERE book_id='{book}';") or 0)
    active = ip._active_counts(["outline_node"], book)["outline_node"]
    assert active < total, (
        f"active {active} == total {total} on a book with archived rows — no discrimination"
    )


def test_the_verdict_reads_the_active_counts():
    """A counter nothing calls is the shape of defect this loop keeps finding."""
    src = pathlib.Path(ip.__file__).read_text(encoding="utf-8")
    at = src.index("_rows_changed(out[\"diff_second\"])")
    seg = src[at:at + 2500]
    assert "_active_counts(" in seg, "the verdict does not read the active counts"
    assert "active_before" in seg
    assert "IDEMPOTENT IN EFFECT" in seg and "NOT IDEMPOTENT" in seg, (
        "the verdict no longer distinguishes archive-and-replace from duplication"
    )


def test_the_before_counts_are_captured_at_the_mid_boundary():
    """They must describe the state the SECOND call acts on, not the fixture's start."""
    src = pathlib.Path(ip.__file__).read_text(encoding="utf-8")
    before_at = src.index('out["active_before"] = _active_counts')
    second_at = src.index("_r2 = fx.mcp.call(tool, args)")
    first_at = src.index("_r1 = fx.mcp.call(tool, args)") if "_r1 = fx.mcp.call(tool, args)" in src else 0
    assert first_at < before_at < second_at, (
        "active_before is not taken between the first and second call"
    )
