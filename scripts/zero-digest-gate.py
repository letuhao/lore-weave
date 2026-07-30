#!/usr/bin/env python3
"""zero-digest-gate — a ruleset pin must not be an anonymous zero.

THE BUG THIS EXISTS TO PREVENT
------------------------------
`RulesetDigest([0u8; 32])` appeared in **15 places**, four of them production
paths (`commit-service` main + spine, and two harness bins). RLS-A13 makes the
digest the thing that pins an event to the rules that produced it; an all-zero
digest makes that pin INERT. Two realities with different rules stamp
indistinguishable events, and replay cannot detect that the rules moved
underneath it — the canonical event-sourcing configuration trap, and the one
that defeats the conformance/oracle spine this repo already runs.

It survived because it looks like a value. Nothing in the type system
distinguishes "we have not wired the loader yet" from "this domain genuinely
has no ruleset", so both were spelled the same way and neither was visible.

WHAT IT CHECKS
--------------
Two rules, in CODE only (comments and string literals are stripped first — a
lint that fires on its own documentation gets switched off, which is how the
`design-lint count` check spent its entire first life):

  anonymous-zero  `RulesetDigest([0u8; 32])` / `([0; 32])` written inline.
                  Anywhere. Use a computed digest, or the NAMED constant.
  unpinned-scope  `RulesetDigest::UNPINNED` outside the places entitled to it:
                  the kernel harness (`crates/sim`) and test files. A service
                  binary reaching for it is exactly the case the constant was
                  introduced to make visible, not to make easy.

AND THE SAME BUG IN TYPESCRIPT
------------------------------
The Rust sweep is not the whole story, which the F1 /review-impl found the hard
way. `contracts/game-wire/session.schema.json` REQUIRES `ruleset_digest` on the
`w0.bind` frame, and its own description says *"the client caches by digest — a
digest can never be stale, only unused."* A 64-zero fallback therefore gives
EVERY reality the same cache key. So `.ts`/`.tsx` are scanned too, for a 64-zero
digest written as `'0'.repeat(64)` or as a literal. Strings are NOT stripped for
TS — there the zero digest IS a string literal.

`UNPINNED` is the same move as `MAX_HIT` in the damage chain: a DECLARED zero
has a name and a reason, an emergent one is a number nobody can explain.

ESCAPE HATCH
------------
An inline reason on the line or the line above:

    // zero-digest-gate: ok — <why this really has no ruleset>

SELF-TEST
---------
`--self-test` runs the checker against a deliberately broken fixture and fails
if it reports nothing. A gate nobody has watched fire is a gate nobody knows is
connected.

Usage:
    python scripts/zero-digest-gate.py [PATH ...]     # default: crates/ services/
    python scripts/zero-digest-gate.py --self-test
    python scripts/zero-digest-gate.py --staged
"""

from __future__ import annotations

import argparse
import os
import re
import sys

# S2 — the ONE shared source stripper (scripts/gatelib.py). Three gates had grown
# three copies and the newest was the buggy one, precisely because it was written
# rather than reused: a `//` inside a string literal silently ate the code after
# it. `gatelib.strip_comments` blanks IN PLACE, so line numbers survive, and
# `keep_strings` is REQUIRED at every call site because getting it backwards
# blinds one gate or makes the other cry wolf.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gatelib import strip_comments  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ROOTS = ["crates", "services", "frontend/src"]
SKIP_DIRS = {"target", "node_modules", ".git", "__pycache__", ".claude"}

# Every 32-byte content-address newtype in the tree. `S-1b` added the second
# one (`ProgressionDigest`, the pin on `Ruleset`), and a gate that knew only
# about the first would have been NV-3 the moment it landed — the check exists,
# the defect is identical, and the SCOPE simply never reaches it. The right
# reading of "a check must be able to fail" is that it must be able to fail on
# the thing that can actually break, so the type list grows with the types.
#
# ⚠ Adding a digest newtype WITHOUT adding it here is the silent way to opt out.
# `test_every_digest_newtype_is_covered` in the selftest pins the list against
# the tree so a new one reds instead of slipping through.
DIGEST_TYPES = ("RulesetDigest", "ProgressionDigest")
_TYPES_ALT = "|".join(DIGEST_TYPES)

# `RulesetDigest([0u8; 32])`, `ProgressionDigest([0; 32])`, `…([0u8;32])`…
ANON_ZERO = re.compile(rf"(?:{_TYPES_ALT})\s*\(\s*\[\s*0(?:u8)?\s*;\s*32\s*\]\s*\)")
UNPINNED = re.compile(r"RulesetDigest::UNPINNED")
PRAGMA = re.compile(r"zero-digest-gate:\s*ok\b")

