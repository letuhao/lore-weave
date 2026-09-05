"""D-THE-GATE-CANNOT-SEE-A-FALSIFIER-I-MEASURED-AS-VIOLATED.

The DATA-falsifier bar asserted a falsifier EXISTS. It had no way to know the run REFUTED it,
so a batch whose own stored calls contradicted its prediction still passed, and the only thing
between it and `proven` was a human reading prose. Twice that human was me:

  * b18-gen-control passed 8 of 9 bars while every composition_generate call carried
    model_ref='default' and came back ok=false — the exact invention its falsifier names.
  * c-regwf passed while 4 of 5 runs reported NINE workflows as studio-available when the
    studio has six — a refutation clause I had added to that falsifier myself before the run.

    THE INVARIANT. A refutation SOMEONE HAS ALREADY WRITTEN DOWN must fail the bar, so
    `conclude` refuses and the only way past is to fix the cause and re-run.

THE MECHANISM WAS ALREADY SHIPPED AND THE ROW WAS NEVER UPDATED — which is why METHOD says to
check whether a mechanism EXISTS and is merely empty before building one. What was missing is
this file: nothing kept it red-able, so it could have been deleted in a refactor and every
suite would have stayed green.

BOTH OF THE ROW'S OWN REFUTED-IF CONDITIONS, RUN 2026-08-27:

    (a) it must fire on b18-gen-control, the ORIGINAL instance
        -> FAIL [composition_generate] DATA falsifier not violated   (8 passed, 2 failed)
    (b) it must NOT fire on a batch already concluded proven
        -> c-gen3    10 passed, 0 failed   (composition_generate's actual proven evidence)
        -> c-regwf5  19 passed, 0 failed   (registry_list_workflows')

The four files on disk that record a violation — b18-gen-control, c-regwf, c-regwf2, c-regwf3 —
are none of them the batch a conclusion rests on. The bar catches exactly what it was written
to catch.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import gate as gt  # noqa: E402

EVID = ROOT / "docs" / "eval" / "toolloop" / "2026-08-14"


def _batch(**tool_extra) -> dict:
    return {"batch": "t", "generated_by": "test", "approval_mode": "none",
            "tools": [{"tool": "zz_tool", "falsifier": "if X then this is refuted",
                       "runs": [], **tool_extra}]}


def _fails_named(batch, needle: str) -> bool:
    g = gt.Gate(batch, EVID / "b18-gen-control.json")
    g.run()
    return any(needle in line for line in g.fail)


def test_a_recorded_violation_FAILS_the_bar():
    assert _fails_named(_batch(falsifier_violated_2026_08_24={"why": "measured false"}),
                        "DATA falsifier not violated")


def test_ANY_suffix_counts():
    """The four on disk use three different suffixes — `_2026_08_24`, `_second_batch`,
    `_third_batch`. The bar matches the PREFIX, and a stricter match would have missed two of
    the three recorded refutations."""
    for key in ("falsifier_violated", "falsifier_violated_2026_08_24_second_batch",
                "falsifier_violated_anything_at_all"):
        assert _fails_named(_batch(**{key: True}), "DATA falsifier not violated"), key


def test_an_entry_with_NO_violation_passes_that_bar():
    """PRECISION. If it fired on every entry the gate would be unusable and would be turned
    off, which is the same as not having it."""
    assert not _fails_named(_batch(), "DATA falsifier not violated")


def test_a_BACK_DATED_falsifier_fails_too():
    """Same family, same file, equally unguarded until now: a prediction edited once the result
    is known is a description, not a falsifier."""
    assert _fails_named(_batch(falsifier_amended_after_run={"was_sha": "a", "now_sha": "b"}),
                        "DATA falsifier not back-dated")
    assert not _fails_named(_batch(), "DATA falsifier not back-dated")


def test_conclude_PROVEN_refuses_over_a_violation(tmp_path, monkeypatch, capsys):
    """🔴 THE BAR IS ONLY WORTH ANYTHING IF `conclude` READS IT. Asserted end to end, with the
    LEDGER redirected — if this ever stops refusing, the test must not be the thing that writes
    a false `proven` into the real ledger."""
    led = tmp_path / "ledger.json"
    led.write_text(json.dumps({"tools": {}, "defects": {}, "progress": {}}), encoding="utf-8")
    monkeypatch.setattr(gt, "LEDGER", led)
    b = tmp_path / "b.json"
    b.write_text(json.dumps(_batch(falsifier_violated_x=True)), encoding="utf-8")

    class A:
        batch, tool, state = str(b), "zz_tool", "proven"
    rc = gt.cmd_conclude(A())
    out = capsys.readouterr().out
    assert rc != 0, "conclude accepted a batch that records its own refutation"
    assert "REFUSED" in out and "falsifier not violated" in out
    assert json.loads(led.read_text(encoding="utf-8"))["tools"] == {}, (
        "a refused conclude still wrote to the ledger"
    )


def test_conclude_BLOCKED_is_not_excused_either(tmp_path, monkeypatch, capsys):
    """`blocked` excuses the bars that describe being EXERCISED (LIVE called, SHIP exercised),
    because demanding those of a tool that could not run is circular. A refuted prediction is a
    different thing: the batch is not evidence for anything, blocked included."""
    led = tmp_path / "ledger.json"
    led.write_text(json.dumps({"tools": {}, "defects": {}, "progress": {}}), encoding="utf-8")
    monkeypatch.setattr(gt, "LEDGER", led)
    b = tmp_path / "b.json"
    b.write_text(json.dumps(_batch(
        falsifier_violated_x=True,
        blocked_reason="a reason long enough for the gate to accept it as checkable later")),
        encoding="utf-8")

    class A:
        batch, tool, state = str(b), "zz_tool", "blocked"
    rc = gt.cmd_conclude(A())
    assert rc != 0
    assert "falsifier not violated" in capsys.readouterr().out


# ── the row's own REFUTED-IF, against the real evidence on disk ──────────────────────────

def test_REFUTED_IF_a_it_fires_on_the_ORIGINAL_instance():
    p = EVID / "b18-gen-control.json"
    if not p.exists():
        pytest.skip("the original instance is not on disk")
    batch = json.loads(p.read_text(encoding="utf-8"))
    assert any(str(k).startswith("falsifier_violated") for k in batch["tools"][0]), (
        "the original instance no longer records its refutation — it is evidence, not a fixture"
    )
    g = gt.Gate(batch, p)
    g.run()
    assert any("DATA falsifier not violated" in line for line in g.fail)


@pytest.mark.parametrize("name", ["c-gen3.json", "c-regwf5.json"])
def test_REFUTED_IF_b_it_does_NOT_fire_on_a_batch_that_concluded_proven(name):
    """The condition that could have refuted the whole bar. These two files are the evidence
    composition_generate and registry_list_workflows are actually `proven` against — read from
    their ledger notes, not assumed."""
    p = EVID / name
    if not p.exists():
        pytest.skip(f"{name} is not on disk")
    g = gt.Gate(json.loads(p.read_text(encoding="utf-8")), p)
    g.run()
    assert not any("DATA falsifier not violated" in line for line in g.fail), g.fail


def test_the_proven_rows_really_point_at_those_batches():
    """ANTI-VACUITY for the pair above. If the conclusions rested on the VIOLATED batches
    instead, REFUTED-IF (b) would be triggered and this row could not close."""
    led = json.loads((ROOT / "contracts" / "tool-deep-dive-ledger.json").read_text(
        encoding="utf-8"))
    for tool, batch in (("composition_generate", "c-gen3.json"),
                        ("registry_list_workflows", "c-regwf5.json")):
        row = led["tools"].get(tool) or {}
        assert row.get("state") == "proven", f"{tool} is no longer proven"
        assert batch in str(row.get("note") or ""), (
            f"{tool}'s proven note no longer names {batch} — re-run REFUTED-IF (b)"
        )
