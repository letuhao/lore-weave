#!/usr/bin/env python
"""A clipped response that cannot stop in a valid place — and almost nothing was checking.

Why
---
DoD-3 of the generation-SSOT spec has three limbs:

    "No LLM call site has an integer max_tokens (literal or default), an ABSENT cap, or
     A MISSING TRUNCATION CHECK."

`llm-budget-ssot-gate.py` enforces the first two. The third appears in that gate exactly once,
in a DOCSTRING, describing the production incident that motivated the whole seam — a judge that
came back `finish_reason=length` with zero verdicts parsed, so the HARD tier had silently
stopped existing. The spec's S7 asked for the check by name. Nothing counted it, and on
2026-08-03 the count was **2 of 28**.

The denominator is the SSOT, not a list
---------------------------------------
"Every call site" would be wrong: for PROSE a truncation shortens the answer, and MIRROR sends
no cap to hit. The SDK already decides which kinds care —
`truncation_is_fatal = (kind is OutputKind.STRUCTURED)` — because a JSON or grammar-constrained
response cannot stop early in a valid place: it comes back unparseable, or worse, parseable
with items missing. So the denominator is every `budget_for(code)` call whose REGISTRY ROW is
STRUCTURED, read from the registries themselves.

The denominator is the RESOLVED budget's `truncation_is_fatal`, not the kind: the kind is only
its default, and a row may ESCALATE. One does — `cross_scene_check` sizes like a VERDICT and
truncates like a list, and a gate keyed on the kind walked past a call whose empty result
`compare_people` reports as a CHECKED, clean seam.

A site is covered when it calls `unusable(job, code)` — one helper per service, in the module
that owns the per-operation facts, which folds the truncation question into the
`status != "completed"` branch every site already wrote. Same degrade, no new judgement.

    python scripts/truncation-check-gate.py
    python scripts/truncation-check-gate.py --list
    python scripts/truncation-check-gate.py --self-test
"""
from __future__ import annotations

import ast
import importlib.util
import io
import re
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: STRUCTURED call sites still deciding on `status` alone. MEASURED 2026-08-03: **2 of 28**.
#: Now 0, and the route there is worth recording because it was not 26 separate judgements:
#:
#:   13  the completion check was a plain `if <status> != "completed":` in the calling
#:       function — rewritten to `unusable(job, code)`, same branch, same degrade
#:    6  the job is owned by a shared helper (`promise_audit._chat`, `plan_heal._chat`,
#:       `self_heal._chat`) that had a `purpose` LOG label but no registry key; each now
#:       takes the `code` it is spending, and every caller names it
#:    5  `plan_forge`'s `_parse_with_repair` sites, covered by making `client.chat` RAISE —
#:       these are the dangerous ones: the repair layer catches a JSONDecodeError and spends
#:       a second call asking the model to fix its own output, so a clipped response would be
#:       handed to a repairer that returns something well-formed and WRONG
#:    4  delegated to a helper whose contract already fixes the answer (`call_json`,
#:       `structured_generate`) — see DELEGATED
#:
#: A ratchet, not a wall, for the reason `gate-teeth-gate` records: a gate with no path to
#: green gets commented out. It may SHRINK and may never GROW — at 0 that means a new
#: STRUCTURED call site which ignores truncation fails here on the day it is written.
UNCHECKED_BASELINE = 0

#: site (file, or file:line) -> the module that owns its job and checks unconditionally.
#:
#: These four hand their budget to a helper whose contract ALREADY fixes the answer, so there
#: is no registry code to link them by: `call_json` exists to get JSON back and `structured_
#: generate` takes a `CallBudget` that carries `truncation_is_fatal`. Giving either a `code`
#: parameter would only create a way to be told the wrong one — and two of `call_json`'s three
#: callers have no registry row at all, so satisfying the parameter would mean inventing rows
#: to please a gate, which is the gate shaping the code instead of checking it.
#:
#: Verified every run: the named file must actually contain a truncation check. A row pointing
#: at a module that stopped checking does not silently pass — it stops covering its site.
DELEGATED: dict[str, str] = {
    "composition-service/app/engine/plan_forge/material_search.py":
        "composition-service/app/engine/llm_json.py",
    "composition-service/app/engine/planning_pipeline.py":
        "composition-service/app/engine/llm_json.py",
    "knowledge-service/app/schema_propose/engine.py":
        "sdks/python/loreweave_llm/structured.py",
}


