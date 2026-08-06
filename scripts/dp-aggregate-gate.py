#!/usr/bin/env python3
"""dp-aggregate-gate — ONE aggregate name binds ONE tier and ONE scope.

WHY THIS EXISTS, AND WHY IT IS NOT A TYPE
-----------------------------------------
`crates/dp` makes `Tier` and `Scope` **associated types** on `DpAggregate`, and
slice 1 was sold to the PO on the claim that this makes a second tier
*unrepresentable*. A cold-start refuter broke that claim on 2026-08-07
(`V1-F1`):

    impl<T: Tier, S: Scope> DpAggregate for PlayerWallet<T, S> {
        type Tier = T;  type Scope = S;
        const TYPE_NAME: &'static str = "player_wallet";   // ONE name, four tiers
    }

It compiled, ran, and selected the tier from an environment variable —
`survives_store_outage` flipping `false -> true`, which is **exactly** the
`REC-102c` promise the crate was written to make un-flippable.

**The type system cannot see this, by construction.** Each monomorphisation is
individually consistent; the contradiction lives *across* monomorphisations, and
that is precisely the comparison a type checker never makes. `TYPE_NAME` is the
aggregate token in the `DP-Ch5` cache key, so two tiers under one name means two
live cache entries for one logical aggregate under two different coherency
contracts. `DP-A9` says a tier is *"not configurable per player"*; a
`Box<dyn _>` picked per request is per-player configuration.

WHAT ROUND 2 PROVED, AND WHY THIS FILE IS A REWRITE
---------------------------------------------------
The first version of this gate concluded *"rustc cannot hold it, so the source
can"* and did not ask **what a source check provably cannot do**. A second
cold-start refuter answered that in six ways, every one compiling and running
while this gate printed `OK` (`R2-1`..`R2-8`), and a third found the gate's own
`--self-test` was a re-implementation that never called `scan()` (`V2-F1`).

    the gate matched TOKENS IN TEXT where the property is about
    TYPES AFTER NAME RESOLUTION, and text has more ways to spell
    a generic than the gate had patterns

So the rules below are no longer "does the token look like a tier". They are a
**closed characterisation of how a generic can reach `type Tier`** — it must
name something the impl binds — plus the ways a concrete-looking token can lie.
Each rule cites the break it was written against.

WHAT IT CHECKS
--------------
  R1  `type Tier  = ...` names a member of the closed tier set
  R2  `type Scope = ...` names a member of the closed scope set
  R3  `TYPE_NAME` is a string LITERAL (a computed name cannot be read without
      running the program, and cannot be checked for collisions at all)
  R4  no two `impl DpAggregate` blocks share a `TYPE_NAME` — compared by
      DECODED VALUE, because rustc compares values and a `\\u{..}` escape spells
      `"wallet"` a second way (`R2-7`)
  R5  the scan's SCOPE is exactly what it claims: every `.rs` file git would let
      you commit, minus one named directory. Not a count — a set difference
      (`V2-F2`)
  R6  the right-hand side of `type Tier`/`type Scope` names **no generic
      parameter the impl binds, and no `Self`** (`R2-1`, `R2-2`). This is the
      load-bearing rule: to be generic, the RHS *must* name something in scope,
      and the only things in scope are the impl's parameters and `Self`
  R7  no generic parameter is NAMED after a taxonomy member (`R2-1` again, from
      the other side — belt to R6's braces, and it catches indirect uses)
  R8  no `use ... as <taxonomy name>` in a file that declares an aggregate: an
      alias makes the gate's own report name the wrong tier, and under `cfg` it
      makes the tier a build-time switch (`R2-6`)
  R9  an `impl ... DpAggregate` that the parser cannot delimit is a FINDING, not
      a skip. The first version returned `-1` and `continue`d — it failed OPEN,
      silently, on one odd brace inside a doc string (`R2-4`)
  R10 an `impl DpAggregate` inside a `macro_rules!` body is REFUSED: one body,
      N invocations, and this gate can only see the body (`R2-8`)

WHAT IT STILL CANNOT DO — read this before trusting it
------------------------------------------------------
It is a **source** check. It runs before name resolution, so anything that
changes what a token *resolves to* without changing the token is outside it:
`include!`, a build script that generates an impl, a proc-macro, or a
sufficiently determined `cfg` maze. R6/R7/R8 close the escapes that are
*writable by hand today*, and the argument for R6 is a closure argument rather
than a pattern list — but "closed at the token level" is not "closed".

**The principled home for this property is `dp-clippy`**, which runs after name
resolution and which `06_data_plane/` has named as one of its three crates since
April. It does not exist. Tracked: `D-DP-CLIPPY-NOT-BUILT`.

`crates/dp/tests/ui/` is excluded — trybuild fixtures exist in order NOT to
compile. The exclusion is an exact repo-relative directory, checked by R5 as a
set difference; it was an unanchored substring (`"tests/ui/"` matched
`src/tests/ui/mod.rs` in any crate) until `R2-5`.

Run: ``python scripts/dp-aggregate-gate.py`` — wired pre-commit.
Exit 0 = clean; 1 = findings; 2 = misuse.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DP_SRC = REPO / "crates" / "dp" / "src"

# The ONE excluded directory, repo-relative and anchored. `R2-5`: this was
# `"tests/ui/"` matched as a substring of the absolute path, so a perfectly
# ordinary `src/tests/ui/mod.rs` in any crate went unscanned.
FIXTURE_DIR = "crates/dp/tests/ui/"


# ─────────────────────────────────────────────────────────────────────────────
# Rust source handling
# ─────────────────────────────────────────────────────────────────────────────
def strip_comments(src: str) -> str:
    """Blank `//` lines and `/* */` blocks, preserving length and newlines.

    Handles string literals, **raw strings** and **char literals**. The char
    case is `R2-3`, and it was not theoretical: `const QUOTE: char = '"';` made
    the lexer here open a phantom string, so what followed was read as string
    content until the next real quote — and a `/*` inside that content then
    blanked the impl entirely. The gate reported one FEWER impl block and exit
    0. `'"'` is ordinary code in any quoting or escaping routine.
    """
    out = list(src)
    i, n = 0, len(src)

    def blank(a: int, b: int) -> None:
        for k in range(a, min(b, n)):
            if src[k] != "\n":
                out[k] = " "

    while i < n:
        c = src[i]
        # raw string: r"..." / r#"..."# / br#"..."#
        m = re.match(r'(?:b?r)(#*)"', src[i:i + 40]) if c in "rb" else None
        if m and (i == 0 or not (src[i - 1].isalnum() or src[i - 1] == "_")):
            hashes = m.group(1)
            close = '"' + hashes
            j = src.find(close, i + m.end())
            i = n if j < 0 else j + len(close)
            continue
        if c == '"':
            i += 1
            while i < n and src[i] != '"':
                i += 2 if src[i] == "\\" else 1
            i += 1
            continue
        if c == "'":
            # A char literal, OR a lifetime (`'a`, `'static`). A lifetime is not
            # quote-delimited, so only treat it as a char when a closing quote
            # arrives within the 1..~12 chars a char literal can occupy.
            m2 = re.match(r"'(?:\\(?:u\{[0-9a-fA-F]{1,6}\}|x[0-9a-fA-F]{2}|.)|[^\\'])'", src[i:])
            if m2:
                i += m2.end()
            else:
                i += 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            depth, j = 1, i + 2
            blank(i, i + 2)
            while j < n and depth:
                if src.startswith("/*", j):
                    depth += 1
                    blank(j, j + 2)
                    j += 2
                elif src.startswith("*/", j):
                    depth -= 1
                    blank(j, j + 2)
                    j += 2
                else:
                    blank(j, j + 1)
                    j += 1
            i = j
            continue
        i += 1
    return "".join(out)


def blank_strings(src: str) -> str:
    """`src` with string/char CONTENT blanked, delimiters kept.

    Brace counting must not see a `{` that lives inside a string. `R2-4`:
    `#[doc = "the cache key opens with a brace: dp:{"]` made `_balanced` run off
    the end of the file, return `-1`, and the impl was skipped **silently** — a
    doc comment about a `DP-Ch5` cache-key template, which is this crate's own
    subject matter.
    """
    out = list(src)
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        m = re.match(r'(?:b?r)(#*)"', src[i:i + 40]) if c in "rb" else None
        if m and (i == 0 or not (src[i - 1].isalnum() or src[i - 1] == "_")):
            hashes = m.group(1)
            close = '"' + hashes
            start = i + m.end()
            j = src.find(close, start)
            end = n if j < 0 else j
            for k in range(start, end):
                if src[k] != "\n":
                    out[k] = " "
            i = n if j < 0 else j + len(close)
            continue
        if c == '"':
            i += 1
            while i < n and src[i] != '"':
                step = 2 if src[i] == "\\" else 1
                for k in range(i, min(i + step, n)):
                    if src[k] != "\n":
                        out[k] = " "
                i += step
            i += 1
            continue
        if c == "'":
            m2 = re.match(r"'(?:\\(?:u\{[0-9a-fA-F]{1,6}\}|x[0-9a-fA-F]{2}|.)|[^\\'])'", src[i:])
            if m2:
                for k in range(i + 1, i + m2.end() - 1):
                    out[k] = " "
                i += m2.end()
            else:
                i += 1
            continue
        i += 1
    return "".join(out)


def _balanced(src: str, start: int, open_c: str, close_c: str) -> int:
    """Index just past the group opened at `start`. -1 if unterminated."""
    depth, i, n = 0, start, len(src)
    while i < n:
        if src[i] == open_c:
            depth += 1
        elif src[i] == close_c:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def macro_spans(code: str) -> list[tuple[int, int]]:
    """`(start, end)` of every `macro_rules!` body."""
    spans = []
    for m in re.finditer(r"\bmacro_rules!\s*[A-Za-z_][A-Za-z0-9_]*\s*", code):
        i = m.end()
        while i < len(code) and code[i] not in "{([":
            i += 1
        if i >= len(code):
            continue
        pairs = {"{": "}", "(": ")", "[": "]"}
        end = _balanced(code, i, code[i], pairs[code[i]])
        if end > 0:
            spans.append((m.start(), end))
    return spans


class ImplBlock:
    def __init__(self, path: Path, line: int, header: str, body: str,
                 generics: list[str], broken: str = ""):
        self.path, self.line, self.header, self.body = path, line, header, body
        self.generics, self.broken = generics, broken

    @property
    def where(self) -> str:
        # `rel` tolerates a path outside the repo — the self-test drives `scan()`
        # over files in a temp dir, which is the point of `V2-F1`'s fix.
        return f"{rel(self.path)}:{self.line}"


def impl_generics(header: str) -> list[str]:
    """Type/const parameter NAMES bound by an `impl<..>` header.

    These are the only things — with `Self` — that can make the right-hand side
    of `type Tier = ..` generic. That closure is the whole argument for R6.
    """
    m = re.search(r"\bimpl\s*<", header)
    if not m:
        return []
    end = _balanced(header, m.end() - 1, "<", ">")
    if end < 0:
        return []
    inner = header[m.end():end - 1]
    names, depth, buf = [], 0, ""
    for ch in inner + ",":
        if ch in "<([":
            depth += 1
        elif ch in ">)]":
            depth -= 1
        if ch == "," and depth <= 0:
            part = buf.strip()
            buf = ""
            if not part or part.startswith("'"):
                continue
            part = part.split(":")[0].split("=")[0].strip()
            part = re.sub(r"^const\s+", "", part).strip()
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part):
                names.append(part)
        else:
            buf += ch
    return names


def find_impls(path: Path, src: str) -> list[ImplBlock]:
    """Every `impl ... DpAggregate for ... { .. }` block in one file.

    **Fails CLOSED.** A header that names `DpAggregate` but cannot be delimited
    is returned with `broken` set, and R9 turns that into a finding. The first
    version `continue`d, which is how `R2-4` hid a live escape behind one odd
    brace in a string.
    """
    # TWO views of the same offsets. `strip_comments` and `blank_strings` both
    # preserve length, so an offset means the same thing in either.
    #   `code`  — comments gone, STRING CONTENT INTACT: what the rules read.
    #   `walk`  — string content blanked too: what the BRACE COUNTER walks, so a
    #             `{` inside a doc string cannot unbalance it (`R2-4`).
    # Slicing the body out of `walk` was this rewrite's own first bug: it made
    # every `TYPE_NAME` read back as spaces, so two distinct aggregates looked
    # like one collision. Caught by the self-test's cry-wolf case, which exists
    # because a check that only ever fires is as useless as one that never does.
    code = strip_comments(src)
    walk = blank_strings(code)
    macros = macro_spans(walk)
    blocks: list[ImplBlock] = []
    for m in re.finditer(r"\bimpl\b", walk):
        i, n, ang = m.end(), len(code), 0
        while i < n:
            c = code[i]
            if c == "<":
                ang += 1
            elif c == ">":
                ang -= 1
            elif c == "{" and ang <= 0:
                break
            elif c == ";" and ang <= 0:
                i = -1
                break
            i += 1
        header_end = i
        if header_end < 0 or header_end >= n:
            # Ran off the end: only a finding if this really was a DpAggregate impl.
            tail = code[m.start():m.start() + 400]
            if re.search(r"\bDpAggregate\b", tail):
                blocks.append(ImplBlock(path, code.count("\n", 0, m.start()) + 1, tail, "",
                                        [], broken="no `{` closes this impl header"))
            continue
        header = code[m.start():header_end]
        if not re.search(r"\bDpAggregate\b", header):
            continue
        line = code.count("\n", 0, m.start()) + 1
        if any(a <= m.start() < b for a, b in macros):
            blocks.append(ImplBlock(path, line, header, "", impl_generics(header),
                                    broken="declared inside a `macro_rules!` body"))
            continue
        end = _balanced(walk, header_end, "{", "}")
        if end < 0:
            blocks.append(ImplBlock(path, line, header, "", impl_generics(header),
                                    broken="braces in this impl body do not balance"))
            continue
        blocks.append(ImplBlock(path, line, header, code[header_end:end],
                                impl_generics(header)))
    return blocks


def decode_rust_str(lit: str) -> str:
    """Decode a Rust string literal's escapes to the value rustc will compare.

    `R2-7`: `"wallet"` and `"walle\\u{74}"` are ONE cache-key token and were two
    rows to a check that compared source text.
    """
    out, i, n = [], 0, len(lit)
    simple = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", "\\": "\\", '"': '"', "'": "'"}
    while i < n:
        if lit[i] != "\\":
            out.append(lit[i])
            i += 1
            continue
        i += 1
        if i >= n:
            break
        c = lit[i]
        if c == "u" and i + 1 < n and lit[i + 1] == "{":
            j = lit.find("}", i)
            if j < 0:
                break
            out.append(chr(int(lit[i + 2:j], 16)))
            i = j + 1
        elif c == "x" and i + 2 < n:
            out.append(chr(int(lit[i + 1:i + 3], 16)))
            i += 3
        elif c == "\n":
            while i < n and lit[i] in " \t\r\n":
                i += 1
        else:
            out.append(simple.get(c, c))
            i += 1
    return "".join(out)


# ─────────────────────────────────────────────────────────────────────────────
# The closed sets — PARSED from the crate, never typed here
# ─────────────────────────────────────────────────────────────────────────────
def declared(pattern: str, filename: str) -> list[str]:
    """Members of a closed taxonomy, read from its own DEFINITION SITE.

    Tiers are declared through `declare_tier!`, scopes as hand-written
    `impl Scope for _`, so each gets the pattern matching where it is actually
    defined. One assumed shape would leave the second parse silently empty, and
    R5 is what would notice.
    """
    f = DP_SRC / filename
    if not f.is_file():
        print(f"dp-aggregate-gate: MISUSE — cannot read {f}", file=sys.stderr)
        sys.exit(2)
    src = strip_comments(f.read_bytes().decode("utf-8"))
    return sorted(set(re.findall(pattern, src)))


TIER_DECL = r"declare_tier!\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)"
SCOPE_DECL = r"\bimpl\s+Scope\s+for\s+([A-Za-z_][A-Za-z0-9_]*)"


def last_segment(ty: str) -> str:
    """`crate::tier::T2` -> `T2`. Generic args are NOT stripped, so `Wrapper<T>`
    stays `Wrapper<T>` and fails the membership test — which is wanted."""
    return ty.strip().rstrip(";").split("::")[-1].strip()


# ─────────────────────────────────────────────────────────────────────────────
def all_rust_files() -> list[Path]:
    """Every `.rs` file git would let you commit."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "*.rs"],
            cwd=REPO, capture_output=True, text=True, check=True,
        ).stdout
        return [REPO / r for r in out.split("\0") if r]
    except (OSError, subprocess.CalledProcessError):
        return [p for p in REPO.rglob("*.rs") if "target" not in p.parts]


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(REPO)).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


