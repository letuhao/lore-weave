#!/usr/bin/env python
"""No model may be its own judge — and the rule that says so must live in ONE place.

Why
---
Invariant 2 is *no model is silently its own judge*, and the repo has now paid for it twice at
the same spot. The predicate

    distinct = bool(critic_ref and critic_source and str(critic_ref) != str(drafter_ref))

was hand-rolled at **seven** sites in `routers/engine.py`, and an **eighth** in `canon_reflect`
that an audit found — not a guard, not a test. Six identical copies is the shape `canon_envelope`
was extracted from, and the reason is the same: when the rule changed, it reached the copies that
someone remembered.

The rule then changed in exactly that way. `90f513632` moved distinctness onto the RESOLVED
PROVIDER MODEL, because five `user_model_id` rows on the dev box are one gemma and every `!=`
between them says "distinct". The router adopted it. The publish gate — the path that decides
whether a conflict BLOCKS — kept comparing refs, and the fix never reached the place it was for.

The spec asked for this gate in S6 (*"the static gate must be: every grading call site resolves
through `resolve_judge`"*). It was not built, so a ninth copy would be found the way the eighth
was: by somebody reading.

What it checks
--------------
  · **NO RE-DERIVATION** — outside `critic_policy.py`, no `==`/`!=` between two model-ref-shaped
    operands where one side names a critic/judge and the other a drafter. That is the literal
    shape of all eight copies, and it is what an author writes when they re-derive the rule
    rather than call it.

  · **EVERY JUDGE-CARRYING MODULE RESOLVES OR DELEGATES** — the denominator is derived from the
    code (a module that builds a judge request, or takes a `judge_ref`/`critic_model_ref`
    parameter), not from a list somebody maintains. Each such module must import the policy, or
    carry a DELEGATES row naming the module that resolved for it.

    python scripts/judge-resolution-gate.py
    python scripts/judge-resolution-gate.py --list
    python scripts/judge-resolution-gate.py --self-test
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Where the rule is allowed to be EXPRESSED rather than called. Two files, and the second is
#: not a loophole: `loreweave_canon_check/base.py` DEFINES `judge_is_self`, the ref-level test
#: knowledge-service uses because it has no critic setting for the resolved-identity one. A
#: definition site cannot import itself, so it is named here instead of exempted by accident.
POLICY_MODULE = "services/composition-service/app/engine/critic_policy.py"
POLICY_MODULES = (POLICY_MODULE, "sdks/python/loreweave_canon_check/base.py")

#: Modules that receive an ALREADY-RESOLVED judge and must not re-resolve. Each names the module
#: that did the resolving, and that module must itself pass the import check — so a delegation
#: chain cannot terminate in nobody.
#:
#: `canon_reflect` is on this list AND imports the policy, which is not a contradiction: it is
#: handed refs a router filtered, and re-checks them because `worker/operations.py` passes
#: `judge_source=critic_source or model_source` — with no critic configured the DRAFTER's own
#: refs arrive. Defence in depth on the unattended path. Removing that call was attempted during
#: this run and a pre-existing test caught it.
DELEGATES: dict[str, str] = {
    "services/composition-service/app/engine/select.py":
        "services/composition-service/app/routers/engine.py",
    "services/composition-service/app/engine/canon_reflect.py":
        "services/composition-service/app/routers/engine.py",
    "services/composition-service/app/worker/operations.py":
        "services/composition-service/app/engine/canon_reflect.py",
    # Receives `model_source`/`model_ref` for the JUDGE, already filtered by `canon_reflect`
    # (which blanks them when the critic is not distinct). It builds the request; it does not
    # decide who may judge.
    "services/composition-service/app/engine/canon_check.py":
        "services/composition-service/app/engine/canon_reflect.py",
}

#: Services whose code can carry a judge. Widened deliberately rather than pointed at
#: composition: knowledge-service builds judge requests too, and a gate scoped to the service
#: where the bug was found is default-uncovered everywhere else (NV-2).
SCAN_ROOTS = ("services/composition-service/app", "services/knowledge-service/app",
              "services/lore-enrichment-service/app", "services/translation-service/app",
              "services/chat-service/app", "sdks/python")

_REF_PARAMS = ("judge_ref", "judge_source", "critic_model_ref", "critic_model_source",
               "critic_ref", "critic_source")

#: Comparisons between two model refs that are NOT the distinctness rule. Each carries the
#: reason, and a row whose comparison has disappeared FAILS — a stale exemption is a live one.
#:
#: This allowlist exists because the first version of the detector keyed on the words
#: "critic"/"judge" appearing in an operand, and the actual historical copy reads
#: `str(c_ref) != str(body.model_ref)`. `c_ref` contains neither word. Keying on NAMES missed
#: the very defect the gate was written for, so the rule is now structural — both operands look
#: like a model reference — and the handful of legitimate ref comparisons are named here
#: instead. Measured: exactly two in the whole scanned surface.
NON_JUDGE_COMPARES: dict[str, str] = {
    "services/composition-service/app/services/plan_forge_service.py":
        "an idempotency check — the stored session's model against the one now requested. "
        "Neither side is a judge; nothing is being decided about who grades whom.",
    "services/chat-service/app/services/stream_service.py":
        "a sub-agent inheriting the parent's model, compared to avoid re-resolving it. "
        "No grading involved.",
    "services/knowledge-service/app/clients/embedding_client.py":
        "a stale user-model identifier compared with provider-registry's current embedding "
        "default before one recovery retry. Neither reference selects or evaluates a judge.",
}


def _skip(p: Path) -> bool:
    s = p.as_posix()
    return ("/tests/" in s or "/build/" in s or "/node_modules/" in s
            or p.name.startswith("test_") or p.name.endswith("_test.py"))


def _files() -> list[Path]:
    out: list[Path] = []
    for root in SCAN_ROOTS:
        base = ROOT / root
        if base.is_dir():
            out += [p for p in sorted(base.rglob("*.py")) if not _skip(p)]
    return out


def _text(node: ast.AST) -> str:
    """A comparison operand as source-ish text, lowercased."""
    try:
        return ast.unparse(node).lower()
    except Exception:  # noqa: BLE001 - unparse is best-effort on exotic nodes
        return ""


_REF_SHAPED = __import__("re").compile(r"(^|[.\[])[a-z0-9_]*(ref|source)$")


def _is_ref(txt: str) -> bool:
    """Does this operand look like a model reference? `str(x)` unwrapped first."""
    t = txt.strip().lower()
    m = __import__("re").fullmatch(r"str\((.*)\)", t)
    if m:
        t = m.group(1).strip()
    return bool(_REF_SHAPED.search(t))


def rederivations(tree: ast.Module) -> list[tuple[int, str]]:
    """`(line, source)` for every comparison of one model ref against another.

    Structural, not name-based, and that is the correction that makes it work: the shape all
    eight copies share is `<ref> != <ref>`, and the real one reads `str(c_ref) !=
    str(body.model_ref)` — an abbreviation that a detector keyed on the words "critic"/"judge"
    walks straight past. The legitimate ref comparisons are few enough to name individually.
    """
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare) or len(node.ops) != 1:
            continue
        if not isinstance(node.ops[0], (ast.Eq, ast.NotEq)):
            continue
        left, right = _text(node.left), _text(node.comparators[0])
        if left and right and _is_ref(left) and _is_ref(right):
            out.append((node.lineno, ast.unparse(node)))
    return out


def carries_a_judge(tree: ast.Module) -> bool:
    """Does this module build a judge request, take a resolved judge ref, or pass one on?

    The third clause matters: `worker/operations.py` never declares a `judge_ref` parameter —
    it PASSES `judge_source=critic_source or model_source` as a keyword. That call is the
    unattended path, and it is where the drafter's own refs arrive when no critic is set, so a
    reading that only looked at parameter lists would have left the riskiest caller invisible.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
            if name == "build_judge_request":
                return True
            if any(k.arg in _REF_PARAMS for k in node.keywords if k.arg):
                return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            for a in (*args.args, *args.posonlyargs, *args.kwonlyargs):
                if a.arg in _REF_PARAMS:
                    return True
    return False


