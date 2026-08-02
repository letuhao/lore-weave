#!/usr/bin/env python3
"""hashed-substrate-float-gate — no float in the bytes that BECOME A NAME.

THE RULE THIS ENFORCES (`U-9`)
------------------------------
`docs/specs/2026-08-02-actor-hub/2026-08-02-engine-substrate.md` §3:

  > "A float inside the hashed bytes lets two machines produce two digests for
  >  one ruleset — two realities with identical content and different NAMES.
  >  Server authority cannot repair that: what breaks is the naming scheme, not
  >  the gameplay."
  >
  > "**Structurally true today, and unguarded:** `crates/ruleset-core/src/`
  >  contains no `f32`/`f64`. **No gate prevents one being added** — `U-9`."

This is that gate. The property was true by accident for four days; a property
nothing watches is a property that is about to stop being true.

WHAT THIS IS *NOT*
------------------
**It is not a float ban.** DF7-A4 was revised on 2026-08-02 precisely because the
old "float cannot reproduce across targets" claim is FALSE for basic IEEE 754
operations, and this repo's own `world-gen` disproves it across 41 files while
hashing its output deterministically. Reproducing that mistake as a repo-wide
lint would be the second time the same wrong belief shipped.

The subject here is narrow and stated: **the crates whose bytes are hashed into
a ruleset digest, and the fold that ranges over them.** A digest does not need
precision; it needs reproducibility of BYTES. Two different properties, and only
the second is at stake.

  crates/ruleset-core   the canonical encoding + `blake3(canonical bytes)`
  crates/actor-hub      the fold over declared quantities; its accumulator is
                        `i64` milli-units by contract (substrate §5)

The scope is the **whole crate**, not `<crate>/src`. That is a correction, and
the reason is `NV-4` — an adjacent decision defeating a check. The first version
guarded `<crate>/src` while its own docstring said test code was in scope; then
the file-ceiling split moved ~800 lines of tests OUT of `crates/actor-hub/src`
into `crates/actor-hub/tests`, and a probe file with `let x: f64 = 1.5;` there
passed the gate with exit 0. Both decisions were individually correct. Together
they emptied the gate of the scope it claimed.

SCOPE IS A DIRECTORY, NOT A FILE LIST
-------------------------------------
`docs/standards/non-vacuity.md` NV-3: an enumerated file list is
**default-uncovered** — it says nothing about a file created tomorrow, which is
exactly when a new `f64` field would arrive. So the scope is the crate's whole
`src/` tree, recursively, and a new file is covered on its first line.

WHAT IT LOOKS FOR
-----------------
The `f32` / `f64` types, and the float-literal syntax that implies them
(`1.0f64`, `2f32`), in **code only** — comments and string literals are stripped
first, because a gate that reds on its own documentation gets switched off. That
is not a hypothetical: it is how `design-lint count` spent its entire first life,
and this file's own module docstring names `f32` four times.

TEST CODE IS IN SCOPE, AND THAT IS DELIBERATE
---------------------------------------------
A `f64` in a `#[cfg(test)]` block cannot reach a digest — but it is how the type
gets into the crate's vocabulary, and the next author copies the nearest
example. Exempting tests would also make the gate's scope depend on parsing
`cfg` attributes, which is more machinery than the rule is worth. A genuine case
takes the pragma below.

THE ESCAPE HATCH REACHES ITS REASON
-----------------------------------
`hashed-substrate-float-gate: ok — <reason>` on the offending line **or on any
of the three lines above it**, so the reason can sit in a doc comment where a
reader will actually see it. A fixed one-line window shipped in three sibling
gates and could not reach the reason it was supposed to carry
(`docs/standards/non-vacuity.md`, the fourth vacuity shape).

    python scripts/hashed-substrate-float-gate.py
    python scripts/hashed-substrate-float-gate.py --staged
    python scripts/hashed-substrate-float-gate.py --self-test
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gatelib import strip_comments  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

# The crates whose bytes become a ruleset digest, plus the fold that ranges over
# them. Directories, recursive — see NV-3 in the module docstring.
GUARDED_TREES = (
    "crates/ruleset-core",
    "crates/actor-hub",
)

# `f32`/`f64` as a token, and float literals that produce them.
#
# The left edge is `(?<![A-Za-z_])` and NOT `\b`, which the self-test caught:
# `\bf64\b` requires a word boundary before `f`, and a suffixed literal `2f64`
# has a DIGIT there — so `let x = 2f64;` passed a gate written to refuse exactly
# that. The lookbehind still refuses `my_f32_helper` (preceded by `_`) and the
# hex literal `0xf32` (preceded by `x`).
FLOAT_RE = re.compile(
    # The types, and the literal suffix `1.0f64` / `2f64`.
    r"(?<![A-Za-z_])f(?:32|64)\b"
    # A float literal with an EXPONENT: `1e5`, `2e-3`, `1E10`, `4.0e-9`. Rust
    # needs a digit before `e`, and `1e5` has no decimal point at all -- which is
    # how every scientific-notation float walked past the first version of this
    # gate. A review measured `4.0e-9`, `1e5`, `2e-3`, `1E10` and `5e-1` all
    # passing with exit 0.
    r"|(?<![\w.])\d[\d_]*(?:\.[\d_]*)?[eE][+-]?\d[\d_]*"
    # A plain float literal: `1.5`, `0.001`, `1_0.5`, `1_000.`
    # `[\d_]` on the left is what admits a digit separator before the dot: `\b`
    # does not match between `_` and `.`, so `1_000.` slipped through before.
    r"|(?<![\w.])\d[\d_]*\.(?:[\d_]+)?(?![\w.])"
)

PRAGMA = "hashed-substrate-float-gate: ok"
PRAGMA_LOOKBACK = 3


class Finding:
    def __init__(self, path: str, line: int, text: str, token: str):
        self.path, self.line, self.text, self.token = path, line, text, token

    def __str__(self) -> str:
        return f"  {self.path}:{self.line}  `{self.token}` in {self.text.strip()[:90]}"


def _pragma_covers(raw: list[str], kept_strings: list[str], idx: int) -> bool:
    """True if a pragma **in a comment** sits on this line or just above it.

    The window exists so the reason can live in the doc comment that explains the
    exception, rather than being crammed onto the end of the code line.

    **A pragma inside a STRING LITERAL does not count**, and that is a fix rather
    than a nicety: a review measured `let msg = "hashed-substrate-float-gate: ok
    - not really";` above an `f64` field silencing the gate entirely. The tell was
    that this file stripped strings for the SCAN and not for the PRAGMA — sibling
    arms of one file disagreeing about what counts as code.

    `kept_strings` is the source with comments blanked and strings kept, so a
    pragma that survives into it came from a string and is refused.
    """
    lo = max(0, idx - PRAGMA_LOOKBACK)
    return any(
        PRAGMA in raw[k] and PRAGMA not in kept_strings[k]
        for k in range(lo, idx + 1)
    )


def scan_source(path: str, src: str) -> list[Finding]:
    """Findings in one file's source text. Pure — the self-test calls it directly."""
    raw_lines = src.splitlines()
    # Offsets are preserved by `strip_comments`, so line numbers stay valid; the
    # pragma is looked up in the RAW lines because it lives in a comment.
    stripped = strip_comments(src, keep_strings=False).splitlines()
    out: list[Finding] = []
    # A pragma is legitimate only inside a COMMENT. Blanking comments while
    # KEEPING strings gives a view in which a pragma written inside a string
    # literal is still visible — and that is exactly the one to refuse.
    in_strings = strip_comments(src, keep_strings=True).splitlines()
    for i, line in enumerate(stripped):
        matches = list(FLOAT_RE.finditer(line))
        if not matches:
            continue
        if _pragma_covers(raw_lines, in_strings, i):
            continue
        # Every float on the line, not just the first: two on one line used to
        # report as one, so fixing the first looked like fixing the line.
        for m in matches:
            out.append(Finding(path, i + 1, raw_lines[i], m.group(0)))
    return out


