#!/usr/bin/env python3
"""dp-aggregate-gate — ONE aggregate name binds ONE tier and ONE scope.

WHY THIS EXISTS, AND WHY IT IS NOT A TYPE
-----------------------------------------
`crates/dp` makes `Tier` and `Scope` **associated types** on `DpAggregate`, and
slice 1 was sold to the PO on the claim that this makes a second tier
*unrepresentable*. A cold-start refuter broke that claim on 2026-08-07
(`V1-F1`), and the break is not subtle:

    pub struct PlayerWallet<T: Tier, S: Scope>(PhantomData<(T, S)>);
    impl<T: Tier, S: Scope> DpAggregate for PlayerWallet<T, S> {
        type Tier = T;  type Scope = S;
        const TYPE_NAME: &'static str = "player_wallet";   // ONE name, four tiers
    }

It compiled, ran, and selected the tier from an environment variable —
`survives_store_outage` flipping `false -> true`, which is **exactly** the
`REC-102c` promise the crate was written to make un-flippable. Two `impl`s
sharing one `TYPE_NAME` do the same thing without generics at all.

**The type system cannot see this, by construction.** Each monomorphisation is
individually consistent; the contradiction lives *across* monomorphisations, and
that is precisely the thing a type checker never compares. `TYPE_NAME` is the
aggregate token in the `DP-Ch5` cache key, so two tiers under one name means two
live cache entries for one logical aggregate under two different coherency
contracts. `DP-A9` says a tier is *"not configurable per player"*; a
`Box<dyn _>` picked per request is per-player configuration.

So the property is enforced where it is actually visible: **over the source**.

WHAT IT CHECKS
--------------
  R1  `type Tier = ...` names a member of the closed tier set
  R2  `type Scope = ...` names a member of the closed scope set
  R3  `TYPE_NAME` is a string LITERAL (a computed name cannot be checked, and it
      is a cache key — it must be readable without running the program)
  R4  no two `impl DpAggregate` blocks share a `TYPE_NAME`
  R5  the scan HAS A SUBJECT: the taxonomies parsed, and at least one real
      `impl DpAggregate` was found. A scan over nothing passes trivially, which
      is worse than no gate (`NV-3`).

THE CLOSED SETS ARE PARSED, NOT TYPED HERE
------------------------------------------
The legal tier names come from `declare_tier!` invocations in
`crates/dp/src/tier.rs`, and the legal scope names from the `impl Scope for _`
blocks in `scope.rs` — each taxonomy read at its own definition site, because
the two are declared differently and one assumed shape would leave the second
parse silently empty. A list typed into this file would be a fourth hand-written
copy of a taxonomy that already has three, and it would rot the day a tier is
added —
`projection-table-mirror-gate` exists because that happened with table names.
Parsing means **adding a tier extends this gate in the same edit**.

STATED LIMIT
------------
This is a source check over **this repository**. It cannot see a `DpAggregate`
impl in a crate that is not here. That limit is real and is why the honest claim
in `crates/dp` is now *"a single non-generic impl binds exactly one tier"* plus
*"this gate forbids the generic escape in-repo"* — not *"unrepresentable"*.

`crates/dp/tests/ui/` is EXCLUDED: those are `trybuild` fixtures whose whole
purpose is to contain code that must not compile. That is a structural property
of the directory (trybuild never builds them as part of any crate), not an
enumerated file list.

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

# trybuild fixture directories: code that exists in order to FAIL to compile.
_FIXTURE_PARTS = ("tests/ui/",)


# ─────────────────────────────────────────────────────────────────────────────
# Rust source handling
# ─────────────────────────────────────────────────────────────────────────────
def strip_comments(src: str) -> str:
    """Blank out `//`-lines and `/* */` blocks, preserving length and newlines.

    Length preservation matters: every offset computed downstream indexes back
    into the ORIGINAL text for line numbers. String literals are respected so a
    `"http://x"` does not eat the rest of the line.
    """
    out = list(src)
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == '"':
            i += 1
            while i < n and src[i] != '"':
                i += 2 if src[i] == "\\" else 1
            i += 1
        elif c == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                out[i] = " "
                i += 1
        elif c == "/" and i + 1 < n and src[i + 1] == "*":
            depth = 1
            out[i] = out[i + 1] = " "
            i += 2
            while i < n and depth:
                if src.startswith("/*", i):
                    depth += 1
                    out[i] = out[i + 1] = " "
                    i += 2
                elif src.startswith("*/", i):
                    depth -= 1
                    out[i] = out[i + 1] = " "
                    i += 2
                else:
                    if src[i] != "\n":
                        out[i] = " "
                    i += 1
        else:
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


class ImplBlock:
    def __init__(self, path: Path, line: int, header: str, body: str):
        self.path, self.line, self.header, self.body = path, line, header, body

    @property
    def where(self) -> str:
        return f"{str(self.path.relative_to(REPO)).replace(chr(92), '/')}:{self.line}"


def find_impls(path: Path, src: str) -> list[ImplBlock]:
    """Every `impl ... DpAggregate for ... { .. }` block in one file."""
    code = strip_comments(src)
    blocks: list[ImplBlock] = []
    for m in re.finditer(r"\bimpl\b", code):
        # Walk to the opening brace, skipping over any `<..>` generic groups so
        # a `Foo<{ N }>` const-generic cannot be mistaken for the body.
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
        if i < 0 or i >= n:
            continue
        header = code[m.start():i]
        if not re.search(r"\bDpAggregate\b", header):
            continue
        end = _balanced(code, i, "{", "}")
        if end < 0:
            continue
        blocks.append(ImplBlock(path, code.count("\n", 0, m.start()) + 1, header, code[i:end]))
    return blocks


# ─────────────────────────────────────────────────────────────────────────────
# The closed sets — PARSED from the crate, never typed here
# ─────────────────────────────────────────────────────────────────────────────
def declared(pattern: str, filename: str) -> list[str]:
    """Members of a closed taxonomy, read from its own DEFINITION SITE.

    The two taxonomies are declared differently — tiers through the
    `declare_tier!` macro, scopes as hand-written `impl Scope for _` — so each
    gets the pattern that matches where it is actually defined. Using one
    assumed shape for both would make the second parse silently empty, and R5
    is what would notice.
    """
    f = DP_SRC / filename
    if not f.is_file():
        print(f"dp-aggregate-gate: MISUSE — cannot read {f}", file=sys.stderr)
        sys.exit(2)
    src = strip_comments(f.read_text(encoding="utf-8"))
    return sorted(set(re.findall(pattern, src)))


TIER_DECL = r"declare_tier!\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)"
SCOPE_DECL = r"\bimpl\s+Scope\s+for\s+([A-Za-z_][A-Za-z0-9_]*)"


def last_segment(ty: str) -> str:
    """`crate::tier::T2` / `dp::T2` -> `T2`. Generic args are NOT stripped, so
    `Wrapper<T>` stays `Wrapper<T>` and fails the membership test, which is the
    behaviour we want."""
    return ty.strip().rstrip(";").split("::")[-1].strip()


# ─────────────────────────────────────────────────────────────────────────────
def rust_files() -> list[Path]:
    """Committable `.rs` files — same git-derived scope as no-absolute-host-paths."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "*.rs"],
            cwd=REPO, capture_output=True, text=True, check=True,
        ).stdout
        paths = [REPO / r for r in out.split("\0") if r]
    except (OSError, subprocess.CalledProcessError):
        paths = [p for p in REPO.rglob("*.rs") if "target" not in p.parts]
    keep = []
    for p in paths:
        s = str(p).replace("\\", "/")
        if any(part in s for part in _FIXTURE_PARTS):
            continue
        if p.is_file():
            keep.append(p)
    return keep


