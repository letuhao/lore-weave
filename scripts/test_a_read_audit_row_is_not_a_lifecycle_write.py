"""D-A-TIER-R-TOOL-WRITES-TO-THE-STORE — the mechanical half, which needs no decision.

    THE INVARIANT. A READ recording that it read is not a lifecycle write, and a GLOBAL counter
    is attributable to nobody. Only a read tool ADVANCING STATE is the defect.

The row's own sweep separates three shapes and says only one is this defect:

    1. plan_run under {plan_validate, package_tree}   — a Tier-R tool moving a lifecycle. THIS.
    2. entity_access_log under glossary reads         — a read recording that it read. Correct.
    3. extraction_pending under tools that cannot enqueue — the TURN, not the tool.

The harness's `read_intent_violations` excluded only shape 3. So shape 2 was reported as a
violation, and a fourth shape nobody had named was too.

MEASURED 2026-08-27 over every read-intent run on disk — 148 clean runs, 20 flagged:

    15  loreweave_knowledge.entity_access_log   an audit row a read legitimately writes
     5  neo4j.Fact.total                        a GLOBAL count of every Fact in the database
     0  an actual read-tool lifecycle write

🔴 `Fact.total` HAS NO SCOPE AT ALL, so any concurrent run moves it — and this loop runs
batches at concurrency 2–3. It is a counter this loop added itself, and it arrived at the same
false attribution `_world_counts` and the arc_template run-nonce already paid for. It stays in
the SNAPSHOT, where a global count is context; what it must not do is make a turn accountable.

After: 0 of 148. The bar still fires on a plan_run lifecycle write, and on an audit row
appearing BESIDE a real write — which is the precision property the shipped docstring already
warned about, and the reason the sets are separate rather than one "ignore" list.

THE DECISION IS UNTOUCHED. Whether a golden-linter PASS should authorise a cost-bearing
authoring run is DQ-T45, and nothing here answers it.
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import fe_runner as fr  # noqa: E402

LEDGER = json.loads((ROOT / "contracts" / "tool-deep-dive-ledger.json").read_text(
    encoding="utf-8"))


def _run(*tables):
    return {"store_diff": {t: {"before": {"rows": 1}, "after": {"rows": 1}} for t in tables}}


def test_a_real_lifecycle_write_still_FIRES():
    """🔴 THE BAR MUST NOT BE MADE VACUOUS BY WIDENING ITS EXEMPTIONS. plan_run is the row's own
    instance: a Tier-R tool moving a plan into the status that authorises a cost-bearing run."""
    assert fr.read_intent_violations([_run("loreweave_composition.plan_run")])


def test_an_audit_row_ALONE_does_not():
    assert not fr.read_intent_violations([_run("loreweave_knowledge.entity_access_log")])


def test_an_audit_row_BESIDE_a_real_write_still_fires():
    """The precision property the shipped docstring warns about: dropping every run that
    MENTIONS an exempt table would hide the runs where a real write appears beside it."""
    assert fr.read_intent_violations([
        _run("loreweave_knowledge.entity_access_log", "loreweave_composition.plan_run")])


def test_a_global_counter_is_attributable_to_nobody():
    assert not fr.read_intent_violations([_run("neo4j.Fact.total")])
    assert fr.read_intent_violations([_run("neo4j.Fact.total", "loreweave_book.chapters")])


def test_turn_bookkeeping_is_still_excluded_for_its_OWN_reason():
    """Three sets, not one. The reasons differ, and a reader who sees one name would otherwise
    assume the other's justification: bookkeeping is written by chat.turn_completed whatever
    tool ran; the audit row IS written by the tool, and writing it is correct."""
    assert not fr.read_intent_violations([_run("loreweave_knowledge.extraction_pending")])
    assert fr.TURN_BOOKKEEPING_TABLES.isdisjoint(fr.READ_AUDIT_TABLES)
    assert fr.TURN_BOOKKEEPING_TABLES.isdisjoint(fr.UNATTRIBUTABLE_GLOBAL_COUNTS)
    assert fr.READ_AUDIT_TABLES.isdisjoint(fr.UNATTRIBUTABLE_GLOBAL_COUNTS)


def test_the_exemptions_are_SMALL():
    """ANTI-VACUITY. An exemption list that grew to cover the store would silence the bar while
    looking like precision."""
    total = (len(fr.TURN_BOOKKEEPING_TABLES) + len(fr.READ_AUDIT_TABLES)
             + len(fr.UNATTRIBUTABLE_GLOBAL_COUNTS))
    assert total <= 6, total


def test_the_corpus_no_longer_produces_a_FALSE_flag():
    """ANTI-VACUITY against the real records: 20 flags before, and every one was an audit row or
    a global counter."""
    intents = {}
    for f in (ROOT / "scripts" / "toolloop").glob("scenarios-*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for s in d.get("scenarios", []):
            intents.setdefault(s["id"], s.get("intent"))
    seen = flagged = 0
    tables: collections.Counter = collections.Counter()
    for f in sorted((ROOT / "docs" / "eval" / "toolloop").rglob("*-raw.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, list):
            continue
        for r in d:
            if not isinstance(r, dict) or r.get("error"):
                continue
            if intents.get(r.get("scenario")) != "read":
                continue
            seen += 1
            if fr.read_intent_violations([r]):
                flagged += 1
                tables.update(r.get("store_diff") or {})
    assert seen >= 100, seen
    assert flagged == 0, dict(tables)


def test_the_row_records_the_mechanical_half_and_keeps_its_DQ():
    r = LEDGER["defects"]["D-A-TIER-R-TOOL-WRITES-TO-THE-STORE"]
    assert r["state"] == "open" and r.get("blocked_by_dq") == "DQ-T45"
    assert "the_mechanical_half_2026_08_27" in r
    assert LEDGER["deferred_questions"]["DQ-T45"]["state"] == "open"


# ── the explanation, which was false before it was right ─────────────────────────────────

def _render(runs, intent="read"):
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        fr.report(runs, [{"id": "s", "expect_tool": "x", "intent": intent}], len(runs))
    return buf.getvalue()


def _rr(*tables):
    return {"scenario": "s", "surfaces": [], "results": [], "tool_calls": [],
            "store_diff": {t: {"before": {"rows": 1}, "after": {"rows": 2}} for t in tables}}


def test_the_explanation_names_the_TABLE_that_was_touched():
    """🔴 IT PRINTED THE WRONG REASON, AND ONLY A LIVE RENDER SHOWED IT. The line used to emit
    the bookkeeping set unconditionally, so a batch whose only write was `entity_access_log`
    was explained as "turn-bookkeeping, written by chat.turn_completed" — false about that
    table twice: it is written BY the tool, and writing it is correct. A message that names the
    wrong exemption teaches the reader the wrong rule."""
    out = _render([_rr("loreweave_knowledge.entity_access_log") for _ in range(5)])
    assert "loreweave_knowledge.entity_access_log" in out
    assert "read AUDIT row" in out
    assert "chat.turn_completed" not in out, out


def test_bookkeeping_still_gets_ITS_reason():
    out = _render([_rr("loreweave_knowledge.extraction_pending") for _ in range(3)])
    assert "chat.turn_completed" in out
    assert "read AUDIT row" not in out


def test_a_global_count_gets_its_own_reason():
    out = _render([_rr("neo4j.Fact.total") for _ in range(3)])
    assert "attributable to nobody" in out


def test_a_REAL_write_still_prints_the_violation():
    """The bar itself, unchanged — and this is what the exemptions must never silence."""
    out = _render([_rr("loreweave_composition.plan_run") for _ in range(5)])
    assert "READ-INTENT TURN WROTE TO THE STORE in 5/5" in out


def test_a_WRITE_intent_scenario_gets_neither_line():
    """PRECISION. These lines are about a turn that asked to LOOK."""
    out = _render([_rr("loreweave_composition.plan_run") for _ in range(5)], intent="write")
    assert "READ-INTENT" not in out and "read AUDIT row" not in out