#: The names that mean "this module asked the policy, rather than restating it". `judge_is_self`
#: is the SDK primitive knowledge-service uses: the same ref-level question, in the one service
#: that has no `work.settings` to hold a critic and therefore cannot use composition's resolver.
_RESOLVER_NAMES = ("critic_policy", "judge_is_self")


def resolves(tree: ast.Module) -> bool:
    """Does this module get its answer from the policy, rather than restating it?"""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if any(n in mod for n in _RESOLVER_NAMES):
                return True
            if any(any(r in a.name for r in _RESOLVER_NAMES) for a in node.names):
                return True
        if isinstance(node, ast.Import):
            if any(any(r in a.name for r in _RESOLVER_NAMES) for a in node.names):
                return True
    return False


def audit() -> tuple[list[str], list[str]]:
    problems: list[str] = []
    carriers: list[str] = []
    seen_policy = False
    for p in _files():
        rel = p.relative_to(ROOT).as_posix()
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        if rel in POLICY_MODULES:
            seen_policy = seen_policy or rel == POLICY_MODULE
            continue
        found = rederivations(tree)
        if found and rel not in NON_JUDGE_COMPARES:
            for line, src in found:
                problems.append(
                    f"{rel}:{line}: one model ref compared against another — `{src}`.\n"
                    f"      If this is the distinctness rule, call `resolve_critic` / "
                    f"`resolve_critic_verified`: a ref comparison cannot see two rows that are "
                    f"ONE model, which is the defect `90f513632` fixed and this would undo. If "
                    f"it is not, add a NON_JUDGE_COMPARES row saying what it is.")
        elif rel in NON_JUDGE_COMPARES and not found:
            problems.append(
                f"{rel}: has a NON_JUDGE_COMPARES exemption and no longer compares two model "
                f"refs. A registry that only grows stops describing the repo, and the row is a "
                f"standing exemption for a comparison that is not there.")
        if not carries_a_judge(tree):
            continue
        carriers.append(rel)
        if resolves(tree):
            continue
        upstream = DELEGATES.get(rel)
        if not upstream:
            problems.append(
                f"{rel}: carries a judge and neither resolves nor declares a delegation. "
                f"Import {POLICY_MODULE.rsplit('/', 1)[-1]}, or add a DELEGATES row naming "
                f"the module that resolved for it.")
        elif not (ROOT / upstream).is_file():
            problems.append(f"{rel}: DELEGATES to {upstream}, which does not exist.")
        else:
            up_tree = ast.parse((ROOT / upstream).read_text(encoding="utf-8", errors="ignore"))
            if not resolves(up_tree) and upstream != POLICY_MODULE:
                problems.append(
                    f"{rel}: DELEGATES to {upstream}, which does not resolve either — a "
                    f"delegation chain that ends in nobody is how the eighth copy survived.")
    if not seen_policy:
        problems.append(
            f"the policy module {POLICY_MODULE} was not scanned — this gate would pass "
            f"vacuously, allowing every re-derivation in the repo.")
    return problems, carriers


