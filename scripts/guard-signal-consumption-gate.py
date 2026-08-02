#!/usr/bin/env python
"""A guard signal nobody reads is a fact, not a guard — and this counts them.

Why
---
The 2026-08-02 audit closed six gaps and five landed the same way: the HONESTY half shipped
and the ACTING half did not. `exclusion_unverified`, `kg_unchecked`, `guard_status: not_run`,
`identity_verified`, `injection_scan` — each emitted, each individually defensible, each with
its own Debt row, and nothing counting them. The pattern reached FIVE before anyone named it,
because a register is read one row at a time.

Every one of those is better than the silence it replaced: they exist because two states used
to be indistinguishable. But an emitted fact that changes no behaviour is the S8 shape, and
five instances in one day is a habit rather than an accident.

So: a ratchet, not a wall. Reddening on all five would leave no path to green, which is how
gates get commented out — this repo's own `gate-teeth-gate` says so. The number may SHRINK and
may never GROW. The sixth unconsumed signal fails.

What it checks
--------------
  · PHANTOM — an emitter or consumer file that does not exist, or that does not reference the
    field in CODE. Comments and docstrings are stripped: this repo has certified three
    separate claims on the strength of prose describing them.
  · SHAPE — a row is exactly one of `consumer:` or `unconsumed:`, never both, never neither.
    "Both" is how a half-migrated row would keep its exemption after growing a consumer.
  · RATCHET — the unconsumed count against UNCONSUMED_BASELINE.

    python scripts/guard-signal-consumption-gate.py
    python scripts/guard-signal-consumption-gate.py --list
    python scripts/guard-signal-consumption-gate.py --self-test
"""
from __future__ import annotations

import ast
import io
import re
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "contracts" / "guard-signals.yaml"

#: Signals emitted with nothing acting on them. MEASURED 2026-08-02, from the audit that
#: named the pattern. Lower it when one grows a consumer; it may never grow.
#:
#: 4 → 3 (2026-08-02): `glossary.kg_sweep_coverage` grew one. The ratchet is doing the job it
#: was written for — it made the four visible as a SET, and the set is what got worked down.
#: 3 → 2 (2026-08-02): `composition.critic_identity` grew one at the publish gate, and
#: wiring it is what surfaced that the distinct-critic fix had never reached the place
#: that decides whether a conflict blocks. A signal with no reader is not just inert —
#: it hides the fact that its consumer was never built.
#: 2 → 1 (2026-08-02): `eval.exclusion_unverified` grew one — and again the wiring found
#: worse than an unread field: it was DROPPED at the `EvalResult` boundary, so the
#: structure built for persistence never carried it. Two for two: a signal with no
#: reader hides whether its producer even works.
#: 1 → **0** (2026-08-02). Every signal in this registry now changes something a human
#: or a gate can act on. The ratchet stays: it is not the count that mattered, it is
#: that a SIXTH emitted-and-unread signal now fails instead of joining a list nobody
#: reads in one sitting. Three of the four wired this day turned out to be broken at
#: the producer, not merely unread — which is the argument for the whole mechanism.
UNCONSUMED_BASELINE = 0


def _strip_prose(src: str, path: Path) -> str:
    """`src` with comments and docstrings blanked.

    Load-bearing, not hygiene. Three separate checks in this repo have gone green on prose:
    a gate that named its contracts in its own docstring, one that matched an argparse `help=`
    string, and an injection lint that read a BASELINE comment as coverage. A field name
    appears in the paragraph explaining it far more often than in the code using it.
    """
    if path.suffix != ".py":
        # Go/Rust/TS — strip `//` and `/* */`, which is all these files use.
        src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
        return re.sub(r"(?m)^\s*//.*$", "", src)
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


def references_in_code(rel: str, field: str) -> bool:
    """Does `rel` mention `field` outside its comments and docstrings?"""
    path = ROOT / rel
    if not path.is_file():
        return False
    try:
        src = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return re.search(rf"\b{re.escape(field)}\b", _strip_prose(src, path)) is not None


def load_registry() -> list[dict]:
    """Parse the registry without a YAML dependency.

    CI's `lints` job is a bare checkout with no `pip install`, so importing `yaml` would make
    this gate crash there while passing locally — the exact failure mode `llm-budget-ssot-gate`
    documents for its own parser. The file's shape is fixed and small, so it is read directly.
    """
    rows: list[dict] = []
    cur: dict | None = None
    key: str | None = None
    for raw in REGISTRY.read_text(encoding="utf-8").splitlines():
        if raw.startswith("#") or not raw.strip():
            continue
        m = re.match(r"^  - id: (\S+)", raw)
        if m:
            cur = {"id": m.group(1)}
            rows.append(cur)
            key = None
            continue
        if cur is None:
            continue
        m = re.match(r"^    (field|unconsumed|emitter|consumer):\s*(.*)$", raw)
        if m:
            key = m.group(1)
            val = m.group(2).strip()
            if key in ("field",):
                cur[key] = val
            elif key == "unconsumed":
                cur["unconsumed"] = val if val not in (">-", "") else ""
            else:
                cur[key] = {}
            continue
        m = re.match(r"^      (file|note):\s*(.*)$", raw)
        if m and key in ("emitter", "consumer") and isinstance(cur.get(key), dict):
            cur[key][m.group(1)] = m.group(2).strip()
            continue
        # a folded-block continuation line
        if key == "unconsumed" and raw.startswith("      "):
            cur["unconsumed"] = (cur.get("unconsumed", "") + " " + raw.strip()).strip()
    return rows


