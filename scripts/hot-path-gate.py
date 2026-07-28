#!/usr/bin/env python3
"""hot-path-gate — no string-keyed lookup on the island step path (IMP-D4).

THE BUG THIS EXISTS TO PREVENT
------------------------------
`QTY-A9` promises that aggregation order is **total and declared**, and `IMP-A3`
promises that extensibility is resolved COLD into a dense block so the hot path
never performs a lookup. Neither promise is enforced by anything today.

The failure is specific and a red team named the exact line it will arrive on.
`Q1` introduces author-declared quantities, which arrive as *names* in TOML:

    [[resources]]
    name = "qi"

The shortest path from that to a working `Q2` is a map on the actor:

    resources: BTreeMap<String, ResourceState>      // <-- the bug

…after which `evaluate_outcome`'s `standing` / `any_present` / `anyone_alive`
closures each do a string compare plus a tree descent, and `outcome_of` runs them
**five times per call**, on every landed Strike and every `EndTurn`. Determinism
SURVIVES — `BTreeMap` is ordered — so **no existing test reds**, and `QTY-A9`'s
letter is even satisfied, because it forbids map iteration in *aggregation*.

That is the whole reason this is a gate and not a code review item: the bug is
invisible to the test suite by construction.

WHAT IT CHECKS — and note WHERE the rule is drawn
-------------------------------------------------
Doc 26 (IMP-D4) anticipated the hard part and stated the requirement:

  > "`BTreeMap` on `CombatState.actors` is a keyed collection over entities, not
  >  a per-stat lookup — the gate targets stat/attribute access, and **this
  >  distinction must be encoded, not assumed**."

So the rule is on the **KEY TYPE**, never on the container:

  string-keyed-map     `HashMap`/`BTreeMap`/`HashSet`/`BTreeSet` whose key type
                       is a string (`String`, `&str`, `Cow<'_, str>`, `Arc<str>`,
                       `Box<str>`) inside a hot-path file.
  string-keyed-lookup  `.get("…")` / `.contains_key("…")` / `.entry("…")` /
                       `["…"]` — the READ, caught even when the declaration
                       lives in another file.

`BTreeMap<EntityId, Actor>` (`domain.rs:256`) **structurally cannot match**,
because `EntityId` is not a string type. That is the distinction, encoded.

SCOPE
-----
The files the island step actually runs through, plus the crates whose types it
reads by reference. `ruleset-loader` is deliberately absent — it is I/O and cold
by IMP-D2, and a name→ordinal map is exactly what it is *supposed* to hold.

ESCAPE HATCH — and the case `Q1` will hit on purpose
----------------------------------------------------
An inline reason on the line or in the comment block attached to it:

    // hot-path-gate: ok — <why this lookup cannot reach the step path>

**`Q1` is expected to trip this, and that is the design, not a bug in the
scope.** `QTY-A5` puts the name→ordinal assignment table INSIDE the hashed
ruleset, so `ruleset-core` will legitimately hold a `BTreeMap<String, u16>` for
*encoding* — resolved once at `create_reality`, never read in `apply`. That is
exactly the claim worth forcing someone to write down:

    // hot-path-gate: ok — the ordinal table is resolved at create_reality and
    // is never read during a step; `apply` indexes the dense array by ordinal.

Do NOT resolve it by removing `crates/ruleset-core/src/` from the scope below.
The whole point is that the *cold* direction has to be asserted rather than
assumed — `ruleset-core` is the one crate that is authored cold and read hot,
which is precisely where the mistake would hide.

SELF-TEST
---------
`--self-test` runs the checker against a deliberately broken fixture and fails if
it reports nothing — and against an entity-keyed fixture and fails if it reports
anything. A gate nobody has watched fire is a gate nobody knows is connected.

Usage:
    python scripts/hot-path-gate.py [PATH ...]
    python scripts/hot-path-gate.py --self-test
    python scripts/hot-path-gate.py --staged
"""

from __future__ import annotations

import argparse
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {"target", "node_modules", ".git", "__pycache__", ".claude"}

# ── TWO CHECKS, TWO SCOPES — and the polarity matters more than the breadth ──
#
# A self-review caught the first version scoping BOTH checks to an enumerated
# list of step files. That is **default-unguarded**: a NEW file — say the
# `resources.rs` that `Q2` will add — holds the string map, is not on the list,
# and the gate says nothing. The declaration is the unambiguous evidence and the
# place the real bug lands, so it gets the WIDE scope: whole directories, where
# a new file is guarded the day it is created and exempting it is a conscious
# act with a written reason.
#
# The READ check cannot have that scope. `serde_json::Value::get("tool")` is
# textually identical to `resources.get("qi")`, and the ingress boundary is full
# of the former — `admission.rs` translating an LLM proposal, `vocabulary.rs`
# mapping a tool call to a payload, `wire.rs` shaping JSON. Widening the read
# check would produce ~25 findings that are all correct code, and a gate that
# cries wolf gets switched off. So the read check stays on the step files, where
# a string literal has no legitimate reason to appear.

