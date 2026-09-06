#!/usr/bin/env python3
"""gatelib — the one Rust/TS source stripper the gates share.

WHY THIS FILE EXISTS
--------------------
Three gates each grew their own `strip_comments`: `hot-path-gate`,
`zero-digest-gate`, and (newest) `crate-purity-gate`. That is the copy-paste
[SDK-First](../docs/standards/sdk-first.md) names — and it was not a tidiness
complaint, it was a defect report:

  **The newest copy was the buggy one, precisely because it was written rather
  than reused.** `crate-purity-gate` shipped a naive `re.sub(r"//.*$", "")`,
  which meant `let p = format!("{}//{}", a, b); std::fs::write(p, x);` was
  **silent** — the `//` inside a string literal ate the violation after it, on
  the one rule that actually states IMP-D2. It also bit on `/* … std::fs … */`,
  so documenting the rule reddened the gate.

Meanwhile the two older copies were correct about something the new one got
wrong (blanking **in place**, so line numbers survive) and wrong about something
the new one got right (raw strings, and `'a` lifetimes vs `'x'` char literals).
No single copy was the best one. This is the union.

THE TWO CONTRACTS, BOTH LOAD-BEARING
------------------------------------
1. **Offsets are preserved.** Every consumed character becomes a space and every
   newline stays a newline, so `line = src[:m.start()].count("\\n") + 1` still
   works. `hot-path-gate` and `zero-digest-gate` both report line numbers and a
   collapsing stripper would have silently misreported every one of them.

2. **`keep_strings` is a real fork, not a default.** `hot-path-gate` MUST keep
   strings — half of what it looks for (`.get("qi")`) *is* a string literal.
   `crate-purity-gate` MUST drop them — a message naming `std::fs` is not a use
   of it. Getting this backwards blinds one gate or makes the other cry wolf, so
   the argument is required at every call site rather than defaulted.

NON-VACUITY
-----------
`python scripts/gatelib.py --self-test` proves both contracts and every lexical
case. Each consuming gate keeps its OWN `--self-test` as well: those are what
prove this shared helper did not change their behaviour when they adopted it.
"""

from __future__ import annotations

import re
import sys

CFG_TEST_RE = re.compile(r"#\[cfg\(test\)\]")


def blank_rust_test_items(text: str) -> str:
    """Blank every `#[cfg(test)]` item in a Rust source, IN PLACE.

    THE HOLE THIS CLOSES — and it has now been found in TWO gates.
    --------------------------------------------------------------
    Test code is excluded BY PATH (`/tests/`, `/benches/`, `/fixtures/`). **Rust
    does not put its unit tests there.** It puts them in a `#[cfg(test)] mod
    tests` at the bottom of the very `src/` file the gate reads as production.

    1. `orphan-model-gate`, 2026-08-05: `crates/rebuilder/src/lib.rs:542` held
       `event_type: "world.kv_set".into()` inside a test fixture, and it was the
       only occurrence outside an excluded path — so the gate reported the
       projector PRODUCED and stayed green. **A test vouching for a projector is
       the exact circularity that gate exists to break** (`D-446`'s shape: a
       witness table counting as its own witness).
    2. `hot-path-gate`, 2026-08-06: a `#[cfg(test)]` mirror test indexing
       `schema["$defs"]["DomainEvent"]` produced **nine** `string-keyed-lookup`
       findings *on the island step path* — for code that never runs in a step.
       A gate that cries wolf on correct test code gets pragma'd around, and a
       pragma is an exemption that keeps silencing after the reason is gone.

    Twice is a class, so it lives here rather than in either gate.

    **BLANKS rather than deletes**, unlike the first implementation: line numbers
    must survive (`strip_comments`'s contract, and `hot-path-gate` reports lines),
    and deleting also JOINS the text either side of the gap, which can
    manufacture a match that was never in the source.

    Brace-matched rather than regex-matched, because a `mod tests` body contains
    braces and a lazy pattern stops at the first `}` it meets — which would strip
    one function and leave the rest of the module readable as production.
    """
    def blanked(s: str) -> str:
        return "".join(c if c == "\n" else " " for c in s)

    out, i = [], 0
    for m in CFG_TEST_RE.finditer(text):
        if m.start() < i:
            continue  # already inside a blanked item
        out.append(text[i:m.start()])
        j = text.find("{", m.end())
        semi = text.find(";", m.end())
        # **A `;` BEFORE the next `{` means this is a statement item**
        # (`#[cfg(test)] use fake::thing;`) and the brace belongs to whatever
        # comes AFTER it. The first implementation only handled `j == -1` — no
        # brace anywhere in the rest of the file — which is nearly never true,
        # so `#[cfg(test)] use foo;` silently brace-matched through the NEXT
        # production item and blanked it. Caught by this file's own new case,
        # which is the reason the case was worth writing: the bug was inherited
        # verbatim from the gate this helper was lifted out of.
        if j == -1 or (semi != -1 and semi < j):
            k = len(text) if semi == -1 else semi + 1
            out.append(blanked(text[m.start():k]))
            i = k
            continue
        depth, k = 0, j
        while k < len(text):
            if text[k] == "{":
                depth += 1
            elif text[k] == "}":
                depth -= 1
                if depth == 0:
                    k += 1
                    break
            k += 1
        out.append(blanked(text[m.start():k]))
        i = k
    out.append(text[i:])
    return "".join(out)


