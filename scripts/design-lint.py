#!/usr/bin/env python3
"""design-lint.py — Layer-1 mechanical lint for the LLM MMO RPG design corpus.

Cross-platform, Python 3.10+, stdlib only (same reasons as ai-provider-gate.py:
no bash, no /tmp, works on Windows).

WHY THIS EXISTS. The 2026-07-26 reconciliation audit
(docs/03_planning/LLM_MMO_RPG/19_reconciliation_register.md §14) found ~150
cross-doc defects with one root cause: "documents are locked individually;
correctness is a property of the set." This lint is the mechanical guard for
the cheapest-to-check cross-doc classes.

CHECKS (each independently toggleable via --check):

  symbol        unregistered-prefix — every stable-ID reference of the shape
                PREFIX-<letter?><number> (RLS-A12, EVT-L13, DP-Ch18, REC-54)
                must have its PREFIX declared in the id catalog
                (00_foundation/06_id_catalog.md, "Prefix" column).
  link          broken-link — every relative markdown link must resolve to an
                existing file (anchors ignored; external URLs skipped).
  registration  phantom-registration — a line claiming "(registered ...)" or
                "registered YYYY-MM-DD" for a prefix that does NOT appear in
                _boundaries/01_feature_ownership_matrix.md. (This exact defect
                shipped 4 times.)
  count         INFO only — counts "N variants / N tools / count=N" style
                assertions. v1 does not parse them against their lists; the
                metric just sizes the drift surface. Never affects exit code.

ALLOWLIST (symbol check):
  - scripts/design-lint.allow.json — {"prefixes": {"UTF": "reason", ...}},
    corpus-wide (for non-namespace tokens like UTF-8 / ISO-8601 / GPT-4).
  - inline pragma in a doc, scoped to that doc only:
      <!-- design-lint: ok prefix XYZ — reason -->

USAGE:
  python scripts/design-lint.py                       # full corpus, all checks
  python scripts/design-lint.py --path <dir>          # another corpus root
  python scripts/design-lint.py --check symbol,link   # subset of checks
  python scripts/design-lint.py --max-print 0         # print every finding

EXIT: 0 = clean · 1 = findings · 2 = usage/config error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
from collections import Counter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
DEFAULT_CORPUS = os.path.join(REPO_ROOT, "docs", "03_planning", "LLM_MMO_RPG")
CATALOG_REL = os.path.join("00_foundation", "06_id_catalog.md")
MATRIX_REL = os.path.join("_boundaries", "01_feature_ownership_matrix.md")
DEFAULT_ALLOWLIST = os.path.join(SCRIPT_DIR, "design-lint.allow.json")
ALL_CHECKS = ("symbol", "link", "registration", "count")
# check → the finding kind it emits (count emits none; INFO only)
KIND_OF_CHECK = {
    "symbol": "unregistered-prefix",
    "link": "broken-link",
    "registration": "phantom-registration",
}

# ── patterns ──────────────────────────────────────────────────────────────
# Stable-ID reference. Letter slot is any single capital or "Ch" — a superset
# of the originally spec'd A|D|Q|R|F|I|L|P|T|V|G|Ch, because DP-K7, EVT-S3 and
# ITM-C13 are real references the narrow set would miss.
ID_REF = re.compile(r"\b([A-Z]{2,5})-(?:Ch|[A-Z])?\d+[a-z]?\b")
# A prefix token as it appears in the catalog's "Prefix" column or on a
# registration-claim line: capitals followed by '-', a digit, or '*'.
PREFIX_TOKEN = re.compile(r"\b([A-Z]{2,5})(?=[-\d*])")
PRAGMA = re.compile(r"design-lint:\s*ok\s+prefix\s+([A-Z]{2,6})")
MD_LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
INLINE_CODE = re.compile(r"`[^`]*`")
FENCE = re.compile(r"^\s*(```|~~~)")
REG_CLAIM = re.compile(r"\(registered\b|\bregistered\s+(?:on\s+)?20\d\d-\d\d-\d\d", re.I)
COUNT_ASSERT = re.compile(
    r"\b\d+\s+(?:variants?|tools?|checks?|validators?|slots?|states?|events?"
    r"|shapes?|kinds?|types?|fields?|columns?|rows?|entries|items?|modes?"
    r"|phases?|tiers?|levels?|categories|namespaces?|prefixes?)\b"
    r"|\bcount\s*=\s*\d+",
    re.I,
)


def die(msg: str) -> "NoReturn":  # noqa: F821 — py3.10 has NoReturn in typing only
    print(f"design-lint: error: {msg}", file=sys.stderr)
    sys.exit(2)


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        return fh.read()


def load_allowlist(path: str, explicit: bool) -> dict[str, str]:
    """prefix → reason. A missing default file is fine; a missing --allowlist
    file is a config error."""
    if not os.path.isfile(path):
        if explicit:
            die(f"allowlist not found: {path}")
        return {}
    try:
        data = json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        die(f"allowlist is not valid JSON ({path}): {exc}")
    prefixes = data.get("prefixes", {})
    if isinstance(prefixes, list):  # tolerate the bare-list form
        return {p: "(no reason recorded)" for p in prefixes}
    if not isinstance(prefixes, dict):
        die(f'allowlist "prefixes" must be an object or list ({path})')
    return dict(prefixes)


def registered_prefixes(catalog_path: str) -> set[str]:
    """Prefixes declared in the id catalog. Only the FIRST column of table
    rows counts as a declaration — a prefix merely *mentioned* in a scope or
    example cell (e.g. "closes AUD-F5") does not register it."""
    prefixes: set[str] = set()
    for line in read_text(catalog_path).splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = line.split("|")
        if len(cells) < 3:
            continue
        first = cells[1]
        if set(first.strip()) <= {"-", ":", " "}:  # header separator row
            continue
        prefixes.update(PREFIX_TOKEN.findall(first))
    return prefixes


def iter_md_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            if fn.endswith(".md"):
                yield os.path.join(dirpath, fn)


def iter_staged_md_files(root: str):
    """Staged `.md` files under `root` — the pre-commit scope.

    Deleted/renamed-away paths are filtered by the isfile check, so a commit
    that removes a doc doesn't fail on its own absence.
    """
    import subprocess
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        die(f"--staged needs a working `git diff --cached`: {e}")
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    for rel in out.splitlines():
        if not rel.strip().endswith(".md"):
            continue
        path = os.path.abspath(os.path.join(repo_root, rel.strip()))
        if os.path.isfile(path) and (path + os.sep).startswith(root + os.sep):
            yield path


# ── per-file scanning ─────────────────────────────────────────────────────

def scan_file(path, rel, lines, checks, registered, allow, matrix_text, findings, counters):
    pragma_ok = {m for line in lines for m in PRAGMA.findall(line)}
    file_dir = os.path.dirname(path)
    in_fence = False
    # filename-derived fallback prefix for registration claims (COMB_003_… → COMB)
    m = re.match(r"([A-Z]{2,5})[_\d]", os.path.basename(path))
    file_prefix = m.group(1) if m else None

    for n, line in enumerate(lines, 1):
        if FENCE.match(line):
            in_fence = not in_fence

        if "symbol" in checks:
            seen_here: set[str] = set()
            for im in ID_REF.finditer(line):
                prefix, ref = im.group(1), im.group(0)
                if prefix in registered or prefix in allow or prefix in pragma_ok:
                    continue
                if ref in seen_here:
                    continue
                seen_here.add(ref)
                findings.append((rel, n, "unregistered-prefix",
                                 f"`{ref}` — prefix `{prefix}` not declared in the id catalog"))
                counters["symbol_prefixes"][prefix] += 1

        if "link" in checks and not in_fence:
            stripped = INLINE_CODE.sub("", line)
            for lm in MD_LINK.finditer(stripped):
                target = urllib.parse.unquote(lm.group(1)).strip("<>")
                target = target.split("#", 1)[0]
                if not target or "://" in target or target.startswith(("mailto:", "{")):
                    continue
                base = REPO_ROOT if target.startswith("/") else file_dir
                resolved = os.path.normpath(os.path.join(base, target.lstrip("/")))
                if not os.path.exists(resolved):
                    findings.append((rel, n, "broken-link",
                                     f"target does not exist: {lm.group(1)}"))

        if "registration" in checks:
            rm = REG_CLAIM.search(line)
            if rm:
                cands = [(t.start(), t.group(1)) for t in PREFIX_TOKEN.finditer(line)]
                before = [p for pos, p in cands if pos < rm.start()]
                named = (before[-1] if before
                         else (cands[0][1] if cands else file_prefix))
                if named and named not in allow and named not in pragma_ok:
                    if not re.search(rf"\b{re.escape(named)}\b", matrix_text):
                        findings.append((rel, n, "phantom-registration",
                                         f"claims registration for `{named}` but `{named}` does not "
                                         f"appear in the feature ownership matrix"))

        if "count" in checks and COUNT_ASSERT.search(line):
            counters["count_assertions"] += 1


# ── main ──────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        prog="design-lint.py", add_help=True,
        description="Layer-1 mechanical lint for the LLM MMO RPG design corpus.")
    ap.add_argument("--path", default=DEFAULT_CORPUS,
                    help="corpus root (default: docs/03_planning/LLM_MMO_RPG)")
    ap.add_argument("--check", default=",".join(ALL_CHECKS),
                    help=f"comma-separated subset of: {','.join(ALL_CHECKS)}")
    ap.add_argument("--allowlist", default=None,
                    help="prefix allowlist JSON (default: scripts/design-lint.allow.json)")
    ap.add_argument("--max-print", type=int, default=200,
                    help="max findings to print (0 = unlimited; default 200)")
    ap.add_argument("--staged", action="store_true",
                    help="scan only STAGED .md files under the corpus (pre-commit scope)")
    ap.add_argument("--warn-check", default="",
                    help="comma-separated checks whose findings WARN instead of "
                         "failing (still printed; exit stays 0 if only these fire)")
    args = ap.parse_args()

    checks = tuple(c.strip() for c in args.check.split(",") if c.strip())
    bad = [c for c in checks if c not in ALL_CHECKS]
    if bad or not checks:
        die(f"unknown --check value(s): {','.join(bad) or '(none)'} "
            f"(valid: {','.join(ALL_CHECKS)})")

    warn_checks = tuple(c.strip() for c in args.warn_check.split(",") if c.strip())
    bad_warn = [c for c in warn_checks if c not in ALL_CHECKS]
    if bad_warn:
        die(f"unknown --warn-check value(s): {','.join(bad_warn)} "
            f"(valid: {','.join(ALL_CHECKS)})")
    warn_kinds = {KIND_OF_CHECK[c] for c in warn_checks if c in KIND_OF_CHECK}

    corpus = os.path.abspath(args.path)
    if not os.path.isdir(corpus):
        die(f"corpus path is not a directory: {corpus}")

    allow = load_allowlist(args.allowlist or DEFAULT_ALLOWLIST,
                           explicit=args.allowlist is not None)

    registered: set[str] = set()
    if "symbol" in checks:
        catalog = os.path.join(corpus, CATALOG_REL)
        if not os.path.isfile(catalog):
            die(f"id catalog not found (needed by symbol check): {catalog}")
        registered = registered_prefixes(catalog)

    matrix_text = ""
    if "registration" in checks:
        matrix = os.path.join(corpus, MATRIX_REL)
        if not os.path.isfile(matrix):
            die(f"ownership matrix not found (needed by registration check): {matrix}")
        matrix_text = read_text(matrix)

    findings: list[tuple[str, int, str, str]] = []
    counters = {"symbol_prefixes": Counter(), "count_assertions": 0}
    n_files = 0
    source = iter_staged_md_files(corpus) if args.staged else iter_md_files(corpus)
    for path in source:
        n_files += 1
        rel = os.path.relpath(path, corpus).replace(os.sep, "/")
        lines = read_text(path).splitlines()
        scan_file(path, rel, lines, checks, registered, allow, matrix_text,
                  findings, counters)

    # ── report ────────────────────────────────────────────────────────────
    scope = "STAGED" if args.staged else "all"
    print(f"design-lint: scanned {n_files} {scope} .md files under {corpus}")
    print(f"  checks: {', '.join(checks)}"
          + (f" (warn-only: {', '.join(warn_checks)})" if warn_checks else ""))
    if "symbol" in checks:
        print(f"  registered prefixes (id catalog): {len(registered)}"
              f" · allowlisted: {len(allow)}")

    shown = findings if args.max_print == 0 else findings[: args.max_print]
    for rel, n, kind, msg in shown:
        print(f"{rel}:{n}: [{kind}] {msg}")
    if len(findings) > len(shown):
        print(f"... and {len(findings) - len(shown)} more "
              f"(rerun with --max-print 0 for all)")

    by_kind = Counter(k for _, _, k, _ in findings)
    print("\n── summary ──")
    if "symbol" in checks:
        print(f"unregistered-prefix: {by_kind.get('unregistered-prefix', 0)} finding(s)"
              f" across {len(counters['symbol_prefixes'])} prefix(es)")
        top = counters["symbol_prefixes"].most_common(15)
        if top:
            print("  top prefixes: " + " · ".join(f"{p}×{c}" for p, c in top))
    if "link" in checks:
        print(f"broken-link: {by_kind.get('broken-link', 0)} finding(s)")
    if "registration" in checks:
        print(f"phantom-registration: {by_kind.get('phantom-registration', 0)} finding(s)")
    if "count" in checks:
        print(f"count-assertions (INFO, not parsed in v1): {counters['count_assertions']}")

    hard = [f for f in findings if f[2] not in warn_kinds]
    soft = [f for f in findings if f[2] in warn_kinds]
    if soft:
        print(f"\ndesign-lint: WARN — {len(soft)} finding(s) in warn-only "
              f"check(s): {', '.join(warn_checks)}")
    if hard:
        print(f"design-lint: FAIL — {len(hard)} finding(s)")
        return 1
    print("design-lint: OK — no blocking findings" if soft
          else "\ndesign-lint: OK — no findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