#: Prose registers that describe guard signals, and that go stale. Both are read at PLAN time
#: and both have been wrong about a signal that already had a consumer.
PROSE_REGISTERS = (
    "docs/plans/2026-07-31-generation-ssot-RUNSTATE.md",
    "docs/sessions/SESSION_HANDOFF.md",
)

#: Ways a register says "nothing reads this". Matched against a WINDOW around each registered
#: field name, so the claim has to be about that field rather than merely near it.
_UNREAD_CLAIM = re.compile(
    r"has no consumer|no consumer\b|nothing consumes it|emitted-but-unconsumed"
    r"|emitted and nothing consumes|unconsumed signal",
    re.IGNORECASE,
)

#: A struck-through row is a RECORD of what was once true, not a live claim. Stripped PER LINE
#: rather than over the whole file: a document-wide `re.DOTALL` sub renames every line number
#: after the first strike, so the gate reported hits at lines whose text did not contain them.
#: Without the strip at all it would red on its own cleared rows, which is how a gate teaches
#: people to delete history instead of striking it.
_STRUCK = re.compile(r"~~.*?~~")

#: Only TABLE ROWS are checked — a line starting with `|`, which in these documents is exactly
#: the Debt / Parked / Drift registers. The AUDIT blocks are dated narrative about what was
#: true when they were written, and three of them say `exclusion_unverified` had no consumer
#: because on that day it did not. Reddening on those would force rewriting the record to
#: satisfy a gate, and a register that edits its own history is worth less than no register.
#: A row is a claim about NOW; a paragraph is a claim about THEN.
_ROW = re.compile(r"^\s*\|")


def stale_prose_claims(rows: list[dict]) -> list[str]:
    """Rows in a prose register that still call a CONSUMED signal unconsumed.

    Why this belongs in this gate rather than a new one: three of the seven stale Debt rows
    found on 2026-08-03 were "signal X has no consumer" for an X this registry already lists
    as consumed. The register was restating a fact a machine already tracks, so it could
    disagree with it — and it did. The repo's own history has the same shape recorded at a
    larger scale: `D-PUBLISHER-DROPS-RULESET-PIN` was cited as an open blocker in four places
    after it was fixed, including in the row of the task that fixed it.

    So: a prose register may POINT at this registry; it may not restate its state.
    """
    consumed = {r["field"] for r in rows if not r.get("unconsumed") and r.get("field")}
    out: list[str] = []
    for rel in PROSE_REGISTERS:
        path = ROOT / rel
        if not path.is_file():
            continue
        for i, raw in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(),
                                1):
            if not _ROW.match(raw):
                continue
            line = _STRUCK.sub("", raw)
            if not _UNREAD_CLAIM.search(line):
                continue
            for field in sorted(consumed):
                if re.search(rf"\b{re.escape(field)}\b", line):
                    out.append(
                        f"{rel}:{i}: still calls `{field}` unconsumed, and "
                        f"contracts/guard-signals.yaml names its consumer. Strike the row "
                        f"(`~~…~~`) with what cleared it, or point at the registry instead of "
                        f"restating it.")
    return out


def check() -> tuple[list[str], list[dict]]:
    problems: list[str] = []
    rows = load_registry()
    if not rows:
        problems.append("the registry parsed to ZERO rows — this gate would pass vacuously")
        return problems, rows

    for r in rows:
        rid = r.get("id", "?")
        field = r.get("field")
        if not field:
            problems.append(f"{rid}: no `field`")
            continue
        has_consumer = isinstance(r.get("consumer"), dict) and r["consumer"].get("file")
        has_unconsumed = bool(r.get("unconsumed"))
        if has_consumer and has_unconsumed:
            problems.append(f"{rid}: declares BOTH a consumer and an `unconsumed` reason — "
                            f"a row that grew a consumer must give up its exemption")
        if not has_consumer and not has_unconsumed:
            problems.append(f"{rid}: declares NEITHER a consumer nor a reason. A signal with "
                            f"no stated status is the silence this registry exists to end")

        emitter = (r.get("emitter") or {}).get("file")
        if not emitter:
            problems.append(f"{rid}: no emitter file")
        elif not (ROOT / emitter).is_file():
            problems.append(f"{rid}: emitter {emitter} does not exist")
        elif not references_in_code(emitter, field):
            problems.append(f"{rid}: emitter {emitter} does not mention {field!r} in CODE "
                            f"(comments and docstrings are stripped)")

        if has_consumer:
            cf = r["consumer"]["file"]
            if not (ROOT / cf).is_file():
                problems.append(f"{rid}: consumer {cf} does not exist")
            elif not references_in_code(cf, field):
                problems.append(f"{rid}: consumer {cf} does not mention {field!r} in CODE — "
                                f"a consumer that does not name the field is not one")
    return problems, rows


