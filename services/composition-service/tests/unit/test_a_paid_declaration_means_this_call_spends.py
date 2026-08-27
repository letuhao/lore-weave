"""DQ-T60 — `_meta.paid` means THIS CALL spends, and composition-service had nothing saying so.

THE RULE IS NOT AMBIGUOUS AND WAS NEVER IN DISPUTE. Three independent sources state it the
same way:

    sdks/go/loreweave_mcp/meta.go        MetaKeyPaid = "paid"  // true ⇒ calling it SPENDS
                                                              //  real money (Track D CD1)
    chat-service tool_discovery.tool_paid  "True when CALLING this tool spends real money."
    glossary-service mcp_meta_contract_test.go, which applies it tool by tool with reasons:
        "web_search + the doc-extractor hit a paid provider/LLM SYNCHRONOUSLY on call;
         plan calls the planner LLM at mint time"

WHAT IT IS NOT is a synonym for Tier W. Tier W means the MUTATION needs human confirmation,
and most of the reasons are irreversibility rather than cost: 57 of the platform's 60 Tier-W
tools declare no `paid` at all, among them book_purge and book_chapter_delete. The axes are
orthogonal, which is what chat-service's spend gate says in its own comment — the spend check
runs "regardless of tier OR mode", and the mutation check runs only for tier A.

WHY THIS FILE EXISTS. glossary-service enforces its four paid declarations against a named
list with a stated reason each. composition-service enforced seven against nothing, and one of
them was wrong for two months: `composition_library_translate` declared `paid` while its
estimate is `chars / _CHARS_PER_TOKEN * 2.5` — arithmetic, no LLM. `_meta.paid` makes the chat
spend gate SUSPEND the call before it runs, so the author was asked to approve a spend before
the number that would tell them its size existed.

    composition_library_translate   15 calls   12 suspended on a card    0 ever ok
    translation_start_job           82 calls    0 suspended             80 ok
    translation_retranslate_dirty   74 calls    0 suspended             74 ok

Identical shape, opposite declaration, and the tool with the extra "protection" is the one
that never worked. The flag was not guarding the spend; it was preventing the card that
carries the price from ever being minted.

🔴 WHAT THIS FILE DOES NOT CLAIM. It cannot prove a tool spends — no static check can. It
pins the SET, so a new `paid=True` (or a silently dropped one) reds until a human writes down
which of the two shapes it is. That is the same guarantee glossary-service's test gives, and
the same one its `paidTools` map gives: a list that can only go stale in the safe direction.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[2] / "app" / "mcp" / "server.py"

#: Every composition tool that declares `_meta.paid`, with the reason it qualifies under the
#: rule above: CALLING it reaches a provider. Each of these runs the planner LLM inside the
#: call and returns its output — none of them mints a confirm token and stops.
PAID_TOOLS: dict[str, str] = {
    "plan_propose_spec": "runs the planner LLM to build the spec, in the call",
    "plan_find_missing_material": "a Tier-R READ that calls the planner LLM — the canonical "
                                  "case for the flag being orthogonal to tier",
    "plan_apply_revision": "runs the planner LLM to apply the revision, in the call",
    "plan_compile": "runs the planner LLM to compile the package, in the call",
    "plan_run_pass": "runs the planner LLM for the pass, in the call",
    "composition_build_cast_and_graph": "runs the planner LLM to derive the cast, in the call",
}

#: Tools deliberately NOT paid, with the reason, so a future reader does not re-add one.
#: These MINT a confirm token: the call itself prices arithmetically and spends nothing, and
#: the money leaves at /actions/confirm, which re-authorises and re-prices.
NOT_PAID_CONFIRM_MINTERS: dict[str, str] = {
    "composition_library_translate":
        "prices via _translate_estimate (chars / _CHARS_PER_TOKEN * 2.5) — no LLM. Declared "
        "paid until 2026-08-27, during which 0 of 15 calls ever executed.",
}


def _source() -> str:
    return SERVER.read_text(encoding="utf-8")


def _declared_paid_tools() -> set[str]:
    """Every tool whose `require_meta(...)` block carries `paid=True`, read from the source.

    Anchored on `tool_name=`, which `require_meta` requires and which sits inside the same
    block — so this cannot drift onto a neighbouring registration the way a backwards search
    for `name="..."` can."""
    src = _source().splitlines()
    found: set[str] = set()
    for i, line in enumerate(src):
        if "paid=True" not in line:
            continue
        for j in range(i, min(len(src), i + 8)):
            m = re.search(r'tool_name="([a-z0-9_]+)"', src[j])
            if m:
                found.add(m.group(1))
                break
        else:  # pragma: no cover - a paid block with no tool_name is itself a defect
            pytest.fail(
                f"a paid=True declaration at line {i + 1} has no tool_name within 8 lines, so "
                f"this guard cannot attribute it — name the tool"
            )
    return found


def test_every_paid_declaration_is_named_and_justified():
    """🔴 THE GUARD. A new `paid=True` reds here until someone writes down WHICH shape it is:
    a call that reaches a provider, or a call that mints a token and stops. Getting that wrong
    is not cosmetic — it decides whether the author is asked to approve a spend before or
    after the amount is known."""
    declared = _declared_paid_tools()
    expected = set(PAID_TOOLS)

    unexpected = declared - expected
    assert not unexpected, (
        f"these tools declare _meta.paid and are not in PAID_TOOLS: {sorted(unexpected)}. "
        f"`paid` means CALLING this tool spends real money. If the call runs an LLM or hits a "
        f"paid provider, add it here with that reason. If it only MINTS A CONFIRM TOKEN and "
        f"prices arithmetically, it is not paid — the confirm route is the money gate, and "
        f"declaring paid stops the tool before it can produce the estimate the card needs."
    )
    missing = expected - declared
    assert not missing, (
        f"these tools are listed as paid and no longer declare it: {sorted(missing)}. If the "
        f"call genuinely stopped spending, remove it from PAID_TOOLS in the same commit — do "
        f"not let this list drift into a description of the past."
    )


def test_a_confirm_minter_does_not_also_carry_a_pre_call_spend_gate():
    """The instance, stated so it cannot come back quietly.

    A tool that mints a confirm token and declares `paid` is gated TWICE: the platform
    suspends before the call to ask about a spend it cannot size, and the tool's own card asks
    again with the price. The first card can only ever be the less informative of the two, and
    it fires first."""
    declared = _declared_paid_tools()
    for tool, why in NOT_PAID_CONFIRM_MINTERS.items():
        assert tool not in declared, (
            f"{tool} declares _meta.paid again. It mints a confirm token: {why} The spend gate "
            f"suspends the call BEFORE the estimate exists, so the author is asked to approve "
            f"a cost the card cannot state."
        )


def _registration_block(tool: str) -> str:
    """The source from a tool's `name="..."` to the start of the NEXT registration.

    🔴 A FIXED-SIZE WINDOW IS THE WRONG INSTRUMENT AND MY FIRST VERSION USED ONE. 900 chars
    reached past the decorator on the day I wrote it; adding a paragraph of comment to the
    same block pushed `require_meta` out of range and the guard reported the tool had been
    downgraded from Tier W when nothing about its tier had changed. A guard whose verdict
    moves when a COMMENT is edited is measuring the comment."""
    src = _source()
    start = src.index(f'name="{tool}"')
    nxt = src.find("@mcp_server.tool(", start)
    return src[start: nxt if nxt != -1 else len(src)]


def test_the_confirm_minter_still_mints_and_still_says_it_costs_money():
    """The control that refutes a lazy repair. Removing `paid` must not also remove the thing
    that actually protects the author — if this tool stopped minting a token, or stopped
    telling them the spend is coming, the change would be a hole and not a fix."""
    block = _registration_block("composition_library_translate")
    assert "mint_confirm_token(" in block, (
        "composition_library_translate no longer mints a confirm token — with `paid` removed "
        "as well, nothing would gate the spend"
    )
    assert "confirm_token" in block and "estimate" in block, (
        "the returned card no longer carries both the token and the estimate"
    )
    assert "human confirmation" in block, (
        "the card no longer tells the author a human confirmation is required"
    )


def test_the_tool_is_still_tier_W():
    """`paid` was removed; the CONFIRMATION requirement was not. Tier W is what makes this a
    human-gated mutation, and it is a separate axis from cost."""
    block = _registration_block("composition_library_translate")
    assert '"W", "user"' in block, (
        "composition_library_translate is no longer Tier W — removing the spend flag must not "
        "downgrade the confirmation the mutation needs"
    )
