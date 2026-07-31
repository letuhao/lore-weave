"""Teeth for `scripts/llm-budget-ssot-gate.py`.

The two failure modes this gate has to survive are opposite, and each one was a real bug in
its first hour:

  * **too broad** — `max_tokens` is overloaded here. `select_for_context(max_tokens=800)` is an
    INPUT packing budget, a different concept sharing a spelling. Sweeping it in would be the
    one-name-two-concepts drift the frontend-tool contract exists to prevent.
  * **too narrow** — the correct architecture is a per-service call-profile registry
    (`budget_for("translate_chunk")`), so a gate recognising only a literal `call_budget(...)`
    at the call site marks every correctly-migrated site unattributed. Measured: the backlog
    went UP by 4 after the first migration, which would have pushed the fix back to inlining.

Plus the one that makes the HARD rule worth having: an absent budget and a deliberate one must
not look alike.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "lbg", Path(__file__).resolve().parent / "llm-budget-ssot-gate.py"
)
lbg = importlib.util.module_from_spec(_SPEC)
sys.modules["lbg"] = lbg
_SPEC.loader.exec_module(lbg)


def _tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, files: dict[str, str]) -> list[dict]:
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    (tmp_path / "sdks").mkdir(exist_ok=True)
    monkeypatch.setattr(lbg, "ROOT", tmp_path)
    return lbg.scan()


_SUBMIT = '''
async def go(llm):
    return await llm.submit_and_wait(
        user_id="u", operation="chat", model_source="m", model_ref="r",
        input={{"messages": [], {budget}}},
    )
'''


def _verdicts(sites: list[dict]) -> list[str]:
    return [s["verdict"] for s in sites]


# ── the HARD rule ─────────────────────────────────────────────────────────────────────────

def test_a_call_with_no_budget_is_absent(tmp_path, monkeypatch):
    sites, _ = _tree(tmp_path, monkeypatch,
                     {"services/x/app/a.py": _SUBMIT.format(budget="")})
    assert _verdicts(sites) == ["ABSENT"]


def test_zero_is_a_decision_not_a_gap(tmp_path, monkeypatch):
    """0 is this platform's wire sentinel for "omit the cap" (adapters.go; the SDK strips it
    in models.py:179). A site that says 0 has decided; one that says nothing has not."""
    sites, _ = _tree(tmp_path, monkeypatch,
                     {"services/x/app/a.py": _SUBMIT.format(budget='"max_tokens": 0')})
    assert _verdicts(sites) == ["attributed"]


def test_the_gate_reds_on_an_absent_budget(tmp_path, monkeypatch, capsys):
    _tree(tmp_path, monkeypatch, {"services/x/app/a.py": _SUBMIT.format(budget="")})
    monkeypatch.setattr(sys, "argv", ["llm-budget-ssot-gate.py"])
    monkeypatch.setattr(lbg, "UNATTRIBUTED_BASELINE", 0)
    assert lbg.main() == 1
    assert "NO output budget declared" in capsys.readouterr().out


# ── too narrow: the registry indirection must be recognised ───────────────────────────────

_REGISTRY = '''
from loreweave_llm.budget import OutputKind, call_budget
PROFILES = {"translate_chunk": call_budget(OutputKind.MIRROR)}
def budget_for(call):
    return PROFILES[call].max_output_tokens
'''


def test_a_service_registry_call_is_attributed(tmp_path, monkeypatch):
    sites, _ = _tree(tmp_path, monkeypatch, {
        "services/x/app/llm_budget.py": _REGISTRY,
        "services/x/app/a.py": _SUBMIT.format(budget='"max_tokens": budget_for("translate_chunk")'),
    })
    assert "attributed" in _verdicts(sites)


def test_registry_attribution_is_earned_not_a_naming_exemption(tmp_path, monkeypatch):
    """A file NAMED llm_budget.py that never calls `call_budget` contributes nothing — the
    whole point is that the indirection really does resolve through the SSOT."""
    fake = 'BUDGETS = {"translate_chunk": 1200}\ndef budget_for(c):\n    return BUDGETS[c]\n'
    sites, _ = _tree(tmp_path, monkeypatch, {
        "services/x/app/llm_budget.py": fake,
        "services/x/app/a.py": _SUBMIT.format(budget='"max_tokens": budget_for("translate_chunk")'),
    })
    assert "unattributed" in _verdicts(sites), \
        "a registry of literals must not launder them into 'attributed'"


def test_a_direct_call_budget_at_the_call_site_is_attributed(tmp_path, monkeypatch):
    src = ('from loreweave_llm.budget import OutputKind, call_budget\n'
           + _SUBMIT.format(budget='"max_tokens": call_budget(OutputKind.PROSE, target=900).max_output_tokens'))
    sites, _ = _tree(tmp_path, monkeypatch, {"services/x/app/a.py": src})
    assert _verdicts(sites) == ["attributed"]


def test_a_local_variable_bound_from_call_budget_is_attributed(tmp_path, monkeypatch):
    src = (
        'from loreweave_llm.budget import OutputKind, call_budget\n'
        'b = call_budget(OutputKind.PROSE, target=900)\n'
        + _SUBMIT.format(budget='"max_tokens": b.max_output_tokens')
    )
    sites, _ = _tree(tmp_path, monkeypatch, {"services/x/app/a.py": src})
    assert _verdicts(sites) == ["attributed"]


# ── too broad: an input packing budget is a different concept ─────────────────────────────

def test_a_context_packing_budget_is_not_swept(tmp_path, monkeypatch):
    """`select_for_context(max_tokens=800)` decides how much glossary to PACK IN. It is not an
    output ceiling and must not be counted as one."""
    src = 'def select_for_context(entities, max_tokens: int = 800):\n    return entities[:max_tokens]\n'
    sites, sigs = _tree(tmp_path, monkeypatch, {"services/x/app/selector.py": src})
    assert sites == [] and sigs == []


def test_a_signature_default_counts_only_in_a_module_that_submits(tmp_path, monkeypatch):
    src = ('def helper(msgs, max_tokens: int = 1200):\n    return max_tokens\n'
           + _SUBMIT.format(budget='"max_tokens": 1200'))
    _, sigs = _tree(tmp_path, monkeypatch, {"services/x/app/a.py": src})
    assert [s["default"] for s in sigs] == [1200]


def test_a_literal_at_the_call_site_is_the_backlog(tmp_path, monkeypatch):
    sites, _ = _tree(tmp_path, monkeypatch,
                     {"services/x/app/a.py": _SUBMIT.format(budget='"max_tokens": 1200')})
    assert _verdicts(sites) == ["literal"]


# ── honesty about what static analysis cannot see ─────────────────────────────────────────

def test_an_off_site_payload_is_reported_opaque_not_clean(tmp_path, monkeypatch):
    """Claiming a payload built elsewhere is fine would be the "asserted with nothing behind
    it" shape this whole cycle is about. It gets its own verdict instead."""
    src = ('async def go(llm, payload):\n'
           '    return await llm.submit_and_wait(user_id="u", input=payload)\n')
    sites, _ = _tree(tmp_path, monkeypatch, {"services/x/app/a.py": src})
    assert _verdicts(sites) == ["opaque"]