def strip_comments(src: str, keep_strings: bool) -> str:
    """Blank `//`, `/* */`, and (unless `keep_strings`) string literals.

    Blanks IN PLACE: the result has the same length as `src` and the same
    newline positions, so byte offsets and line numbers stay valid.

    `keep_strings` is positional-required on purpose — see contract 2 above.
    """
    out = list(src)
    i, n = 0, len(src)

    def blank(a: int, b: int) -> None:
        for k in range(a, min(b, n)):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        c = src[i]

        # Raw string: r"…" / r#"…"# / r##"…"##. Must be handled BEFORE the plain
        # string case, and before `//` — `r"http://x"` contains neither a comment
        # nor an escapable quote.
        if c == "r" and i + 1 < n and src[i + 1] in '#"':
            j, hashes = i + 1, 0
            while j < n and src[j] == "#":
                hashes += 1
                j += 1
            if j < n and src[j] == '"':
                close = '"' + "#" * hashes
                k = src.find(close, j + 1)
                end = n if k < 0 else k + len(close)
                if not keep_strings:
                    blank(i, end)
                i = end
                continue

        # A string is ALWAYS consumed; `keep_strings` decides only whether its
        # bytes survive.
        #
        # **Consuming it unconditionally is the load-bearing part.** The first
        # version gated the whole branch on `not keep_strings`, so under
        # `keep_strings=True` — which is exactly how `hot-path-gate` runs — a
        # `//` INSIDE a string opened a comment and ate the rest of the line:
        #
        #     let u = "http://x"; m.get("qi");   ->   let u = "http:
        #
        # …silently dropping a real `.get("qi")` finding. That is the same defect
        # this file was extracted to fix, surviving in the other branch, and the
        # raw-string arm directly above already did it right — two sibling arms
        # disagreeing is the tell. Knowing where a string ENDS is required to
        # know where a comment BEGINS, whatever you then do with its contents.
        if c == '"':
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == '"':
                    break
                j += 1
            if not keep_strings:
                blank(i, j + 1)
            i = j + 1
            continue

        # A char literal may contain a quote (`'"'`) and would otherwise open a
        # bogus string. A LIFETIME (`'a`) has no closing quote and must be left
        # alone — treating it as a literal would swallow the rest of the line and
        # hide real findings, which is how a stripper goes from noisy to blind.
        if c == "'":
            if i + 3 < n and src[i + 1] == "\\":
                k = src.find("'", i + 2)
                if k >= 0:
                    if not keep_strings:
                        blank(i, k + 1)
                    i = k + 1
                    continue
            elif i + 2 < n and src[i + 2] == "'":
                if not keep_strings:
                    blank(i, i + 3)
                i += 3
                continue
            # else: a lifetime — fall through, consume just the tick.

        if src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
            continue

        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
            continue

        i += 1

    return "".join(out)