#: WIDE — where a string-keyed DECLARATION is a finding. Whole directories, so
#: new files default to guarded. `crates/game-rules/` is listed before it exists:
#: the gate must not need editing on the day the S2 extraction moves the laws.
DECL_SCOPE = (
    "services/commit-service/src/",
    "crates/sim-core/src/",
    # The resolved rules are read BY REFERENCE inside `apply`, so a string-keyed
    # collection on `Ruleset` is on the hot path even though the crate has no
    # I/O. `ruleset-loader` is the COLD half and is deliberately NOT here — a
    # name→ordinal map is exactly what a loader should hold.
    "crates/ruleset-core/src/",
    "crates/game-rules/",
)

#: NARROW — where a lookup BY STRING LITERAL is a finding: the step itself.
LOOKUP_SCOPE = (
    "services/commit-service/src/domain.rs",
    "services/commit-service/src/combat.rs",
    "services/commit-service/src/stats.rs",
    "crates/sim-core/src/island.rs",
    "crates/sim-core/src/domain.rs",
    "crates/game-rules/",
)

#: Union, for file selection.
HOT_PATH_PREFIXES = DECL_SCOPE + LOOKUP_SCOPE

#: A string-ish key type, spelled every way Rust allows.
_STR_KEY = r"""(?:
      &\s*(?:'[a-zA-Z_][a-zA-Z0-9_]*\s+)?str
    | String
    | str
    | Cow\s*<[^<>]*\bstr\b[^<>]*>
    | Arc\s*<\s*str\s*>
    | Box\s*<\s*str\s*>
)"""

#: `HashMap<String, _>` / `BTreeMap<&str, _>` / `HashSet<String>` / …
STRING_KEYED = re.compile(
    r"\b(?:Hash|BTree)(?:Map|Set)\s*<\s*" + _STR_KEY + r"\s*[,>]",
    re.VERBOSE,
)

#: The READ. Catches the case where the declaration lives elsewhere.
STRING_LOOKUP = re.compile(
    r"""\.(?:get|get_mut|contains_key|remove|entry|insert)\s*\(\s*&?\s*"   # .get("qi")
      | \[\s*"                                                            # map["qi"]
    """,
    re.VERBOSE,
)

PRAGMA = re.compile(r"hot-path-gate:\s*ok\b")


def in_scope(rel: str) -> bool:
    return rel.startswith(HOT_PATH_PREFIXES)


def is_test_file(rel: str) -> bool:
    return (
        "/tests/" in rel
        or rel.endswith("_test.rs")
        or rel.endswith("/tests.rs")
        or "/benches/" in rel
    )


def strip_comments(src: str) -> str:
    """Blank out `//` and `/* */`, KEEP string literals.

    Strings are kept because half of what this gate looks for — `.get("qi")` —
    *is* a string literal. Comments are stripped because a lint that fires on
    its own documentation gets switched off; that is how `design-lint`'s count
    check spent its entire first life.
    """
    out = list(src)
    i, n = 0, len(src)
    while i < n:
        if src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = " "
            i = j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
        else:
            i += 1
    return "".join(out)


def pragma_near(lines: list[str], line_no: int) -> bool:
    """A reason on this line, or anywhere in the comment block attached to it.

    Walks the contiguous block upward rather than guessing a fixed distance —
    `zero-digest-gate` and `closed-set-gate` both shipped a two-line window that
    silently did nothing, because the real justification was eleven lines up.
    """
    idx = line_no - 1
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
    if not in_scope(rel) or is_test_file(rel):
        return []
    clean = strip_comments(src)
    lines = src.split("\n")
    findings: list[tuple[str, int, str]] = []

    for m in (STRING_KEYED.finditer(clean) if rel.startswith(DECL_SCOPE) else ()):
        line_no = clean.count("\n", 0, m.start()) + 1
        if pragma_near(lines, line_no):
            continue
        findings.append((
            rel, line_no,
            "string-keyed-map: a map/set keyed by a STRING on the island step "
            "path. IMP-A3 says extensibility resolves COLD into a dense block; a "
            "name-keyed collection here puts the lookup back inside `apply`. Use "
            "an interned ordinal (QTY-A5) and index an array. Note this rule is "
            "on the KEY TYPE — `BTreeMap<EntityId, Actor>` is fine and always was.",
        ))

    for m in (STRING_LOOKUP.finditer(clean) if rel.startswith(LOOKUP_SCOPE) else ()):
        line_no = clean.count("\n", 0, m.start()) + 1
        if pragma_near(lines, line_no):
            continue
        findings.append((
            rel, line_no,
            "string-keyed-lookup: a lookup by string literal on the step path. "
            "Even if the collection is declared elsewhere, THIS is the read that "
            "costs a hash/descent per call — and `outcome_of` runs its closures "
            "five times per invocation. Resolve the name to an ordinal once, cold.",
        ))
    return findings