def _rust_files(staged_only: bool) -> list[Path]:
    if staged_only:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            cwd=REPO, capture_output=True, text=True,
        )
        names = [n.strip() for n in out.stdout.splitlines() if n.strip().endswith(".rs")]
        paths = [REPO / n for n in names]
        return [
            p for p in paths
            if p.exists() and any(
                str(p.relative_to(REPO)).replace("\\", "/").startswith(t) for t in GUARDED_TREES
            )
        ]
    found: list[Path] = []
    for tree in GUARDED_TREES:
        root = REPO / tree
        if not root.exists():
            # A guarded tree that has been renamed away is a gate that silently
            # guards nothing, which is worse than no gate. Say so.
            print(
                f"hashed-substrate-float-gate: guarded tree `{tree}` does not exist — "
                "the gate is guarding nothing. Fix GUARDED_TREES or restore the crate.",
                file=sys.stderr,
            )
            sys.exit(2)
        found.extend(sorted(root.rglob("*.rs")))
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--staged", action="store_true", help="only staged files")
    ap.add_argument("--self-test", action="store_true", help="prove the rule bites")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    findings: list[Finding] = []
    for p in _rust_files(args.staged):
        rel = str(p.relative_to(REPO)).replace("\\", "/")
        findings.extend(scan_source(rel, p.read_text(encoding="utf-8", errors="replace")))

    if findings:
        print(f"hashed-substrate-float-gate: {len(findings)} finding(s)\n")
        for f in findings:
            print(f)
        print(
            "\nA float inside the hashed bytes lets two machines produce two digests for one\n"
            "ruleset — two realities with identical content and different NAMES. This is NOT a\n"
            "float ban: it is narrow to the crates whose bytes are hashed (engine-substrate §3).\n"
            f"A genuine exception carries `{PRAGMA} — <reason>` on the line or up to\n"
            f"{PRAGMA_LOOKBACK} lines above it."
        )
        return 1

    print(
        "hashed-substrate-float-gate: OK — "
        + ", ".join(GUARDED_TREES)
        + " carry no float"
    )
    return 0