class Finding:
    def __init__(self, rule: str, where: str, detail: str):
        self.rule, self.where, self.detail = rule, where, detail

    def __str__(self) -> str:
        return f"  {self.rule}  {self.where}\n      {self.detail}"


def scan(files: list[Path], tiers: list[str], scopes: list[str]) -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    names: dict[str, str] = {}
    count = 0

    for path in files:
        try:
            src = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "DpAggregate" not in src:
            continue
        for blk in find_impls(path, src):
            count += 1

            for rule, assoc, legal in (("R1", "Tier", tiers), ("R2", "Scope", scopes)):
                m = re.search(rf"\btype\s+{assoc}\s*=\s*([^;]+);", blk.body)
                if not m:
                    findings.append(Finding(
                        rule, blk.where,
                        f"no `type {assoc} = ..;` in this impl — the gate cannot tell which "
                        f"{assoc.lower()} this aggregate binds",
                    ))
                    continue
                seg = last_segment(m.group(1))
                if seg not in legal:
                    findings.append(Finding(
                        rule, blk.where,
                        f"`type {assoc} = {m.group(1).strip()}` does not name a declared "
                        f"{assoc.lower()} ({', '.join(legal)}). A generic parameter here lets ONE "
                        f"aggregate name carry several {assoc.lower()}s, chosen by the caller at "
                        f"runtime — DP-A9: a tier is design-time, 'not configurable per player'",
                    ))

            m = re.search(r"\bconst\s+TYPE_NAME\s*:[^=]*=\s*([^;]+);", blk.body)
            if not m:
                findings.append(Finding("R3", blk.where, "no `const TYPE_NAME` in this impl"))
                continue
            lit = re.fullmatch(r'\s*"([^"]*)"\s*', m.group(1))
            if not lit:
                findings.append(Finding(
                    "R3", blk.where,
                    f"`TYPE_NAME = {m.group(1).strip()}` is not a string literal. It is the "
                    f"aggregate token of the DP-Ch5 cache key: a computed name cannot be read "
                    f"without running the program, and cannot be checked for collisions at all",
                ))
                continue
            name = lit.group(1)
            if name in names:
                findings.append(Finding(
                    "R4", blk.where,
                    f"TYPE_NAME {name!r} is already bound at {names[name]}. Two impls under one "
                    f"name = two cache entries for one logical aggregate, under two coherency "
                    f"contracts (REC-102c's survives_store_outage among them)",
                ))
            else:
                names[name] = blk.where
    return findings, count