def _load_budget_gate():
    spec = importlib.util.spec_from_file_location(
        "_lbg", ROOT / "scripts" / "llm-budget-ssot-gate.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def code_only(src: str) -> str:
    """Comments and docstrings blanked. Kept for the self-test, NOT used by the audit.

    The audit parses RAW source, and that is the stronger choice rather than a lazier one:
    every signal it looks for is an AST NODE — a `Call`, an `Attribute`, a `code=` keyword —
    and a comment or a docstring cannot produce one. Stripping first was actively wrong
    here: blanking a docstring line leaves `if ...:` with an empty body, `ast.parse` raises
    `IndentationError`, and the loop `continue`d — so `self_heal.py` was skipped entirely
    and its site reported as unchecked while the check sat two functions away. A stripper
    that silently removes a file from the denominator is worse than no stripper.
    """
    blank: set[int] = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                blank.add(tok.start[0])
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    try:
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, (ast.Module, ast.FunctionDef,
                                     ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                blank.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    except (SyntaxError, ValueError):
        pass
    return "\n".join("" if i in blank else ln for i, ln in enumerate(src.splitlines(), 1))


def _resolve(rel: str) -> Path | None:
    for base in (ROOT / "services", ROOT / "sdks" / "python", ROOT):
        p = base / rel
        if p.is_file():
            return p
    return None


def _enclosing(tree: ast.Module, line: int):
    best = None
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and n.lineno <= line <= (n.end_lineno or n.lineno):
            if best is None or n.lineno > best.lineno:
                best = n
    return best


def covered(scope_src: str) -> bool:
    """Does this scope consult the truncation question at all?

    `unusable(job, code)` is the intended form. A hand-rolled `finish_reason` check counts too:
    the point is the QUESTION being asked, and a site that asks it directly is not worse than
    one that asks through the helper — `session_translator` does exactly that, deliberately,
    because the translate path sends no cap and the check there is advisory by design.
    """
    try:
        tree = ast.parse(scope_src)
    except SyntaxError:
        return "unusable(" in scope_src or "finish_reason" in scope_src
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            fn = n.func
            if (fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")) == "unusable":
                return True
        if isinstance(n, ast.Attribute) and n.attr == "finish_reason":
            return True
        if isinstance(n, ast.Constant) and n.value == "finish_reason":
            return True
    return False


#: Rows that ESCALATE truncation fatality above their kind, read from each service's registry
#: source rather than by importing it: the `lints` job is a bare checkout with no service deps,
#: and importing `app.llm_budget` there would make this gate crash in CI while passing locally
#: — the failure mode `llm-budget-ssot-gate` documents for its own parser.
_ESCALATED = re.compile(r'"([a-z_0-9]+)"\s*:\s*CallProfile\((?:[^)]*?)truncation_fatal\s*=\s*True',
                        re.DOTALL)


def _escalated_codes() -> set[str]:
    out: set[str] = set()
    for p in sorted(ROOT.glob("services/*/app/llm_budget.py")):
        out |= set(_ESCALATED.findall(p.read_text(encoding="utf-8", errors="ignore")))
    return out


_ESCALATED_CACHE: set[str] | None = None


def _fatal_by_registry(code: str | None) -> bool:
    global _ESCALATED_CACHE
    if _ESCALATED_CACHE is None:
        _ESCALATED_CACHE = _escalated_codes()
    return bool(code) and code in _ESCALATED_CACHE


def owns_a_job(scope_src: str) -> bool:
    """Does this scope RECEIVE the job, or only hand a number to something that does?

    Not bookkeeping. `plan_forge`'s five `_parse_with_repair` sites resolve
    `max_tokens_for("plan_forge_chat")` and pass it to `client.chat(...)`, which owns the job
    and does the checking. Counting them unchecked would demand a `finish_reason` test in a
    function that never sees a `finish_reason` — and the only way to satisfy that is theatre.
    """
    try:
        tree = ast.parse(scope_src)
    except SyntaxError:
        return "submit_and_wait" in scope_src
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            fn = n.func
            name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
            if name == "submit_and_wait":
                return True
    return False


def audit() -> tuple[list[dict], list[dict]]:
    """Coverage is per registry CODE: every scope that OWNS a job for that code must check.

    A scope that only resolves the budget and hands it on is covered by the scope it hands it
    to — but only when that one checks, so a delegation still cannot terminate in nobody. And
    a code with NO job-owning scope at all fails rather than passing for lack of anyone to ask.
    """
    g = _load_budget_gate()
    # The RESOLVED budget decides, not the kind — `truncation_is_fatal` is the SSOT and the
    # kind is only its default. `cross_scene_check` is why: it sizes like a VERDICT and
    # truncates like a list, and a gate keyed on the kind walked straight past a call whose
    # empty result `compare_people` reports as a CHECKED, clean seam. Reading the kind was
    # reading a proxy for the fact when the fact itself is one call away.
    sites = [s for s in g.scan_signal()
             if s.get("kind") == "STRUCTURED" or _fatal_by_registry(s.get("code"))]
    rows: list[dict] = []
    for s in sites:
        p = _resolve(s["file"])
        if p is None:
            rows.append({**s, "fn": "?", "owns": True, "checks": False})
            continue
        src = p.read_text(encoding="utf-8", errors="ignore")
        try:
            fn = _enclosing(ast.parse(src), s["line"])
        except SyntaxError:
            fn = None
        scope = ("\n".join(src.splitlines()[fn.lineno - 1:fn.end_lineno])
                 if fn else src)
        rows.append({**s, "fn": fn.name if fn else "<module>",
                     "owns": owns_a_job(scope), "checks": covered(scope)})

    # A code can also be answered by a scope that holds no budget of its own — a shared
    # `_chat`/`client.chat` helper that owns the job for several callers. `unusable(job, code)`
    # names the code, so the code string IS the link, and looking for it is not a heuristic.
    # Without this, `promise_audit`'s two callers stayed counted while the helper they both go
    # through did the check — which would have pushed me to duplicate the check into functions
    # that never see a job, for the number.
    named: set[str] = set()
    for rel in {r["file"] for r in rows}:
        p = _resolve(rel)
        if p is None:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            fn = n.func
            if (fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")) != "unusable":
                continue
            for a in n.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    named.add(a.value)
        # …and the indirection one hop further out: a shared helper takes `code` as a
        # PARAMETER and the callers supply the literal, so the constant never appears next to
        # `unusable(` at all. `promise_audit._chat` is exactly that shape.
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                for k in n.keywords:
                    if k.arg == "code" and isinstance(k.value, ast.Constant) \
                            and isinstance(k.value.value, str):
                        named.add(k.value.value)

    answered: dict[str, bool] = {}
    for code in {r["code"] for r in rows}:
        owners = [r for r in rows if r["code"] == code and r["owns"]]
        answered[code] = (all(r["checks"] for r in owners) if owners else False) or \
            (code in named and not any(r["owns"] and not r["checks"] for r in rows
                                       if r["code"] == code))

    # Sites whose job is owned by a shared helper that decides truncation from its OWN
    # contract rather than from a registry code — so there is no code string to link them by.
    # Each row names the file, and the file is verified to contain a real check on every run:
    # an exemption pointing at a module that stopped checking is worse than no exemption.
    for site, checker in DELEGATED.items():
        p = _resolve(checker) or (ROOT / checker if (ROOT / checker).is_file() else None)
        if p is None or not covered(p.read_text(encoding="utf-8", errors="ignore")):
            continue  # left uncovered on purpose: the claim did not hold, so the row fails
        for r in rows:
            if f"{r['file']}:{r['line']}" == site or r["file"] == site:
                r["checks"] = True

    ok = [r for r in rows if r["checks"] or (not r["owns"] and answered[r["code"]])]
    bad = [r for r in rows if not (r["checks"] or (not r["owns"] and answered[r["code"]]))]
    return ok, bad


def self_test() -> int:
    """Prove the coverage test is not satisfied by prose, and that it sees both real forms."""
    asks = 'def f():\n    job = go()\n    if (why := unusable(job, "x")):\n        return None\n'
    direct = 'def f():\n    if getattr(job, "finish_reason", None) == "length":\n        pass\n'
    prose = ('def f():\n    """We should really check finish_reason here."""\n'
             '    # unusable(job, "x") would be the way\n    return 1\n')
    if not covered(asks):
        print("[truncation] SELFTEST FAIL — the helper form is not recognised")
        return 1
    if not covered(direct):
        print("[truncation] SELFTEST FAIL — a hand-rolled finish_reason check is not recognised")
        return 1
    if covered(code_only(prose)):
        print("[truncation] SELFTEST FAIL — a docstring and a comment counted as a check")
        return 1
    print("[truncation] SELFTEST PASS — helper and hand-rolled forms both count; a docstring "
          "plus a commented-out call does not (non-vacuous).")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    ok, bad = audit()
    total = len(ok) + len(bad)
    if "--list" in sys.argv:
        for s in sorted(ok + bad, key=lambda r: (r["file"], r["line"])):
            mark = "ok " if s in ok else "..."
            print(f"  {mark} {s['file']}:{s['line']:5} {s['code']:30} in {s.get('fn', '?')}")
        return 0
    if not total:
        print("truncation-check-gate: FAIL — zero STRUCTURED call sites found; this gate "
              "would pass vacuously. The registries or the scanner changed shape.")
        return 1
    if len(bad) != UNCHECKED_BASELINE:
        grew = len(bad) > UNCHECKED_BASELINE
        print(f"{'FAIL' if grew else 'NOTE'} — STRUCTURED call sites with no truncation check "
              f"{'grew to' if grew else 'dropped to'} {len(bad)} of {total} "
              f"(baseline {UNCHECKED_BASELINE}).")
        for s in sorted(bad, key=lambda r: (r["file"], r["line"])):
            print(f"     {s['file']}:{s['line']} {s['code']} in {s.get('fn', '?')}")
        if grew:
            print("\n   A STRUCTURED response cannot stop early in a valid place. Call")
            print("   `unusable(job, \"<code>\")` in place of the `status != \"completed\"`")
            print("   check — same degrade, and a clipped structure stops reading as a short one.")
        else:
            print(f"\n   Progress — lower UNCHECKED_BASELINE to {len(bad)} in "
                  f"{Path(__file__).name}.")
        return 1
    print(f"truncation-check-gate: PASS — {total} STRUCTURED call site(s); {len(ok)} consult "
          f"`finish_reason`, {len(bad)} held at baseline.")
    if bad:
        print("   The held ones route through a repair/salvage layer or a helper that swallows "
              "the job, and each needs its own read — those are also where truncation produces "
              "parseable-but-WRONG output rather than an obvious failure.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
