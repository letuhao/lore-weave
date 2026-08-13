#!/usr/bin/env python
"""DP-COV — every data-plane invariant is traceable to a guard AND to a test.

Why this exists
---------------
`docs/03_planning/LLM_MMO_RPG/06_data_plane/` declares 84 invariants across four
families (`DP-A`, `DP-R`, `DP-T`, `DP-Ch`). The repo's own convention for a
durable rule is stated in `docs/standards/README.md` §C:

    Durable `INV-<id>` rules cited **at the enforcement site and in a proving
    test**. Grep an ID to find both its guard and its test.

Nothing measured whether the data plane obeyed it. Measured by hand on
2026-08-13: **32 of 84 could not be grepped to any code, SQL or gate file at
all** -- and a hand count is exactly the thing that goes stale, so it is a gate
now instead of a sentence.

TWO TIERS, because the convention asks for two things
-----------------------------------------------------
* **sited**  -- the id appears in a non-test code/SQL/gate file. Traceability.
* **proven** -- the id appears in a TEST: under a `tests/` dir, in a
  `test_*.py`, inside a `#[cfg(test)]` module, or inside a `self_test`/
  `selftest` function.

An id that is *sited* but not *proven* is the `// TODO(DP-Ch9007)` case: you can
find it, and nothing defends it. **The strict ratchet is on `proven`**, because
that is the tier a comment cannot satisfy.

A note on why comments COUNT for `sited`
----------------------------------------
The first draft of this gate's spec said to strip comments and count only code.
That was wrong, and wrong in a direction that would have inverted the whole
exercise: in this repo the citation *is* a comment beside the guard (`INV-KAL`,
`INV-T2`, every `DP-` reference in `crates/`). Stripping them would have scored
the convention itself as zero coverage. The rule being misapplied -- *a comment
is not a mechanism* -- is about a comment claimed AS the enforcement, which is a
different thing from a comment POINTING AT it. Hence two tiers.

    python scripts/dp-invariant-coverage-gate.py            # gate
    python scripts/dp-invariant-coverage-gate.py --list     # per-id inventory
    python scripts/dp-invariant-coverage-gate.py --regen    # print baselines
    python scripts/dp-invariant-coverage-gate.py --self-test
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SELF = Path(__file__).name
ROOT = Path(__file__).resolve().parents[1]
DP_DOCS = ROOT / "docs" / "03_planning" / "LLM_MMO_RPG" / "06_data_plane"

ID_RE = re.compile(r"DP-(?:A|R|T|Ch)\d+")
#: A DECLARATION is a heading. A mention in a paragraph is a reference, and a
#: mention in a numbering instruction is not even that -- see PHANTOM_OK.
HEADING_RE = re.compile(r"^#+\s+\**`?(DP-(?:A|R|T|Ch)\d+)", re.M)

FAMILIES = ("DP-A", "DP-R", "DP-T", "DP-Ch")

#: Ids MENTIONED in the tier's docs that are deliberately NOT declarations, with
#: the reason. Measured 2026-08-13: both are `DP-R9`/`DP-R10`, and neither is a
#: rule. Without this the gate would demand code for an invariant the tier
#: explicitly REFUSED, which is worse than missing coverage -- it is coverage
#: pointing the wrong way.
#:
#: Each row carries a SHRINK ARM (see `check_phantoms`): if the id ever becomes a
#: real heading, the row must go.
PHANTOM_OK: dict[str, str] = {
    "DP-R9": "not a rule. Appears as a PLACEHOLDER in the numbering instruction "
             "(11_access_pattern_rules.md: \"A new stable ID `DP-R9`, `DP-R10`, ... is "
             "assigned\"), and 99_open_questions.md records that a proposed DP-R9 "
             "subscribe-completion rule was REJECTED under the G4a decision",
    "DP-R10": "not a rule. The second placeholder in the same numbering instruction; "
              "never proposed, never declared",
}

#: Where a citation may live. Deliberately a set of ROOTS plus a suffix filter
#: rather than a file list: a crate added tomorrow is in scope by construction.
CODE_ROOTS = (
    ("crates", {".rs"}),
    ("services", {".rs", ".go", ".py", ".ts"}),
    ("contracts/migrations", {".sql"}),
    ("migrations", {".sql"}),
    ("scripts", {".py", ".sh"}),
    ("lints", {".rs", ".toml", ".sh"}),
)

#: REACH FLOORS. A walk that reaches nothing is byte-identical to full coverage,
#: exit code included -- so the only honest floor is on what was WALKED, never on
#: what was found. Both measured 2026-08-13 (84 declared, 3196 files).
MIN_DECLARED = 60
MIN_FILES = 800

#: The ratchets, per family: (uncited, unproven). Measured 2026-08-13.
#: BOTH DIRECTIONS RED. A ratchet that only reds upward never falls, and one
#: that only reds downward is a wall -- this is a worklist, so it must shrink and
#: must be seen to shrink.
BASELINE: dict[str, tuple[int, int]] = {
    "DP-A": (7, 11),
    "DP-R": (1, 0),
    "DP-T": (0, 0),
    "DP-Ch": (25, 36),
}


# ── the corpus ────────────────────────────────────────────────────────────────

def declared() -> dict[str, str]:
    """`{id: file}` for every id DECLARED by a heading in the tier's docs."""
    out: dict[str, str] = {}
    for md in sorted(DP_DOCS.glob("*.md")):
        text = md.read_text(encoding="utf-8", errors="replace")
        for m in HEADING_RE.finditer(text):
            out.setdefault(m.group(1), md.name)
    return out


