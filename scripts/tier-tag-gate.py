#!/usr/bin/env python3
"""tier-tag-gate — the central, cross-service C-TOOL tier gate (Track A / M9a).

THE GAP THIS CLOSES. The shared kit's `ValidateToolMeta` (sdks/go/loreweave_mcp/meta.go)
checks only that every tool carries a *valid* tier (one of R|A|W|S) and scope. It does NOT
check that the tier MATCHES what the tool does. So a WRITE tool mistakenly tagged `R` passes
every existing validator and every per-service unit test — and Tier-R means "read: no confirm,
auto-runs, doesn't count against the write budget". A mutation tool tagged R therefore
auto-commits with no confirm card and no Undo strip: exactly the silent-write class this repo
keeps fighting. No single check asserted "a write tool is non-R", and the per-service tier
tests that come closest are Go-only + the Python ones were byte-compile-only in CI.

WHAT IT ASSERTS. Across ALL services, for every MCP tool whose NAME begins with an
unambiguous MUTATION verb (create/save/update/delete/propose/merge/adopt/apply/…), the
declared `_meta.tier` MUST be non-R (A = auto-commit+Undo, W/S = confirm-token). A mutation
verb tagged R is a FAILURE. Read-named tools (list/get/read/search/count/…) are unconstrained.

WHY A NAME HEURISTIC IS THE RIGHT PROXY. A static gate cannot run a handler to see if it
writes. The tool NAME is the contract the agent and the tier system both read; the C-TOOL
convention already names writes by their verb. This gate holds the name and the tier to each
other — the one cross-cutting invariant neither the SDK validator nor a unit test enforces.

DESIGN FOR CI (runs on every branch, no live stack): pure source parse, zero deps, and
CONSERVATIVE — it flags only unambiguous mutation verbs, so it cannot false-positive a green
tree into a red build. New ambiguous verbs are added to REVIEW_VERBS (reported, never failed)
until classified. Exit 1 on any violation; exit 0 clean.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SERVICES = REPO / "services"

# Unambiguous MUTATION verbs — a tool named `<verb>_*` (or `<domain>_<verb>_*`) MUST be non-R.
# Kept deliberately tight: every verb here changes stored state in a way that needs a confirm
# or an Undo strip. Ambiguous verbs (generate/run/build/project/start) are NOT here — they go
# to REVIEW_VERBS so a maybe-write is surfaced for a human, never used to fail the build.
WRITE_VERBS = frozenset({
    "create", "save", "update", "delete", "remove", "patch", "propose", "merge",
    "adopt", "apply", "reassign", "rename", "archive", "restore", "publish",
    "add", "set", "confirm", "revert", "upsert", "insert", "edit", "reorder",
    "duplicate", "assign", "grant", "revoke", "promote", "unpublish", "purge",
})
# Verbs that MIGHT write — reported for human classification, never a failure on their own.
REVIEW_VERBS = frozenset({
    "generate", "run", "build", "project", "start", "submit", "enqueue",
    "ingest", "seed", "import", "execute", "fork", "clone", "move", "capture",
})
# READ verbs — a tool LED by one of these is a read regardless of later noun tokens. This is
# what stops `glossary_list_merge_candidates` (lists candidates; "merge" is a NOUN) reading as
# a write: `_verb` returns the FIRST recognised verb left-to-right, and `list` wins over `merge`.
READ_VERBS = frozenset({
    "list", "get", "read", "search", "show", "fetch", "count", "find", "describe",
    "preview", "view", "state", "resolve", "check", "lookup", "inspect", "load",
})
_ALL_VERBS = WRITE_VERBS | REVIEW_VERBS | READ_VERBS

# A tool registration in Go: `<helper>(srv, "tool_name", "desc"…, NewToolMeta(lwmcp.TierX,…)…`.
# We anchor on NewToolMeta and walk BACK to the nearest tool-name string in the same call, so
# all three helpers (RegisterTool / addTool / registerTool) parse uniformly.
_GO_META = re.compile(r"NewToolMeta\(\s*(?:lwmcp\.)?Tier([RAWS])\b")
_GO_NAME = re.compile(r'"([a-z][a-z0-9]*(?:_[a-z0-9]+)+)"')
# Python/TS static declarations: a tool dict with a "name" and a "_meta":{"tier":"X"} nearby.
_PY_ENTRY = re.compile(
    r'"name"\s*:\s*"([a-z][a-z0-9_]+)".*?"tier"\s*:\s*"([RAWS])"', re.DOTALL)
_PY_ENTRY_REV = re.compile(
    r'"tier"\s*:\s*"([RAWS])".*?"name"\s*:\s*"([a-z][a-z0-9_]+)"', re.DOTALL)


def _verb(tool: str) -> str:
    """The leading verb of a tool name, skipping a known domain prefix.

    `book_chapter_save_draft` → the first token that is a verb we recognise (`save`), so a
    domain/noun prefix (book, chapter, glossary) never hides the verb behind it."""
    parts = tool.split("_")
    for p in parts:
        if p in _ALL_VERBS:
            return p  # first RECOGNISED verb wins (read/write/review) — a read verb ahead of a
                      # noun like "merge" correctly classifies the tool as a read.
    return parts[0] if parts else ""


def _scan_go(text: str) -> list[tuple[str, str]]:
    """Return (tool_name, tier) pairs from one Go file. For each NewToolMeta, the tool name is
    the last tool-name-shaped string literal appearing BEFORE it (the register call's name arg)."""
    pairs: list[tuple[str, str]] = []
    for m in _GO_META.finditer(text):
        tier = m.group(1)
        window = text[max(0, m.start() - 1200):m.start()]
        names = _GO_NAME.findall(window)
        if names:
            pairs.append((names[-1], tier))
    return pairs


def _scan_py_or_ts(text: str) -> list[tuple[str, str]]:
    pairs = [(n, t) for n, t in _PY_ENTRY.findall(text)]
    pairs += [(n, t) for t, n in _PY_ENTRY_REV.findall(text)]
    return pairs


def main() -> int:
    violations: list[str] = []
    review: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    scanned_go = scanned_py = 0

    for path in SERVICES.rglob("*.go"):
        if path.name.endswith("_test.go") or "/vendor/" in path.as_posix():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "NewToolMeta(" not in text:
            continue
        scanned_go += 1
        rel = path.relative_to(REPO).as_posix()
        for tool, tier in _scan_go(text):
            key = (tool, tier, rel)
            if key in seen:
                continue
            seen.add(key)
            v = _verb(tool)
            if v in WRITE_VERBS and tier == "R":
                violations.append(f"  {rel}: {tool!r} is a WRITE (verb {v!r}) but tagged Tier-R "
                                  f"— a mutation would auto-run with no confirm/Undo. Tag it A/W/S.")
            elif v in REVIEW_VERBS and tier == "R":
                review.append(f"  {rel}: {tool!r} (verb {v!r}, ambiguous) is Tier-R — confirm it truly only reads.")

    # Python static tool decls that carry an inline _meta.tier (chat-service frontend/meta tools).
    for path in SERVICES.rglob("*.py"):
        if "/tests/" in path.as_posix() or "/test_" in path.name:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if '"tier"' not in text or '"name"' not in text:
            continue
        rel = path.relative_to(REPO).as_posix()
        found = _scan_py_or_ts(text)
        if found:
            scanned_py += 1
        for tool, tier in found:
            key = (tool, tier, rel)
            if key in seen:
                continue
            seen.add(key)
            v = _verb(tool)
            if v in WRITE_VERBS and tier == "R":
                violations.append(f"  {rel}: {tool!r} is a WRITE (verb {v!r}) but tagged Tier-R. Tag it A/W/S.")

    total = len(seen)
    print(f"tier-tag-gate: scanned {scanned_go} Go + {scanned_py} Python tool-bearing files, "
          f"{total} (tool,tier) declarations.")
    if review:
        print(f"\n⚠ {len(review)} ambiguous-verb Tier-R tool(s) to eyeball (NOT a failure):")
        print("\n".join(sorted(set(review))))
    if violations:
        print(f"\n✖ {len(violations)} TIER VIOLATION(S) — a write tool tagged Tier-R:")
        print("\n".join(sorted(set(violations))))
        print("\nA Tier-R tool auto-runs with no confirm card and no Undo strip. A write MUST be "
              "A (auto+Undo) or W/S (confirm-token). Fix the tier in the tool's NewToolMeta/_meta.")
        return 1
    if total == 0:
        print("✖ no tool declarations found — the parser matched nothing, which means it is "
              "broken, not that the tree is clean. Failing rather than passing vacuously.")
        return 1
    print("✓ every write-named tool carries a non-R tier.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