def test_a_spread_payload_is_opaque(tmp_path, monkeypatch):
    src = ('async def go(llm, extra):\n'
           '    return await llm.submit_and_wait(user_id="u", input={"messages": [], **extra})\n')
    sites, _ = _tree(tmp_path, monkeypatch, {"services/x/app/a.py": src})
    assert _verdicts(sites) == ["opaque"]


# ── the ratchet ───────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("baseline,expected", [(1, 0), (0, 1), (2, 1)])
def test_ratchet_reds_in_both_directions(tmp_path, monkeypatch, baseline, expected):
    _tree(tmp_path, monkeypatch,
          {"services/x/app/a.py": _SUBMIT.format(budget='"max_tokens": 1200')})
    monkeypatch.setattr(sys, "argv", ["llm-budget-ssot-gate.py"])
    monkeypatch.setattr(lbg, "UNATTRIBUTED_BASELINE", baseline)
    assert lbg.main() == expected


# ── the live repo state ───────────────────────────────────────────────────────────────────

def test_no_llm_call_site_in_this_repo_is_missing_a_budget():
    sites, _ = lbg.scan()
    absent = [f"{s['file']}:{s['line']}" for s in sites if s["verdict"] == "ABSENT"]
    assert absent == [], f"LLM call sites with no declared output budget: {absent}"


# ── a budget that arrives via a PARAMETER DEFAULT ─────────────────────────────────────────

def test_a_parameter_whose_default_resolves_through_the_ssot_is_attributed(tmp_path, monkeypatch):
    """The migrated shape: `def f(…, max_tokens: int = max_tokens_for("propose_cast"))` with
    `input={… "max_tokens": max_tokens}`. Without resolving the default, all 18 signature
    defaults would clear and the 24 call sites they feed would not move — the same
    punishes-its-own-architecture failure the registry indirection already hit."""
    src = '''
from loreweave_llm.budget import OutputKind, call_budget
def max_tokens_for(code):
    return call_budget(OutputKind.STRUCTURED).max_output_tokens

async def go(llm, max_tokens: int = max_tokens_for("propose_cast")):
    return await llm.submit_and_wait(
        user_id="u", input={"messages": [], "max_tokens": max_tokens},
    )
'''
    sites, _ = _tree(tmp_path, monkeypatch, {"services/x/app/a.py": src})
    assert _verdicts(sites) == ["attributed"], sites


def test_a_parameter_with_a_LITERAL_default_is_still_the_backlog(tmp_path, monkeypatch):
    """The resolution must follow the default's PROVENANCE, not merely the existence of one —
    otherwise every `max_tokens: int = 1200` launders itself by being passed along."""
    src = '''
async def go(llm, max_tokens: int = 1200):
    return await llm.submit_and_wait(
        user_id="u", input={"messages": [], "max_tokens": max_tokens},
    )
'''
    sites, sigs = _tree(tmp_path, monkeypatch, {"services/x/app/a.py": src})
    assert _verdicts(sites) == ["unattributed"], sites
    assert [s["default"] for s in sigs] == [1200]


def test_the_repo_has_no_remaining_signature_default_feeding_an_llm_payload():
    """M2's actual deliverable, against the live tree — the form a call-site-only gate would
    have reported clean."""
    _, sigs = lbg.scan()
    assert sigs == [], f"signature defaults still feeding LLM payloads: {sigs}"
