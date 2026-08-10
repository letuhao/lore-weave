#!/usr/bin/env python3
"""dp-oracle-coverage-gate — the count of LOCKED data-plane documents that a
test actually READS may only rise.

WHAT IT GUARDS
--------------
`crates/dp/tests/spec_oracle.rs` exists because *"a second hand-written table
agreeing with the first is not an oracle — it is the same act done twice"*. It
parses LOCKED markdown and compares the parse to a `const`.

It opened **9 of the 26** documents in
`docs/03_planning/LLM_MMO_RPG/06_data_plane/`, and the seventeen it did not open
included `05_control_plane_spec.md` — which governs everything slices `5B` and
`5C` built, and where the capability TTL sat at **three times** its specified
value until somebody read the file by hand (`BDR-52`). The spec says 5 minutes
in three independent places; the `const` said 15; nothing compared them.

So the failure is not "a rule is missing". It is that **nobody could see the
denominator**. This gate makes the denominator a number in a file, and makes the
numerator a ratchet.

WHY A REACHABILITY WALK AND NOT A GREP FOR THE FILENAME
--------------------------------------------------------
A grep counts a document as covered when its name appears anywhere — in a
docstring listing what is NOT covered, in a comment, in a dead helper nobody
calls. `spec_oracle.rs`'s own module docstring names five documents it does not
read. Counting those would make this gate report 14/26 on the day it was written
and be wrong about every one of the extra five.

Worse, it would be *gameable in the direction of the claim*: raise the number by
adding `dp_doc("17_channel_lifecycle.md");` to a function nothing calls. That is
the shape `NV-1` names — a subject that cannot vary — arriving through the front
door.

A document is COVERED here only when all three hold:

1. its filename appears as a **string literal in code** — bare, or as the last
   segment of a path literal — and not in a comment;
2. the enclosing function is **reachable from a `#[test]`** — directly, or
   through a chain of calls within the same file;
3. that function **asserts something** (`assert*!` / `panic!`). Opening a file
   and comparing nothing is the vacuity this whole corpus of gates exists about.

THE TWO FAILURE MODES, BOTH DIRECTIONS
--------------------------------------
* a **DECREASE** — a document that used to be read is not any more. Either a
  rule was deleted, or (the interesting case) a rule was *silently defeated*: a
  helper renamed so nothing calls it, an assertion removed, a `dp_doc` call
  moved into a comment. The ratchet cannot tell those apart and does not try —
  all three are the coverage going backwards.
* an **UNRECORDED INCREASE** — coverage rose and the baseline was not updated.
  Accepting improvement silently sounds harmless and is not: the baseline stops
  describing the tree, so the next decrease is measured against a stale figure
  that hides it. Same argument as `channel-id-adoption-gate`.

STATED LIMITS, because a check that overclaims is worse than none
-----------------------------------------------------------------
* **Reachability is WITHIN ONE FILE.** A test in `a.rs` calling a helper in
  `b.rs` that opens a document leaves that document uncovered here. Every
  current reader is file-local; the day one is not, this gate under-counts,
  which is the safe direction.
* **A literal outside any function** (a module-level `const DOCS: &[&str]`) does
  not count, for the same reason.
* **"Asserts something" is textual.** A function containing `assert!(true)`
  satisfies it. This gate measures whether a document is *read by a live test*,
  not whether the comparison is meaningful — that is what the bite harnesses are
  for, and no static walk can answer it.

    python scripts/dp-oracle-coverage-gate.py
    python scripts/dp-oracle-coverage-gate.py --selftest
    REGEN_ORACLE_COVERAGE_BASELINE=1 python scripts/dp-oracle-coverage-gate.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOC_DIR = REPO / "docs" / "03_planning" / "LLM_MMO_RPG" / "06_data_plane"
BASELINE = REPO / "contracts" / "dp" / "oracle-coverage-baseline.json"

# `.claude/worktrees/` holds whole-repo agent copies; counting them inflated a
# sibling gate's first measurement from 23 to 115.
ROOTS = ("crates", "services")

ASSERTS = ("assert!", "assert_eq!", "assert_ne!", "panic!", "assert_matches!")


# ── the scanner ──────────────────────────────────────────────────────────────
#
# Comments and string CONTENTS are blanked to spaces, so brace-matching and the
# `fn` search run over code only. Positions are preserved (blank, never delete),
# because the literal offsets are matched back against function spans.


def mask(src: str) -> tuple[str, list[tuple[int, str]]]:
    """Return (code-only text, [(offset, string-literal-content)]).

    Handles `//`, `/* */` (nested, as Rust does), `"…"` with escapes, `r"…"` /
    `r#"…"#`, and `'a'` char literals. A lifetime (`&'a T`) is not a char
    literal and is left alone — the difference is the closing quote.
    """
    out = list(src)
    literals: list[tuple[int, str]] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        # line comment
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                out[i] = " "
                i += 1
            continue
        # block comment, nested
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            depth = 0
            while i < n:
                if src.startswith("/*", i):
                    depth += 1
                    out[i] = out[i + 1] = " "
                    i += 2
                    continue
                if src.startswith("*/", i):
                    depth -= 1
                    out[i] = out[i + 1] = " "
                    i += 2
                    if depth == 0:
                        break
                    continue
                if src[i] != "\n":
                    out[i] = " "
                i += 1
            continue
        # raw string
        if c == "r" and i + 1 < n and src[i + 1] in '#"':
            j = i + 1
            hashes = 0
            while j < n and src[j] == "#":
                hashes += 1
                j += 1
            if j < n and src[j] == '"':
                close = '"' + "#" * hashes
                end = src.find(close, j + 1)
                end = n if end < 0 else end
                content = src[j + 1 : end]
                literals.append((j + 1, content))
                for k in range(i, min(end + len(close), n)):
                    if src[k] != "\n":
                        out[k] = " "
                i = min(end + len(close), n)
                continue
        # normal string
        if c == '"':
            j = i + 1
            buf = []
            while j < n:
                if src[j] == "\\":
                    buf.append(src[j : j + 2])
                    j += 2
                    continue
                if src[j] == '"':
                    break
                buf.append(src[j])
                j += 1
            literals.append((i + 1, "".join(buf)))
            for k in range(i, min(j + 1, n)):
                if src[k] != "\n":
                    out[k] = " "
            i = min(j + 1, n)
            continue
        # char literal — `'x'` or `'\n'`, but NOT a lifetime
        if c == "'":
            if i + 2 < n and src[i + 1] == "\\":
                end = src.find("'", i + 2)
                if 0 <= end <= i + 5:
                    for k in range(i, end + 1):
                        out[k] = " "
                    i = end + 1
                    continue
            elif i + 2 < n and src[i + 2] == "'":
                out[i] = out[i + 1] = out[i + 2] = " "
                i += 3
                continue
        i += 1
    return "".join(out), literals


FN = re.compile(r"\bfn\s+([A-Za-z_]\w*)")
CALL = re.compile(r"\b([A-Za-z_]\w*)\s*\(")


def functions(src: str, code: str) -> list[tuple[str, int, int, bool]]:
    """[(name, body_start, body_end, is_test)] over the masked text."""
    found = []
    for m in FN.finditer(code):
        brace = code.find("{", m.end())
        if brace < 0:
            continue
        # A `;` before the `{` means this was a trait method declaration or a
        # signature whose body is elsewhere.
        if ";" in code[m.end() : brace]:
            continue
        depth, k = 0, brace
        while k < len(code):
            if code[k] == "{":
                depth += 1
            elif code[k] == "}":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        found.append((m.group(1), brace, k, _is_test(src, m.start())))
    return found


def _is_test(src: str, fn_offset: int) -> bool:
    """Walk UP from the `fn` line through attributes, comments and blanks.

    Read off the RAW source, not the masked one: doc comments are blanked to
    whitespace by `mask`, so a masked walk would sail through them into
    unrelated code above.
    """
    line_start = src.rfind("\n", 0, fn_offset) + 1
    lines = src[:line_start].splitlines()
    for ln in reversed(lines):
        t = ln.strip()
        if not t or t.startswith("//"):
            continue
        if t.startswith("#["):
            if re.search(r"#\[\s*(test|tokio::test|rstest)\b", t):
                return True
            continue
        break
    return False


def docs_read_by(path: Path, locked: set[str]) -> set[str]:
    src = path.read_text(encoding="utf-8", errors="replace")
    code, literals = mask(src)
    fns = functions(src, code)
    if not fns:
        return set()

    by_name: dict[str, list[tuple[int, int, bool]]] = {}
    for name, a, b, is_test in fns:
        by_name.setdefault(name, []).append((a, b, is_test))

    # Reachability: a fn is LIVE if it is a test, or is CALLED FROM a live fn.
    #
    # Note the direction. The first draft asked whether a function *calls*
    # something live, which is backwards, and it reported `check_deferred_write_
    # forms` — a real helper reached from a real test — as dead. The self-test
    # caught it on the first run, which is the only reason this comment can be
    # written from measurement rather than from intent.
    #
    # `roots_of` records WHICH tests reach each function, because the assertion
    # requirement below is about the CHAIN, not about one frame of it.
    roots = {n for n, spans in by_name.items() if any(t for _, _, t in spans)}
    roots_of: dict[str, set[str]] = {}
    for root in roots:
        seen = {root}
        frontier = {root}
        while frontier:
            nxt: set[str] = set()
            for name in frontier:
                for a, b, _ in by_name.get(name, []):
                    for callee in CALL.findall(code[a:b]):
                        if callee in by_name and callee not in seen:
                            seen.add(callee)
                            nxt.add(callee)
            frontier = nxt
        for name in seen:
            roots_of.setdefault(name, set()).add(root)

    def asserts(name: str) -> bool:
        return any(
            k in code[a:b] for a, b, _ in by_name.get(name, []) for k in ASSERTS
        )

    covered: set[str] = set()
    for off, content in literals:
        # The BASENAME of the literal, so a reader that joins the whole relative
        # path in one string counts.
        #
        # This cost the gate its first real measurement. `spec_oracle.rs` passes
        # a bare `dp_doc("08_scale_and_slos.md")`, so matching the whole literal
        # against a filename worked — and `spec_oracle_cp.rs`, written the same
        # hour, spells it
        # `.join("../../docs/…/06_data_plane/05_control_plane_spec.md")` and was
        # reported as reading NOTHING. A gate that measures a naming convention
        # rather than the property is `NV-3`, inside the gate written to close an
        # `NV-3`.
        name = content.replace("\\", "/").rsplit("/", 1)[-1]
        if name not in locked:
            continue
        content = name
        # innermost enclosing fn
        enclosing = [(a, b, name) for name, a, b, _ in fns if a <= off <= b]
        if not enclosing:
            continue
        _, _, name = max(enclosing, key=lambda t: t[0])
        reaching = roots_of.get(name)
        if not reaching:
            continue
        # The assertion may live in the reader or in any test that reaches it —
        # a helper that reads a document and RETURNS it, with the comparison in
        # the caller, is the ordinary shape and must not be scored as vacuous.
        if not (asserts(name) or any(asserts(r) for r in reaching)):
            continue
        covered.add(content)
    return covered


def locked_docs() -> set[str]:
    return {p.name for p in DOC_DIR.glob("*.md")}


def measure() -> dict[str, list[str]]:
    """doc name -> the files that read it."""
    locked = locked_docs()
    out: dict[str, list[str]] = {}
    for root in ROOTS:
        base = REPO / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.rs")):
            if ".claude" in path.parts or "target" in path.parts:
                continue
            try:
                for d in sorted(docs_read_by(path, locked)):
                    out.setdefault(d, []).append(
                        str(path.relative_to(REPO)).replace("\\", "/")
                    )
            except OSError:
                continue
    return out


def load_baseline() -> list[str]:
    if not BASELINE.exists():
        return []
    return json.loads(BASELINE.read_text(encoding="utf-8")).get("covered", [])


def write_baseline(covered: dict[str, list[str]]) -> None:
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(
        json.dumps({"covered": sorted(covered)}, indent=2) + "\n", encoding="utf-8"
    )


def compare(covered: set[str], baseline: list[str], locked: set[str]) -> list[str]:
    problems = []
    for d in sorted(set(baseline) - covered):
        problems.append(
            f"COVERAGE LOST: {d} was read by a live oracle test and is not any more. "
            f"A rule was deleted, or one was defeated — a helper renamed so nothing "
            f"calls it, an assertion removed, a `dp_doc` call commented out. The "
            f"ratchet cannot tell those apart, and all three are coverage going "
            f"backwards."
        )
    for d in sorted(covered - set(baseline)):
        problems.append(
            f"UNRECORDED INCREASE: {d} is now read and the baseline does not say so. "
            f"Good — record it: REGEN_ORACLE_COVERAGE_BASELINE=1 python "
            f"scripts/dp-oracle-coverage-gate.py"
        )
    for d in sorted(set(baseline) - locked):
        problems.append(
            f"STALE BASELINE ROW: {d} is not a document in {DOC_DIR.name}/ any more. "
            f"The baseline is describing a corpus that has moved."
        )
    return problems


# ── self-test ────────────────────────────────────────────────────────────────

_LOCKED_FIXTURE = {"05_control_plane_spec.md", "17_channel_lifecycle.md"}

_LIVE = '''
fn helper() -> String { read("05_control_plane_spec.md") }

#[test]
fn t() {
    let s = helper();
    assert_eq!(s, s);
}
'''

_DEAD = '''
fn orphan() {
    let _ = read("05_control_plane_spec.md");
    assert!(true);
}

#[test]
fn t() { assert!(true); }
'''

_COMMENTED = '''
#[test]
fn t() {
    // read("05_control_plane_spec.md") — not yet
    /* also "17_channel_lifecycle.md" */
    assert!(true);
}
'''

_NO_ASSERT = '''
#[test]
fn t() {
    let _ = read("05_control_plane_spec.md");
}
'''

_INDIRECT_ASSERT = '''
#[test]
fn t() {
    let _ = read("05_control_plane_spec.md");
    assert_eq!(1, 1);
}
'''

# The document named by a FULL RELATIVE PATH in one literal, which is how
# `spec_oracle_cp.rs` spells it. Matching whole literals against bare filenames
# reported that file as reading nothing at all — the gate measuring a naming
# convention instead of the property.
_FULL_PATH = '''
#[test]
fn t() {
    let p = base().join("../../docs/03_planning/LLM_MMO_RPG/06_data_plane/05_control_plane_spec.md");
    assert!(p.exists());
}
'''

# The reader is reached from a test and NOTHING in the chain asserts. This is
# the case `_LIVE` is one assertion away from, and the pair is the point: the
# rule is about the chain, so it must be able to answer differently for two
# sources that differ by exactly one line.
_CHAIN_NO_ASSERT = '''
fn helper() -> String { read("05_control_plane_spec.md") }

#[test]
fn t() {
    let _ = helper();
}
'''


def _scan_text(text: str, tmp: Path) -> set[str]:
    tmp.write_text(text, encoding="utf-8")
    return docs_read_by(tmp, _LOCKED_FIXTURE)


def selftest() -> int:
    import tempfile

    failures: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "fixture.rs"
        if _scan_text(_LIVE, tmp) != {"05_control_plane_spec.md"}:
            failures.append("a doc opened by a helper CALLED FROM a #[test] was not counted")
        if _scan_text(_DEAD, tmp):
            failures.append("a doc opened only by an UNCALLED function was counted")
        if _scan_text(_COMMENTED, tmp):
            failures.append("a doc named only inside comments was counted")
        if _scan_text(_NO_ASSERT, tmp):
            failures.append("a doc opened by a test that asserts NOTHING was counted")
        if _scan_text(_INDIRECT_ASSERT, tmp) != {"05_control_plane_spec.md"}:
            failures.append("a doc opened by an asserting test was not counted")
        if _scan_text(_CHAIN_NO_ASSERT, tmp):
            failures.append(
                "a doc read through a live chain that asserts NOWHERE was counted"
            )
        if _scan_text(_FULL_PATH, tmp) != {"05_control_plane_spec.md"}:
            failures.append(
                "a doc named by a FULL RELATIVE PATH in one literal was not counted"
            )

    # The ratchet arms, on synthetic sets rather than on the tree.
    locked = {"a.md", "b.md", "c.md"}
    if not compare({"a.md"}, ["a.md", "b.md"], locked):
        failures.append("decrease check did NOT red on a lost document")
    if not compare({"a.md", "b.md", "c.md"}, ["a.md", "b.md"], locked):
        failures.append("increase check did NOT red on an unrecorded gain")
    if not compare({"a.md"}, ["a.md", "gone.md"], locked):
        failures.append("stale-row check did NOT red on a baseline doc that no longer exists")
    if compare({"a.md", "b.md"}, ["a.md", "b.md"], locked):
        failures.append("exact match reded (false positive)")

    # …and the corpus itself must be findable, or the denominator is a lie.
    if len(locked_docs()) < 20:
        failures.append(
            f"only {len(locked_docs())} document(s) found in {DOC_DIR} — the corpus "
            f"path is wrong and every ratio this gate prints is meaningless"
        )

    if failures:
        for f in failures:
            print(f"dp-oracle-coverage-gate: SELFTEST FAIL — {f}")
        return 1
    print(
        "dp-oracle-coverage-gate: SELFTEST PASS — 11 case(s); it counts a doc read "
        "through a helper, ignores one in dead code / in a comment / with no "
        "assertion, reds on a decrease, an unrecorded increase and a stale row, does "
        "NOT red on an exact match, and can see the corpus"
    )
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    if selftest() != 0:
        return 1

    readers = measure()
    covered = set(readers)
    locked = locked_docs()

    if os.environ.get("REGEN_ORACLE_COVERAGE_BASELINE") == "1":
        write_baseline(readers)
        print(
            f"dp-oracle-coverage-gate: baseline rewritten — {len(covered)}/{len(locked)} "
            f"LOCKED document(s) read by a live oracle test"
        )
        return 0

    baseline = load_baseline()
    if not baseline:
        print(
            "dp-oracle-coverage-gate: MISUSE — no baseline. Create it with "
            "REGEN_ORACLE_COVERAGE_BASELINE=1",
            file=sys.stderr,
        )
        return 2

    print(
        f"[dp-oracle-coverage] {len(covered)}/{len(locked)} LOCKED 06_data_plane "
        f"document(s) read by a live, asserting test"
    )
    for d in sorted(readers):
        print(f"    {d}  <- {', '.join(readers[d])}")
    unread = sorted(locked - covered)
    if unread:
        print(f"    still unread ({len(unread)}): {', '.join(unread)}")

    problems = compare(covered, baseline, locked)
    if problems:
        print("\ndp-oracle-coverage-gate: FAIL")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("[dp-oracle-coverage-gate] OK — matches the baseline exactly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