def mentioned() -> set[str]:
    """Every id that appears ANYWHERE in the tier's docs."""
    out: set[str] = set()
    for md in sorted(DP_DOCS.glob("*.md")):
        out |= set(ID_RE.findall(md.read_text(encoding="utf-8", errors="replace")))
    return out


def _is_test_path(p: Path) -> bool:
    parts = p.as_posix()
    return ("/tests/" in parts or "/test/" in parts
            or p.name.startswith("test_") or p.name.endswith("_test.go")
            or p.stem.endswith("_test"))


def _test_region(p: Path, text: str) -> str:
    """The part of `text` that is a TEST, for a file that is not wholly one.

    Rust: everything from the first `#[cfg(test)]`. Python/shell: the body of a
    `self_test`/`selftest` definition onward. Coarse on purpose -- the failure
    direction is to call a citation *proven* slightly too readily, and the strict
    tier is still strictly harder to satisfy than `sited`.
    """
    if p.suffix == ".rs":
        i = text.find("#[cfg(test)]")
        return text[i:] if i >= 0 else ""
    m = re.search(r"^(?:def\s+self_?test|self_?test\s*\(\)\s*\{)", text, re.M)
    return text[m.start():] if m else ""


def walk() -> tuple[dict[str, set[str]], dict[str, set[str]], int]:
    """`(sited, proven, n_files)` — each maps id -> the files citing it."""
    sited: dict[str, set[str]] = {}
    proven: dict[str, set[str]] = {}
    n = 0
    for rel, exts in CODE_ROOTS:
        base = ROOT / rel
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix not in exts:
                continue
            sp = p.as_posix()
            if "/node_modules/" in sp or "/target/" in sp or "/.bite-" in sp:
                continue
            # **EXCLUDE THIS FILE.** Its self-test writes fixture ids into
            # synthetic trees, and `scripts/` is in the walk -- so it read its own
            # source and reported three real DP-A ids as `sited|proven`, sourced to
            # itself. Three real invariants certified by a fixture, in the gate
            # built to catch exactly that. `gate-self-tests.discover()` carries
            # the same exclusion, for the same reason, and says so too.
            if p.name == SELF:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            n += 1
            ids = set(ID_RE.findall(text))
            if not ids:
                continue
            where = p.relative_to(ROOT).as_posix()
            whole_test = _is_test_path(p)
            region = text if whole_test else _test_region(p, text)
            tested = set(ID_RE.findall(region)) if region else set()
            for i in ids:
                if not whole_test:
                    sited.setdefault(i, set()).add(where)
                if i in tested:
                    proven.setdefault(i, set()).add(where)
    return sited, proven, n


def family_of(i: str) -> str:
    return "DP-Ch" if i.startswith("DP-Ch") else i[:4]


# ── the rules ─────────────────────────────────────────────────────────────────