#: A 64-zero digest in TypeScript: `'0'.repeat(64)` or the literal spelled out.
#: Strings are NOT stripped for TS — there the zero digest IS a string literal.
TS_ZERO = re.compile(r"""['"]0['"]\s*\.\s*repeat\(\s*64\s*\)|['"]0{64}['"]""")

#: Where `UNPINNED` is legitimate.
#:
#: `crates/sim` is the kernel's own chaos/bench harness: its `TestDomain` has
#: rules invented by the test, not a resolved artifact, so there is nothing for
#: a digest to address and fabricating one would be a lie. Test files are the
#: same argument one level down. `sim-core/src/types.rs` is the DEFINITION.
UNPINNED_OK_PREFIXES = ("crates/sim/",)
UNPINNED_OK_FILES = ("crates/sim-core/src/types.rs",)


def is_test_file(rel: str) -> bool:
    return (
        "/tests/" in rel
        or rel.endswith("_test.rs")
        or rel.endswith("/tests.rs")
        or "/benches/" in rel
    )


def pragma_near(lines: list[str], line_no: int) -> bool:
    """A reason on this line, or anywhere in the comment block attached to it.

    **This started as a fixed two-line window and that was wrong**, exactly as
    it was wrong in `closed-set-gate` a few commits earlier: the real
    justification for the one live finding is an eleven-line comment above its
    line, so the pragma did NOTHING and the bite-test that "proved" it worked
    reported the finding both with and without it. A vacuous check that looks
    green — the same failure the whole non-vacuity discipline exists to catch,
    committed twice by the same author in the same week.

    A reason belongs in the item's own comment block, so walk the contiguous
    block upward rather than guessing a distance.
    """
    idx = line_no - 1  # to 0-based
    if 0 <= idx < len(lines) and PRAGMA.search(lines[idx]):
        return True
    k = idx - 1
    while k >= 0:
        stripped = lines[k].strip()
        if stripped.startswith(("///", "//!", "//", "#[", "*", "/*")) or stripped == "":
            if PRAGMA.search(lines[k]):
                return True
            if stripped == "" and not (
                k > 0 and lines[k - 1].strip().startswith(("///", "//", "*"))
            ):
                break
            k -= 1
            continue
        break
    return False


def check_source(rel: str, src: str) -> list[tuple[str, int, str]]:
    if not any(t in src for t in DIGEST_TYPES):
        return []
    clean = strip_comments(src, keep_strings=False)
    lines = src.split("\n")
    findings: list[tuple[str, int, str]] = []

    for m in ANON_ZERO.finditer(clean):
        line_no = clean.count("\n", 0, m.start()) + 1
        if pragma_near(lines, line_no):
            continue
        findings.append((
            rel, line_no,
            "anonymous-zero: a 32-byte digest newtype written as an inline zero "
            "(RulesetDigest/ProgressionDigest([0u8; 32])). An "
            "all-zero digest makes RLS-A13's pin INERT — two realities with "
            "different rules stamp indistinguishable events. Pass a computed "
            "`Ruleset::digest()`, or `RulesetDigest::UNPINNED` if this domain "
            "genuinely has no ruleset.",
        ))

    allowed = (
        rel.startswith(UNPINNED_OK_PREFIXES)
        or rel in UNPINNED_OK_FILES
        or is_test_file(rel)
    )
    if not allowed:
        for m in UNPINNED.finditer(clean):
            line_no = clean.count("\n", 0, m.start()) + 1
            if pragma_near(lines, line_no):
                continue
            findings.append((
                rel, line_no,
                "unpinned-scope: `RulesetDigest::UNPINNED` outside the kernel "
                "harness and tests. Production code runs a REAL ruleset; if the "
                "loader is not wired here yet, that is the bug, not the digest.",
            ))
    return findings


def check_ts_source(rel: str, src: str) -> list[tuple[str, int, str]]:
    if "0" not in src:
        return []
    clean = strip_comments(src, keep_strings=True)
    lines = src.split("\n")
    findings: list[tuple[str, int, str]] = []
    for m in TS_ZERO.finditer(clean):
        line_no = clean.count("\n", 0, m.start()) + 1
        if pragma_near(lines, line_no):
            continue
        findings.append((
            rel, line_no,
            "anonymous-zero (ts): a 64-zero `ruleset_digest` on the wire. "
            "`contracts/game-wire/session.schema.json` says the client caches BY "
            "digest, so a shared zero gives every reality one cache key. Send "
            "the reality's real digest, or state why there is none.",
        ))
    return findings


