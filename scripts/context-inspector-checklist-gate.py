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

#: A child with no timeout hangs the pre-commit hook forever, with no
#: output and nothing to kill but the terminal. Surfaced by the bite
#: harness's unbounded-child survey when this gate joined its table.
#: A test suite is not a git command. 60s would kill a legitimate
#: four-minute pytest run every time; this budget is for the SUITE.
SUITE_TIMEOUT_S = 900

def _suite_timed_out(tool: str, rel) -> None:
    """A suite that never returns is CANNOT-RUN, not a passing suite."""
    print(f"CANNOT RUN — {tool} did not finish within {SUITE_TIMEOUT_S}s for "
          f"{' '.join(map(str, rel))}; refusing to report a verdict on a suite "
          f"whose result was never read.", file=sys.stderr)
    raise SystemExit(2)


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


def resolve_test_ref(item: Item, repo: Path = REPO) -> str | None:
    """Return an error string if the ✓test ref is dangling, else None.

    `repo` is a parameter because `--self-test` drives the REAL resolver over a
    synthetic checklist AND synthetic test files. Reading the module constant
    here would have sent every probe at the live tree — a self-test that never
    reaches its own fixture, which is `GTD-17`."""
    if not item.path or not item.needle:
        return f"malformed ✓test ref (need <path>::<needle>): {item.ref!r}"
    fp = repo / item.path
    if not fp.exists():
        return f"referenced test file does not exist: {item.path}"
    text = fp.read_text(encoding="utf-8", errors="replace")
    if item.needle not in text:
        # NOT an independent rule — a needle absent from the file cannot be on a
        # declaration line either, so the check below would catch it anyway. It
        # is kept for the MESSAGE: "not found" and "found, but in a comment" send
        # a reader to different places. Measured by a bite arm that went green
        # when this line was disabled; the arm was removed rather than the line,
        # because unlike a shadowed reach floor this one earns its keep as
        # diagnostics. Do not mistake it for detection.
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
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", *rel],
                cwd=chat_svc,
                env={**_env(), "PYTHONPATH": env_pp},
                capture_output=True, text=True,
                timeout=SUITE_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            _suite_timed_out("pytest", rel)
        if proc.returncode != 0:
            errors.append("pytest suite RED:\n" + proc.stdout[-2000:] + proc.stderr[-1000:])

    if ts_files:
        frontend = REPO / "frontend"
        rel = sorted(str((REPO / p).relative_to(frontend)) for p in ts_files)
        print(f"  [run] vitest: {len(rel)} files")
        try:
            proc = subprocess.run(
                ["npx", "vitest", "run", *rel],
                cwd=frontend, env=_env(), capture_output=True, text=True,
                shell=(sys.platform == "win32"),
                timeout=SUITE_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            _suite_timed_out("vitest", rel)
        if proc.returncode != 0:
            errors.append("vitest suite RED:\n" + proc.stdout[-2000:] + proc.stderr[-1000:])

    return errors


def _env() -> dict:
    import os
    return dict(os.environ)


#: `⊘manual` is the escape hatch, and marking an item manual is the ONE way to
#: satisfy this gate without writing a test — so the count is ratcheted. Measured
#: 2026-08-12: 2 of 85 items, both pure CSS easing. The spec (§13c) calls manual
#: items "the small minority"; this is that sentence made mechanical.
MANUAL_CEIL = 2

#: A reason must actually say something. The previous check (`if not it.reason`)
#: could NEVER fire: `PROOF_MANUAL` requires a non-space character, so `reason`
#: was non-empty by construction — dead code guarding the escape hatch. This bar
#: replaces it: measured, both live reasons run ~100 characters.
MIN_REASON_CHARS = 20
_PLACEHOLDER_REASON = re.compile(r"^\s*(todo|tbd|fixme|n/?a|\?+)\b", re.IGNORECASE)


def check(spec: Path, repo: Path = REPO, manual_expected: int = MANUAL_CEIL,
          run: bool = False) -> int:
    """The REAL checker, parameterised so `--self-test` can drive it over a
    synthetic checklist and synthetic test files."""
    if not spec.exists():
        print(f"FAIL: spec not found: {spec}", file=sys.stderr)
        return 2
    items = parse_items(spec.read_text(encoding="utf-8"))
    # ── REACH FLOOR (GT-F3), already present before this pass and worth keeping
    # named: zero parsed items is a renamed header, not an empty obligation.
    if not items:
        print("FAIL: no §11a checklist items parsed — did the section header change?", file=sys.stderr)
        return 2

    failures: list[str] = []
    n_test = n_manual = 0
    for it in items:
        if it.kind == "manual":
            n_manual += 1
            reason = it.reason or ""
            if len(reason) < MIN_REASON_CHARS or _PLACEHOLDER_REASON.match(reason):
                failures.append(
                    f"L{it.line_no}: ⊘manual reason is not a reason ({reason!r}) — the escape "
                    f"hatch needs {MIN_REASON_CHARS}+ characters saying why this cannot be a "
                    f"test — {it.text}")
            continue
        if it.kind == "test":
            n_test += 1
            err = resolve_test_ref(it, repo)
            if err:
                failures.append(f"L{it.line_no}: {err}\n        item: {it.text}")
            continue
        # neither
        failures.append(f"L{it.line_no}: UNPROVEN — no ✓test/⊘manual ref — {it.text}")

    # ── THE ESCAPE-HATCH RATCHET. There is no exemption LIST here to shrink —
    # `⊘manual` is an inline marker on the item it excuses, so it cannot outlive
    # its subject the way an allowlist row does, and inventing a shrink arm for
    # it would be decoration. What CAN rot is the population: one more manual
    # item each cycle and the manifest quietly stops being proven. Both
    # directions bite.
    if n_manual > manual_expected:
        failures.append(
            f"{n_manual} ⊘manual item(s), ratchet is {manual_expected}. Marking an item manual "
            f"is the only way to satisfy this gate without a test; the spec calls them 'the "
            f"small minority'. Write the test, or raise MANUAL_CEIL with a reason.")
    elif n_manual < manual_expected:
        failures.append(
            f"{n_manual} ⊘manual item(s), but the ratchet still says {manual_expected}. A "
            f"ratchet that never falls stops being one. Set MANUAL_CEIL={n_manual}.")

    print(f"§11a checklist: {len(items)} items · {n_test} ✓test · {n_manual} ⊘manual "
          f"(ratchet {manual_expected}) · {len(failures)} problem(s)")

    if run and not failures:
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


# ── SELF-TEST ────────────────────────────────────────────────────────────────
_GOOD_TEST = "def test_gauge_fill():\n    assert True\n"
_GOOD_TS = "it('renders the gauge', () => { expect(1).toBe(1) })\n"
_LONG_REASON = "pure CSS easing with no measurable single-render effect"


def _checklist(*items: str) -> str:
    body = "\n".join(f"- [x] {i}" for i in items)
    return f"# Spec\n\n### 11a. Inspector checklist\n\n{body}\n\n## 12. Next\n"


def self_test() -> int:
    import contextlib
    import io
    import tempfile

    failures = 0

    def probe(name: str, want: int, items: tuple[str, ...],
              files: dict[str, str] | None = None, manual_expected: int = 0,
              spec_text: str | None = None, write_spec: bool = True) -> None:
        nonlocal failures
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            for rel, body in (files or {}).items():
                fp = repo / rel
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(body, encoding="utf-8")
            spec = repo / "spec.md"
            if write_spec:
                spec.write_text(spec_text if spec_text is not None else _checklist(*items),
                                encoding="utf-8")
            try:
                with contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()):
                    got = check(spec, repo, manual_expected)
            except Exception as e:  # noqa: BLE001 - a crash is what this asserts against
                failures += 1
                print(f"  FAIL {name}: raised {type(e).__name__}: {e} — it must return a code")
                return
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: rc={got} (want {want})")

    T = {"tests/test_gauge.py": _GOOD_TEST, "src/gauge.test.ts": _GOOD_TS}

    print("context-inspector-checklist-gate --self-test")

    probe("a fully proven checklist passes", 0,
          ("gauge fill — ✓test:tests/test_gauge.py::def test_gauge_fill",), T)

    probe("an item with NO proof-ref fails", 1, ("gauge fill",), T)
    probe("a ✓test naming a missing FILE fails", 1,
          ("gauge fill — ✓test:tests/gone.py::def test_gauge_fill",), T)
    probe("a ✓test whose NEEDLE is absent fails", 1,
          ("gauge fill — ✓test:tests/test_gauge.py::def test_nowhere",), T)
    probe("a malformed ref with no :: fails", 1,
          ("gauge fill — ✓test:tests/test_gauge.py",), T)

    # the comment-match hole this gate had already closed — kept covered
    probe("a needle matching only a COMMENT fails", 1,
          ("gauge fill — ✓test:tests/test_gauge.py::gauge fill transition",),
          {"tests/test_gauge.py": "# gauge fill transition is covered elsewhere\n"
                                  "def test_other():\n    assert True\n"})
    probe("...but a needle on an it(...) line passes", 0,
          ("gauge — ✓test:src/gauge.test.ts::renders the gauge",), T)

    # the escape hatch
    probe("a ⊘manual item with a substantive reason passes", 0,
          (f"easing — ⊘manual:{_LONG_REASON}",), T, manual_expected=1)
    probe("a ⊘manual item with a one-word reason fails", 1,
          ("easing — ⊘manual:aesthetics",), T, manual_expected=1)
    probe("a ⊘manual item with a TODO reason fails", 1,
          (f"easing — ⊘manual:TODO {_LONG_REASON}",), T, manual_expected=1)
    probe("an EXTRA ⊘manual item trips the ratchet", 1,
          (f"a — ⊘manual:{_LONG_REASON}", f"b — ⊘manual:{_LONG_REASON}"), T,
          manual_expected=1)
    probe("...and the ratchet reds when the count FALLS below it", 1,
          ("gauge fill — ✓test:tests/test_gauge.py::def test_gauge_fill",), T,
          manual_expected=1)

    # reach floor + misuse
    probe("a renamed §11a header (0 items parsed) is misuse, not a pass", 2, (),
          T, spec_text="# Spec\n\n### 11b. Something else\n\n- [x] a — ✓test:x::y\n")
    probe("a MISSING spec is misuse, not a pass", 2, (), T, write_spec=False)

    if failures:
        print(f"context-inspector-checklist-gate --self-test: {failures} rule(s) did not behave")
        return 2
    print("context-inspector-checklist-gate --self-test: every rule bites, and none cries wolf")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="§13c CI meta-check for the §11a Inspector checklist")
    ap.add_argument("--run", action="store_true",
                    help="also EXECUTE referenced test files and fail if any suite is red")
    ap.add_argument("--spec", default=str(SPEC),
                    help="override the spec path (for gate self-tests)")
    ap.add_argument("--self-test", "--selftest", dest="self_test", action="store_true",
                    help="prove every rule bites, over a synthetic checklist")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    rc = self_test()
    if rc:
        return rc
    print()
    return check(Path(args.spec), REPO, MANUAL_CEIL, args.run)


if __name__ == "__main__":
    raise SystemExit(main())