def self_test() -> int:
    """Prove the prose-stripper is what makes this gate mean anything.

    Every other assertion here is satisfied by a `references_in_code` that returns True for
    everything — and returning True for everything is exactly what a raw-text scan does, since
    a field name appears in its own explanation more often than in code.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        prose = tmp / "prose_only.py"
        prose.write_text('"""Explains identity_verified at length."""\n'
                         "# identity_verified is mentioned here too\n"
                         "X = 1\n", encoding="utf-8")
        real = tmp / "real_use.py"
        real.write_text('"""No mention in the docstring."""\n'
                        "if report.identity_verified:\n    pass\n", encoding="utf-8")

        global ROOT
        saved, ROOT = ROOT, tmp
        try:
            if references_in_code("prose_only.py", "identity_verified"):
                print("[guard-signals] SELFTEST FAIL — a docstring/comment counted as a use")
                return 1
            if not references_in_code("real_use.py", "identity_verified"):
                print("[guard-signals] SELFTEST FAIL — a real branch was not seen")
                return 1
        finally:
            ROOT = saved

    # …and the prose-register check must be able to fail, or clearing the seven stale rows
    # it was written for would be the last thing it ever did.
    rows = [{"field": "identity_verified", "consumer": {"file": "x"}}]
    fixture = (
        "| `identity_verified` is emitted and nothing consumes it. |\n"
        "| ~~`identity_verified` has no consumer~~ — CLEARED, struck through. |\n"
        "An AUDIT paragraph saying `identity_verified` has no consumer. Dated NARRATIVE, not\n"
        "a row: it records what was true then, and reddening on it would force rewriting the\n"
        "record to satisfy a gate.\n"
    )
    saved_registers = PROSE_REGISTERS
    globals()["PROSE_REGISTERS"] = ("__selftest__.md",)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        (tmp / "__selftest__.md").write_text(fixture, encoding="utf-8")
        saved_root, ROOT = ROOT, tmp
        try:
            hits = stale_prose_claims(rows)
        finally:
            ROOT = saved_root
            globals()["PROSE_REGISTERS"] = saved_registers
    if len(hits) != 1:
        print(f"[guard-signals] SELFTEST FAIL — expected exactly ONE stale claim (a live ROW). "
              f"The struck-through row and the AUDIT paragraph must NOT count; "
              f"got {len(hits)}: {hits}")
        return 1

    print("[guard-signals] SELFTEST PASS — a docstring + comment mention is NOT a use, a "
          "real branch is; and a prose register that still calls a CONSUMED signal unconsumed "
          "is caught, while a struck-through row is not (non-vacuous).")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    problems, rows = check()
    problems += stale_prose_claims(rows)
    unconsumed = [r for r in rows if r.get("unconsumed")]

    if "--list" in sys.argv:
        for r in rows:
            state = "UNCONSUMED" if r.get("unconsumed") else \
                f"→ {(r.get('consumer') or {}).get('file', '?')}"
            print(f"  {r.get('id', '?'):34} {r.get('field', '?'):22} {state}")
        return 0

    rc = 0
    if problems:
        print("guard-signal-consumption-gate: FAIL\n")
        for p in problems:
            print(f"   {p}")
        print()
        rc = 1

    if len(unconsumed) != UNCONSUMED_BASELINE:
        grew = len(unconsumed) > UNCONSUMED_BASELINE
        print(f"{'FAIL' if grew else 'NOTE'} — guard signals with nothing acting on them "
              f"{'grew to' if grew else 'dropped to'} {len(unconsumed)} "
              f"(baseline {UNCONSUMED_BASELINE}).")
        if grew:
            print("   A signal that changes no behaviour is a fact, not a guard. This repo")
            print("   shipped FIVE in one day, each defensible on its own. Give the new one a")
            print("   consumer — a branch, a gate condition, a rendered badge — or say why it")
            print("   has none and lower nothing.")
            for r in unconsumed:
                print(f"     {r['id']}")
        else:
            print(f"   Progress — lower UNCONSUMED_BASELINE to {len(unconsumed)} in "
                  f"{Path(__file__).name}.")
        rc = 1

    if rc == 0:
        consumed = len(rows) - len(unconsumed)
        print(f"guard-signal-consumption-gate: PASS — {len(rows)} guard signal(s) registered; "
              f"{consumed} consumed, {len(unconsumed)} held at baseline.")
        if unconsumed:
            print("   Held signals are honest, not harmless: each names two states a "
                  "reader can now tell apart, and nothing yet acts on the difference.")
        else:
            # Said only when it is TRUE. The old line printed the held-signal caveat
            # unconditionally, so at zero it described a set that no longer existed —
            # a small instance of exactly what this gate is for.
            print("   Every registered signal changes something a human or a gate can "
                  "act on. The ratchet stays: a SIXTH emitted-and-unread signal fails.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
