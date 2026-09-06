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
                if r.get("session_id") in _FIXTURE_RACE_SESSIONS:
                    continue
                flagged += 1
                tables.update(r.get("store_diff") or {})
    assert seen >= 100, seen
    assert flagged == 0, dict(tables)


#: Runs whose flag is REFUTED by the store's own timestamps, not excused by judgement.
#:
#: 🔴 ONE SESSION, NAMED, WITH THE ARITHMETIC THAT CLEARS IT — because "the harness was flaky"
#: is exactly what someone says when a read tool really did write.
#:
#:   session 01a04fe3-bd8e-7d21-81f2-4555c920a8c7, composition-arc-get-v2 rep 4
#:   flagged table   loreweave_composition.composition_work
#:                   before rows=1 latest=2026-08-29 23:38:22.478817
#:                   after  rows=1 latest=2026-08-29 23:38:37.437706
#:
#:   THE TURN'S FIRST MESSAGE           23:38:40.448765   (loreweave_chat)
#:   THE ROW'S created_at == updated_at 23:38:37.437706   (loreweave_composition)
#:
#: The row was CREATED three seconds BEFORE the turn began, and a row whose updated_at equals its
#: created_at was never updated. So nothing wrote during the measured window. Seven of the eight
#: tables in the same run carry `after: None` — the after-snapshot largely failed — which is
#: independently the shape D-FAILED-SNAPSHOT-COUNTED-AS-A-STORE-CHANGE exists to stop being read
#: as a change.
#:
#: THE UNDERLYING DEFECT IS NOT THIS FLAG. The before-snapshot is taken straight after seeding,
#: yet the book's composition_work row was REPLACED between that snapshot and the turn — so the
#: baseline is not the state the turn actually starts from. Filed as
#: D-THE-BEFORE-SNAPSHOT-IS-NOT-THE-STATE-THE-TURN-STARTS-FROM. This exception is deliberately a
#: SESSION ID and not a scenario or a table, so it cannot quietly cover the next one.
_FIXTURE_RACE_SESSIONS = {"01a04fe3-bd8e-7d21-81f2-4555c920a8c7"}


def test_the_fixture_race_exception_stays_a_single_named_run():
    """ANTI-CREEP. An exception list is a place to hide the next real finding; this one is
    allowed exactly one entry, and growing it has to be a deliberate edit here."""
    assert len(_FIXTURE_RACE_SESSIONS) == 1, (
        "the fixture-race exception list has grown. Each entry must be cleared by the store's own "
        "timestamps, and a SECOND one means the race is recurring and wants fixing, not listing")


def test_the_row_records_the_mechanical_half_whatever_its_state():
    """🔴 RE-ANCHORED 2026-08-28. This pinned `state == "open"` and `blocked_by_dq == "DQ-T45"`.
    DQ-T45 has since been answered and the row closed on a live run, so the pin went red for the
    work being FINISHED — the one outcome a guard should never punish.

    What actually matters here survives the row's state and is asserted instead: the mechanical
    half — the separation of a read AUDIT row from a lifecycle write — must stay written down.
    Lose that and the next reader re-derives it from a store diff, which is how the entity
    access log got counted as a write in the first place."""
    r = LEDGER["defects"]["D-A-TIER-R-TOOL-WRITES-TO-THE-STORE"]
    assert "the_mechanical_half_2026_08_27" in r, (
        "the mechanical half is no longer recorded on the row that owns it")
    # The row may be open or fixed, but it must not claim a block on a settled question.
    named = str(r.get("blocked_by_dq") or "")
    if named:
        assert LEDGER["deferred_questions"][named]["state"] == "open", (
            f"the row is blocked on {named}, which is no longer open")


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