# ─────────────────────────────────────────────────────────────────────────────
def self_test() -> int:
    tiers, scopes = ["T0", "T1", "T2", "T3"], ["RealityScope", "ChannelScope"]
    cases: list[tuple[str, str, str | None]] = [
        ("a plain, correct impl", """
            struct A;
            impl DpAggregate for A {
                type Tier = T2; type Scope = RealityScope; type Id = u64;
                const TYPE_NAME: &'static str = "a";
            }""", None),
        ("the refuter's generic escape", """
            impl<T: Tier, S: Scope> DpAggregate for W<T, S> {
                type Tier = T; type Scope = S; type Id = u64;
                const TYPE_NAME: &'static str = "w";
            }""", "R1"),
        ("a generic SCOPE only", """
            impl<S: Scope> DpAggregate for W<S> {
                type Tier = T1; type Scope = S; type Id = u64;
                const TYPE_NAME: &'static str = "w2";
            }""", "R2"),
        ("a path-qualified tier is fine", """
            impl DpAggregate for B {
                type Tier = dp::tier::T3; type Scope = crate::ChannelScope; type Id = u64;
                const TYPE_NAME: &'static str = "b";
            }""", None),
        ("a wrapper around a tier is NOT a tier", """
            impl<T: Tier> DpAggregate for C<T> {
                type Tier = Wrapper<T>; type Scope = RealityScope; type Id = u64;
                const TYPE_NAME: &'static str = "c";
            }""", "R1"),
        ("a computed TYPE_NAME", """
            impl DpAggregate for D {
                type Tier = T0; type Scope = RealityScope; type Id = u64;
                const TYPE_NAME: &'static str = NAMES[0];
            }""", "R3"),
        ("a violation inside a COMMENT is not a violation", """
            // impl<T: Tier> DpAggregate for Bad<T> { type Tier = T; }
            /* impl<T: Tier> DpAggregate for Worse<T> { type Tier = T; } */
            impl DpAggregate for E {
                type Tier = T1; type Scope = ChannelScope; type Id = u64;
                const TYPE_NAME: &'static str = "e";
            }""", None),
        ("an unrelated impl is ignored", """
            impl Display for F { fn fmt(&self) -> R { Ok(()) } }""", None),
    ]

    bad: list[str] = []
    for label, src, want in cases:
        tmp = REPO / "scripts" / ".dp_aggregate_gate_selftest.rs"
        blocks = find_impls(tmp, src)
        got: set[str] = set()
        for blk in blocks:
            for rule, assoc, legal in (("R1", "Tier", tiers), ("R2", "Scope", scopes)):
                m = re.search(rf"\btype\s+{assoc}\s*=\s*([^;]+);", blk.body)
                if m and last_segment(m.group(1)) not in legal:
                    got.add(rule)
            m = re.search(r"\bconst\s+TYPE_NAME\s*:[^=]*=\s*([^;]+);", blk.body)
            if m and not re.fullmatch(r'\s*"([^"]*)"\s*', m.group(1)):
                got.add("R3")
        if want is None and got:
            bad.append(f"{label}: expected clean, got {sorted(got)}")
        elif want is not None and want not in got:
            bad.append(f"{label}: expected {want}, got {sorted(got) or 'nothing'}")

    # R4 is cross-block, so it gets its own case.
    dup = """
        impl DpAggregate for G { type Tier = T1; type Scope = RealityScope;
            type Id = u64; const TYPE_NAME: &'static str = "same"; }
        impl DpAggregate for H { type Tier = T3; type Scope = RealityScope;
            type Id = u64; const TYPE_NAME: &'static str = "same"; }
    """
    seen: set[str] = set()
    collided = False
    for blk in find_impls(REPO / "x.rs", dup):
        m = re.search(r'const\s+TYPE_NAME\s*:[^=]*=\s*"([^"]*)"', blk.body)
        if m:
            collided |= m.group(1) in seen
            seen.add(m.group(1))
    if not collided:
        bad.append("R4: two impls sharing a TYPE_NAME were not detected")

    # The parse of the closed sets must itself find something.
    if len(declared(TIER_DECL, "tier.rs")) < 4:
        bad.append("the tier taxonomy parsed fewer than 4 tiers from tier.rs")
    if len(declared(SCOPE_DECL, "scope.rs")) < 2:
        bad.append("the scope taxonomy parsed fewer than 2 scopes from scope.rs")

    if bad:
        print("dp-aggregate-gate: SELF-TEST FAIL")
        for b in bad:
            print("  " + b)
        return 1
    print(f"dp-aggregate-gate: SELF-TEST PASS — {len(cases)} block case(s) + R4 + the taxonomy "
          f"parse. It flags the refuter's generic escape, a generic scope, a wrapper type and a "
          f"computed name, and does NOT flag a path-qualified tier, a commented-out violation or "
          f"an unrelated impl (non-vacuous in both directions).")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    if self_test() != 0:
        return 2

    tiers = declared(TIER_DECL, "tier.rs")
    scopes = declared(SCOPE_DECL, "scope.rs")

    # ── R5 — the scan must have had a subject ────────────────────────────────
    if len(tiers) < 4 or len(scopes) < 2:
        print(f"dp-aggregate-gate: FAIL — parsed {len(tiers)} tier(s) and {len(scopes)} scope(s) "
              f"from crates/dp/src. DP-A5 closes the tier taxonomy at four and DP-A14 the scope "
              f"set at two; a short parse means the macro shape moved and every membership test "
              f"below would be comparing against a truncated set.", file=sys.stderr)
        return 1

    files = rust_files()
    findings, impls = scan(files, tiers, scopes)

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
        print("across them. See V1-F1 in docs/plans/2026-08-06-game-tier-build-RUN-STATE.md.")
        return 1

    print(f"dp-aggregate-gate: OK — {impls} `impl DpAggregate` block(s) in {len(files)} .rs "
          f"file(s); every one binds one of {tiers} and one of {scopes}, with a literal, "
          f"unique TYPE_NAME")
    return 0


if __name__ == "__main__":
    sys.exit(main())