def walk(roots: list[str]) -> list[str]:
    files = []
    for root in roots:
        base = root if os.path.isabs(root) else os.path.join(REPO_ROOT, root)
        if os.path.isfile(base):
            files.append(base)
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                if fn.endswith((".rs", ".ts", ".tsx")):
                    files.append(os.path.join(dirpath, fn))
    return files


BROKEN_FIXTURE = """
fn wire() {
    let a = Island::new(id, seed, rules, RulesetDigest([0u8; 32]), w, s);
    let b = Island::new(id, seed, rules, RulesetDigest([0; 32]), w, s);
    let c = RulesetDigest::UNPINNED;
}
"""

CLEAN_FIXTURE = """
fn wire() {
    // Was RulesetDigest([0u8; 32]) — a comment must NOT trip the gate.
    let msg = "RulesetDigest([0u8; 32])";
    let d = ruleset.digest();
    // zero-digest-gate: ok — documented fixture, no ruleset exists here
    let e = RulesetDigest([0u8; 32]);
}
"""


TS_BROKEN = "  ruleset_digest: this.opts.rulesetDigest ?? '0'.repeat(64),"
TS_CLEAN = (
    "  // zero-digest-gate: ok — fixture\n"
    "  ruleset_digest: '0'.repeat(64),\n"
    "  const real = digestHex; // no zero here\n"
)


def self_test() -> int:
    bad = check_source("services/x/src/main.rs", BROKEN_FIXTURE)
    good = check_source("services/x/src/main.rs", CLEAN_FIXTURE)
    ok = True
    if sum(1 for f in bad if "anonymous-zero" in f[2]) != 2:
        print("SELF-TEST FAIL: both anonymous-zero spellings were not reported")
        ok = False
    if not any("unpinned-scope" in f[2] for f in bad):
        print("SELF-TEST FAIL: UNPINNED in a service path was not reported")
        ok = False
    # The same UNPINNED line, in a place entitled to it, must be silent —
    # otherwise the scope rule is decorative and the gate is just a banner.
    if check_source("crates/sim/src/bin/bench.rs", "let c = RulesetDigest::UNPINNED;"):
        print("SELF-TEST FAIL: UNPINNED was reported inside crates/sim")
        ok = False
    if good:
        print(f"SELF-TEST FAIL: a clean file was reported: {good}")
        ok = False
    if not check_ts_source("services/g/src/R.ts", TS_BROKEN):
        print("SELF-TEST FAIL: the TypeScript 64-zero digest was not reported")
        ok = False
    if check_ts_source("services/g/src/R.ts", TS_CLEAN):
        print("SELF-TEST FAIL: a pragma'd TypeScript line was reported")
        ok = False
    if ok:
        print("self-test: the gate bites (2 anonymous zeros + 1 out-of-scope "
              "UNPINNED + 1 TypeScript 64-zero detected; comments, Rust strings, "
              "pragmas and crates/sim silent)")
        return 0
    print("  detail:", [f[2][:40] for f in bad])
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="*", default=None,
                    help="files or directories (default: crates/ services/)")
    ap.add_argument("--self-test", action="store_true",
                    help="prove the gate can fail, then exit")
    ap.add_argument("--staged", action="store_true",
                    help="scan only staged .rs files (pre-commit mode)")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    if args.staged:
        import subprocess
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            cwd=REPO_ROOT, capture_output=True, text=True).stdout
        files = [
            os.path.join(REPO_ROOT, p.strip())
            for p in out.split("\n")
            if p.strip().endswith((".rs", ".ts", ".tsx"))
            and os.path.exists(os.path.join(REPO_ROOT, p.strip()))
        ]
    else:
        files = walk(args.paths or DEFAULT_ROOTS)

    findings: list[tuple[str, int, str]] = []
    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                src = fh.read()
        except OSError:
            continue
        rel = os.path.relpath(path, REPO_ROOT).replace("\\", "/")
        if rel.endswith(".rs"):
            findings.extend(check_source(rel, src))
        else:
            findings.extend(check_ts_source(rel, src))

    print(f"zero-digest-gate: scanned {len(files)} source file(s)")
    for rel, line, msg in findings:
        print(f"{rel}:{line}: [zero-digest] {msg}")

    if findings:
        print(f"\nzero-digest-gate: FAIL — {len(findings)} finding(s)")
        print("A ruleset pin that is an anonymous zero pins nothing (IMP-D6/RLS-A13).")
        print("Fix the wiring, or add an inline reason: `zero-digest-gate: ok — <why>`.")
        return 1
    print("zero-digest-gate: OK — no findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
