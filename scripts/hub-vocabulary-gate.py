#!/usr/bin/env python3
"""hub-vocabulary-gate — the hub may ORDER by an ordinal, never READ its meaning.

THE RULE THIS ENFORCES (`A-1`, supplement §3)
---------------------------------------------
actor-hub.md §4:

  > "The hub never inspects `fold_layer` semantically. It orders by it and
  >  nothing else. **If the hub ever needs to know what a layer MEANS, a
  >  plugin's vocabulary has leaked in.**"

The second sentence is the rule stating its own failure condition, which is what
makes it gateable rather than aspirational. Until this file existed, NOTHING
checked it.

WHY IT EXISTS AT ALL
--------------------
`D-513`, from the completeness audit: the property held **structurally, and
unguarded** — no branch on a specific layer or quantity value existed anywhere in
`crates/actor-hub/src`, and nothing would have noticed the first one. That is
verbatim the situation engine-substrate §3 recognised for floats — *"structurally
true today, and unguarded"* — and answered with `U-9`'s gate. The identical shape,
one contract over, had no gate and no seam.

WHAT SEPARATES A LEAK FROM ARITHMETIC
-------------------------------------
An ordinal is an ADDRESS. Comparing one against a **named width constant**
(`< MAX_PLUGINS`) asks *"is this address in range"* — mechanism, and silent here.
Comparing one against a **literal** asks *"is this the address I mean"* — which
is a name, and a name belongs to the plugin that authored it.

So every rule below keys on a LITERAL. That is the whole discriminator, and it
is why `raw >= MAX_PLUGINS` in `ordinal.rs` is not a finding while
`layer.get() == 3` would be.

SCOPE IS A DIRECTORY, NOT A FILE LIST (NV-3)
--------------------------------------------
`crates/actor-hub/src`, recursive. An enumerated file list is
*default-uncovered*: it says nothing about the file created tomorrow, and the
gate would keep reporting OK while the leak sat in it. The float gate carries
this same paragraph for the same reason.

WHAT IS EXCLUDED, AND WHY EACH EXCLUSION IS SAFE
------------------------------------------------
* `#[cfg(test)]` blocks — naming an ordinal is how a test is WRITTEN. Excluded by
  BRACE COUNTING, not by cutting at the first occurrence: a `mod tests` in the
  middle of a file would otherwise make every line after it default-uncovered,
  which is NV-3 one level in.
* comments — `mana` and `hp` are how the rule is EXPLAINED. Blanked in place by
  `gatelib.strip_comments`, so line numbers stay true.

WHAT THIS GATE CANNOT SEE -- STATED, NOT DISCOVERED
---------------------------------------------------
A line regex cannot know a receiver TYPE, and every remaining escape is a
consequence of that. Measured by a cold-start verifier against this file:

  * a named constant -- `const TREASURE: u8 = 3; ... l.get() == TREASURE`.
    Indistinguishable from `>= MAX_PLUGINS`, which MUST stay silent.
  * laundering -- `fn raw(l: FoldLayer) -> u8 { l.get() }` then `raw(l) == 3`.
  * a slice or iterator -- `[3u8, 7u8].contains(&l.get())`.
  * a conversion -- `FoldLayer::from(3)`, `3u8.into()`, `u8::from(l.get())`.

These are NOT caught, and the ledger says so rather than claiming the
property is enforced. **A check that reports coverage it does not have is
worse than no check**, which is the standard this file is built under; the
honest statement is that the DIRECT spellings are mechanised and the
laundered ones remain a review question.

THE ESCAPE HATCH MUST BE ABLE TO REACH ITS REASON (NV-6)
---------------------------------------------------------
The pragma is `hub-vocabulary-gate: ok — <reason>`, honoured anywhere in the
**contiguous comment block** immediately above the finding, however long that
block runs.

A FIXED line window is deliberately NOT used. One shipped in three sibling gates
and is NV-6's own worked example: a reason that does not fit in the window gets
deleted, and the exemption survives it. A block that ends where the comments end
can always hold the reason.
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

# A directory, recursive — see NV-3 above.
GUARDED_TREE = "crates/actor-hub/src"

PRAGMA = "hub-vocabulary-gate: ok"

# The hub's own address types. `FoldLayer` is a public tuple struct, so
# `FoldLayer(3)` is a construction too — leaving it out would have exempted the
# most natural way to write the leak.
ADDRESS = r"(?:FoldLayer|QuantityOrdinal|PluginOrdinal)"

# **Keyed on the ACCESSOR, not on the variable's name.**
#
# The first version of this file keyed on names — `fold_layer`, `layer`,
# `ordinal`, … — and its own BITE TEST walked straight through it: a planted
# `fn treasure_is_special(l: FoldLayer) -> bool { l.get() == 40 }` was NOT
# reported, because the author had called the binding `l`. Every self-test case
# passed, because every case had been written FROM THE REGEX rather than from
# the defect. **A variable's name belongs to whoever wrote the leak.**
#
# `get()` and `index()` are the only ways out of an ordinal, and measured across
# the hub's production code every single `.get()` receiver is an ordinal type —
# `c.fold_layer`, `decl.ordinal`, `row.source_quantity`, and five one-letter
# bindings. So the accessor is exact where the name was a guess.
ACCESSOR = r"\.(?:get|index)\(\)"

RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "constructs a named address",
        re.compile(rf"\b{ADDRESS}(?:::new)?\(\s*\d"),
        "an address built from a literal is a NAME the hub chose — and this "
        "catches a match PATTERN too, since an arm per ordinal must name one",
    ),
    (
        "compares an address to a literal",
        re.compile(rf"{ACCESSOR}(?:\s+as\s+\w+)?\s*(?:==|!=|<=|>=|<|>)\s*-?\d"),
        "asking whether an address IS a particular one is reading its meaning",
    ),
    (
        "compares a literal to an address",
        re.compile(rf"-?\d+\s*(?:==|!=|<=|>=|<|>)\s*[\w.]*{ACCESSOR}"),
        "the same comparison written the other way round",
    ),
    (
        "matches on an address",
        re.compile(rf"\b(?:match|matches!)\s*\(?[\w.]*{ACCESSOR}"),
        "a match arm per ordinal is a vocabulary table -- spec shape 3, "
        "which the first version never implemented",
    ),
    (
        "reads an address through its tuple field",
        re.compile(r"\b(?!self\b)\w+\.0\s*(?:==|!=|<=|>=|<|>)\s*-?\d"),
        "`FoldLayer` has a public tuple field, so `l.0 == 3` reaches past the "
        "accessor. `self.0` is excluded: a type reading its OWN representation "
        "is not reaching into an address, and `self.0 == 0` ships today",
    ),
)


class Finding:
    def __init__(self, path: str, line: int, rule: str, text: str):
        self.path, self.line, self.rule, self.text = path, line, rule, text

    def __str__(self) -> str:
        return f"  {self.path}:{self.line}  {self.rule} — {self.text.strip()[:88]}"


def strip_test_blocks(src: str) -> str:
    """Blank every `#[cfg(test)]` item IN PLACE, by counting braces.

    In place, so line numbers survive. By counting, so a test module in the
    MIDDLE of a file does not blank the production code below it — cutting at
    the first occurrence would make every later line default-uncovered, which is
    NV-3 one level in and is a real shape: `ordinal.rs` and `rows.rs` both end
    with their tests, but nothing makes that a rule.
    """
    out = list(src)
    for m in re.finditer(r"#\[cfg\(test\)\]", src):
        i = src.find("{", m.end())
        if i < 0:
            continue
        depth, j = 0, i
        while j < len(src):
            if src[j] == "{":
                depth += 1
            elif src[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        for k in range(m.start(), min(j + 1, len(src))):
            if out[k] != "\n":
                out[k] = " "
    return "".join(out)


def _pragma_covers(raw: list[str], idx: int) -> bool:
    """True when the contiguous comment block above `idx` carries the pragma.

    `idx` is 0-based. The block ends at the first line above that is not a
    comment — so the reason may be as long as it needs to be, which is the whole
    difference from a fixed window (NV-6).
    """
    if PRAGMA in raw[idx]:
        return True
    k = idx - 1
    while k >= 0:
        stripped = raw[k].strip()
        if not stripped.startswith(("//", "/*", "*")):
            return False
        if PRAGMA in raw[k]:
            return True
        k -= 1
    return False


def scan_source(path: str, src: str) -> list[Finding]:
    """Scanned as ONE STRING, not line by line.

    A per-line scan cannot see a comparison wrapped across two lines, and a
    verifier found exactly that: `l.get()` on one line and `== 3` on the next
    was silent. `\s` spans newlines, so the whole file is one subject and
    the line number is computed from the match offset.
    """
    raw = src.split("\n")
    code = strip_comments(strip_test_blocks(src), False)
    seen: set[int] = set()
    out: list[Finding] = []
    for rule, rx, _why in RULES:
        for m in rx.finditer(code):
            i = code.count("\n", 0, m.start())
            if i in seen or _pragma_covers(raw, i):
                continue
            seen.add(i)
            out.append(Finding(path, i + 1, rule, raw[i]))
    return sorted(out, key=lambda f: f.line)


def _rust_files(staged_only: bool) -> list[Path]:
    tree = REPO / GUARDED_TREE
    if not staged_only:
        return sorted(tree.rglob("*.rs"))
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            cwd=REPO, capture_output=True, text=True, timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"hub-vocabulary-gate: cannot ask git what is staged ({e})")
        sys.exit(2)
    keep = []
    for rel in (out.stdout or "").splitlines():
        rel = rel.strip()
        if rel.startswith(GUARDED_TREE) and rel.endswith(".rs"):
            p = REPO / rel
            if p.exists():
                keep.append(p)
    return sorted(keep)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--staged", action="store_true", help="only staged files")
    ap.add_argument("--self-test", action="store_true", help="prove the rule bites")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    findings: list[Finding] = []
    files = _rust_files(args.staged)
    for p in files:
        rel = str(p.relative_to(REPO)).replace("\\", "/")
        findings.extend(scan_source(rel, p.read_text(encoding="utf-8", errors="replace")))

    if findings:
        print(f"hub-vocabulary-gate: {len(findings)} finding(s)\n")
        for f in findings:
            print(f)
        print(
            "\nThe hub ORDERS by an ordinal and never reads its meaning (actor-hub.md §4).\n"
            "A comparison against a named width constant is arithmetic and is silent here;\n"
            "a comparison against a LITERAL is a name, and a name belongs to the plugin that\n"
            f"authored it. A genuine exception carries `{PRAGMA} — <reason>` anywhere in the\n"
            "comment block directly above the line."
        )
        return 1

    print(
        f"hub-vocabulary-gate: OK — {len(files)} file(s) under {GUARDED_TREE}; "
        "the hub names no ordinal"
    )
    return 0


# ── non-vacuity ──────────────────────────────────────────────────────────────

def self_test() -> int:
    """Every rule is run against input that violates it AND against input that
    must stay silent. A gate with no cry-wolf case is half-tested, and the
    cry-wolf direction is the one that gets a gate switched off.
    """
    failures = 0

    def case(label: str, src: str, want: int) -> None:
        nonlocal failures
        got = len(scan_source("probe.rs", src))
        if got != want:
            failures += 1
            print(f"  FAIL {label}: {got} finding(s), want {want}")
        else:
            print(f"  ok   {label}")

    # ── one bite per rule ────────────────────────────────────────────────
    case("a literal fold layer is constructed",
         "fn f() { let l = FoldLayer(3); }", 1)
    case("a literal quantity ordinal is constructed",
         "fn f() { let q = QuantityOrdinal::new(5); }", 1)
    case("a layer is compared to a literal",
         "fn f() { if row.fold_layer.get() == 3 { } }", 1)
    case("a literal is compared to a layer",
         "fn f() { if 3 == l.get() { } }", 1)
    # **The shape the FIRST version of this gate missed**, and its own bite test
    # is what caught that. The binding is one letter, so a rule keyed on
    # variable names reported nothing; the accessor is what makes it visible.
    case("a ONE-LETTER binding is not an escape",
         "fn treasure_is_special(l: FoldLayer) -> bool {\n    l.get() == 40\n}", 1)
    case("an index accessor is the same leak",
         "fn f() { if o.index() == 3 { } }", 1)
    case("a cast does not hide it",
         "fn f() { if l.get() as usize == 3 { } }", 1)
    # A match ARM must name an ordinal to discriminate, so rule 1 reaches it.
    case("a match arm per ordinal is caught by the construction rule",
         "fn f() { match l { FoldLayer(40) => (), _ => () } }", 1)

    # ── the three COMPILING leaks a cold-start verifier planted ──────────
    case("a match on the accessor -- spec shape 3, never implemented",
         "fn f(l: FoldLayer) -> i64 { match l.get() { 3 => 100, _ => 0 } }", 1)
    case("a match on index() is the same leak",
         "fn f(q: QuantityOrdinal) -> &str { match q.index() { 0 => \"hp\", _ => \"?\" } }", 1)
    case("the public tuple field reaches past the accessor",
         "fn f(l: FoldLayer) -> bool { l.0 == 3 }", 1)
    case("a matches! on the accessor",
         "fn f(l: FoldLayer) -> bool { matches!(l.get(), 3) }", 1)
    # ...and a comparison WRAPPED across two lines, which a per-line scan
    # could not see at all.
    case("a wrapped comparison is not invisible",
         "fn f(l: FoldLayer) -> bool {\n    l.get()\n        == 3\n}", 1)

    # ── and one per SILENCE, which is the half that gets gates switched off ──
    case("a width constant is arithmetic, not a name",
         "fn f() { if raw >= MAX_PLUGINS { return None } }", 0)
    case("a declared width is arithmetic too, through the accessor",
         "fn f() { if ordinal.get() < MAX_DECLARED_QUANTITIES { } }", 0)
    # Every one of these ships in the hub today. If the rule reported any of
    # them it would block correct work, which is the direction that gets a gate
    # switched off rather than fixed.
    case("a divisor guard is arithmetic", "fn f() { if row.divisor == 0 { } }", 0)
    case("a bitmask emptiness test is arithmetic", "fn f() { if self.0 == 0 { } }", 0)
    case("a type reading its own representation is not a leak",
         "impl PluginSet { fn empty(&self) -> bool { self.0 == 0 } }", 0)
    case("a saturation probe is arithmetic", "fn f() { if factor != 0 { } }", 0)
    case("a doc comment may name an ordinal",
         "//! reality A's `QuantityOrdinal::new(3)` is `hp`\nfn f() { }", 0)
    case("a line comment may name one",
         "fn f() { // FoldLayer(3) is the treasure layer\n}", 0)
    case("a test module may name as many as it likes",
         "fn f() { }\n#[cfg(test)]\nmod tests {\n    fn t() { let l = FoldLayer(3); }\n}", 0)

    # **A test module in the MIDDLE must not blank what follows it.** Cutting at
    # the first `#[cfg(test)]` would make this pass for the wrong reason — the
    # leak below the module would be invisible, not absent.
    case("production code BELOW a test module is still scanned",
         "#[cfg(test)]\nmod tests {\n    fn t() { let a = FoldLayer(1); }\n}\n"
         "fn later() { let l = FoldLayer(3); }", 1)

    # ── the escape hatch, and its reason ─────────────────────────────────
    case("a pragma on the line exempts it",
         f"fn f() {{ let l = FoldLayer(3); }} // {PRAGMA} — the sentinel layer", 0)
    case("a pragma in the comment block above exempts it",
         f"// {PRAGMA} — the sentinel layer, and here is a long reason\n"
         "// that runs to a second line, and a third, because a reason\n"
         "// that does not fit is a reason that gets deleted\n"
         "fn f() { let l = FoldLayer(3); }", 0)
    case("a pragma separated by real code does NOT exempt",
         f"// {PRAGMA} — a reason for something else\n"
         "fn unrelated() { }\n"
         "fn f() { let l = FoldLayer(3); }", 1)

    # ── the scope is a directory, and it is not empty ────────────────────
    tree = REPO / GUARDED_TREE
    found = sorted(tree.rglob("*.rs"))
    if len(found) < 2:
        failures += 1
        print(f"  FAIL the guarded tree holds {len(found)} file(s) — the scope has no subject")
    else:
        print(f"  ok   the guarded tree is a directory holding {len(found)} file(s)")

    # ── and the shipped tree must be SILENT, or the gate cries wolf ──────
    shipped = []
    for p in found:
        rel = str(p.relative_to(REPO)).replace("\\", "/")
        shipped.extend(scan_source(rel, p.read_text(encoding="utf-8", errors="replace")))
    if shipped:
        failures += 1
        print(f"  FAIL the shipped hub reports {len(shipped)} finding(s) — cry wolf")
        for f in shipped:
            print(f"       {f}")
    else:
        print("  ok   the shipped hub reports nothing, so the rule does not cry wolf")

    if failures:
        print(f"\nhub-vocabulary-gate --self-test: {failures} rule(s) did not behave")
        return 1
    print("\nhub-vocabulary-gate --self-test: every rule bites, and none cries wolf")
    return 0


if __name__ == "__main__":
    sys.exit(main())
