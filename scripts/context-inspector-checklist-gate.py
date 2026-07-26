#!/usr/bin/env python3
"""Context Budget Law §13c — the CI meta-check that makes §11a un-gameable.

The §11a checklist (spec `docs/specs/2026-07-03-context-budget-law.md`) is a
**coverage manifest, not a to-do list** (§13). The rule:

    A checklist item is DONE  ⟺  a test asserts it BY ITS EFFECT.
    An item with no proving test is treated as NOT done — never trust the implementer.

So every `- [ ]` / `- [x]` line under "### 11a." MUST carry exactly one proof-ref:

    ✓test:<path>::<needle>   the test that proves the item (default; most items)
    ⊘manual:<reason>         genuinely un-automatable (pure aesthetics only)

This script parses §11a and FAILS (exit 1) if any item:
  • has neither a ✓test nor a ⊘manual ref (an unproven box), or
  • has a ✓test whose <path> does not exist, or whose <needle> substring is not
    present in that file (a dangling reference — the test was renamed/deleted).

That is the same philosophy as `language-rule-lint` failing on a service with no
row: you cannot mark the effort done by leaving an item without a green test.

`--run` additionally EXECUTES the referenced test files (pytest for .py, vitest
for .ts/.tsx) and fails if any suite is red — enforcing §13c's "(b) is in the
passing set" (the default static pass only enforces "(a) exists + is referenced").
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SPEC = REPO / "docs" / "specs" / "2026-07-03-context-budget-law.md"

SECTION_START = re.compile(r"^###\s+11a\.")
SECTION_END = re.compile(r"^##\s+12\.")  # next top-level section
ITEM = re.compile(r"^\s*-\s*\[[ xX]\]\s*(?P<body>.*\S)\s*$")
PROOF_TEST = re.compile(r"✓test:(?P<ref>\S(?:.*\S)?)\s*$")
PROOF_MANUAL = re.compile(r"⊘manual:(?P<reason>\S(?:.*\S)?)\s*$")


class Item:
    __slots__ = ("line_no", "text", "kind", "ref", "path", "needle", "reason")

    def __init__(self, line_no: int, text: str):
        self.line_no = line_no
        self.text = text
        self.kind: str | None = None      # "test" | "manual" | None
        self.ref: str | None = None
        self.path: str | None = None
        self.needle: str | None = None
        self.reason: str | None = None


def parse_items(spec_text: str) -> list[Item]:
    lines = spec_text.splitlines()
    in_section = False
    items: list[Item] = []
    for i, raw in enumerate(lines, start=1):
        if SECTION_START.match(raw):
            in_section = True
            continue
        if in_section and SECTION_END.match(raw):
            break
        if not in_section:
            continue
        m = ITEM.match(raw)
        if not m:
            continue
        body = m.group("body")
        item = Item(i, body)
        tm = PROOF_TEST.search(body)
        mm = PROOF_MANUAL.search(body)
        if tm:
            item.kind = "test"
            item.ref = tm.group("ref").strip()
            if "::" in item.ref:
                path, needle = item.ref.split("::", 1)
                item.path, item.needle = path.strip(), needle.strip()
        elif mm:
            item.kind = "manual"
            item.reason = mm.group("reason").strip()
        items.append(item)
    return items


# A needle must land on an actual TEST DECLARATION line — an `it(`/`test(`/`describe(`
# (vitest) or a `def test_` (pytest) — NOT a bare comment/docstring match. This closes
# the "needle matches an unrelated comment" hole: a proof-ref must point at a real test.
_TEST_DECL = re.compile(r"\b(it|test|describe)\s*\(|def\s+test")


def resolve_test_ref(item: Item) -> str | None:
    """Return an error string if the ✓test ref is dangling, else None."""
    if not item.path or not item.needle:
        return f"malformed ✓test ref (need <path>::<needle>): {item.ref!r}"
    fp = REPO / item.path
    if not fp.exists():
        return f"referenced test file does not exist: {item.path}"
    text = fp.read_text(encoding="utf-8", errors="replace")
    if item.needle not in text:
        return f"needle not found in {item.path}: {item.needle!r}"
    # the needle must appear on a genuine test-declaration line (not just any line)
    on_decl = any(
        item.needle in line and _TEST_DECL.search(line)
        for line in text.splitlines()
    )
    if not on_decl:
        return (f"needle found but NOT on a test-declaration line (it/test/describe/def test) "
                f"in {item.path}: {item.needle!r} — point the ref at a real test")
    return None


def run_suites(items: list[Item]) -> list[str]:
    """Execute the referenced test files; return a list of failure messages."""
    py_files: set[str] = set()
    ts_files: set[str] = set()
    for it in items:
        if it.kind != "test" or not it.path:
            continue
        if it.path.endswith(".py"):
            py_files.add(it.path)
        elif it.path.endswith((".ts", ".tsx")):
            ts_files.add(it.path)
    errors: list[str] = []

    if py_files:
        chat_svc = REPO / "services" / "chat-service"
        rel = sorted(str((REPO / p).relative_to(chat_svc)) for p in py_files)
        env_pp = str(REPO / "sdks" / "python")
        print(f"  [run] pytest: {' '.join(rel)}")
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *rel],
            cwd=chat_svc,
            env={**_env(), "PYTHONPATH": env_pp},
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            errors.append("pytest suite RED:\n" + proc.stdout[-2000:] + proc.stderr[-1000:])

    if ts_files:
        frontend = REPO / "frontend"
        rel = sorted(str((REPO / p).relative_to(frontend)) for p in ts_files)
        print(f"  [run] vitest: {len(rel)} files")
        proc = subprocess.run(
            ["npx", "vitest", "run", *rel],
            cwd=frontend, env=_env(), capture_output=True, text=True, shell=(sys.platform == "win32"),
        )
        if proc.returncode != 0:
            errors.append("vitest suite RED:\n" + proc.stdout[-2000:] + proc.stderr[-1000:])

    return errors


def _env() -> dict:
    import os
    return dict(os.environ)


def main() -> int:
    ap = argparse.ArgumentParser(description="§13c CI meta-check for the §11a Inspector checklist")
    ap.add_argument("--run", action="store_true",
                    help="also EXECUTE referenced test files and fail if any suite is red")
    ap.add_argument("--spec", default=str(SPEC),
                    help="override the spec path (for gate self-tests)")
    args = ap.parse_args()

    spec = Path(args.spec)
    if not spec.exists():
        print(f"FAIL: spec not found: {spec}", file=sys.stderr)
        return 2
    items = parse_items(spec.read_text(encoding="utf-8"))
    if not items:
        print("FAIL: no §11a checklist items parsed — did the section header change?", file=sys.stderr)
        return 2

    failures: list[str] = []
    n_test = n_manual = 0
    for it in items:
        if it.kind == "manual":
            n_manual += 1
            if not it.reason:
                failures.append(f"L{it.line_no}: ⊘manual with no reason — {it.text}")
            continue
        if it.kind == "test":
            n_test += 1
            err = resolve_test_ref(it)
            if err:
                failures.append(f"L{it.line_no}: {err}\n        item: {it.text}")
            continue
        # neither
        failures.append(f"L{it.line_no}: UNPROVEN — no ✓test/⊘manual ref — {it.text}")

    print(f"§11a checklist: {len(items)} items · {n_test} ✓test · {n_manual} ⊘manual "
          f"· {len(failures)} problem(s)")

    if args.run and not failures:
        print("Executing referenced suites (--run)…")
        failures.extend(run_suites(items))

    if failures:
        print("\nFAIL — the manifest is not fully proven:\n", file=sys.stderr)
        for f in failures:
            print(f"  ✗ {f}", file=sys.stderr)
        print(f"\n{len(failures)} problem(s). Every §11a item needs a ✓test:<path>::<needle> "
              "(or a ⊘manual:<reason> for pure aesthetics).", file=sys.stderr)
        return 1

    print("OK — every §11a item is bound to an existing proving test (or a reasoned manual item).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
