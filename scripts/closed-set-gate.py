#!/usr/bin/env python3
"""closed-set-gate — a closed enum and its companion list must not drift apart.

THE BUG THIS EXISTS TO PREVENT
------------------------------
`ModifierSource` is a closed 6-variant enum with a hand-written companion array
`ALL`, and `resolve_block` iterated `ALL`. The array listed THREE of the six. So
`Base`, `Archetype` and `Lex` flat modifiers were constructible, accepted by the
API, and **silently discarded** — a world rule worked or did nothing depending on
which operator the author happened to pick. It passed all 76 tests, it was
deterministic, so replay agreed with itself and the conformance suite stayed
green. Nothing was observable. (XST-D7, fixed 2026-07-28.)

WHY A GATE AND NOT A LANGUAGE FEATURE
-------------------------------------
Rust can force you to HANDLE every variant (a `match` with no wildcard arm). It
cannot force an ARRAY to CONTAIN every variant, and `std::mem::variant_count` is
unstable. Two constructions look like they close this and do not:

  * a successor chain `fn next(self) -> Option<Self>` — an exhaustive match makes
    a variant HANDLED, never REACHED, so a variant nothing points at is skipped;
  * tying the array length to a named `COUNT` — real, and it converts a one-line
    slip into a compile error, but forgetting BOTH still compiles.

So this is checked outside the compiler, once, for every closed set in the tree —
rather than per-enum, by discipline. `StatSlot`, `EffectOp`, `StatusFlag`,
`DiscardReason` and `SeedRole` are all the same shape.

WHAT IT CHECKS
--------------
For every `const NAME: [EnumType; _] = [ ... ];` whose `EnumType` is an enum
defined somewhere in the scanned tree:

  missing    — a variant the enum declares and the list omits   (the silent-drop)
  unknown    — a name in the list that the enum does not declare (a stale entry)
  duplicate  — the same variant listed twice

It deliberately does NOT flag an enum that has no companion list: not every
closed set needs one, and inventing that opinion would make the gate noisy and
therefore ignored.

ESCAPE HATCH
------------
A genuinely partial list carries an inline reason, on the const line or the line
above:

    // closed-set-gate: ok — presentation order only; Deprecated is intentionally absent
    pub const MENU: [Kind; 3] = [ ... ];

SELF-TEST
---------
`--self-test` runs the checker against a deliberately broken fixture and fails if
it reports nothing. A gate nobody has watched fire is a gate nobody knows is
connected.

Usage:
    python scripts/closed-set-gate.py [PATH ...]     # default: crates/ services/
    python scripts/closed-set-gate.py --self-test
"""

from __future__ import annotations

import argparse
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ROOTS = ["crates", "services"]
SKIP_DIRS = {"target", "node_modules", ".git", "dist", "build", ".claude"}

PRAGMA = re.compile(r"closed-set-gate:\s*ok\b")
ENUM_HEAD = re.compile(r"\benum\s+([A-Za-z_]\w*)\s*(?:<[^>{]*>)?\s*\{")
# `const NAME: [Type; ...] = [`  — the length expression is irrelevant here; the
# compiler already checks it against the literal's arity.
LIST_HEAD = re.compile(
    r"\bconst\s+([A-Z_][A-Z0-9_]*)\s*:\s*&?\s*\[\s*([A-Za-z_]\w*)\s*;[^\]]*\]\s*=\s*&?\s*\["
)


def strip_comments(src: str) -> str:
    """Blank out // and /* */ and string literals, preserving offsets and lines."""
    out = list(src)
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == '"':
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == '"':
                    break
                j += 1
            for k in range(i, min(j + 1, n)):
                if out[k] != "\n":
                    out[k] = " "
            i = j + 1
        elif src.startswith("//", i):
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


def match_block(src: str, open_idx: int, opener: str, closer: str) -> int:
    """Index just past the balanced closer for the delimiter at `open_idx`."""
    depth = 0
    for i in range(open_idx, len(src)):
        if src[i] == opener:
            depth += 1
        elif src[i] == closer:
            depth -= 1
            if depth == 0:
                return i
    return -1


def parse_enums(clean: str) -> dict[str, list[str]]:
    """enum name -> variant names, in declaration order."""
    enums: dict[str, list[str]] = {}
    for m in ENUM_HEAD.finditer(clean):
        name = m.group(1)
        open_idx = clean.index("{", m.end() - 1)
        close_idx = match_block(clean, open_idx, "{", "}")
        if close_idx < 0:
            continue
        body = clean[open_idx + 1 : close_idx]

        variants: list[str] = []
        depth = 0
        item = []
        for ch in body:
            if ch in "{([":
                depth += 1
            elif ch in "})]":
                depth -= 1
            if depth == 0 and ch == ",":
                variants.append("".join(item))
                item = []
            else:
                item.append(ch)
        variants.append("".join(item))

        names = []
        for raw in variants:
            raw = re.sub(r"#\[[^\]]*\]", " ", raw).strip()
            if not raw:
                continue
            vm = re.match(r"^([A-Za-z_]\w*)", raw)
            if vm:
                names.append(vm.group(1))
        if names:
            enums[name] = names
    return enums