def check_phantoms(decl: dict[str, str], seen: set[str]) -> list[str]:
    """An id mentioned but never declared, and the SHRINK ARM on the exemptions."""
    problems = []
    for i in sorted(seen - set(decl)):
        if i not in PHANTOM_OK:
            problems.append(
                f"{i} is referenced in the data-plane docs but DECLARED BY NO HEADING. "
                f"Either it is a real rule missing its `## {i}` section, or it is prose — "
                f"give it a PHANTOM_OK row saying which.")
    # ...and a row whose id became real, or stopped being mentioned, is dead.
    for i, why in sorted(PHANTOM_OK.items()):
        if i in decl:
            problems.append(
                f"PHANTOM_OK[{i}] says it is not a rule, but it now has a `## {i}` "
                f"heading in {decl[i]}. It became one — delete the row and let the "
                f"coverage rules see it.")
        elif i not in seen:
            problems.append(
                f"PHANTOM_OK[{i}] exempts an id the docs no longer mention anywhere. "
                f"It exempts nothing, and would exempt it again the day it returns. "
                f"Delete the row. (reason was: {why[:60]}…)")
    return problems


def evaluate() -> dict:
    decl = declared()
    seen = mentioned()
    sited, proven, n_files = walk()
    per: dict[str, dict] = {}
    for fam in FAMILIES:
        ids = sorted(i for i in decl if family_of(i) == fam)
        per[fam] = {
            "declared": ids,
            "uncited": [i for i in ids if i not in sited],
            "unproven": [i for i in ids if i not in proven],
        }
    return {"decl": decl, "seen": seen, "sited": sited, "proven": proven,
            "n_files": n_files, "per": per}


def run() -> int:
    st = evaluate()
    decl, per, n_files = st["decl"], st["per"], st["n_files"]

    # REACH FLOORS FIRST, and they exit 2 (misuse), not 1 (violation). A gate
    # that reports "0 uncited" because it read nothing looks exactly like a gate
    # reporting real success.
    if len(decl) < MIN_DECLARED:
        print(f"[dp-coverage] MISUSE — only {len(decl)} declared invariant(s) parsed from "
              f"{DP_DOCS.relative_to(ROOT).as_posix()} (floor {MIN_DECLARED}, measured 84).\n"
              f"  The heading form changed, or the directory moved. Zero declared ids means "
              f"every family reports full coverage.", file=sys.stderr)
        return 2
    if n_files < MIN_FILES:
        print(f"[dp-coverage] MISUSE — the citation walk reached {n_files} file(s) "
              f"(floor {MIN_FILES}, measured 3196). A walk that reaches nothing is "
              f"byte-identical to full coverage.", file=sys.stderr)
        return 2

    problems = check_phantoms(decl, st["seen"])

    for fam in FAMILIES:
        base_unc, base_unp = BASELINE[fam]
        unc, unp = len(per[fam]["uncited"]), len(per[fam]["unproven"])
        if unc > base_unc:
            problems.append(
                f"{fam}: {unc} invariant(s) cited NOWHERE, baseline {base_unc}. New: "
                f"{', '.join(per[fam]['uncited'][-6:])}")
        elif unc < base_unc:
            problems.append(
                f"{fam}: PROGRESS — {unc} uncited, baseline {base_unc}. Lower BASELINE"
                f"[{fam!r}] to ({unc}, {unp}) and say what closed them.")
        if unp > base_unp:
            problems.append(
                f"{fam}: {unp} invariant(s) have no PROVING TEST, baseline {base_unp}.")
        elif unp < base_unp:
            problems.append(
                f"{fam}: PROGRESS — {unp} unproven, baseline {base_unp}. Lower BASELINE"
                f"[{fam!r}] to ({unc}, {unp}).")

    if problems:
        print("[dp-coverage] FAIL:")
        for p in problems:
            print(f"    {p}")
        return 1

    tot_unc = sum(len(per[f]["uncited"]) for f in FAMILIES)
    tot_unp = sum(len(per[f]["unproven"]) for f in FAMILIES)
    print(f"[dp-coverage] PASS — {len(decl)} declared invariant(s) across {len(FAMILIES)} "
          f"famil(ies), {n_files} file(s) walked.")
    print(f"  sited:  {len(decl) - tot_unc}/{len(decl)}   "
          f"proven: {len(decl) - tot_unp}/{len(decl)}   "
          f"({len(PHANTOM_OK)} non-rule mention(s) exempted)")
    return 0


