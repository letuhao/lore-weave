"""D-THE-OUT2-LINT-ONLY-INSPECTS-TOOLS-THAT-ARE-ALREADY-COMPLIANT — the measurable half.

    THE INVARIANT. A lint cited as "blocks NEW violations" must have its RECALL measured, not
    assumed — and a tool must not be exempted by being MORE non-compliant.

`context-budget-defaults-lint.py` triggers on the presence of the compliance machinery:

    if "detail" not in params or "limit" not in params: continue      # inline params
    if "detail" in fields and "limit" in fields:                      # request models

So it checks that a tool which ALREADY has both defaults them well, and a tool that implemented
neither falls through.

RE-DERIVED 2026-08-27 — 🔴 WORSE THAN THE ROW RECORDED, which is why re-deriving is the rule:

    41  list-shaped tools      8 with BOTH (seen)      12 with exactly ONE      21 with NEITHER
    ---
    33 of 41 skipped; recall 8/41 = 20%

The row counted the 21 and not the 12. Both triggers require BOTH names, so `limit` alone falls
through exactly as neither does. And 32 Go files register MCP tools that the Python-AST lint
never sees at all.

🔴 SKIPPED IS NOT OVER BUDGET, and this file claims no offenders. Exactly one was ever measured
— settings_list_models at 10,380 bytes. Calling 32 unexamined tools on a live account to find
the rest is what the standing constraint forbids.

THE LINT WAS UNTOUCHED WHILE THIS WAS ONLY A MEASUREMENT — widening its trigger reds a
pre-commit hook for five service teams on its first run, and that was DQ-T52's to decide, not a
measurement's to take.

🔴 THE OWNER DECIDED IT (2026-08-28): "TRIGGER ON LIST SHAPE, seed today's offenders as a
flip-pending ALLOW, and EXTEND TO THE GO REGISTRATIONS." So the lint IS widened now, and the two
guards below that pinned the restraint have been RE-ANCHORED rather than deleted: what survives
is not "nothing changed" but "what changed is exactly what was ruled, and no further". The
seeded baseline has its own ratchet in test_the_out2_allow_list_only_shrinks.py.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "toolloop"))

import out2_coverage as cov  # noqa: E402

LEDGER = json.loads((ROOT / "contracts" / "tool-deep-dive-ledger.json").read_text(
    encoding="utf-8"))
LINT = (ROOT / "scripts" / "context-budget-defaults-lint.py").read_text(encoding="utf-8")


def test_the_trigger_still_requires_BOTH_names():
    """The defect itself, read from the lint. If either trigger ever widens, the recall below is
    stale and this row changes — so it must fail rather than quietly keep an old number."""
    assert 'if "detail" not in params or "limit" not in params:' in LINT
    assert 'if "detail" in fields and "limit" in fields:' in LINT


def test_exactly_one_field_is_skipped_TOO():
    """🔴 THE HALF THE ROW MISSED. `limit` alone satisfies neither trigger — the first needs both
    in params, the second needs both as fields — so those 12 tools are as invisible as the 21."""
    d = cov.derive()
    assert d["exactly_one"], "no tool carries exactly one of the pair — re-derive the row"
    assert d["skipped"] == len(d["exactly_one"]) + len(d["neither"])


def test_the_recall_is_low_and_derived():
    d = cov.derive()
    assert d["list_shaped"] >= 30, d["list_shaped"]
    assert d["recall"] < 0.5, d["recall"]
    stored = json.loads((ROOT / "contracts" / "out2-lint-coverage.json").read_text(
        encoding="utf-8"))
    assert stored["_derived_by"] == "python scripts/toolloop/out2_coverage.py"
    assert stored["recall"] == d["recall"], "the contract is stale — re-run the deriver"


def test_the_GO_half_is_no_longer_a_blind_spot():
    """RE-ANCHORED 2026-08-30, and this one was passing while its NAME lied.

    It was written as `test_the_lint_is_PYTHON_only` to pin the second, disjoint blind spot:
    every Go tool, whatever its shape. Its assertions still held after the DQ-T52 widening —
    the Python pass still filters on `.py`, and the Go scanner does not use `NewToolMeta` — so
    it stayed green while the fact in its name became false. A green test whose name states the
    opposite of the truth is worse than a red one, because nobody re-reads it.

    What it pins now is the blind spot being CLOSED: the deriver still counts the Go population,
    and the lint actually reaches it."""
    assert 'f.endswith(".py")' in LINT, "the Python pass is gone"
    assert "def iter_go_files(" in LINT, "the lint no longer reaches the Go registrations"
    assert cov.derive()["go_files_registering_mcp_tools"] >= 10


def test_the_shape_test_discriminates():
    """ANTI-VACUITY. A predicate that called everything list-shaped would make the recall
    meaningless."""
    assert cov.is_list_shaped("settings_list_models")
    assert cov.is_list_shaped("glossary_web_search")
    assert cov.is_list_shaped("kg_list_templates")
    assert not cov.is_list_shaped("book_read")
    assert not cov.is_list_shaped("jobs_cancel")


def test_the_widening_is_the_DECIDED_one_and_went_NO_FURTHER():
    """🔴 RE-ANCHORED 2026-08-30. This guard used to assert `"is_list_shaped" not in LINT` — the
    RESTRAINT, correct while this row was only a measurement and the widening was still DQ-T52's
    to accept. The owner accepted it, the lint was widened, and the guard then failed for the
    best possible reason: the thing it forbade had been properly decided.

    Deleting it would have thrown away the half that is still load-bearing. A measurement must
    not widen a lint on its own authority, and the way that stays enforced once a widening IS
    authorised is to pin the widening to the SHAPE OF THE RULING — list-shape as the trigger, the
    original both-names check still present and still single, and the offenders parked behind an
    ALLOW rather than the lint simply shouting at everything."""
    # the ruling landed. Matched WITH THE PAREN: `"def scan_go_file"` also matches
    # `def scan_go_file2`, so the first version of this guard survived its own inverse edit.
    assert "def is_list_shaped(" in LINT, "the DQ-T52 widening is gone — the lint has been reverted"
    assert "def scan_go_file(" in LINT, "the Go half of the ruling is missing"
    # and it went no further: the original trigger survives, exactly once
    assert LINT.count('if "detail" not in params or "limit" not in params:') == 1
    # the seeded debt is behind the allow-list, not silently unflagged
    assert "in ALLOW" in LINT, "the widening flags without the ALLOW ratchet the ruling required"


def test_the_row_is_LINKED_and_the_recommendation_does_not_decide():
    """🔴 RE-ANCHORED 2026-08-28: DQ-T52 was answered and this row's block was correctly
    cleared. A pin on `state == "open"` would punish the decision landing; what survives is that
    the recommendation, preserved verbatim, never crossed into deciding it."""
    row = LEDGER["defects"]["D-THE-OUT2-LINT-ONLY-INSPECTS-TOOLS-THAT-ARE-ALREADY-COMPLIANT"]
    named = row.get("blocked_by_dq")
    if named:
        assert LEDGER["deferred_questions"][named]["state"] == "open", (
            f"the row is blocked on {named}, which is no longer open")
    dq = LEDGER["deferred_questions"]["DQ-T52"]
    assert "Not my call" in dq["my_recommendation"]