# ── non-vacuity ──────────────────────────────────────────────────────────────

def self_test() -> int:
    """Every rule is run against input that violates it, and against input that
    must NOT trip it. A gate whose self-test only feeds it clean input proves
    nothing — that is the shape `docs/standards/non-vacuity.md` calls a check
    whose subject cannot vary."""
    cases: list[tuple[str, str, int]] = [
        ("a struct field", "pub struct D { pub rate: f64 }", 1),
        ("a cast", "let x = y as f32;", 1),
        ("a float literal", "let x = 1.5;", 1),
        ("a suffixed literal", "let x = 2f64;", 1),
        ("a trailing-dot literal", "let x = 3.;", 1),
        ("a generic parameter", "fn f(v: Vec<f64>) {}", 1),
        # Must NOT fire:
        ("the word in a comment", "// this crate contains no f64 anywhere\nlet x = 1;", 0),
        ("the word in a string", 'let s = "f64 is not allowed";', 0),
        ("an integer", "let x = 42;", 0),
        ("a range", "let r = 0..32;", 0),
        ("a tuple index", "let a = t.0;", 0),
        ("an identifier that contains it", "let my_f64_note = 1;", 0),
        ("a method call", "let n = v.len();", 0),
        ("i64 milli-units, the sanctioned representation", "let acc: i64 = 0;", 0),
        ("scientific notation, no dot", "let x = 1e5;", 1),
        ("scientific notation, negative exponent", "let x = 2e-3;", 1),
        ("scientific notation, capital E", "let x = 1E10;", 1),
        ("scientific notation with a dot", "let x = 4.0e-9;", 1),
        ("a digit separator before the dot", "let x = 1_000.;", 1),
        ("a digit separator inside the mantissa", "let x = 1_0.5;", 1),
        ("two floats on one line are two findings", "let a = 1.5; let b = 2.5;", 2),
        ("an integer with a separator is not a float", "let x = 1_000;", 0),
        ("a range with separators is not a float", "let r = 0..1_000;", 0),
        ("an identifier ending in a digit is not a float", "let x1e5 = 3;", 0),
        ("a hex literal is not a float", "let x = 0xf32;", 0),
        ("pragma on the same line", f"pub rate: f64, // {PRAGMA} — reason", 0),
        (
            "a pragma inside a STRING does not silence anything",
            f'let msg = "{PRAGMA} - not really";\npub rate: f64,',
            1,
        ),
        (
            "pragma two lines above",
            f"/// {PRAGMA} — reason\n/// more prose\npub rate: f64,",
            0,
        ),
    ]
    failures = 0
    for name, src, expected in cases:
        got = len(scan_source("<self-test>", src))
        status = "ok " if got == expected else "FAIL"
        if got != expected:
            failures += 1
        print(f"  {status} {name}: expected {expected}, got {got}")

    # The pragma window must be BOUNDED — an unbounded one silences the whole
    # file. Four lines above is outside the window and must still be a finding.
    far = f"/// {PRAGMA} — reason\n///\n///\n///\npub rate: f64,"
    got = len(scan_source("<self-test>", far))
    if got != 1:
        failures += 1
        print(f"  FAIL pragma window is unbounded: expected 1 finding, got {got}")
    else:
        print("  ok  pragma window is bounded at 3 lines")

    if failures:
        print(f"\nhashed-substrate-float-gate --self-test: {failures} rule(s) did not behave")
        return 1
    print("\nhashed-substrate-float-gate --self-test: every rule bites, and none cries wolf")
    return 0


if __name__ == "__main__":
    sys.exit(main())