def walk(roots: list[str]) -> list[str]:
    files = []
    for root in roots:
        base = root if os.path.isabs(root) else os.path.join(REPO_ROOT, root)
        if os.path.isfile(base):
            files.append(base)
            continue
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                if fn.endswith(".rs"):
                    files.append(os.path.join(dirpath, fn))
    return files


BROKEN = """
pub struct Actor {
    pub resources: BTreeMap<String, ResourceState>,
}
fn outcome_of(state: &CombatState) -> Option<Outcome> {
    let hp = a.resources.get("hp")?;
    let qi = a.resources["qi"];
}
"""

#: The case doc 26 warned must NOT trip: entity-keyed, and an ordinal read.
CLEAN = """
pub struct CombatState {
    pub actors: BTreeMap<EntityId, Actor>,
}
fn outcome_of(state: &CombatState) -> Option<Outcome> {
    let a = state.actors.get(&id)?;
    let hp = a.resources[rules.vital_ordinal as usize].current;
    // A comment mentioning BTreeMap<String, Foo> and .get("qi") must be silent.
}
"""

PRAGMA_FIXTURE = """
pub struct Loader {
    // hot-path-gate: ok — resolved once at create_reality, never read in `apply`
    pub by_name: BTreeMap<String, u16>,
}
"""


def self_test() -> int:
    ok = True
    hot = "services/commit-service/src/domain.rs"

    bad = check_source(hot, BROKEN)
    if not any("string-keyed-map" in f[2] for f in bad):
        print("SELF-TEST FAIL: BTreeMap<String, _> in a hot-path file was not reported")
        ok = False
    if sum(1 for f in bad if "string-keyed-lookup" in f[2]) != 2:
        print('SELF-TEST FAIL: .get("hp") and ["qi"] were not both reported')
        ok = False

    # THE distinction doc 26 demanded be encoded. If this ever reports, the gate
    # has become the naive grep it was written not to be.
    good = check_source(hot, CLEAN)
    if good:
        print(f"SELF-TEST FAIL: an entity-keyed file was reported: {good}")
        ok = False

    if check_source(hot, PRAGMA_FIXTURE):
        print("SELF-TEST FAIL: a pragma'd line was reported")
        ok = False

    # Scope must bite too, or the gate is a repo-wide grep wearing a scope.
    if check_source("crates/ruleset-loader/src/patch.rs", BROKEN):
        print("SELF-TEST FAIL: the COLD loader was reported — scope is not applied")
        ok = False

    # ── The two-scope split, both directions ────────────────────────────────
    #
    # A file inside DECL_SCOPE but outside LOOKUP_SCOPE — e.g. the `resources.rs`
    # that Q2 will add, or today's `wire.rs` — must have its DECLARATION caught
    # (that is the polarity fix: new files are guarded the day they appear) and
    # its string LOOKUPS ignored (that is the noise fix: `serde_json::Value::get`
    # is textually identical to a stat lookup, and the ingress boundary is full
    # of it — widening the read check produced ~25 correct-code findings, and a
    # gate that cries wolf gets switched off).
    wide = "services/commit-service/src/resources.rs"
    wf = check_source(wide, BROKEN)
    if not any("string-keyed-map" in f[2] for f in wf):
        print("SELF-TEST FAIL: a NEW file in the wide scope was not guarded — "
              "the gate is default-unguarded again")
        ok = False
    if any("string-keyed-lookup" in f[2] for f in wf):
        print("SELF-TEST FAIL: the read check leaked outside LOOKUP_SCOPE — "
              "every `serde_json::Value::get(\"x\")` at the ingress boundary "
              "will now be a finding")
        ok = False

    if ok:
        print("self-test: the gate bites (1 string-keyed map + 2 string lookups "
              "detected; entity-keyed maps, ordinal reads, comments, pragmas and "
              "the cold loader all silent)")
        return 0
    print("  detail:", [f[2][:48] for f in bad])
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="*", default=None)
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
            if p.strip().endswith(".rs")
            and os.path.exists(os.path.join(REPO_ROOT, p.strip()))
        ]
    else:
        files = walk(args.paths or ["crates", "services"])

    findings: list[tuple[str, int, str]] = []
    scanned = 0
    for path in files:
        rel = os.path.relpath(path, REPO_ROOT).replace("\\", "/")
        if not in_scope(rel):
            continue
        scanned += 1
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                src = fh.read()
        except OSError:
            continue
        findings.extend(check_source(rel, src))

    print(f"hot-path-gate: scanned {scanned} hot-path file(s)")
    for rel, line, msg in findings:
        print(f"{rel}:{line}: [hot-path] {msg}")

    if findings:
        print(f"\nhot-path-gate: FAIL — {len(findings)} finding(s)")
        print("A string-keyed lookup inside the island step defeats IMP-A3 and "
              "QTY-A9, and no test will catch it — BTreeMap is ordered, so "
              "determinism survives and the suite stays green.")
        print("Fix by interning to an ordinal, or add: `hot-path-gate: ok — <why>`.")
        return 1
    print("hot-path-gate: OK — no findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