def self_test() -> int:
    fails: list[str] = []

    def case(name, src, keep, must_keep=(), must_drop=()):
        got = strip_comments(src, keep)
        if len(got) != len(src):
            fails.append(f"{name}: LENGTH CHANGED ({len(src)} -> {len(got)}) — offsets destroyed")
        if got.count("\n") != src.count("\n"):
            fails.append(f"{name}: newline count changed — line numbers destroyed")
        for t in must_keep:
            if t not in got:
                fails.append(f"{name}: lost {t!r} (should survive)\n    got: {got!r}")
        for t in must_drop:
            if t in got:
                fails.append(f"{name}: kept {t!r} (should be blanked)\n    got: {got!r}")

    # ── contract 1: offsets + newlines survive every construct ──
    case("line comment", "a();\n// x\nb();\n", False, ("a();", "b();"), ("// x",))
    case("block comment", "a();\n/* x\ny */\nb();\n", False, ("a();", "b();"), ("/* x",))

    # ── the bug that caused this file to exist ──
    case("// inside a string hides code after it",
         'let p = format!("{}//{}", a, b); std::fs::write(p, x);', False,
         must_keep=("std::fs::write",))
    case("block comment mentioning a banned path",
         "/* never call std::fs::read */", False, must_drop=("std::fs",))
    case("string naming a banned path is not a use of it",
         'let s = "std::fs::read is banned";', False, must_drop=("std::fs",))

    # ── blank_rust_test_items: the hole found in TWO gates ──
    def tcase(name, src, must_keep=(), must_drop=()):
        got = blank_rust_test_items(src)
        if len(got) != len(src):
            fails.append(f"{name}: LENGTH CHANGED ({len(src)} -> {len(got)}) — offsets destroyed")
        if got.count("\n") != src.count("\n"):
            fails.append(f"{name}: newline count changed — line numbers destroyed")
        for t in must_keep:
            if t not in got:
                fails.append(f"{name}: lost {t!r} (production code must survive)")
        for t in must_drop:
            if t in got:
                fails.append(f"{name}: kept {t!r} (test code must be blanked)")

    tcase("a #[cfg(test)] mod at the bottom of a src file is blanked",
          'fn prod() { real(); }\n#[cfg(test)]\nmod tests {\n  fn t() { fake(); }\n}\n',
          must_keep=("real();",), must_drop=("fake();",))
    # The reason it is brace-MATCHED: a lazy `.*?}` stops at the inner function's
    # closing brace and leaves the rest of the module readable as production.
    tcase("nested braces do not end the item early",
          '#[cfg(test)]\nmod t {\n  fn a() { if x { y(); } }\n  fn b() { leaked(); }\n}\nfn prod() { real(); }\n',
          must_keep=("real();",), must_drop=("leaked();", "y();"))
    tcase("a #[cfg(test)] use statement has no brace and stops at the line",
          '#[cfg(test)]\nuse fake::thing;\nfn prod() { real(); }\n',
          must_keep=("real();",), must_drop=("fake::thing",))
    tcase("production code with no test module is untouched",
          'fn prod() { real(); }\n', must_keep=("real();", "fn prod()"))
    # Deleting rather than blanking would JOIN these and manufacture `ab`.
    tcase("blanking does not join the text either side of the gap",
          'let a\n#[cfg(test)]\nmod t { }\nb = 1;\n', must_keep=("let a", "b = 1;"),
          must_drop=("mod t",))

    # ── the case the OLD copies got right and the new one got wrong ──
    case("lifetime is not a char literal",
         "fn f<'a>(p: &'a str) { std::fs::read(p); }", False,
         must_keep=("std::fs::read",))
    case("char literal containing a quote does not open a string",
         "let q = '\"'; std::fs::read(p);", False, must_keep=("std::fs::read",))
    case("raw string", 'let u = r"http://x"; std::fs::read(p);', False,
         must_keep=("std::fs::read",), must_drop=("http",))
    case("hashed raw string", 'let u = r#"a"b//c"#; std::fs::read(p);', False,
         must_keep=("std::fs::read",))

    # ── contract 2: keep_strings is a real fork ──
    case("keep_strings=True preserves the literal a gate is looking for",
         'm.get("qi"); // comment', True, must_keep=('"qi"',), must_drop=("// comment",))
    case("keep_strings=False drops it",
         'm.get("qi");', False, must_drop=('"qi"',))

    # ── every lexical case must hold under BOTH forks, not just one ──
    #
    # The first version of this file only probed `keep_strings=False` here, and
    # the `//`-inside-a-string bug shipped in the True branch — the branch
    # `hot-path-gate` actually runs. A self-test that exercises one fork of a
    # two-fork function is testing half a function.
    for keep in (False, True):
        case(f"[keep={keep}] a `//` inside a string never opens a comment",
             'let u = "http://x"; m.get("qi");', keep, must_keep=('m.get',))
        case(f"[keep={keep}] a `/*` inside a string never opens a block comment",
             'let u = "a/*b"; m.get("qi");', keep, must_keep=('m.get',))
        case(f"[keep={keep}] an escaped quote does not end the string early",
             r'let s = "he said \"hi\" //x"; m.get("qi");', keep, must_keep=('m.get',))
        case(f"[keep={keep}] a raw string containing // is not a comment",
             'let u = r"a//b"; m.get("qi");', keep, must_keep=('m.get',))
    # …and under keep=True the hunted literal must still be readable after one.
    got = strip_comments('let u = "http://x"; m.get("qi");', True)
    if '"qi"' not in got:
        fails.append("keep=True lost the target literal after a URL-ish string: " + repr(got))

    if fails:
        print("gatelib SELF-TEST FAILED:")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("gatelib: self-test OK — offsets and newlines preserved across every construct; "
          "strings/comments/raw-strings/char-literals handled; lifetimes left alone; "
          "keep_strings forks both ways")
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv else self_test())