def show_list() -> int:
    st = evaluate()
    for fam in FAMILIES:
        d = st["per"][fam]
        print(f"\n{fam}  —  {len(d['declared'])} declared, "
              f"{len(d['uncited'])} uncited, {len(d['unproven'])} unproven")
        for i in d["declared"]:
            s = "sited " if i not in d["uncited"] else "  —   "
            p = "proven" if i not in d["unproven"] else "  —   "
            where = sorted(st["proven"].get(i) or st["sited"].get(i) or [])[:1]
            print(f"  [{s}|{p}] {i:10} {where[0] if where else ''}")
    return 0


def regen() -> int:
    st = evaluate()
    print("BASELINE: dict[str, tuple[int, int]] = {")
    for fam in FAMILIES:
        d = st["per"][fam]
        print(f'    "{fam}": ({len(d["uncited"])}, {len(d["unproven"])}),')
    print("}")
    print(f"# files walked: {st['n_files']}   declared: {len(st['decl'])}")
    return 0


# ── self-test ─────────────────────────────────────────────────────────────────

def self_test() -> int:
    import tempfile
    failures = 0

    # **THIS FILE MUST NOT NAME A REAL INVARIANT.** Its prose and fixtures are
    # full of ids, and an id in this file is indistinguishable from a citation.
    # Self-exclusion hides that from the ORIGINAL and not from a COPY -- which is
    # what `gate-bite-harness` runs, so every mutant measured a different tree
    # than the shipped baseline describes and three ratchet arms survived on the
    # difference. The 9000 range is reserved for examples and cannot be declared.
    own = set(ID_RE.findall(Path(__file__).read_text(encoding="utf-8", errors="replace")))
    real_here = sorted(i for i in own
                       if not re.fullmatch(r"DP-(?:A|R|T|Ch)9\d{3}", i)
                       and i not in PHANTOM_OK)
    if real_here:
        failures += 1
        print(f"  FAIL this file names real invariant id(s) {real_here} — a copy of it "
              f"(which is what the mutation harness runs) counts them as citations. "
              f"Use the reserved 9000 range for examples.")
    else:
        print("  ok   this file names no real invariant, so a copy of it certifies nothing")

    def ok(name: str, cond: bool, detail: str = "") -> None:
        nonlocal failures
        if cond:
            print(f"  ok   {name}")
        else:
            failures += 1
            print(f"  FAIL {name}{(': ' + detail) if detail else ''}")

    print("dp-invariant-coverage-gate --self-test")

    # ── the declaration rule: a HEADING declares, a mention does not ──────────
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        (t / "01.md").write_text(
            "## DP-A9001\nbody\n\n### `DP-Ch9007`\nbody mentioning DP-A9099 in prose\n",
            encoding="utf-8")
        global DP_DOCS
        keep = DP_DOCS
        DP_DOCS = t
        try:
            dec, seen = declared(), mentioned()
        finally:
            DP_DOCS = keep
        ok("a `## DP-A9001` heading declares", "DP-A9001" in dec)
        ok("a `### `DP-Ch9007`` heading declares (backticked, deeper level)", "DP-Ch9007" in dec)
        ok("a prose mention does NOT declare", "DP-A9099" not in dec)
        ok("...but IS seen, so the phantom rule can judge it", "DP-A9099" in seen)

    # ── the phantom rule, and both shrink arms ───────────────────────────────
    p = check_phantoms({"DP-A9001": "01.md"}, {"DP-A9001", "DP-A9077"})
    ok("an undeclared mention with no PHANTOM_OK row fails",
       any("DP-A9077" in x and "DECLARED BY NO HEADING" in x for x in p), str(p))
    p = check_phantoms({"DP-A9001": "01.md", "DP-R9": "11.md"}, {"DP-A9001", "DP-R9"})
    ok("a PHANTOM_OK row whose id BECAME a heading fails (shrink arm 1)",
       any("DP-R9" in x and "became one" in x.lower() for x in p), str(p))
    p = check_phantoms({"DP-A9001": "01.md"}, {"DP-A9001"})
    ok("a PHANTOM_OK row the docs no longer mention fails (shrink arm 2)",
       any("exempts nothing" in x for x in p), str(p))
    p = check_phantoms({"DP-A9001": "01.md"}, {"DP-A9001", "DP-R9", "DP-R10"})
    ok("...and the two real rows are quiet when their reason still holds", p == [], str(p))

    # ── sited vs proven ──────────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        (t / "src").mkdir()
        (t / "tests").mkdir()
        (t / "src" / "a.rs").write_text("// DP-A9001 guarded here\nfn f() {}\n", encoding="utf-8")
        (t / "src" / "b.rs").write_text(
            "fn g() {}\n#[cfg(test)]\nmod t { /* DP-A9002 */ }\n", encoding="utf-8")
        (t / "tests" / "c.rs").write_text("// DP-A9003\n", encoding="utf-8")
        global CODE_ROOTS, ROOT
        keepr, keepc = ROOT, CODE_ROOTS
        ROOT, CODE_ROOTS = t, (("", {".rs"}),)
        try:
            sited, proven, n = walk()
        finally:
            ROOT, CODE_ROOTS = keepr, keepc
        ok("a citation in ordinary source is SITED", "DP-A9001" in sited)
        ok("...and is NOT proven on its own", "DP-A9001" not in proven)
        ok("a citation inside `#[cfg(test)]` is PROVEN", "DP-A9002" in proven)
        ok("a citation in a tests/ file is PROVEN", "DP-A9003" in proven)
        ok("...and a tests/ file does not also count as a SITE",
           "DP-A9003" not in sited, f"sited={sorted(sited)}")
        ok("the walk counts the files it read", n == 3, f"n={n}")

    # ── the floors, which are the whole reason this can be trusted ───────────
    keep = globals()["MIN_DECLARED"]
    globals()["MIN_DECLARED"] = 10 ** 6
    try:
        rc = run()
    finally:
        globals()["MIN_DECLARED"] = keep
    ok("an unreachable declared-floor is MISUSE (2), not a pass", rc == 2, f"rc={rc}")

    keep = globals()["MIN_FILES"]
    globals()["MIN_FILES"] = 10 ** 9
    try:
        rc = run()
    finally:
        globals()["MIN_FILES"] = keep
    ok("an unreachable file-floor is MISUSE (2), not a pass", rc == 2, f"rc={rc}")

    # ── the ratchet, both directions, driven ─────────────────────────────────
    keep = dict(BASELINE)
    st = evaluate()
    real = {f: (len(st["per"][f]["uncited"]), len(st["per"][f]["unproven"]))
            for f in FAMILIES}
    try:
        BASELINE["DP-A"] = (real["DP-A"][0] - 1, real["DP-A"][1])
        ok("a GROWN uncited count reds", run() == 1)
        BASELINE["DP-A"] = (real["DP-A"][0] + 1, real["DP-A"][1])
        ok("...and a FALLEN one reds too, so the worklist is seen to shrink", run() == 1)
        BASELINE["DP-A"] = (real["DP-A"][0], real["DP-A"][1] + 1)
        ok("a FALLEN unproven count reds (progress must be recorded)", run() == 1)
        # ...and the OTHER direction. Setting the baseline BELOW the real count
        # is the only thing that reaches `unp > base_unp`; the case above drives
        # the progress branch only, so the regression arm survived its mutation.
        BASELINE["DP-A"] = (real["DP-A"][0], real["DP-A"][1] - 1)
        ok("a GROWN unproven count reds (a rule losing its test)", run() == 1)
        BASELINE.clear()
        BASELINE.update(real)
        # NB: this drives an INJECTED baseline, so it proves the gate does not
        # cry wolf when the numbers agree. It does NOT check that the SHIPPED
        # constant is current — running the gate is what does that.
        ok("a baseline EQUAL to the tree passes (no cry-wolf)", run() == 0)
    finally:
        BASELINE.clear()
        BASELINE.update(keep)

    if failures:
        print(f"dp-invariant-coverage-gate --self-test: {failures} rule(s) did not behave")
        return 2
    print("dp-invariant-coverage-gate --self-test: every rule bites, and none cries wolf")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    if "--list" in sys.argv:
        return show_list()
    if "--regen" in sys.argv:
        return regen()
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