def parse_lists(clean: str) -> list[tuple[str, str, list[str], int]]:
    """(const name, element type, listed identifiers, line number)."""
    found = []
    for m in LIST_HEAD.finditer(clean):
        const_name, ty = m.group(1), m.group(2)
        open_idx = clean.rindex("[", m.start(), m.end())
        close_idx = match_block(clean, open_idx, "[", "]")
        if close_idx < 0:
            continue
        body = clean[open_idx + 1 : close_idx]
        entries = re.findall(r"(?:[A-Za-z_]\w*\s*::\s*)*([A-Za-z_]\w*)", body)
        line = clean.count("\n", 0, m.start()) + 1
        found.append((const_name, ty, entries, line))
    return found


def pragma_near(lines: list[str], line_no: int) -> bool:
    """A reason on the const line, or anywhere in the doc block attached to it.

    Scanning a fixed number of lines above was the first implementation and it
    was WRONG in a way that produced a vacuous test: a four-line justification
    sat five lines above its `const`, outside a two-line window, so the pragma
    silently did nothing — and the bite-test that "proved" the pragma worked
    reported a finding both with and without it. A reason belongs in the item's
    own documentation, so walk the contiguous doc/attribute block upward
    instead of guessing a distance.
    """
    idx = line_no - 1  # to 0-based
    if 0 <= idx < len(lines) and PRAGMA.search(lines[idx]):
        return True
    k = idx - 1
    while k >= 0:
        stripped = lines[k].strip()
        if stripped.startswith(("///", "//!", "//", "#[")) or stripped == "":
            if PRAGMA.search(lines[k]):
                return True
            # A blank line ends the block unless the doc block continues above.
            if stripped == "" and not (k > 0 and lines[k - 1].strip().startswith(("///", "//"))):
                break
            k -= 1
            continue
        break
    return False


def check_source(rel: str, src: str) -> list[tuple[str, int, str]]:
    clean = strip_comments(src)
    lines = src.splitlines()
    enums = parse_enums(clean)
    findings = []
    for const_name, ty, entries, line in parse_lists(clean):
        if ty not in enums:
            continue  # companion for a type declared elsewhere — out of scope
        if pragma_near(lines, line):
            continue
        declared = enums[ty]
        listed = [e for e in entries if e in declared or e not in ("", ty)]
        listed_set = [e for e in listed if e in declared]

        missing = [v for v in declared if v not in listed_set]
        unknown = [e for e in listed if e not in declared and e != ty]
        dupes = sorted({e for e in listed_set if listed_set.count(e) > 1})

        if missing:
            findings.append((rel, line,
                             f"`{ty}::{const_name}` OMITS {missing} — a variant the enum "
                             f"declares is silently absent from its companion list"))
        if unknown:
            findings.append((rel, line,
                             f"`{ty}::{const_name}` lists {unknown}, which `{ty}` does not declare"))
        if dupes:
            findings.append((rel, line, f"`{ty}::{const_name}` lists {dupes} more than once"))
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
                if fn.endswith(".rs"):
                    files.append(os.path.join(dirpath, fn))
    return files


BROKEN_FIXTURE = """
pub enum Colour { Red, Green, Blue, Violet }

impl Colour {
    pub const ALL: [Colour; 3] = [Colour::Red, Colour::Green, Colour::Red];
}
"""

WHOLE_FIXTURE = """
pub enum Colour { Red, Green, Blue }

impl Colour {
    pub const ALL: [Colour; 3] = [Colour::Red, Colour::Green, Colour::Blue];
}
"""


def self_test() -> int:
    bad = check_source("<fixture-broken>", BROKEN_FIXTURE)
    good = check_source("<fixture-whole>", WHOLE_FIXTURE)
    ok = True
    kinds = " ".join(f[2] for f in bad)
    if not any("OMITS" in f[2] for f in bad):
        print("SELF-TEST FAIL: a missing variant was not reported")
        ok = False
    if not any("more than once" in f[2] for f in bad):
        print("SELF-TEST FAIL: a duplicated variant was not reported")
        ok = False
    if good:
        print(f"SELF-TEST FAIL: a correct list was reported: {good}")
        ok = False
    if ok:
        print("self-test: the gate bites (missing + duplicate detected, "
              "a complete list is silent)")
        return 0
    print("  detail:", kinds)
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
            os.path.join(REPO_ROOT, p)
            for p in out.split("\n")
            if p.strip().endswith(".rs") and os.path.exists(os.path.join(REPO_ROOT, p.strip()))
        ]
    else:
        roots = args.paths or DEFAULT_ROOTS
        files = walk(roots)
    findings: list[tuple[str, int, str]] = []
    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                src = fh.read()
        except OSError:
            continue
        if "enum" not in src or "const" not in src:
            continue
        rel = os.path.relpath(path, REPO_ROOT).replace("\\", "/")
        findings.extend(check_source(rel, src))

    print(f"closed-set-gate: scanned {len(files)} .rs file(s)")
    for rel, line, msg in findings:
        print(f"{rel}:{line}: [closed-set-drift] {msg}")

    if findings:
        print(f"\nclosed-set-gate: FAIL — {len(findings)} finding(s)")
        print("A closed set and its companion list have drifted. This is the XST-D7")
        print("class: the enum can express something the consumer silently ignores.")
        print("Fix the list, or add an inline reason: `closed-set-gate: ok — <why>`.")
        return 1
    print("closed-set-gate: OK — no findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
