"""A tool that says it spends money must DECLARE that it spends money.

    THE INVARIANT. `_meta.paid` is what makes a call clear the SPEND gate. A tool whose own
    description tells the model it costs money, or whose own schema takes a spend ceiling in
    USD, and which then declares `paid: False`, is asking to be charged for silently.

🔴 THIS IS NOT AN INFERENCE ABOUT WHAT A TOOL PROBABLY DOES. The evidence is the tool's own
words, measured over the catalogue on 2026-08-27:

    say "COSTS money" / "SPEND money" in their own description   5   declaring paid: 1
    take a `budget_usd` spend ceiling in their own schema         2   declaring paid: 0

Six distinct tools, and the two arms do not overlap. The platform's own recipe says it out loud
for one of them — "composition_authoring_run_manage (op='start') … This SPENDS money" — while
the machine-readable declaration beside it says False.

WHAT THAT COSTS, concretely. `_required_kinds` only gains "spend" when `tool_paid()` is true
(stream_service, the approval block), so for these six:
  * the SPEND gate is never consulted, and a standing mutation allow is enough to run them;
  * the confirm card is never marked `spend: True`, so the FE cannot render "this costs money"
    as distinct from "this modifies data" — which is the exact distinction that wire signal
    exists for.

IT IS SHRINK-ONLY, seeded with today's six. Whether those six should be re-declared changes how
often authors are prompted for money, which is DQ-T60 and not this gate's business. What the
gate does is stop a SEVENTH arriving.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASELINE = ROOT / "contracts" / "undeclared-paid-tools-baseline.json"

#: The tool telling the model, in its own description, that calling it costs money.
SAYS_IT_SPENDS = re.compile(
    r"spends? (real )?money|costs? money|incurs? (a )?cost|billable|real spend", re.I)

#: A spend ceiling in the tool's own schema. `budget`/`limit` alone are NOT here: `limit` is
#: pagination on 8 tools and a bare `budget` appears nowhere — measured, not assumed.
MONEY_ARGS = ("budget_usd", "cost_usd", "max_spend_usd", "spend_usd")


def _catalog():
    spec = importlib.util.spec_from_file_location(
        "_gate", ROOT / "scripts" / "test_a_measured_turn_reaches_its_tool_gate.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    return mod._catalog()


def undeclared_paid() -> dict[str, list[str]]:
    """{tool: the reasons it looks paid} for every tool that does not declare `_meta.paid`."""
    out: dict[str, list[str]] = {}
    for td in _catalog():
        fn = td["function"]
        meta = fn.get("_meta") or {}
        if meta.get("paid"):
            continue
        why = []
        hit = SAYS_IT_SPENDS.search(fn.get("description") or "")
        if hit:
            why.append(f"its description says {hit.group(0)!r}")
        props = (fn.get("parameters") or {}).get("properties") or {}
        money = [k for k in MONEY_ARGS if k in props]
        if money:
            why.append(f"its schema takes {money}")
        if why:
            out[fn["name"]] = why
    return out


def _baseline() -> set[str]:
    if not BASELINE.exists():
        return set()
    return set(json.loads(BASELINE.read_text(encoding="utf-8"))["tools"])


def test_no_NEW_tool_says_it_costs_money_without_declaring_it():
    """THE GATE. Shrink-only, like every other baseline in this contract directory."""
    new = sorted(set(undeclared_paid()) - _baseline())
    assert not new, (
        "these tools say they cost money — in their own description or their own schema — and "
        "declare `_meta.paid: False`, so they never clear the SPEND gate and their confirm card "
        "cannot be marked as a spend:\n  "
        + "\n  ".join(f"{t}: {'; '.join(undeclared_paid()[t])}" for t in new)
        + "\n\nDeclare `paid` on the tool, or change the description if it does not cost money."
    )


def test_the_baseline_only_SHRINKS():
    """A tool that was fixed must not be able to come back through the baseline."""
    stale = sorted(_baseline() - set(undeclared_paid()))
    assert not stale, (
        "these are in the baseline but no longer offend — remove them from "
        f"{BASELINE.name} so it cannot re-admit them: {stale}"
    )


def test_the_gate_is_not_vacuous():
    """🔴 IT MUST STILL FIND THE SIX. A gate whose finder returns nothing passes forever, and
    this one is seeded with a population rather than starting empty — so if the finder breaks,
    `test_the_baseline_only_SHRINKS` reds instead, which is the tell."""
    found = undeclared_paid()
    assert len(found) >= 6, f"only {len(found)} found — the finder has narrowed: {sorted(found)}"
    assert "translation_start_job" in found
    assert "composition_authoring_run_manage" in found


def test_a_tool_that_DOES_declare_paid_is_not_flagged():
    """PRECISION: `book_index_chapter` says 'COSTS MONEY' and declares it. It must stay out."""
    assert "book_index_chapter" not in undeclared_paid()
    paid = [td["function"]["name"] for td in _catalog()
            if (td["function"].get("_meta") or {}).get("paid")]
    assert len(paid) >= 13, len(paid)
    assert not (set(paid) & set(undeclared_paid()))


def test_pagination_is_not_money():
    """🔴 THE NAME-SHAPED GUESS THIS REFUSES TO MAKE. `limit` is a page size on 8 tools and
    `spend` is a BOOLEAN on 12 — measured across every recorded call. A gate matching those
    words would demand a paid declaration from `book_list`."""
    assert "limit" not in MONEY_ARGS and "spend" not in MONEY_ARGS
    assert "book_list" not in undeclared_paid()
    assert "jobs_list" not in undeclared_paid()