def partition(files: list[Path]) -> tuple[list[Path], list[Path]]:
    """(scanned, excluded). The exclusion is ONE anchored directory."""
    scanned, excluded = [], []
    for p in files:
        (excluded if rel(p).startswith(FIXTURE_DIR) else scanned).append(p)
    return scanned, excluded


class Finding:
    def __init__(self, rule: str, where: str, detail: str):
        self.rule, self.where, self.detail = rule, where, detail

    def __str__(self) -> str:
        return f"  {self.rule}  {self.where}\n      {self.detail}"


def scan(files: list[Path], tiers: list[str], scopes: list[str]) -> tuple[list[Finding], int]:
    """The REAL check. `self_test` drives THIS — see `V2-F1`."""
    findings: list[Finding] = []
    names: dict[str, str] = {}
    taxonomy = set(tiers) | set(scopes)
    count = 0

    for path in files:
        try:
            src = path.read_bytes().decode("utf-8", errors="replace")
        except OSError:
            continue
        if "DpAggregate" not in src:
            continue
        code = strip_comments(src)
        blocks = find_impls(path, src)

        # ── R8 — aliasing a taxonomy name ────────────────────────────────────
        if blocks:
            for m in re.finditer(r"\buse\s+([A-Za-z_][A-Za-z0-9_:]*)\s+as\s+([A-Za-z_][A-Za-z0-9_]*)",
                                 code):
                if m.group(2) in taxonomy:
                    findings.append(Finding(
                        "R8", f"{rel(path)}:{code.count(chr(10), 0, m.start()) + 1}",
                        f"`use {m.group(1)} as {m.group(2)}` renames something to a taxonomy name. "
                        f"Every check below then reads {m.group(2)!r} and reports the WRONG tier — "
                        f"and under `#[cfg(..)]` the tier becomes a build-time switch, which DP-A9 "
                        f"forbids: a tier is 'not switchable without a design-change'",
                    ))

        for blk in blocks:
            count += 1

            # ── R9 / R10 — fail CLOSED ───────────────────────────────────────
            if blk.broken:
                findings.append(Finding(
                    "R10" if "macro_rules" in blk.broken else "R9", blk.where,
                    f"this `impl DpAggregate` cannot be checked: {blk.broken}. A gate that skips "
                    f"what it cannot parse reports coverage it does not have — one odd brace "
                    f"inside a string hid a live generic escape (R2-4), and one macro body emits "
                    f"N impls this gate can only see once (R2-8)",
                ))
                continue

            # ── R7 — a parameter named after a taxonomy member ───────────────
            for g in blk.generics:
                if g in taxonomy:
                    findings.append(Finding(
                        "R7", blk.where,
                        f"generic parameter `{g}` shadows the taxonomy name `{g}`. `type Tier = "
                        f"{g}` then looks concrete and is not — this is V1-F1 restored by a "
                        f"one-character rename (R2-1), the likeliest accidental recurrence",
                    ))

            for rule, assoc, legal in (("R1", "Tier", tiers), ("R2", "Scope", scopes)):
                m = re.search(rf"\btype\s+{assoc}\s*=\s*([^;]+);", blk.body)
                if not m:
                    findings.append(Finding(
                        rule, blk.where,
                        f"no `type {assoc} = ..;` in this impl — the gate cannot tell which "
                        f"{assoc.lower()} this aggregate binds",
                    ))
                    continue
                rhs = m.group(1).strip()

                # ── R6 — the load-bearing rule ───────────────────────────────
                bound = [g for g in blk.generics if re.search(rf"\b{re.escape(g)}\b", rhs)]
                if re.search(r"\bSelf\b", rhs):
                    bound.append("Self")
                if bound:
                    findings.append(Finding(
                        "R6", blk.where,
                        f"`type {assoc} = {rhs}` names {', '.join(f'`{b}`' for b in bound)}, which "
                        f"this impl binds. To be generic the right-hand side MUST name something "
                        f"in scope, and the only things in scope are the impl's parameters and "
                        f"`Self` — so one aggregate name carries several {assoc.lower()}s, chosen "
                        f"by the caller at runtime. DP-A9: a tier is design-time, 'not "
                        f"configurable per player'",
                    ))
                    continue

                if last_segment(rhs) not in legal:
                    findings.append(Finding(
                        rule, blk.where,
                        f"`type {assoc} = {rhs}` does not name a declared {assoc.lower()} "
                        f"({', '.join(legal)})",
                    ))

            m = re.search(r"\bconst\s+TYPE_NAME\s*:[^=]*=\s*([^;]+);", blk.body)
            if not m:
                findings.append(Finding("R3", blk.where, "no `const TYPE_NAME` in this impl"))
                continue
            lit = re.fullmatch(r'\s*"((?:[^"\\]|\\.)*)"\s*', m.group(1), re.DOTALL)
            if not lit:
                findings.append(Finding(
                    "R3", blk.where,
                    f"`TYPE_NAME = {m.group(1).strip()}` is not a string literal. It is the "
                    f"aggregate token of the DP-Ch5 cache key: a computed name cannot be read "
                    f"without running the program, and cannot be checked for collisions at all",
                ))
                continue
            name = decode_rust_str(lit.group(1))
            if name in names:
                findings.append(Finding(
                    "R4", blk.where,
                    f"TYPE_NAME {name!r} is already bound at {names[name]}. Two impls under one "
                    f"name = two cache entries for one logical aggregate, under two coherency "
                    f"contracts (REC-102c's survives_store_outage among them). Compared by "
                    f"DECODED value, because rustc does",
                ))
            else:
                names[name] = blk.where
    return findings, count


