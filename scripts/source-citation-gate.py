#!/usr/bin/env python3
"""source-citation-gate — a citation in SOURCE must name what DEFINES the thing.

THE DEFECT THIS EXISTS TO PREVENT (`A-2`, supplement §3 — `D-512`)
-------------------------------------------------------------------
`crates/actor-hub/src/actor.rs` cited `dp-kernel/src/entity_status.rs` as where
`GoneState` ships. actor-hub.md §3.3 had ALREADY recorded that the type moved to
`crates/entity-existence`, and fixed the contract's copy of the citation — while
the source copy went unread. `citation-gate` governs DOCUMENTS, so nothing
reached a citation living in a `//!` header.

WHY THE TWO OBVIOUS CHECKS DO NOT WORK
--------------------------------------
Measured against that exact defect, before this file was written:

  does the cited FILE RESOLVE?      MISSES — the file exists
  does the file MENTION the symbol? MISSES — 38 occurrences of `GoneState`
  does the file DEFINE the symbol?  CATCHES — the only line is
                                    `pub use entity_existence::{GoneState, …}`

**A `pub use` is not a definition**, and that is the entire discriminating
power of this gate. A gate built on either of the first two would have been
written for `D-512`, shipped, and been unable to catch it.

THE CONVENTION IS HALF THE MECHANISM
------------------------------------
A file citation in a source doc comment names its subject:

    entity-existence/src/lib.rs#GoneState

Without the `#Symbol` there is nothing to look for, and this gate would have no
subject at all — vacuous by construction. So the convention landed FIRST, on the
hub's six citations, and the gate checks what the convention makes checkable.

An unsuffixed `path.rs` citation is NOT reported. That is a deliberate MISS
rather than a silent one: reporting them would make the gate a style enforcer
over every comment in the tree on its first run, which is the cry-wolf direction
that gets a gate switched off. What is enforced is that a citation which CLAIMS
a definition has one.

RESOLUTION IS CRATE-RELATIVE **AND** REPO-RELATIVE
--------------------------------------------------
`entity-existence/src/lib.rs` is really `crates/entity-existence/src/lib.rs`.
A resolver trying only one of the two would report all five of the hub's
citations as missing — measured, and the reason both are tried.

HONEST LIMIT, INHERITED FROM `citation-gate`
--------------------------------------------
This proves a citation names a file that DEFINES the symbol. It never proves
the sentence around it is true.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# A directory, recursive — never an enumerated file list (NV-3).
GUARDED_TREE = "crates/actor-hub/src"

PRAGMA = "source-citation-gate: ok"

# `some/path/file.rs#Symbol`, inside a comment. The symbol is what makes it
# checkable; a citation without one is out of scope, see the docstring.
CITE_RE = re.compile(r"(?P<path>[A-Za-z0-9_./-]+\.rs)#(?P<sym>[A-Za-z_][A-Za-z0-9_]*)")

# What COUNTS as defining a symbol. `pub use` is deliberately absent — it is the
# whole point.
def _defines(text: str, sym: str) -> bool:
    kinds = r"(?:enum|struct|trait|type|const|fn|static|mod|union)"
    return re.search(rf"\bpub(?:\([^)]*\))?\s+{kinds}\s+{re.escape(sym)}\b", text) is not None \
        or re.search(rf"\bmacro_rules!\s+{re.escape(sym)}\b", text) is not None


def _resolve(path: str) -> Path | None:
    """Repo-relative first, then crate-relative. Both, or five false alarms."""
    for cand in (REPO / path, REPO / "crates" / path):
        if cand.is_file():
            return cand
    return None


class Finding:
    def __init__(self, path: str, line: int, cite: str, why: str):
        self.path, self.line, self.cite, self.why = path, line, cite, why

    def __str__(self) -> str:
        return f"  {self.path}:{self.line}  `{self.cite}` — {self.why}"


def _pragma_covers(raw: list[str], idx: int) -> bool:
    """The contiguous comment block above, not a fixed window (NV-6)."""
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


def scan_source(path: str, src: str, resolve=None) -> list[Finding]:
    """`resolve` is injectable so the self-test can drive it with no filesystem."""
    res = resolve or _resolve
    raw = src.split("\n")
    out: list[Finding] = []
    for i, line in enumerate(raw):
        stripped = line.strip()
        if not stripped.startswith(("//", "/*", "*")):
            continue
        for m in CITE_RE.finditer(line):
            cite = f"{m.group('path')}#{m.group('sym')}"
            if _pragma_covers(raw, i):
                continue
            target = res(m.group("path"))
            if target is None:
                out.append(Finding(path, i + 1, cite,
                                   "no such file, repo-relative or crate-relative"))
                continue
            text = target if isinstance(target, str) else target.read_text(
                encoding="utf-8", errors="replace")
            if not _defines(text, m.group("sym")):
                out.append(Finding(
                    path, i + 1, cite,
                    "that file does not DEFINE it — a `pub use` re-export is not a "
                    "definition, which is exactly how D-512 shipped"))
    return out


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
        print(f"source-citation-gate: cannot ask git what is staged ({e})")
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
    cited = 0
    files = _rust_files(args.staged)
    for p in files:
        rel = str(p.relative_to(REPO)).replace("\\", "/")
        src = p.read_text(encoding="utf-8", errors="replace")
        cited += sum(1 for line in src.split("\n")
                     if line.strip().startswith(("//", "/*", "*"))
                     for _ in CITE_RE.finditer(line))
        findings.extend(scan_source(rel, src))

    if findings:
        print(f"source-citation-gate: {len(findings)} finding(s)\n")
        for f in findings:
            print(f)
        print(
            "\nA source citation names the file that DEFINES its subject. A `pub use`\n"
            "re-export is not a definition — that distinction is the whole gate, because\n"
            "`D-512` cited a file that existed and mentioned the symbol 38 times.\n"
            f"A genuine exception carries `{PRAGMA} — <reason>` in the comment block above."
        )
        return 1

    print(
        f"source-citation-gate: OK — {cited} symbol-bearing citation(s) across "
        f"{len(files)} file(s) under {GUARDED_TREE}; each names a file that defines it"
    )
    return 0


# ── non-vacuity ──────────────────────────────────────────────────────────────

def self_test() -> int:
    failures = 0

    def case(label: str, src: str, want: int, resolve=None) -> None:
        nonlocal failures
        got = len(scan_source("probe.rs", src, resolve=resolve))
        if got != want:
            failures += 1
            print(f"  FAIL {label}: {got} finding(s), want {want}")
        else:
            print(f"  ok   {label}")

    def fake(defines: str):
        return lambda path: defines if path == "a/src/lib.rs" else None

    # ── the bite: `D-512`'s exact shape ──────────────────────────────────
    case("a re-export is NOT a definition — D-512's shape",
         "//! shipped: a/src/lib.rs#GoneState",
         1, fake("pub use entity_existence::{GoneState, higher, reduce};"))
    case("...and a MENTION is not one either",
         "//! shipped: a/src/lib.rs#GoneState",
         1, fake("// GoneState appears here 38 times\nlet x = GoneState::Active;"))
    case("a real definition is silent",
         "//! shipped: a/src/lib.rs#GoneState",
         0, fake("pub enum GoneState { Active }"))
    case("a file that does not resolve is reported",
         "//! shipped: nope/src/lib.rs#GoneState", 1, fake(""))

    # ── every definition kind the tree actually uses ─────────────────────
    # The symbol is passed EXPLICITLY. The first version derived it from the
    # declaration with a regex, and that regex read `pub` out of
    # `pub(crate) struct EntityId` and `u16` out of `pub type Q = u16` — two
    # cases failing on the CASE's own bug while the gate was correct. **A case
    # that computes its own expectation can be wrong in the same direction as
    # the thing it is checking.**
    for kind, decl, sym in (("struct", "pub struct EntityId(u64);", "EntityId"),
                            ("enum", "pub enum Layer { A }", "Layer"),
                            ("fn", "pub fn fold() {}", "fold"),
                            ("type", "pub type Q = u16;", "Q"),
                            ("const", "pub const MAX: u8 = 32;", "MAX"),
                            ("trait", "pub trait Reader {}", "Reader"),
                            ("restricted pub", "pub(crate) struct Inner(u8);", "Inner")):
        case(f"a {kind} definition is silent",
             f"//! see a/src/lib.rs#{sym}", 0, fake(decl))

    # ── the cry-wolf direction ───────────────────────────────────────────
    case("a citation with NO symbol is out of scope, deliberately",
         "//! see a/src/lib.rs for the reason", 0, fake(""))
    case("a citation in CODE, not a comment, is not a citation",
         'let s = "a/src/lib.rs#GoneState";', 0, fake(""))
    # **A symbol that is a PREFIX of a defined one is not that symbol.** The
    # word boundary is what says so, and nothing reached it until this case.
    case("a longer name is not the symbol",
         "//! see a/src/lib.rs#GoneState", 1, fake("pub enum GoneStateExtra { }"))
    # ...and the pragma has TWO branches. Every case put it in the block
    # above, so the same-line branch could be deleted with the suite green.
    case("the pragma exempts on the citation line itself",
         f"//! shipped: a/src/lib.rs#GoneState  // {PRAGMA} — on purpose",
         0, fake("pub use x::GoneState;"))
    case("the pragma exempts, from the comment block above",
         f"// {PRAGMA} — cited for the re-export ON PURPOSE, and here is a\n"
         "// reason long enough that a fixed window would have cut it\n"
         "//! shipped: a/src/lib.rs#GoneState",
         0, fake("pub use x::GoneState;"))

    # ── resolution must try BOTH roots, or it cries wolf five times ──────
    hub = REPO / GUARDED_TREE
    real = []
    for p in sorted(hub.rglob("*.rs")):
        rel = str(p.relative_to(REPO)).replace("\\", "/")
        real.extend(scan_source(rel, p.read_text(encoding="utf-8", errors="replace")))
    if real:
        failures += 1
        print(f"  FAIL the shipped hub reports {len(real)} finding(s) — cry wolf")
        for f in real:
            print(f"       {f}")
    else:
        print("  ok   the shipped hub reports nothing, so the rule does not cry wolf")

    # ...and it must have a SUBJECT, or the silence above means nothing.
    subject = 0
    for p in sorted(hub.rglob("*.rs")):
        for line in p.read_text(encoding="utf-8", errors="replace").split("\n"):
            if line.strip().startswith(("//", "/*", "*")):
                subject += len(CITE_RE.findall(line))
    if subject == 0:
        failures += 1
        print("  FAIL there are ZERO symbol-bearing citations — the gate has no subject")
    else:
        print(f"  ok   the gate has a subject: {subject} symbol-bearing citation(s)")

    # ...and crate-relative resolution genuinely resolves one of them.
    if _resolve("entity-existence/src/lib.rs") is None:
        failures += 1
        print("  FAIL crate-relative resolution does not reach a real crate file")
    else:
        print("  ok   crate-relative resolution reaches a real crate file")

    if failures:
        print(f"\nsource-citation-gate --self-test: {failures} rule(s) did not behave")
        return 1
    print("\nsource-citation-gate --self-test: every rule bites, and none cries wolf")
    return 0


if __name__ == "__main__":
    sys.exit(main())
