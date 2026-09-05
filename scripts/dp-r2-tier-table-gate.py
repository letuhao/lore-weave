#!/usr/bin/env python3
"""dp-r2-tier-table-gate — every PRODUCTION aggregate has a `DP-R2` tier row.

`DP-R2` (`11_access_pattern_rules.md`): *"Every feature design doc MUST contain a
tier table listing every aggregate the feature touches and the tier used for
each access pattern. Missing table, ambiguous entries, or 'to be decided' blocks
design review."*

Its stated enforcement is **"review — governance checklist requires the tier
table before sign-off."** Measured 2026-08-14, that produced exactly this:

    documents in the whole tree containing a DP-R2 tier table:  1
    ...and it is `11_access_pattern_rules.md`, which DEFINES the template.

Zero feature docs complied, and `2026-08-06-command-hub.md` says so about
itself in its own header — *"`DP-R2` is OWED and unpaid"*. A rule enforced by a
checklist nobody runs is a rule with no subjects, which is why this exists.

WHY DISCOVERY AND NOT A LIST
------------------------------------------------------------
`NV-3` — the *default-uncovered* shape: an enumerated file list says nothing
about the aggregate someone adds tomorrow. This gate walks the source for
`impl DpAggregate for`, reads each `TYPE_NAME`, and requires a row. A new
aggregate therefore arrives RED rather than unnoticed, which is the only version
of this check worth having.

WHAT COUNTS AS PRODUCTION
------------------------------------------------------------
Not a test. `crates/dp`'s own suites define eleven fixtures — `Chatter`, `Inv`,
`Prof` — and demanding design docs for them would flood the gate with noise and
train a reader to ignore it. Excluded: any file under `tests/`, and any impl
inside a `#[cfg(test)]` module. That exclusion is itself checked: the self-test
below proves a fixture is skipped AND that a production impl in the same file
is still caught, because an over-broad exclusion is how this gate would go
quietly vacuous.

Exit 0 = every production aggregate has a row · 1 = one does not · 2 = misuse.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOTS = ("crates", "services")
DOCS = REPO / "docs"

IMPL = re.compile(r"impl\s+(?:dp::)?DpAggregate\s+for\s+(\w+)")
TYPE_NAME = re.compile(r'const\s+TYPE_NAME\s*:\s*&.*?str\s*=\s*"([^"]+)"')
# A DP-R2 row: the aggregate in backticks in the FIRST cell of a table row.
ROW = re.compile(r"^\|\s*`([a-z0-9_]+)`\s*\|", re.MULTILINE)


def code_only(text: str) -> str:
    """Strip line comments. `DP-R2` in a doc comment is prose, not a declaration."""
    return "\n".join("" if l.strip().startswith("//") else l for l in text.splitlines())


def cfg_test_spans(text: str) -> list[tuple[int, int]]:
    """Character spans of `#[cfg(test)] mod ... { ... }`, brace-matched.

    A regex to the closing brace would stop at the first `}` inside the module.
    Counting braces is the difference between excluding a test module and
    excluding one line of it.
    """
    spans = []
    for m in re.finditer(r"#\[cfg\(test\)\]\s*mod\s+\w+\s*\{", text):
        depth, i = 0, m.end() - 1
        while i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    spans.append((m.start(), i))
                    break
            i += 1
    return spans


def production_aggregates(root: Path) -> dict[str, str]:
    """`{type_name: where}` for every impl that is not a test fixture."""
    found: dict[str, str] = {}
    for base in ROOTS:
        for f in (root / base).rglob("*.rs"):
            rel = f.relative_to(root).as_posix()
            if "/tests/" in rel or "/.claude/" in rel or "/target/" in rel:
                continue
            raw = f.read_text(encoding="utf-8", errors="replace")
            text = code_only(raw)
            spans = cfg_test_spans(text)
            for m in IMPL.finditer(text):
                if any(a <= m.start() <= b for a, b in spans):
                    continue  # a fixture inside `#[cfg(test)]`
                # The TYPE_NAME belongs to this impl: the next one after it.
                nxt = TYPE_NAME.search(text, m.end())
                if nxt:
                    found[nxt.group(1)] = rel
    return found


def declared_rows(docs: Path) -> set[str]:
    out: set[str] = set()
    for f in docs.rglob("*.md"):
        if "/_superseded/" in f.as_posix():
            continue
        body = f.read_text(encoding="utf-8", errors="replace")
        if "Read tier" not in body or "Write tier" not in body:
            continue
        out |= set(ROW.findall(body))
    return out


def check(root: Path = REPO) -> list[str]:
    aggregates = production_aggregates(root)
    rows = declared_rows(root / "docs")
    return [
        f"`{name}` ({where}) is a PRODUCTION DpAggregate with no DP-R2 tier row. "
        f"Add one to the feature's design doc: | `{name}` | <read tier> | <write tier> | <why> |"
        for name, where in sorted(aggregates.items())
        if name not in rows
    ]


def verdict(root: Path) -> int:
    """0 clean · 1 findings · 2 MISUSE (the walk found nothing).

    Extracted from `main` so the SELF-TEST can reach the misuse arm. It lived
    only in `main`, which the self-test never calls — so `gate-bite-harness`
    mutated `if not aggregates:` to `if False:` and the mutation **survived**.
    A guard with no case is the vacuity this gate exists to prevent, occurring
    inside this gate. Found by its own bite rows, which is the harness paying
    for itself on its first run here.
    """
    aggregates = production_aggregates(root)
    if not aggregates:
        return 2
    return 1 if check(root) else 0


def self_test() -> int:
    """Both directions, on synthetic trees — the arms that keep this honest."""
    import tempfile

    problems: list[str] = []

    PROD = (
        'impl DpAggregate for Real {\n'
        '    const TYPE_NAME: &\'static str = "real_thing";\n'
        '}\n'
    )
    FIXTURE = (
        '#[cfg(test)]\n'
        'mod tests {\n'
        '    impl DpAggregate for Fake {\n'
        '        const TYPE_NAME: &\'static str = "fake_thing";\n'
        '    }\n'
        '    fn helper() { if true { } }\n'
        '}\n'
    )
    TABLE = "| Aggregate type | Read tier | Write tier | Rationale |\n|---|---|---|---|\n| `real_thing` | T2 | T2 | x |\n"

    def build(src: str, doc: str) -> Path:
        d = Path(tempfile.mkdtemp())
        (d / "crates" / "x" / "src").mkdir(parents=True)
        (d / "services").mkdir()
        (d / "docs").mkdir()
        (d / "crates" / "x" / "src" / "lib.rs").write_text(src, encoding="utf-8")
        (d / "docs" / "f.md").write_text(doc, encoding="utf-8")
        return d

    # 1 · a production aggregate WITHOUT a row is caught.
    if not check(build(PROD, "no table here")):
        problems.append("a production aggregate with no tier row was NOT caught")
    # 2 · ...and WITH a row is not.
    if check(build(PROD, TABLE)):
        problems.append("a production aggregate WITH a tier row was wrongly flagged")
    # 3 · a `#[cfg(test)]` fixture is skipped — the exclusion works...
    if check(build(FIXTURE, "no table here")):
        problems.append("a #[cfg(test)] fixture was demanded a tier row")
    # 4 · ...and is NOT over-broad: a production impl in the SAME file is still
    #     caught. Without this arm, an exclusion that swallowed the whole file
    #     would pass arm 3 and make the gate vacuous.
    if not check(build(FIXTURE + PROD, "no table here")):
        problems.append("the #[cfg(test)] exclusion swallowed a PRODUCTION impl in the same file")
    # 5 · a comment mentioning the impl is prose, not a declaration.
    if check(build("// impl DpAggregate for Ghost {\n// const TYPE_NAME: &'static str = \"ghost\";\n", "x")):
        problems.append("a COMMENTED-OUT impl was treated as real")
    # 6 · a table missing the DP-R2 headers does not count as a declaration.
    if not check(build(PROD, "| `real_thing` | a | b |\n")):
        problems.append("a table without Read/Write tier headers was accepted as a DP-R2 table")

    # 7 · AN EMPTY WALK IS MISUSE, NOT SUCCESS. Without this arm the guard had
    #     no case and its mutation survived the bite harness.
    empty = Path(tempfile.mkdtemp())
    for sub in ("crates", "services", "docs"):
        (empty / sub).mkdir()
    if verdict(empty) != 2:
        problems.append("a walk that found ZERO aggregates did not report MISUSE — a broken "
                        "walk would pass on nothing")
    # 8 · ...and a tree WITH an aggregate is not misuse, so arm 7 cannot pass by
    #     always returning 2.
    if verdict(build(PROD, TABLE)) != 0:
        problems.append("a clean tree was reported as misuse or findings")

    if problems:
        print(f"dp-r2-tier-table-gate: SELFTEST FAIL — {len(problems)} problem(s)")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("dp-r2-tier-table-gate: SELFTEST PASS — 8 case(s): a missing row is caught and a present "
          "one is not; a #[cfg(test)] fixture is skipped WITHOUT swallowing a production impl in "
          "the same file; a commented-out impl is prose; and a table lacking the DP-R2 headers is "
          "not a DP-R2 table; and an EMPTY walk is MISUSE while a clean tree is not (non-vacuous in both directions)")
    return 0


def main() -> int:
    if "--self-test" in sys.argv or "--selftest" in sys.argv:
        return self_test()

    aggregates = production_aggregates(REPO)
    if verdict(REPO) == 2:
        print("dp-r2-tier-table-gate: MISUSE — found ZERO production DpAggregate impls. The walk "
              "is broken or the trait was renamed; a gate with no subjects passes on nothing.",
              file=sys.stderr)
        return 2

    problems = check()
    if problems:
        print(f"dp-r2-tier-table-gate: {len(problems)} finding(s) — DP-R2\n")
        for p in problems:
            print(f"  {p}")
        print("\nDP-R2's stated enforcement is a review checklist, and when this gate was written "
              "\nexactly ONE document in the tree had a tier table — the one that defines the "
              "\ntemplate. A rule with no subjects is not enforced.")
        return 1

    print(f"dp-r2-tier-table-gate: OK — {len(aggregates)} production aggregate(s) "
          f"({', '.join(sorted(aggregates))}), each with a DP-R2 tier row")
    return 0


if __name__ == "__main__":
    sys.exit(main())
