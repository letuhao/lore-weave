#!/usr/bin/env python3
"""knowledge-http-surface-gate.py — enforce INV-KAL's HTTP-surface half (D6 mechanism ii).

Part of the Incremental Temporal Knowledge Architecture (spec
docs/specs/2026-06-29-incremental-temporal-knowledge-architecture.md §6D, §12.5.5).
Companion to scripts/knowledge-access-gate.py (the TABLE-READ half).

INV-KAL: entity/lore KNOWLEDGE is read through the Knowledge Access Layer (the
knowledge-gateway, KAL), never by a consumer reaching the owning services' bespoke
`/internal/*` KNOWLEDGE routes over HTTP. This gate is the HTTP-SURFACE half: it
FAILS when a CONSUMER service references one of the owning services' bi-temporal
knowledge-read `/internal/*` endpoints that the KAL federates — read those through
`KNOWLEDGE_GATEWAY_URL` (`/v1/kal/...`) instead.

🔴 **The guarded set is DERIVED from the KAL's own read controller, not written here.**
It used to be a list in this file, and the list went stale: measured 2026-08-22 (T55) the
KAL federated 11 upstream reads and this gate guarded 7. `canonical-translation`,
`entities/by-ids` and `state` were federated and UNGUARDED, so a consumer bypassing the
KAL on any of them was invisible while this gate printed PASS. Every path
`kal-read.controller.ts` calls is by definition a federated read, so a read is guarded the
day it is federated rather than the day someone remembers this file. Run `--selftest`.

⚠️ **What deriving cannot do**: it cannot guard a knowledge read the KAL does not federate.
composition-service reads `/internal/context/build`, `/internal/context/glossary-semantic`
and `/internal/projects/{id}/fact-for-check` directly, and the KAL offers none of the three
— so no rule in this file can cover them. Closing that needs the KAL to federate them,
which is a design decision and not a gate change. Recorded rather than hand-listed here,
because adding them to a list in this file would make the gate look complete while the
reads stayed exactly as direct as they are.

SCOPE (deliberately matched to the table-read gate): INV-KAL governs the DERIVED
bi-temporal knowledge substrate — the EAV-projected facts + the KG. The AUTHORED
entity CATALOG (`glossary_entities`: name / kind / short_description, served by the
`/internal/books/{book}/entities` LIST endpoint that KAL `roster` thins to id+name)
is NOT part of that substrate — it is the authored source consumers may read
directly, exactly as the table-read gate exempts `glossary_entities`. So the LIST
endpoint is NOT flagged here; only the bi-temporal reads above are.

The owning services (glossary, knowledge) themselves and the KAL (knowledge-gateway)
are exempt — they ARE the endpoints / the federator.

Mirrors scripts/knowledge-access-gate.py (cross-platform; allowlist + --staged).

Usage:
  python scripts/knowledge-http-surface-gate.py            # full scan (CI / manual)
  python scripts/knowledge-http-surface-gate.py --staged   # only git-staged files (pre-commit)
  python scripts/knowledge-http-surface-gate.py --selftest # prove the derivation can go red

Exit 0 = clean (or allowlisted-only). Exit 1 = violation.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SEARCH_DIRS = ("services",)
SCAN_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".mjs")
EXCLUDE_DIRS = {
    "node_modules", "__pycache__", ".pytest_cache", ".venv", "venv",
    "dist", "build", ".next", ".git", "vendor", "coverage",
}

# Owners + the KAL itself are exempt: they ARE the endpoints / the federator.
EXEMPT_SERVICE_PREFIXES = (
    "services/glossary-service/",     # owns the glossary /internal routes
    "services/knowledge-service/",    # owns the knowledge /internal routes
    "services/knowledge-gateway/",    # the KAL — the SANCTIONED federator of these routes
)

# Allowlisted KNOWN outliers (tracked, not enforced) — keep tight + comment each.
ALLOWLIST_PREFIXES: tuple[str, ...] = (
    # (none — the bi-temporal knowledge reads are fully migrated to the KAL.)
)

# ── prose is not a call site ─────────────────────────────────────────
#
# ⚠️ The scan used to match RAW LINES, and the derived set walked straight into it: two
# services carry a docstring naming `/internal/books/{book_id}/entities/by-ids` while both
# actually call the KAL's `/v1/kal/books/{id}/cast/by-ids`. Reporting those is worse than a
# false positive — the cheapest way to make the gate green is to edit the sentence, which
# deletes the explanation and changes nothing about the code.
_LINE_COMMENT = re.compile(r"(?://|#).*$")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_PY_DOCSTRING = re.compile(r'"""(?:.|\n)*?"""' + "|" + r"'''(?:.|\n)*?'''")


def strip_prose(src: str) -> str:
    """`src` with comments and Python docstrings blanked, LINE COUNT preserved.

    Line numbers have to survive so a violation still points at the right line — replacing a
    multi-line docstring with nothing would shift every number after it.
    """
    def _blank(match: re.Match[str]) -> str:
        return "\n" * match.group(0).count("\n")

    src = _PY_DOCSTRING.sub(_blank, src)
    src = _BLOCK_COMMENT.sub(_blank, src)
    return "\n".join(_LINE_COMMENT.sub("", line) for line in src.split("\n"))


# ── the guarded set, DERIVED from the KAL's own read controller ───────
#
# 🔴 **This list used to be hand-written, and it was short.** Measured 2026-08-22 (T55): the
# KAL federates **11** distinct upstream read paths and the hand-list guarded **7**. Three real
# federated reads — `canonical-translation`, `entities/by-ids` and `state` — were unguarded, so
# a consumer calling one of them past the KAL was invisible to this gate while the gate printed
# PASS. That is the failure mode a hand-list always has: it is correct on the day it is written.
#
# The KAL's read controller IS the manifest. Every upstream path it calls is, by definition, a
# federated read; deriving from it means a read added to the KAL is guarded the day it is
# federated rather than the day someone remembers this file.
KAL_READ_CONTROLLER = os.path.join(
    "services", "knowledge-gateway", "src", "kal", "kal-read.controller.ts",
)

#: The ONE deliberate exclusion, named rather than silently absent. The authored entity CATALOG
#: is not part of the bi-temporal substrate INV-KAL governs (see the module header), so the
#: `/internal/books/{book}/entities` LIST endpoint is not flagged — exactly as the table-read
#: gate exempts `glossary_entities`. It is written as a rule the derivation applies, so the
#: exclusion survives the list changing underneath it.
_AUTHORED_CATALOG_TAIL = "/entities"


def _derive_federated_reads(controller_src: str) -> list[str]:
    """The upstream `/internal/...` paths the KAL read controller calls, normalised.

    Template holes (`${bookId}`) become a wildcard; query strings are dropped. Returns the
    paths in first-seen order so the gate's own output is stable.
    """
    out: list[str] = []
    for raw in re.findall(r"`(/internal/[^`]*)`", controller_src):
        path = raw.split("?")[0]
        path = re.sub(r"\$\{[^}]*\}", "{}", path).rstrip("{}").rstrip("/")
        if not path or path in out:
            continue
        if path.endswith(_AUTHORED_CATALOG_TAIL):
            continue          # the authored catalog — see the header, and the note above
        out.append(path)
    return out


def _to_pattern(paths: list[str]) -> re.Pattern[str]:
    """One alternation matching any of `paths`, with `{}` standing for a path segment."""
    if not paths:
        # ⚠️ `re.compile("(?:)")` matches EVERY line, so an empty guarded set would flag the
        # whole repo rather than guarding nothing. `_load_covered` checks emptiness too, but
        # its check does not protect a second caller — the selftest found this one.
        raise ValueError(
            "refusing to build a guarded-set pattern from zero paths: `(?:)` matches every "
            "line, so the gate would flag the whole repo instead of guarding nothing"
        )
    parts = []
    for path in paths:
        # `[^\s"'`/]+` for a hole: an id, an f-string interpolation, a `${...}` — but never a
        # slash, so `/entities/{}/facts` cannot match `/entities/search/x/facts`.
        frag = re.escape(path).replace(r"\{\}", "[^\\s\"'`/]+")
        parts.append(frag + r"\b")
    return re.compile("(?:" + "|".join(parts) + ")")


def _load_covered() -> tuple[re.Pattern[str], list[str]]:
    path = os.path.join(REPO_ROOT, KAL_READ_CONTROLLER)
    try:
        src = open(path, "r", encoding="utf-8", errors="replace").read()
    except OSError as exc:
        raise SystemExit(
            f"[knowledge-http-surface-gate] cannot read the KAL read controller at "
            f"{KAL_READ_CONTROLLER}: {exc}. The guarded set is DERIVED from it — refusing to "
            f"run against an empty manifest, which would pass everything."
        ) from exc
    # The manifest is read as CODE, not prose. The first derivation picked up
    # `/internal/.../entities/by-ids` from a comment in the controller — an ellipsis where a
    # book id belongs — and turned it into a guarded pattern. A gate whose guarded set can be
    # extended by writing a sentence is the same defect as one that fires on a sentence.
    paths = _derive_federated_reads(strip_prose(src))
    if not paths:
        raise SystemExit(
            f"[knowledge-http-surface-gate] derived ZERO federated reads from "
            f"{KAL_READ_CONTROLLER}. A gate with an empty pattern passes every consumer — "
            f"refusing rather than reporting a clean scan."
        )
    return _to_pattern(paths), paths



KAL_COVERED, KAL_COVERED_PATHS = _load_covered()




def is_test_file(rel: str) -> bool:
    base = os.path.basename(rel)
    return (
        "/tests/" in rel or "/test/" in rel or "/fixtures/" in rel
        or "/__fixtures__/" in rel or "/__mocks__/" in rel
        or rel.endswith("_test.go")
        or base.startswith("test_")
        or base.endswith((".spec.ts", ".spec.tsx", ".test.ts", ".test.tsx"))
        or base == "conftest.py"
    )


def scan_file(path: str, rel: str) -> list[tuple[int, str, str]]:
    if is_test_file(rel) or rel.startswith(ALLOWLIST_PREFIXES) or rel.startswith(EXEMPT_SERVICE_PREFIXES):
        return []
    out: list[tuple[int, str, str]] = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            src = fh.read()
        for n, line in enumerate(strip_prose(src).split("\n"), 1):
            if KAL_COVERED.search(line):
                out.append((n, rel, line.strip()[:160]))
    except OSError:
        pass
    return out


def iter_full_scan():
    for d in SEARCH_DIRS:
        root = os.path.join(REPO_ROOT, d)
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [x for x in dirnames if x not in EXCLUDE_DIRS]
            for fn in filenames:
                if fn.endswith(SCAN_EXTS):
                    full = os.path.join(dirpath, fn)
                    yield full, os.path.relpath(full, REPO_ROOT).replace("\\", "/")


def iter_staged():
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return
    for rel in out.splitlines():
        rel = rel.strip().replace("\\", "/")
        if rel.endswith(SCAN_EXTS) and rel.startswith(SEARCH_DIRS):
            full = os.path.join(REPO_ROOT, rel)
            if os.path.isfile(full):
                yield full, rel


def selftest() -> int:
    """Offline proof that the derivation is real, bounded, and can go red.

    A hand-bite is invisible to CI, and this gate's whole change is that its guarded set is no
    longer something a human wrote down. So the properties that matter are: it DERIVES, it
    derives from CODE, it refuses an empty manifest instead of passing everything, and it does
    not fire on prose.
    """
    ok = True
    print("knowledge-http-surface-gate - selftest (offline)")

    def check(label: str, got, want) -> None:
        nonlocal ok
        good = got == want
        ok = ok and good
        print(f"  {'PASS' if good else 'FAIL'}  {label}: expected {want!r}, got {got!r}")

    controller = (
        "class KalReadController {\n"
        "  a() { return g.get(`/internal/books/${bookId}/entities/${id}/facts?x=1`); }\n"
        "  b() { return g.get(`/internal/books/${bookId}/kg/neighborhood`); }\n"
        "  c() { return g.get(`/internal/books/${bookId}/entities?limit=1`); }\n"
        "  // see also `/internal/books/.../made-up-in-a-comment`\n"
        "}\n"
    )
    derived = _derive_federated_reads(strip_prose(controller))
    check("the manifest yields its federated reads", len(derived), 2)
    check("the authored-catalog LIST is excluded by rule",
          any(p.endswith("/entities") for p in derived), False)
    check("a path named only in a COMMENT is not a federated read",
          any("made-up" in p for p in derived), False)

    pat = _to_pattern(derived)
    check("a consumer calling a federated read is caught",
          bool(pat.search("r = get(f'/internal/books/{b}/entities/{e}/facts')")), True)
    check("the KAL's own /v1/kal path is not caught",
          bool(pat.search("r = get('/v1/kal/books/x/facts')")), False)
    check("the authored LIST is not caught",
          bool(pat.search("r = get(f'/internal/books/{b}/entities')")), False)
    # The hole is one SEGMENT, not "anything": a deeper path must not be swallowed.
    check("a hole does not span a slash",
          bool(pat.search("get('/internal/books/b/entities/search/deep/facts')")), False)

    # ── the property this whole change exists for ────────────────────────────────────────
    grown = controller.replace(
        "}\n", "  d() { return g.get(`/internal/books/${bookId}/lore-digest`); }\n}\n", 1)
    grown_pat = _to_pattern(_derive_federated_reads(strip_prose(grown)))
    check("a read the KAL STARTS federating is guarded with NO gate edit",
          bool(grown_pat.search("get(f'/internal/books/{b}/lore-digest')")), True)

    # ── prose is not a call site ─────────────────────────────────────────────────────────
    doc = '"""Calls: POST /internal/books/{book_id}/entities/{e}/facts\n\nprose.\n"""\nx = 1\n'
    stripped = strip_prose(doc)
    check("a docstring naming a guarded read is not scanned",
          bool(pat.search(stripped)), False)
    check("stripping preserves the LINE COUNT so violations still point at the right line",
          len(stripped.split("\n")), len(doc.split("\n")))
    check("a trailing `# comment` naming a guarded read is not scanned",
          bool(pat.search(strip_prose("x = 1  # /internal/books/b/entities/e/facts"))), False)
    check("...but the CODE on that same line still is",
          bool(pat.search(strip_prose(
              "get('/internal/books/b/entities/e/facts')  # a comment"))), True)

    # ── an empty manifest must REFUSE, not pass everything ───────────────────────────────
    try:
        _to_pattern([])
        empty_pattern_built = True
    except ValueError:
        empty_pattern_built = False
    check("an empty derived set REFUSES rather than matching everything",
          empty_pattern_built, False)

    print(f"{chr(10)}  {'all checks passed' if ok else 'SELFTEST FAILED'}")
    return 0 if ok else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    staged = "--staged" in sys.argv
    it = iter_staged() if staged else iter_full_scan()
    violations: list[tuple[int, str, str]] = []
    for full, rel in it:
        violations.extend(scan_file(full, rel))

    if not violations:
        print(f"[knowledge-http-surface-gate] PASS — no consumer hits the "
              f"{len(KAL_COVERED_PATHS)} bi-temporal knowledge /internal reads the KAL "
              f"federates (DERIVED from its read controller, not hand-listed)")
        return 0

    print("[knowledge-http-surface-gate] FAIL — INV-KAL HTTP-surface violations "
          "(read bi-temporal knowledge through the KAL, not the owning service's /internal route):\n")
    for n, rel, line in violations:
        print(f"  [kal-covered-internal-read] {rel}:{n}\n      {line}")
    # The guarded set is DERIVED, so the remedy prints the derivation rather than a second
    # hand-list — the first one drifted four reads behind the KAL before anyone noticed.
    print("\nFix: call KNOWLEDGE_GATEWAY_URL /v1/kal/... instead of the owning "
          "service's /internal/* route.")
    print(f"The KAL federates these {len(KAL_COVERED_PATHS)} reads, derived from "
          f"{KAL_READ_CONTROLLER}:")
    for covered in KAL_COVERED_PATHS:
        print(f"    {covered}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