# ─────────────────────────────────────────────────────────────────────────────
def self_test() -> int:
    """Drives the REAL `scan()` over synthetic files on disk.

    `V2-F1`: the previous version re-implemented R1/R2/R3 inline and R4 with a
    *different regex*, so it never touched `scan()`. Gutting `scan()`'s
    membership test to `if False:` left this printing *"non-vacuous in both
    directions"* while a live `V1-F1` escape sat in the tree and the gate
    reported `OK`. A self-test that does not drive the subject is `NV-3` at the
    scope level — it is the shape this repo has a standard about, committed
    inside the commit that was discharging it.
    """
    import tempfile

    tiers, scopes = ["T0", "T1", "T2", "T3"], ["RealityScope", "ChannelScope"]
    OK = "type Id = u64;"

    cases: list[tuple[str, str, str | None]] = [
        ("a plain, correct impl", f'''
            struct A;
            impl DpAggregate for A {{
                type Tier = T2; type Scope = RealityScope; {OK}
                const TYPE_NAME: &'static str = "a";
            }}''', None),
        ("the refuter's generic escape (V1-F1)", f'''
            impl<T: Tier, S: Scope> DpAggregate for W<T, S> {{
                type Tier = T; type Scope = S; {OK}
                const TYPE_NAME: &'static str = "w";
            }}''', "R6"),
        ("a generic parameter NAMED T2 (R2-1)", f'''
            impl<T2: Tier, RealityScope: Scope> DpAggregate for W<T2, RealityScope> {{
                type Tier = T2; type Scope = RealityScope; {OK}
                const TYPE_NAME: &'static str = "w2";
            }}''', "R7"),
        ("associated-type projection (R2-2)", f'''
            impl<A: Tier, B: Scope> DpAggregate for W<A, B> {{
                type Tier = <Self as Pick>::T2; type Scope = <Self as Pick>::RealityScope; {OK}
                const TYPE_NAME: &'static str = "w3";
            }}''', "R6"),
        ("a char literal must not blank the impl (R2-3)", f'''
            pub const QUOTE: char = '"';
            pub const OPEN: &str = "/*";
            impl<A: Tier, B: Scope> DpAggregate for Ledger<A, B> {{
                type Tier = A; type Scope = B; {OK}
                const TYPE_NAME: &'static str = "ledger";
            }}
            pub const CLOSE: &str = "*/";''', "R6"),
        ("an odd brace in a doc string must not hide it (R2-4)", f'''
            impl<A: Tier, B: Scope> DpAggregate for Evil<A, B> {{
                #[doc = "the cache key opens with a brace: dp:{{"]
                type Tier = A; type Scope = B; {OK}
                const TYPE_NAME: &'static str = "evil";
            }}''', "R6"),
        ("aliasing a tier name (R2-6)", f'''
            use dp::T3 as T2;
            impl DpAggregate for Wallet {{
                type Tier = T2; type Scope = RealityScope; {OK}
                const TYPE_NAME: &'static str = "wallet";
            }}''', "R8"),
        ("an impl inside a macro body (R2-8)", f'''
            macro_rules! agg {{ ($ty:ident) => {{
                impl DpAggregate for $ty {{
                    type Tier = dp::T2; type Scope = dp::RealityScope; {OK}
                    const TYPE_NAME: &'static str = "shared";
                }}
            }}; }}''', "R10"),
        ("a path-qualified tier is fine", f'''
            impl DpAggregate for B {{
                type Tier = dp::tier::T3; type Scope = crate::ChannelScope; {OK}
                const TYPE_NAME: &'static str = "b";
            }}''', None),
        ("a CONCRETE tier in a generic impl is fine", f'''
            impl<X: Send> DpAggregate for C<X> {{
                type Tier = T1; type Scope = ChannelScope; {OK}
                const TYPE_NAME: &'static str = "c";
            }}''', None),
        # These two exercise the MEMBERSHIP branch specifically: concrete, not
        # generic, not a taxonomy name. Without them, gutting `if last_segment(..)
        # not in legal:` to `if False:` left this whole self-test GREEN — the
        # branch had no case of its own, because every other R1/R2 expectation
        # was really testing R6 or the missing-declaration path. Found by biting.
        ("a concrete NON-tier as the tier", f'''
            impl DpAggregate for Y {{
                type Tier = MyCustomTier; type Scope = RealityScope; {OK}
                const TYPE_NAME: &'static str = "y";
            }}''', "R1"),
        ("a concrete NON-scope as the scope", f'''
            impl DpAggregate for Z {{
                type Tier = T0; type Scope = ZoneScope; {OK}
                const TYPE_NAME: &'static str = "z";
            }}''', "R2"),
        ("a wrapper around a tier is NOT a tier", f'''
            impl<T: Tier> DpAggregate for D<T> {{
                type Tier = Wrapper<T>; type Scope = RealityScope; {OK}
                const TYPE_NAME: &'static str = "d";
            }}''', "R6"),
        ("a computed TYPE_NAME", f'''
            impl DpAggregate for E {{
                type Tier = T0; type Scope = RealityScope; {OK}
                const TYPE_NAME: &'static str = NAMES[0];
            }}''', "R3"),
        ("no `type Tier` at all", f'''
            impl DpAggregate for F {{
                type Scope = RealityScope; {OK}
                const TYPE_NAME: &'static str = "f";
            }}''', "R1"),
        ("no TYPE_NAME at all", f'''
            impl DpAggregate for G {{
                type Tier = T0; type Scope = RealityScope; {OK}
            }}''', "R3"),
        ("a violation inside a COMMENT is not a violation", f'''
            // impl<T: Tier> DpAggregate for Bad<T> {{ type Tier = T; }}
            /* impl<T: Tier> DpAggregate for Worse<T> {{ type Tier = T; }} */
            impl DpAggregate for H {{
                type Tier = T1; type Scope = ChannelScope; {OK}
                const TYPE_NAME: &'static str = "h";
            }}''', None),
        ("an unrelated impl is ignored", '''
            impl Display for I { fn fmt(&self) -> R { Ok(()) } }''', None),
        ("a lifetime is not a char literal", f'''
            impl<'a> DpAggregate for J<'a> {{
                type Tier = T2; type Scope = RealityScope; {OK}
                const TYPE_NAME: &'static str = "j";
            }}''', None),
    ]

    bad: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for idx, (label, src, want) in enumerate(cases):
            f = tmp / f"case_{idx}.rs"
            f.write_bytes(src.encode("utf-8"))
            found, _ = scan([f], tiers, scopes)
            got = {x.rule for x in found}
            if want is None and got:
                bad.append(f"{label}: expected clean, got {sorted(got)}")
            elif want is not None and want not in got:
                bad.append(f"{label}: expected {want}, got {sorted(got) or 'nothing'}")

        # R4 is cross-block, and must compare DECODED values (R2-7).
        dup = tmp / "dup.rs"
        dup.write_bytes(('''
            impl DpAggregate for K { type Tier = T1; type Scope = RealityScope;
                type Id = u64; const TYPE_NAME: &'static str = "wallet"; }
            impl DpAggregate for L { type Tier = T3; type Scope = RealityScope;
                type Id = u64; const TYPE_NAME: &'static str = "walle\\u{74}"; }
        ''').encode("utf-8"))
        if "R4" not in {x.rule for x in scan([dup], tiers, scopes)[0]}:
            bad.append("R4: two impls sharing a TYPE_NAME by VALUE were not detected (R2-7)")

        # ...and must NOT fire on two genuinely different names.
        distinct = tmp / "distinct.rs"
        distinct.write_bytes(('''
            impl DpAggregate for M { type Tier = T1; type Scope = RealityScope;
                type Id = u64; const TYPE_NAME: &'static str = "m"; }
            impl DpAggregate for N { type Tier = T3; type Scope = RealityScope;
                type Id = u64; const TYPE_NAME: &'static str = "n"; }
        ''').encode("utf-8"))
        if scan([distinct], tiers, scopes)[0]:
            bad.append("R4: fired on two distinct TYPE_NAMEs — cry-wolf")

    # The parse of the closed sets must itself find something.
    if len(declared(TIER_DECL, "tier.rs")) < 4:
        bad.append("the tier taxonomy parsed fewer than 4 tiers from tier.rs")
    if len(declared(SCOPE_DECL, "scope.rs")) < 2:
        bad.append("the scope taxonomy parsed fewer than 2 scopes from scope.rs")

    # The exclusion must be ANCHORED (R2-5): a plausible in-crate path with the
    # same tail must NOT be excluded.
    decoy = REPO / "services" / "x" / "src" / "tests" / "ui" / "mod.rs"
    real = REPO / "crates" / "dp" / "tests" / "ui" / "two_tiers.rs"
    scanned, excluded = partition([decoy, real])
    if decoy not in scanned:
        bad.append("the fixture exclusion is not anchored: src/tests/ui/mod.rs was dropped (R2-5)")
    if real not in excluded:
        bad.append("the fixture exclusion does not cover crates/dp/tests/ui/")

    if bad:
        print("dp-aggregate-gate: SELF-TEST FAIL")
        for b in bad:
            print("  " + b)
        return 1
    print(f"dp-aggregate-gate: SELF-TEST PASS — {len(cases)} case(s) driven through the REAL "
          f"`scan()`, plus R4-by-value both ways, the taxonomy parse, and the anchored exclusion. "
          f"It flags the generic escape, a shadowing parameter, a projection, a char-literal and a "
          f"brace-in-string hiding attempt, an alias, a macro body, a wrapper and a computed name; "
          f"and does NOT flag a concrete tier in a generic impl, a path-qualified tier, a "
          f"lifetime, a commented-out violation or an unrelated impl.")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    if self_test() != 0:
        return 2

    tiers = declared(TIER_DECL, "tier.rs")
    scopes = declared(SCOPE_DECL, "scope.rs")

    if len(tiers) < 4 or len(scopes) < 2:
        print(f"dp-aggregate-gate: FAIL — parsed {len(tiers)} tier(s) and {len(scopes)} scope(s) "
              f"from crates/dp/src. DP-A5 closes the tier taxonomy at four and DP-A14 the scope "
              f"set at two; a short parse means the macro shape moved and every membership test "
              f"would compare against a truncated set.", file=sys.stderr)
        return 1

    files = all_rust_files()
    scanned, excluded = partition(files)

    # ── R5 — the SCOPE, as a set difference rather than a count ─────────────
    #
    # `V2-F2`: the old R5 fired only on `impls == 0`, so ANY scope collapse that
    # left one fixture standing passed. One added substring took 494 files to
    # 305 and hid a live escape. A count cannot see a scope; only the scope can.
    stray = [rel(p) for p in excluded if not rel(p).startswith(FIXTURE_DIR)]
    if stray:
        print(f"dp-aggregate-gate: FAIL — {len(stray)} file(s) were excluded that are not under "
              f"{FIXTURE_DIR}: {stray[:5]}", file=sys.stderr)
        return 1
    if not scanned:
        print("dp-aggregate-gate: FAIL — the scan has no subject.", file=sys.stderr)
        return 1

    findings, impls = scan(scanned, tiers, scopes)

    if impls == 0:
        print("dp-aggregate-gate: FAIL — no `impl DpAggregate` found in any committable .rs file. "
              "A scan over nothing passes trivially (NV-3).", file=sys.stderr)
        return 1

    if findings:
        print(f"dp-aggregate-gate: {len(findings)} finding(s) across {impls} `impl DpAggregate` "
              f"block(s)\n")
        for f in findings:
            print(f)
        print("\nONE aggregate name binds ONE tier and ONE scope. The type system cannot check")
        print("this: each monomorphisation is individually consistent and the contradiction lives")
        print("across them. See V1-F1 / R2-* in docs/plans/2026-08-06-game-tier-build-RUN-STATE.md.")
        return 1

    print(f"dp-aggregate-gate: OK — {impls} `impl DpAggregate` block(s) in {len(scanned)} .rs "
          f"file(s) ({len(excluded)} trybuild fixture(s) excluded); every one binds one of {tiers} "
          f"and one of {scopes}, with a literal, unique TYPE_NAME, and none reaches its tier "
          f"through a generic parameter, an alias or a macro body")
    return 0


if __name__ == "__main__":
    sys.exit(main())
