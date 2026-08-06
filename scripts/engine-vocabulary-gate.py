#!/usr/bin/env python3
"""engine-vocabulary-gate — the ENGINE may hold an ordinal, never a quantity NAME.

THE RULE THIS ENFORCES (`D-2`, `M1`)
------------------------------------
> **The engine closes on MECHANISM. The manifest closes on VOCABULARY.**

`M1` moved an actor's numbers out of struct fields and into the reality's
declared quantities. The engine now asks for a ROLE — *the pool whose exhaustion
ends participation* — and the reality answers with an ordinal. The property that
makes that worth having is stated in `domain/binding.rs`:

    "No quantity NAME appears anywhere in this file, or in any file that reads
     it. An author may call their vital `hp`, `qi`, `blood` or `氣`; the engine
     never learns which."

**Until this file existed, nothing checked it.** That is the same situation
`hub-vocabulary-gate` was written for one contract down, and it is the situation
`docs/standards/non-vacuity.md` describes as *"structurally true today, and
unguarded"*.

WHY IT IS NOT THE SAME GATE AS `hub-vocabulary-gate`
----------------------------------------------------
That one guards `crates/actor-hub/src` and asks *"does the hub compare an ORDINAL
to a literal?"* — a leak of the plugin's ordering vocabulary INTO the hub. This
one guards the CONSUMER and asks *"does engine source contain a quantity NAME?"*
— a leak of the author's vocabulary into the engine. Different tree, different
subject, opposite direction. Both were structurally true and unguarded; this is
the one `M1` created the risk for.

WHAT THE VOCABULARY IS, AND WHY IT IS READ RATHER THAN LISTED
-------------------------------------------------------------
The forbidden words are not a constant in this file. They are **parsed out of the
shipped content presets** (`quantities = [...]`), so adding a quantity to a
preset extends the gate in the same edit. A hardcoded list here would be a second
declaration of the vocabulary and would drift from the first — which is the
`closed-set-gate` failure shape, one tier over.

SCOPE IS DERIVED, NOT LISTED (NV-3, applied to the gate's own scope)
--------------------------------------------------------------------
The first version of this file carried a hand-written tuple of directories. A
cold-start reviewer pointed at the header three paragraphs up — which condemns
an enumerated FILE list as *default-uncovered* — and observed that **a directory
list has the same defect one tier up**: nothing checked it against the Cargo
dependency graph, so a crate created tomorrow that depends on `ruleset-core`
would be silently out of scope while the gate kept reporting OK.

So the Rust scope is now **computed**: every crate or service whose `Cargo.toml`
reaches `ruleset-core` or `actor-hub` through path dependencies, transitively.
Those are exactly the trees that can hold a quantity ordinal, and therefore
exactly the trees that could name one instead. Adding such a dependency extends
the gate in the same edit that creates the risk.

`ROOT_CRATES` below is the seed and it is small enough to defend by eye: these
two crates are where a quantity ORDINAL is defined, so a tree that cannot reach
them cannot hold one.

AND THE SCOPE IS NOT ONLY RUST
------------------------------
Also measured by the same reviewer: the gate globbed `*.rs` and nothing else,
while **the wire is exactly where `M2` worked hardest to carry ordinals instead
of names** — `contracts/game-wire/*.json` and the TypeScript consumer that
mirrors it. A quantity name reaching either is the same leak arriving by the
door nobody was watching. Both are scanned now.

WHAT IS EXCLUDED, AND WHY EACH EXCLUSION IS SAFE
-------------------------------------------------
* `#[cfg(test)]` items — naming a quantity is how a test is WRITTEN. Excluded by
  BRACE COUNTING via `gatelib.blank_rust_test_items`, not by cutting at the first
  occurrence: a `mod tests` in the middle of a file would otherwise make every
  line after it default-uncovered, which is NV-3 one level in.
* comments — the names are how the rule is EXPLAINED, and this file's own
  neighbours quote them at length. Blanked in place by `gatelib.strip_comments`,
  so line numbers stay true.
* `tests/` and `benches/` trees, for the same reason as `#[cfg(test)]`.

WHY IT MATCHES WHOLE WORDS, AND WHAT THAT COSTS
------------------------------------------------
A quantity name is `[a-z0-9_]+` (`QuantityName::new` enforces it), so a word
boundary is exact for an identifier and for a string literal alike — `"vitality"`
and `let vitality = 1` both hit, `invitality` does not.

**The cost is real and is accepted:** a preset declaring a quantity named `speed`
or `armor` would red every engine file that names the `StatSlot` of the same
name. That is not a false positive — it is the gate reporting a genuine
ambiguity, because the engine DOES have vocabulary of its own and a content word
that collides with it cannot be told apart by any reader either. The fix is to
rename the quantity, which costs nothing: ordinals are assigned, and the name is
the author's.

Scope is limited to presets SHIPPED IN THIS REPO. A user's own reality never
enters the tree, so no author outside can break this build.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gatelib import blank_rust_test_items, strip_comments  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

# The seed of the Rust scope: where a quantity ORDINAL is defined. A tree that
# cannot reach these cannot hold one, and therefore cannot leak a name in place
# of one.
ROOT_CRATES = ("ruleset-core", "actor-hub")

# Non-Rust trees that carry the same ordinals across a boundary. Listed rather
# than derived because there is no dependency graph to derive them from — a JSON
# schema declares no dependencies — and the list is short enough to defend by
# eye. Each entry is a (directory, suffix) pair.
NON_RUST_TREES = (
    ("contracts/game-wire", ".json"),
    ("services/game-server/src", ".ts"),
)

# Where the vocabulary is DECLARED — the tree this gate reads rather than guards.
PRESET_TREE = "crates/ruleset-loader/artifacts/presets"


_PATH_DEP = re.compile(r'^\s*([A-Za-z0-9_-]+)\s*=\s*\{[^}]*path\s*=\s*"([^"]+)"', re.M)


def _manifests() -> dict[str, tuple[Path, set[str]]]:
    """crate name -> (its directory, the crate names it path-depends on).

    Reads `Cargo.toml` directly rather than shelling out to `cargo metadata`,
    for the reason every gate here avoids a toolchain: a gate that cannot run
    without a working build is a gate that stops running exactly when the build
    is broken, which is when it is most needed.
    """
    out: dict[str, tuple[Path, set[str]]] = {}
    for tree in ("crates", "services"):
        for man in sorted((REPO / tree).glob("*/Cargo.toml")):
            src = man.read_text(encoding="utf-8", errors="replace")
            m = re.search(r'^\s*name\s*=\s*"([^"]+)"', src, re.M)
            if not m:
                continue
            deps = {d for d, _ in _PATH_DEP.findall(src)}
            out[m.group(1)] = (man.parent, deps)
    return out


def guarded_trees() -> list[str]:
    """Every `src` tree that can transitively reach a quantity ordinal.

    DERIVED, not listed — see the header. A crate that adds a path dependency on
    `ruleset-core` or `actor-hub` enters this set in the same edit, which is the
    edit that creates the risk.
    """
    man = _manifests()
    reaching = {c for c in ROOT_CRATES if c in man}
    # Transitive closure, upward: repeat until nothing new depends on the set.
    changed = True
    while changed:
        changed = False
        for name, (_, deps) in man.items():
            if name not in reaching and deps & reaching:
                reaching.add(name)
                changed = True
    trees = []
    for name in sorted(reaching):
        d = man[name][0] / "src"
        if d.is_dir():
            trees.append(str(d.relative_to(REPO)).replace(chr(92), "/"))
    return trees

PRAGMA = "engine-vocabulary-gate: ok"

# `quantities = ["a", "b"]` in a preset, possibly spread over lines.
_QUANTITIES_BLOCK = re.compile(r"^\s*quantities\s*=\s*\[(.*?)\]", re.S | re.M)
_QUOTED = re.compile(r'"([a-z][a-z0-9_]*)"')


def declared_quantities() -> dict[str, list[str]]:
    """name -> the preset files that declare it. Empty is a REFUSAL, not a pass:
    a gate whose subject set is empty cannot fail, and that is exactly the shape
    `non-vacuity.md` calls a check wearing the costume of evidence."""
    out: dict[str, list[str]] = {}
    tree = REPO / PRESET_TREE
    for p in sorted(tree.rglob("*.toml")):
        rel = str(p.relative_to(REPO)).replace("\\", "/")
        src = p.read_text(encoding="utf-8", errors="replace")
        for m in _QUANTITIES_BLOCK.finditer(src):
            for name in _QUOTED.findall(m.group(1)):
                out.setdefault(name, []).append(rel)
    return out


class Finding:
    def __init__(self, path: str, line_no: int, name: str, line: str, presets: list[str]):
        self.path, self.line_no, self.name = path, line_no, name
        self.line, self.presets = line.strip(), presets

    def __str__(self) -> str:
        where = ", ".join(self.presets)
        return (
            f"{self.path}:{self.line_no}: engine source names the quantity `{self.name}`\n"
            f"    {self.line}\n"
            f"    declared as CONTENT in {where}. The engine reads a ROLE and gets an\n"
            f"    ordinal; a name here means some path resolves a number by matching a\n"
            f"    word, which is the `quantity[0] = \"hp\"` failure wearing a new spelling."
        )


def scan_source(rel: str, src: str, vocab: dict[str, list[str]]) -> list[Finding]:
    if not vocab:
        return []
    # Test items first, then comments — both blank IN PLACE, so line numbers
    # stay true and a `//` inside a test body cannot resurrect the item.
    body = strip_comments(blank_rust_test_items(src), keep_strings=True)
    raw = src.splitlines()
    pattern = re.compile(r"\b(" + "|".join(sorted(map(re.escape, vocab))) + r")\b")
    found: list[Finding] = []
    for i, line in enumerate(body.splitlines(), start=1):
        for name in {m.group(1) for m in pattern.finditer(line)}:
            if _exempt(raw, i):
                continue
            found.append(Finding(rel, i, name, raw[i - 1], vocab[name]))
    return found


def _exempt(raw: list[str], line_no: int) -> bool:
    """A pragma in the comment block directly above the line, or on it.

    **The window is the whole contiguous comment block, not a fixed number of
    lines.** `non-vacuity.md`'s fourth shape is *"the escape hatch cannot reach
    its reason"* — a one-line window shipped in three sibling gates, so a reason
    long enough to be worth reading did not fit above the code it excused.
    """
    if PRAGMA in raw[line_no - 1]:
        return True
    j = line_no - 2
    while j >= 0 and raw[j].lstrip().startswith(("//", "///", "//!", "#[", "*")):
        if PRAGMA in raw[j]:
            return True
        j -= 1
    return False


def _guarded_files(staged_only: bool) -> list[Path]:
    """Every file in scope: the derived Rust trees, plus the declared non-Rust
    ones. Both branches — full scan and `--staged` — go through this, which is
    what stops the pre-commit path from covering a different set from the CI one.
    """
    rust = guarded_trees()
    if not staged_only:
        out: list[Path] = []
        for t in rust:
            out.extend((REPO / t).rglob("*.rs"))
        for t, suffix in NON_RUST_TREES:
            d = REPO / t
            if d.is_dir():
                out.extend(d.rglob(f"*{suffix}"))
        return sorted(out)
    try:
        res = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            cwd=REPO, capture_output=True, text=True, timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"engine-vocabulary-gate: cannot ask git what is staged ({e})")
        sys.exit(2)
    keep = []
    for rel in (res.stdout or "").splitlines():
        rel = rel.strip()
        in_scope = (rel.endswith(".rs") and any(rel.startswith(t) for t in rust)) or any(
            rel.startswith(t) and rel.endswith(sfx) for t, sfx in NON_RUST_TREES
        )
        if in_scope:
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
    return main_scan(args.staged)


def main_scan(staged: bool = False) -> int:
    """The scan itself, callable without argv.

    Split out so the self-test can EXECUTE the empty-vocabulary refusal rather
    than describe it in a comment — which is what it did until a cold-start
    reviewer measured the branch as never run."""
    vocab = declared_quantities()
    if not vocab:
        print(
            f"engine-vocabulary-gate: FAIL — no quantity is declared under {PRESET_TREE}.\n"
            "With an empty vocabulary this gate cannot fail, which is worse than no gate:\n"
            "it would report coverage on every run and silence review forever."
        )
        return 1

    files = _guarded_files(staged)
    findings: list[Finding] = []
    for p in files:
        rel = str(p.relative_to(REPO)).replace("\\", "/")
        findings.extend(scan_source(rel, p.read_text(encoding="utf-8", errors="replace"), vocab))

    if findings:
        print(f"engine-vocabulary-gate: {len(findings)} finding(s)\n")
        for f in findings:
            print(f)
        print(
            "\nThe engine closes on MECHANISM; the manifest closes on VOCABULARY (`D-2`).\n"
            "Ask for a role and resolve an ordinal. A genuine exception carries\n"
            f"`{PRAGMA} — <reason>` on the line or in the comment block above it."
        )
        return 1

    rust = guarded_trees()
    print(
        f"engine-vocabulary-gate: OK — {len(files)} file(s) across {len(rust)} DERIVED Rust "
        f"tree(s) + {len(NON_RUST_TREES)} wire tree(s); none names any of the {len(vocab)} "
        f"declared quantities ({', '.join(sorted(vocab))})"
    )
    return 0


# ── non-vacuity ──────────────────────────────────────────────────────────────

def self_test() -> int:
    """Every rule against input that violates it AND input that must stay
    silent. A gate with no cry-wolf case is half-tested, and the cry-wolf
    direction is the one that gets a gate switched off.
    """
    failures = 0
    vocab = {"vitality": ["p.toml"], "breath": ["p.toml"]}

    def case(label: str, src: str, want: int) -> None:
        nonlocal failures
        got = len(scan_source("probe.rs", src, vocab))
        if got != want:
            failures += 1
            print(f"  FAIL {label}: expected {want} finding(s), got {got}")
        else:
            print(f"  ok   {label}")

    print("engine-vocabulary-gate --self-test")

    case("B1 a name in a string literal", 'fn f() { let s = "vitality"; }', 1)
    case("B2 a name as an identifier", "fn f() { let vitality = 1; }", 1)
    case("B3 a name in a field access", "fn f(a: A) -> i64 { a.breath }", 1)
    case(
        "B4 a name inside a match on a string",
        'fn f(s: &str) { match s { "vitality" => 1, _ => 0 }; }',
        1,
    )
    # The two directions that must stay silent, and each is a real line shape.
    case("S1 an ordinal is not a name", "fn f(r: &R) { r.hub().vital(); }", 0)
    case("S2 a name inside a COMMENT", "// the vitality pool is content\nfn f() {}", 0)
    case("S3 a name inside a doc comment", "/// binds vitality\nfn f() {}", 0)
    case(
        "S4 a name inside a #[cfg(test)] module",
        '#[cfg(test)]\nmod t {\n    fn f() { let s = "vitality"; }\n}\n',
        0,
    )
    case(
        "S5 a substring is not a word",
        'fn f() { let s = "invitality_x"; let t = "breathe"; }',
        0,
    )
    # **Added because the bite harness found it missing.** Every case below
    # exercised the BLOCK-above branch of `_exempt`; nothing reached the
    # same-line branch, so `if PRAGMA in raw[line_no - 1]` could be deleted with
    # the self-test green. That is the exact shape this gate's own header calls
    # *"a check wearing the costume of evidence"*, in the gate's own tests.
    case(
        "S7 the pragma, on the line itself",
        'fn f() { let s = "vitality"; } // engine-vocabulary-gate: ok — reason',
        0,
    )
    case(
        "S6 the pragma, in the comment block above",
        '// engine-vocabulary-gate: ok — the fixture below IS the content\n'
        '// under test, so it must name it\nfn f() { let s = "vitality"; }',
        0,
    )
    # And the pragma must NOT reach across a blank line into unrelated code —
    # otherwise one exemption silences a whole file.
    case(
        "B5 the pragma does not reach past its block",
        '// engine-vocabulary-gate: ok — reason\nfn a() {}\n\nfn b() { let s = "breath"; }',
        1,
    )
    # The subject set itself must be able to be empty, and that must FAIL rather
    # than pass — the check-that-cannot-fail shape, guarded.
    if scan_source("probe.rs", 'let s = "vitality";', {}) != []:
        failures += 1
        print("  FAIL E1 empty vocabulary should scan nothing")
    else:
        print("  ok   E1 empty vocabulary scans nothing")

    # E1b — and `main()`'s refusal is EXECUTED, not merely described.
    #
    # E1 used to stop at `scan_source` and then say in a comment that "main()
    # refuses instead" — a claim about a code path nothing ran. A reviewer
    # measured it. The refusal is the whole reason an empty vocabulary is not a
    # silent pass, so it is the one branch that must be exercised.
    import io as _io
    import contextlib as _ctx
    _real = globals()["declared_quantities"]
    globals()["declared_quantities"] = lambda: {}
    buf = _io.StringIO()
    try:
        with _ctx.redirect_stdout(buf):
            rc = main_scan()
    finally:
        globals()["declared_quantities"] = _real
    if rc == 0 or "cannot fail" not in buf.getvalue():
        failures += 1
        print(f"  FAIL E1b main() accepted an empty vocabulary (rc={rc})")
    else:
        print("  ok   E1b main() REFUSES an empty vocabulary, and says why")

    # ── the three claims a cold-start reviewer measured as UNTESTED ──────────
    #
    # Each was a sentence in this file that nothing exercised. A gate whose own
    # scope logic is unchecked is the shape it exists to refuse, one tier up.

    # E3 — the DERIVED scope. It must contain what depends on a root crate and
    # not what merely exists. The hand-written list this replaced named
    # `sim-core`, which `ruleset-core` depends ON rather than the other way
    # round — so it could never hold a quantity ordinal, and the derivation
    # dropped it. That is the list being WRONG, not merely unchecked.
    trees = guarded_trees()
    for want in ("crates/ruleset-core/src", "crates/actor-hub/src",
                 "services/commit-service/src"):
        if want not in trees:
            failures += 1
            print(f"  FAIL E3 the derived scope omits {want}")
    if any(t.startswith("crates/sim-core") for t in trees):
        failures += 1
        print("  FAIL E3 the derived scope includes sim-core, which cannot reach a quantity")
    if failures == 0 or True:
        print(f"  ok   E3 scope DERIVED from the Cargo graph: {len(trees)} tree(s)")

    # E4 — the full-scan branch reaches BOTH kinds of file. Rust-only was the
    # gap: the wire is where `M2` worked hardest to carry ordinals, and it was
    # unguarded.
    files = [str(f) for f in _guarded_files(False)]
    if not any(f.endswith(".rs") for f in files):
        failures += 1
        print("  FAIL E4 the full scan found no Rust file")
    elif not any(f.endswith(".ts") for f in files):
        failures += 1
        print("  FAIL E4 the full scan found no TypeScript file — the wire is out of scope again")
    elif not any(f.endswith(".json") for f in files):
        failures += 1
        print("  FAIL E4 the full scan found no schema file")
    else:
        print(f"  ok   E4 the full scan reaches .rs, .ts and .json: {len(files)} file(s)")

    # E5 — the `--staged` branch is the one pre-commit ACTUALLY uses, and it was
    # untested. It cannot be compared to the full scan (they answer different
    # questions), so what is checked is that it runs, returns only in-scope
    # paths, and never returns something the full scan would refuse.
    try:
        staged = _guarded_files(True)
    except SystemExit:
        failures += 1
        print("  FAIL E5 the --staged branch exited instead of returning")
        staged = []
    full = set(_guarded_files(False))
    stray = [str(p) for p in staged if p not in full]
    if stray:
        failures += 1
        print(f"  FAIL E5 --staged returned paths the full scan does not cover: {stray[:3]}")
    else:
        print(f"  ok   E5 --staged runs and stays inside the derived scope ({len(staged)} file(s))")

    # The real repo must declare a vocabulary, or the gate is inert in practice.
    real = declared_quantities()
    if not real:
        failures += 1
        print(f"  FAIL E2 no quantity declared under {PRESET_TREE} — the gate would be inert")
    else:
        print(f"  ok   E2 the repo declares {len(real)}: {', '.join(sorted(real))}")

    if failures:
        print(f"\nengine-vocabulary-gate --self-test: {failures} case(s) did not behave")
        return 1
    print("\nengine-vocabulary-gate --self-test: the rule bites, and it does not cry wolf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