def self_test() -> int:
    """The rule-detector must fire on the REAL historical copy and stay quiet on a near-miss."""
    real = ast.parse('distinct = bool(c_ref and c_src and str(c_ref) != str(body.model_ref))')
    if not rederivations(real):
        print("[judge-resolution] SELFTEST FAIL — the shape all eight copies had is not caught")
        return 1
    eighth = ast.parse(
        'distinct = bool(judge_ref and judge_source and str(judge_ref) != str(drafter_ref))')
    if not rederivations(eighth):
        print("[judge-resolution] SELFTEST FAIL — the eighth copy's wording is not caught")
        return 1
    for benign in (
        'if critic_status == "not_configured": pass',   # a status against a literal
        'if len(refs) == count: pass',                  # neither side is a ref
        'if res.verdict != prior.verdict: pass',        # two verdicts, not two models
    ):
        if rederivations(ast.parse(benign)):
            print(f"[judge-resolution] SELFTEST FAIL — false positive on `{benign}`")
            return 1
    # …and the carrier detector must see a judge passed as a KEYWORD, which is the only way
    # `worker/operations.py` — the unattended path — appears at all.
    if not carries_a_judge(ast.parse('f(judge_source=critic_source or model_source)')):
        print("[judge-resolution] SELFTEST FAIL — a judge passed by keyword is invisible")
        return 1
    print("[judge-resolution] SELFTEST PASS — both historical wordings caught (including the "
          "abbreviated `c_ref`, which a name-keyed detector missed); three near-misses are "
          "not; a keyword-passed judge is seen.")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    problems, carriers = audit()
    if "--list" in sys.argv:
        print(f"{len(carriers)} module(s) carry a judge:")
        for c in carriers:
            state = f"delegates -> {DELEGATES[c]}" if c in DELEGATES else "resolves"
            print(f"  {c:70} {state}")
        return 0
    stale = [k for k in DELEGATES if k not in carriers]
    for s in stale:
        problems.append(
            f"DELEGATES has a row for {s}, which no longer carries a judge. A registry that "
            f"only grows stops describing the repo, and a stale row is a live exemption.")
    if problems:
        print("judge-resolution-gate: FAIL\n")
        for p in problems:
            print(f"   {p}")
        return 1
    print(f"judge-resolution-gate: PASS — the distinctness rule is stated in ONE place "
          f"({POLICY_MODULE.rsplit('/', 1)[-1]}); {len(carriers)} judge-carrying module(s), "
          f"{len(carriers) - len(DELEGATES)} resolving and {len(DELEGATES)} declaring a "
          f"delegation, and no module re-derives it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
