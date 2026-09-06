#!/usr/bin/env python3
"""changelog-gate — CHANGELOG.md is structurally valid, and a tagged release names itself in it.

THE GAP THIS CLOSES. "The changelog is the SSOT for what shipped" is a sentence, not an
invariant, until something refuses to let a release happen without it. Every other cross-cutting
rule in this repo lives behind a gate for exactly that reason (see docs/standards/README.md's own
"meta-pattern" section) — a doc nobody has to keep in sync is a doc that drifts the first week.

TWO MODES, BECAUSE THEY CHECK DIFFERENT THINGS AT DIFFERENT TIMES.

1. STRUCTURAL (default, runs in `all-gates` on every push — cheap, deterministic, no git
   history needed beyond the working tree): CHANGELOG.md exists, opens with a `# Changelog`
   heading, has exactly ONE `## [Unreleased]` section, every OTHER `## [...]` heading names a
   valid SemVer version followed by an ISO date, and versions appear newest-first with no
   duplicates. This catches a malformed file long before anyone tries to cut a release from it.

2. RELEASE (`--release X.Y.Z`, used by `.github/workflows/oss-release.yml` at tag time, and by
   nothing else): on top of the structural check, section `## [X.Y.Z] - <date>` must exist and
   have at least one real entry under it (a `-`/`*` bullet in some subsection, not just empty
   subheadings). This is the actual SSOT enforcement moment — no changelog entry, no release,
   full stop. Everything else here is scaffolding that makes THIS check meaningful.

WHAT THIS DELIBERATELY DOES NOT DO. It does not try to decide, per pull request, whether YOUR
change needed a changelog entry — that is a semantic judgment ("does this diff change user-
visible behavior") a filename-pattern heuristic gets wrong constantly, and a gate that is wrong
constantly is a gate people route around. `[Unreleased]` accumulates by hand (or via the
`/oss-publish` skill at cut time, summarizing what actually shipped); this gate only refuses to
let a release happen with nothing recorded, which is the failure mode that actually matters —
a v0.2.0 nobody can later say what was in.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHANGELOG = REPO / "CHANGELOG.md"

# SemVer 2.0.0 core + optional pre-release identifier, e.g. 0.1.0 or 0.2.0-rc.1.
# Deliberately does not accept build metadata (+...) in a heading -- this repo has no use for it
# and accepting it would let a heading drift from the tag it is supposed to name exactly.
_VERSION_RE = re.compile(
    r"^\[(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)\]\s*-\s*(\d{4}-\d{2}-\d{2})$"
)
_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^\s*[-*]\s+\S")


def _semver_key(v: str) -> tuple:
    """Sortable key so 0.2.0 > 0.10.0 is FALSE the way string comparison would get wrong,
    and a pre-release (0.1.0-rc.1) sorts BEFORE its final release (0.1.0) per SemVer's own
    precedence rule (spec item 11) -- a release-ordering check that trusted string order would
    put 0.1.0 ahead of 0.1.0-rc.1 and never notice."""
    core, _, pre = v.partition("-")
    nums = tuple(int(p) for p in core.split("."))
    return (nums, 0) if not pre else (nums, -1, pre)


def parse(text: str) -> tuple[list[str], dict[str, tuple[int, int]]]:
    """(errors, {heading_label: (line_no, body_end_line)}) -- body_end_line is exclusive, the
    line the NEXT `## ` heading starts on (or EOF), so a caller can slice a section's body
    without re-parsing."""
    errors: list[str] = []
    lines = text.splitlines()
    headings: list[tuple[int, str]] = []
    for i, ln in enumerate(lines):
        m = _HEADING_RE.match(ln)
        if m:
            headings.append((i, m.group(1)))

    if not lines or not lines[0].lstrip().startswith("# "):
        errors.append("CHANGELOG.md must open with a top-level `# Changelog` heading.")

    unreleased = [h for _, h in headings if h == "[Unreleased]"]
    if len(unreleased) != 1:
        errors.append(f"expected exactly ONE `## [Unreleased]` section, found {len(unreleased)}.")

    spans: dict[str, tuple[int, int]] = {}
    versions: list[str] = []
    for idx, (line_no, label) in enumerate(headings):
        end = headings[idx + 1][0] if idx + 1 < len(headings) else len(lines)
        spans[label] = (line_no, end)
        if label == "[Unreleased]":
            continue
        m = _VERSION_RE.match(label)
        if not m:
            errors.append(f"line {line_no + 1}: `## {label}` is not `[Unreleased]` and does not "
                           f"match `[x.y.z] - YYYY-MM-DD` (SemVer + ISO date).")
            continue
        versions.append(m.group(1))

    if len(versions) != len(set(versions)):
        dupes = sorted({v for v in versions if versions.count(v) > 1})
        errors.append(f"duplicate version section(s): {', '.join(dupes)}.")

    ordered = sorted(set(versions), key=_semver_key, reverse=True)
    seen_order = [v for v in versions if versions.count(v) == 1]
    if seen_order != [v for v in ordered if v in seen_order]:
        errors.append("version sections are not in newest-first order — "
                       f"found {seen_order}, expected {[v for v in ordered if v in seen_order]}.")

    return errors, spans


def _section_has_content(lines: list[str], span: tuple[int, int]) -> bool:
    start, end = span
    return any(_BULLET_RE.match(ln) for ln in lines[start:end])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--release", metavar="X.Y.Z",
                     help="also require this exact version's section to exist and be non-empty")
    ap.add_argument("--print-section", metavar="X.Y.Z",
                     help="print that version's body (for GitHub Release notes) and exit; "
                          "does not run the structural checks")
    ap.add_argument("--path", type=Path, default=CHANGELOG,
                     help="changelog file to check (default: repo root CHANGELOG.md)")
    args = ap.parse_args(argv)

    if args.print_section:
        text = args.path.read_text(encoding="utf-8", errors="replace")
        _, spans = parse(text)
        label = f"[{args.print_section}] - "
        match = next((h for h in spans if h.startswith(label)), None)
        if match is None:
            print(f"changelog-gate: no section for {args.print_section}", file=sys.stderr)
            return 1
        start, end = spans[match]
        lines = text.splitlines()
        # Skip the heading line itself; trim trailing blank lines.
        body = lines[start + 1:end]
        while body and not body[-1].strip():
            body.pop()
        print("\n".join(body))
        return 0

    if not args.path.is_file():
        print(f"changelog-gate: {args.path} does not exist.")
        return 1

    text = args.path.read_text(encoding="utf-8", errors="replace")
    errors, spans = parse(text)

    if args.release:
        label = f"[{args.release}] - "
        match = next((h for h in spans if h.startswith(label)), None)
        if match is None:
            errors.append(
                f"RELEASE MODE: no `## [{args.release}] - YYYY-MM-DD` section found. "
                f"A tagged release must name itself in CHANGELOG.md before it can ship — "
                f"that is the SSOT invariant this gate exists for. Move the relevant "
                f"`[Unreleased]` entries into a `[{args.release}]` section and commit that "
                f"BEFORE tagging.")
        elif not _section_has_content(text.splitlines(), spans[match]):
            errors.append(
                f"RELEASE MODE: `## {match}` exists but has no entries under it. An empty "
                f"section is the same failure as a missing one — nobody could later say what "
                f"v{args.release} actually shipped.")

    if errors:
        print(f"changelog-gate: {len(errors)} problem(s) in {args.path.relative_to(REPO) if args.path.is_relative_to(REPO) else args.path}:")
        for e in errors:
            print(f"  - {e}")
        return 1

    mode = f"structure + release {args.release}" if args.release else "structure"
    print(f"changelog-gate: {mode} OK ({len(spans)} section(s)).")
    return 0


def _selftest() -> int:
    """Proves the gate fires on the failure shapes it claims to catch, and stays quiet on a
    clean file — the two directions a mutation-bite would otherwise catch separately."""
    cases: list[tuple[str, str, bool, str | None]] = [
        ("a clean file with only Unreleased passes",
         "# Changelog\n\n## [Unreleased]\n\n### Added\n- x\n", True, None),
        ("missing top heading fails",
         "## [Unreleased]\n\n- x\n", False, None),
        ("missing Unreleased section fails",
         "# Changelog\n\n## [0.1.0] - 2026-01-01\n- x\n", False, None),
        ("duplicate Unreleased fails",
         "# Changelog\n\n## [Unreleased]\n- a\n\n## [Unreleased]\n- b\n", False, None),
        ("a non-version, non-Unreleased heading fails",
         "# Changelog\n\n## [Unreleased]\n- a\n\n## Old Notes\n- b\n", False, None),
        ("bad date shape fails",
         "# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 01/01/2026\n- x\n", False, None),
        ("out-of-order versions fail",
         "# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-01-01\n- a\n\n"
         "## [0.2.0] - 2026-02-01\n- b\n", False, None),
        ("in-order versions pass",
         "# Changelog\n\n## [Unreleased]\n\n## [0.2.0] - 2026-02-01\n- b\n\n"
         "## [0.1.0] - 2026-01-01\n- a\n", True, None),
        ("release mode: matching section with content passes",
         "# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-01-01\n- shipped x\n",
         True, "0.1.0"),
        ("release mode: missing section fails",
         "# Changelog\n\n## [Unreleased]\n- a\n", False, "0.1.0"),
        ("release mode: empty section fails",
         "# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-01-01\n\n### Added\n\n",
         False, "0.1.0"),
        ("release mode: pre-release identifier is a valid heading",
         "# Changelog\n\n## [Unreleased]\n\n## [0.1.0-rc.1] - 2026-01-01\n- x\n",
         True, "0.1.0-rc.1"),
    ]
    failures = 0
    import tempfile
    for label, content, want_ok, release in cases:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "CHANGELOG.md"
            p.write_text(content, encoding="utf-8")
            argv = ["--path", str(p)] + (["--release", release] if release else [])
            rc = main(argv)
            got_ok = rc == 0
            if got_ok != want_ok:
                failures += 1
                print(f"  FAIL {label}: expected {'pass' if want_ok else 'fail'}, "
                      f"got {'pass' if got_ok else 'fail'}")
            else:
                print(f"  ok   {label}")

    # --print-section: the release-notes extraction path, checked separately since it
    # deliberately skips structural validation (a release-notes tool that ALSO refuses on an
    # unrelated structural nit would surprise whoever wires it into the release workflow).
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "CHANGELOG.md"
        p.write_text(
            "# Changelog\n\n## [Unreleased]\n\n"
            "## [0.1.0] - 2026-01-01\n\n### Added\n- first thing\n- second thing\n\n"
            "## [0.0.9] - 2025-12-01\n- older\n",
            encoding="utf-8")
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["--path", str(p), "--print-section", "0.1.0"])
        printed = buf.getvalue()
        ok = (rc == 0 and "first thing" in printed and "second thing" in printed
              and "older" not in printed and "### Added" in printed)
        print(f"  {'ok  ' if ok else 'FAIL'} --print-section prints exactly this version's body")
        if not ok:
            failures += 1
        rc2 = main(["--path", str(p), "--print-section", "9.9.9"])
        ok2 = rc2 != 0
        print(f"  {'ok  ' if ok2 else 'FAIL'} --print-section fails for a version with no section")
        if not ok2:
            failures += 1

    if failures:
        print(f"\nchangelog-gate --self-test: {failures} case(s) did not behave")
        return 1
    print(f"\nchangelog-gate --self-test: all {len(cases)} cases behaved")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_selftest())
    sys.exit(main())
