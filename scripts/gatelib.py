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

import sys


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
