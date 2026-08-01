#!/usr/bin/env python3
"""pin-resolution-gate — a content-address pin must be RESOLVED wherever a
ruleset is admitted into a reality.

THE BUG THIS EXISTS TO PREVENT
------------------------------
`Ruleset` carries `progression: Option<ProgressionDigest>` — 32 bytes naming a
table that lives in a separate store. `RulesetStore::get` verifies the OUTER
artifact only: a ruleset whose pin names absent or corrupt bytes comes back
CLEAN, because the pin is inside the bytes that verified.

`resolve_progression` was written to catch exactly that, shipped with 12 tests
and a module doc arguing for it, and had **ZERO production callers**. A probe
showed `activate_reality_epoch` moving a reality to epoch 2 onto a ruleset whose
ladder had been deleted, and returning `Ok`:

    !!! SWITCH SUCCEEDED onto a dangling progression pin: epoch=2

A mechanism nothing invokes is not a mechanism. It is a claim with a test suite
attached, and it reads as coverage to the next person who greps.

WHY THIS SHAPE AND NOT THE GENERAL ONE
--------------------------------------
The general form — *"every exported entry point must have a production
caller"* — was prototyped first and **rejected on measurement**: 64 of 143
module-level `pub fn`s in `crates/` have no non-test caller, because the game
tier is young and much of it is exercised only by its own suites. A gate that
fires 64 times is a gate someone switches off, which is worse than no gate.

So the subject is narrowed to the invariant that actually bit, and BOTH halves
are DISCOVERED rather than listed — a hand-list is `NV-3` waiting to happen,
since the next pin and the next admission point would simply not be in it:

  pins              fields on `Ruleset` whose type names a `*Digest` other than
                    the ruleset's own. Today: `progression`.
  admission points  every `pub fn` taking BOTH a `RulesetStore` and a
                    `BindingStore` — the two arguments that together mean "this
                    call puts a ruleset behind a reality id". Today:
                    `create_reality`, `load_reality`, `activate_reality_epoch`.

Each admission point must mention a resolver for each pin. Add a second pin, or
a fourth admission point, and this reds without anyone remembering to look.

An admission point that genuinely does not need to resolve carries an inline
`pin-resolution-gate: ok — <reason>` in its body or doc block.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOADER = ROOT / "crates" / "ruleset-loader" / "src"
CORE_RULESET = ROOT / "crates" / "ruleset-core" / "src" / "ruleset.rs"

PRAGMA = re.compile(r"pin-resolution-gate:\s*ok\b")

# The ruleset's OWN digest is not a pin into another store — it is the address
# of these very bytes, and resolving it here would be circular.
SELF_DIGEST = "RulesetDigest"


def strip_comments(src: str) -> str:
    """A pragma in a comment must not satisfy the check it exempts, and a
    resolver NAMED in a doc comment must not count as calling one — the exact
    trap that certified three prose-only deferrals as covered."""
    src = re.sub(r"//.*", "", src)
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def discover_pins() -> list[tuple[str, str]]:
    """`(field, digest_type)` for every content-address pin on `Ruleset`."""
    src = strip_comments(CORE_RULESET.read_text(encoding="utf-8", errors="ignore"))
    m = re.search(r"pub struct Ruleset\s*\{(.*?)\n\}", src, flags=re.S)
    if not m:
        return []
    out = []
    for fm in re.finditer(r"pub (\w+)\s*:\s*([^,]+),", m.group(1)):
        field, ty = fm.group(1), fm.group(2)
        if "Digest" in ty and SELF_DIGEST not in ty:
            out.append((field, re.search(r"(\w*Digest)", ty).group(1)))
    return out


def fn_bodies(src: str) -> list[tuple[str, str, int]]:
    """`(name, body, line)` for each module-level `pub fn`, by brace matching."""
    out = []
    for m in re.finditer(r"^pub fn (\w+)\s*\(", src, flags=re.M):
        i = src.index("{", m.end() - 1)
        depth, j = 0, i
        while j < len(src):
            if src[j] == "{":
                depth += 1
            elif src[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        # include the signature so the arg types are visible to the caller
        out.append((m.group(1), src[m.start() : j + 1], src[: m.start()].count("\n") + 1))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    pins = discover_pins()
    if not pins:
        print(
            "pin-resolution-gate: FAIL — no content-address pin found on `Ruleset`.\n"
            "  Either the struct moved, or the discovery regex stopped matching. A gate\n"
            "  whose subject silently became EMPTY is the NV-3 shape and passes forever,\n"
            "  so an empty discovery is a FAILURE here, never a quiet OK."
        )
        return 1

    findings: list[str] = []
    checked = 0
    for f in sorted(LOADER.rglob("*.rs")):
        raw = f.read_text(encoding="utf-8", errors="ignore")
        code = strip_comments(raw)
        for name, body, line in fn_bodies(code):
            if "RulesetStore" not in body or "BindingStore" not in body:
                continue
            checked += 1
            raw_body = raw[raw.index(f"pub fn {name}") :][: len(body) + 400]
            if PRAGMA.search(raw_body):
                continue
            for field, ty in pins:
                resolver = f"resolve_{field}"
                if resolver not in body and "admit_progression" not in body:
                    findings.append(
                        f"{f.relative_to(ROOT).as_posix()}:{line}: `{name}` admits a ruleset "
                        f"(it takes both a RulesetStore and a BindingStore) but never resolves "
                        f"the `{field}` pin ({ty}). `RulesetStore::get` verifies the OUTER "
                        f"artifact only - a pin naming absent bytes comes back CLEAN. Call "
                        f"`{resolver}` / `admit_progression`, or add an inline "
                        f"`pin-resolution-gate: ok - <why this one need not>`."
                    )

    if args.self_test:
        ok = len(pins) >= 1 and checked >= 1
        print(
            f"self-test: {len(pins)} pin(s) discovered {pins}, {checked} admission point(s) "
            f"found. Both non-empty: {'yes' if ok else 'NO'}"
        )
        return 0 if ok else 1

    print(
        f"pin-resolution-gate: scanned {checked} admission point(s) against "
        f"{len(pins)} pin(s): {[p[0] for p in pins]}"
    )
    if findings:
        for x in findings:
            print(f"  {x}")
        print(f"\npin-resolution-gate: FAIL — {len(findings)} finding(s)")
        print("A pin nothing resolves is a reality that boots with its content silently gone.")
        return 1
    print("pin-resolution-gate: OK — every admission point resolves every pin")
    return 0


if __name__ == "__main__":
    sys.exit(main())
