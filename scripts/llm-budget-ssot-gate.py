#!/usr/bin/env python
"""D-LLM-BUDGET-SSOT — every LLM call must declare where its output budget came from.

The defect
----------
The reasoning axis is already adaptive: ``UserReasoningPref="auto"`` →
``resolve_reasoning(auto_effort=score_effort(signals))``, scoring real per-call signals into
a level. The budget axis is ~40 flat literals. **Both draw from the same token allowance** —
reasoning tokens are spent BEFORE the visible output — so having one that adapts and one
that is a constant is not an omission, it is the bug. It already bit: a scene prompt asked
for 900 Vietnamese words (~2300 tokens) while the wire allowed 1024, and it looked like the
model writing short. Measured targets of 900/850/800/750/800 produced 445/414/532/618/736.

``sdks/python/loreweave_llm/budget.py`` is the seam. This gate is what stops the literals
growing back.

Three forms, because a one-form gate greens on the common one
-------------------------------------------------------------
1. **call-site literal** — ``input={… "max_tokens": 1200}``
2. **signature default** — ``def f(…, max_tokens: int = 1200)``; the *most* common form,
   and the one a call-site-only gate would have reported clean
3. **absent entirely** — no cap at all, so the provider decides

What this gate deliberately does NOT sweep
------------------------------------------
``max_tokens`` is overloaded in this repo. ``select_for_context(max_tokens=800)`` and
``build_glossary_context(max_tokens=1500)`` are INPUT packing budgets — how much glossary
context to select — not output ceilings. They are a different concept that happens to share
a spelling, and folding them in would be the one-name-two-concepts drift the frontend-tool
contract exists to prevent. So a budget only counts when it reaches an **LLM request
payload**, established structurally rather than by name.

Two tiers
---------
**HARD** — an LLM call site whose payload declares no budget AT ALL fails. "Deliberately
unbounded" is sayable (``OutputKind.MIRROR`` → ``0``, this platform's existing wire sentinel
for *omit the cap*), so the only thing that reds here is a site that never decided. Silence
and intent must not look alike.

**RATCHET** — sites whose budget is a bare literal or a variable not traceable to
``call_budget``. That is the migration backlog; it may not grow, and shrinking it is
recorded. Making it hard today would mean ~30 findings and no path to green.

    python scripts/llm-budget-ssot-gate.py           # gate
    python scripts/llm-budget-ssot-gate.py --list    # every call site with its verdict
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Unattributed budgets (bare literal, or a variable not traceable to `call_budget`).
#: Ratcheted. 2026-07-31: 32 — MEASURED. The first value here was a guess of 41 and the gate
#: rejected it on its own first run, which is what a ratchet is for.
UNATTRIBUTED_BASELINE = 32

#: Methods that submit an LLM request. Structural, not name-based: what makes a budget an
#: OUTPUT budget is that it rides in one of these payloads.
_SUBMIT = {"submit_and_wait", "submit_job", "submit"}
_PAYLOAD_KWARGS = ("input", "payload", "body")
_BUDGET_KEYS = {"max_tokens", "max_output_tokens", "max_out", "max_completion_tokens"}

_SKIP_PARTS = ("/tests/", "/build/", "/.venv/", "/node_modules/")


def _is_scanned(p: Path) -> bool:
    s = p.as_posix()
    if any(part in s for part in _SKIP_PARTS):
        return False
    name = p.name
    if name.startswith("test_") or name.endswith("_test.py"):
        return False
    # Diagnostic/eval one-offs under a service's scripts/ dir are not product call paths.
    return "/scripts/" not in s or "/services/" not in s


def budget_provider_names(roots: list[Path]) -> set[str]:
    """Top-level names exported by a module that genuinely resolves through `call_budget`.

    Tier 2 of this design is a per-service call-profile registry — the per-operation knowledge
    belongs to the SERVICE (`PASS_REGISTRY`, `_OPERATION_INSTRUCTIONS` are the precedent) while
    the SDK owns only the mechanism. So the real call site reads
    `"max_tokens": budget_for("translate_chunk")`, and a gate that only recognises a literal
    `call_budget(...)` at the call site would mark every correctly-migrated site UNATTRIBUTED —
    measured: the backlog went UP by 4 after the first migration. A gate that punishes the
    architecture it is enforcing pushes people back to inlining.

    This is EARNED, not a naming exemption: a module contributes names only if it actually
    imports and calls `call_budget`. A file called `llm_budget.py` full of literals gets nothing.
    """
    out: set[str] = set()
    for root in roots:
        for p in sorted(root.rglob("*.py")):
            if not _is_scanned(p):
                continue
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            calls_it = any(
                isinstance(n, ast.Call)
                and (n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", ""))
                == "call_budget"
                for n in ast.walk(tree)
            )
            if not calls_it:
                continue
            for n in tree.body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.add(n.name)
                elif isinstance(n, ast.Assign):
                    for t in n.targets:
                        if isinstance(t, ast.Name):
                            out.add(t.id)
                elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
                    out.add(n.target.id)
    out.discard("call_budget")
    return out


def _call_budget_names(tree: ast.AST) -> set[str]:
    """Names bound to a `call_budget(...)` result (or one of its attributes) in this module.

    `b = call_budget(OutputKind.PROSE, …)` then `"max_tokens": b.max_output_tokens`, and the
    direct `mt = call_budget(…).max_output_tokens`, are both attributed."""
    out: set[str] = set()
    for n in ast.walk(tree):
        if not isinstance(n, ast.Assign):
            continue
        val = n.value
        if isinstance(val, ast.Attribute):
            val = val.value
        if isinstance(val, ast.Call):
            fn = val.func.attr if isinstance(val.func, ast.Attribute) else getattr(val.func, "id", "")
            if fn == "call_budget":
                for t in n.targets:
                    if isinstance(t, ast.Name):
                        out.add(t.id)
    return out


def _attributed(node: ast.AST, names: set[str], providers: set[str]) -> bool:
    """Does this payload value trace to `call_budget` — directly, or via a service registry?"""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            fn = sub.func.attr if isinstance(sub.func, ast.Attribute) else getattr(sub.func, "id", "")
            if fn == "call_budget" or fn in providers:
                return True
        if isinstance(sub, ast.Name) and (sub.id in names or sub.id in providers):
            return True
    return False


def scan() -> tuple[list[dict], list[dict]]:
    """(call sites, signature defaults that feed an LLM payload)."""
    sites: list[dict] = []
    sigs: list[dict] = []
    roots = [ROOT / "services", ROOT / "sdks"]
    providers = budget_provider_names(roots)
    for root in roots:
        for p in sorted(root.rglob("*.py")):
            if not _is_scanned(p):
                continue
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            rel = p.relative_to(ROOT).as_posix()
            names = _call_budget_names(tree)

            for n in ast.walk(tree):
                if not isinstance(n, ast.Call):
                    continue
                fn = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
                if fn not in _SUBMIT:
                    continue
                payload = next((kw.value for kw in n.keywords if kw.arg in _PAYLOAD_KWARGS), None)
                if payload is None or not isinstance(payload, ast.Dict):
                    # Built elsewhere — this gate cannot see it, and saying otherwise would
                    # be the "asserted with nothing behind it" shape it exists to reject.
                    sites.append({"file": rel, "line": n.lineno, "verdict": "opaque"})
                    continue
                if any(k is None for k in payload.keys):      # {**spread}
                    sites.append({"file": rel, "line": n.lineno, "verdict": "opaque"})
                    continue
                val = None
                for k, v in zip(payload.keys, payload.values):
                    if isinstance(k, ast.Constant) and k.value in _BUDGET_KEYS:
                        val = v
                if val is None:
                    sites.append({"file": rel, "line": n.lineno, "verdict": "ABSENT"})
                elif _attributed(val, names, providers):
                    sites.append({"file": rel, "line": n.lineno, "verdict": "attributed"})
                elif isinstance(val, ast.Constant) and val.value == 0:
                    # The wire sentinel for "omit the cap" — a decision, not a gap.
                    sites.append({"file": rel, "line": n.lineno, "verdict": "attributed"})
                elif isinstance(val, ast.Constant):
                    sites.append({"file": rel, "line": n.lineno, "verdict": "literal"})
                else:
                    sites.append({"file": rel, "line": n.lineno, "verdict": "unattributed"})

            # Form 2 — a signature default that is threaded into an LLM payload. Counted only
            # when the SAME module submits a request, so a context-packer's `max_tokens=800`
            # (a different concept sharing a spelling) is not swept in.
            if not any(s["file"] == rel for s in sites):
                continue
            for n in ast.walk(tree):
                if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                a = n.args
                pairs = list(zip(a.args[len(a.args) - len(a.defaults):], a.defaults))
                pairs += list(zip(a.kwonlyargs, a.kw_defaults))
                for arg, d in pairs:
                    if arg.arg in _BUDGET_KEYS and isinstance(d, ast.Constant) \
                            and isinstance(d.value, int) and d.value != 0:
                        sigs.append({"file": rel, "line": n.lineno,
                                     "fn": n.name, "arg": arg.arg, "default": d.value})
    return sites, sigs


def main() -> int:
    sites, sigs = scan()
    absent = [s for s in sites if s["verdict"] == "ABSENT"]
    literal = [s for s in sites if s["verdict"] == "literal"]
    unattr = [s for s in sites if s["verdict"] == "unattributed"]
    attributed = [s for s in sites if s["verdict"] == "attributed"]
    opaque = [s for s in sites if s["verdict"] == "opaque"]
    backlog = len(literal) + len(unattr) + len(sigs)

    if "--list" in sys.argv:
        print(f"{len(sites)} LLM call site(s)\n")
        for s in sites:
            print(f"  [{s['verdict']:12}] {s['file']}:{s['line']}")
        print(f"\n{len(sigs)} signature default(s) in modules that submit LLM requests")
        for s in sigs:
            print(f"  {s['file']}:{s['line']}  {s['fn']}({s['arg']}={s['default']})")
        return 0

    rc = 0
    if absent:
        print("FAIL — LLM call site with NO output budget declared:\n")
        for s in absent:
            print(f"   {s['file']}:{s['line']}")
        print("\n   Decide, then say so. If the model's natural stop IS correct here")
        print("   (translation, transcription — the output's length is set by the input),")
        print("   declare it: `call_budget(OutputKind.MIRROR).max_output_tokens` → 0, which")
        print("   the SDK strips (models.py) so the wire is unchanged. Otherwise size it")
        print("   from the kind. Silence and intent must not look alike.")
        rc = 1

    if backlog != UNATTRIBUTED_BASELINE:
        verb = "grew to" if backlog > UNATTRIBUTED_BASELINE else "dropped to"
        print(f"\n{'FAIL' if backlog > UNATTRIBUTED_BASELINE else 'NOTE'} — budgets not "
              f"traceable to call_budget() {verb} {backlog} (baseline {UNATTRIBUTED_BASELINE}).")
        if backlog > UNATTRIBUTED_BASELINE:
            print("   A new flat literal is exactly what the seam was built to stop.")
            for s in (literal + unattr)[-6:]:
                print(f"     {s['file']}:{s['line']}")
            for s in sigs[-4:]:
                print(f"     {s['file']}:{s['line']}  {s['fn']}({s['arg']}={s['default']})")
        else:
            print(f"   Progress — lower UNATTRIBUTED_BASELINE to {backlog} in "
                  f"{Path(__file__).name}.")
        rc = 1

    if rc == 0:
        print(f"llm-budget-ssot-gate: PASS — {len(sites)} LLM call site(s); every one "
              f"declares a budget.")
        print(f"  {len(attributed)} traced to call_budget() · {backlog} held at baseline "
              f"({len(literal)} literal, {len(unattr)} unattributed, {len(sigs)} signature "
              f"defaults) · {len(opaque)} payload built off-site (not statically visible).")
    return rc


if __name__ == "__main__":
    sys.exit(main())
