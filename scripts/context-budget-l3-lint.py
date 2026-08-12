#!/usr/bin/env python3
"""context-budget-l3-lint.py — enforce Context Budget Law L3 (concise wire).

Spec: docs/specs/2026-07-03-context-budget-law.md §6a, §14a.

L3 = tool-result serialization uses ensure_ascii=False + drop-empty. The bytes
the model reads are serialized at the chat turn-loop's tool-result `content`
sites, which MUST go through the single `tool_result_content()` funnel
(app/services/tool_result_wire.py) — never a raw `json.dumps(...)` (which defaults
to ensure_ascii=True → the \\uXXXX tax that inflates VI/CJK 2-3×).

This lint is the regex-decidable teeth from §6a: it flags any model-facing
tool-result `content` produced by a bare `json.dumps` in the chat-service stream
loop. (L1/L2 honoring is NOT statically decidable → covered by contract-snapshot
tests, not this lint.)

Detection: a line matching   "content": json.dumps(   (or single-quoted) inside
the chat-service turn-loop files. The funnel call `tool_result_content(...)` is
the compliant form and is ignored.

Usage:
  python scripts/context-budget-l3-lint.py             # self-test, then scan
  python scripts/context-budget-l3-lint.py --self-test # the proof alone
  python scripts/context-budget-l3-lint.py --staged    # only git-staged files

Exit 0 = clean. 1 = a raw tool-result json.dumps slipped in, or an assembly path
is unwatched. 2 = self-test failure / a scan target that is not there.

GT5/GT6 · what this gate lacked
-------------------------------
**Its success line said a number nothing measured.** It printed
`len(SCAN_FILES)` — the count of NAMES in a hardcoded list — as *"N turn-loop
files checked"*, while the loop above it did `if not os.path.exists(path):
continue`. Rename one and the gate reported the same three files checked, having
read two. Both halves fixed: a missing entry is now exit 2, and the count is
files actually READ.

**`SCAN_FILES` is an enumerated list, which is `NV-3` by construction** — a file
created tomorrow is default-uncovered, and the module comment said exactly that
in prose (*"a new assembly path MUST be added here — a missing file is how a
bypass ships silently"*) with nothing to enforce it. A DISCOVERY ARM now reds
when a chat-service module uses the `tool_result_content` funnel and is not on
the list: a genuine new assembly path reaches for the funnel, so that is the
signal available without guessing.

Deliberately NOT part of that arm: "any file matching the violation regex must
be listed". Measured 2026-08-12, two chat-service files match it and neither is
in scope — `routers/outputs.py` serializes a downloadable `chat_export.json`,
and `services/stream_events.py` builds the AG-UI `TOOL_CALL_RESULT` SSE envelope
the BROWSER reads. L3 governs the bytes the MODEL reads. An arm that reds on
those two would be crying wolf about the wrong wire.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The turn-loop files that assemble model-facing tool-result messages. Every
# entry must EXIST (a missing one is exit 2) and any funnel user outside this
# list reds — see the discovery arm in `run_lint`.
SCAN_FILES = (
    "services/chat-service/app/services/stream_service.py",
    "services/chat-service/app/services/voice_stream_service.py",
    "services/chat-service/app/services/subagent_runtime.py",
)

# Where a new assembly path would live, and the funnel's own module (which uses
# the name because it DEFINES it).
CHAT_SERVICE_ROOT = "services/chat-service/app"
FUNNEL_HOME = "services/chat-service/app/services/tool_result_wire.py"
FUNNEL_CALL = "tool_result_content"

# A tool-result content site fed a raw json.dumps. Two shapes (T0 review LOW-2 —
# the split-variable + multiline forms bypassed the old single-line regex):
#   (a) inline dict:   "content": json.dumps(...)      (may span lines → DOTALL)
#   (b) split var:     content = json.dumps(...)  then "content": content
# `tool_result_content(...)` is the compliant funnel and never matches either.
# `\bcontent` (not `content_parts`) keeps the assignment form off the persist seam.
VIOLATION_RES = (
    re.compile(r"""["']content["']\s*:\s*json\.dumps\(""", re.DOTALL),
    re.compile(r"""\bcontent\s*=\s*json\.dumps\("""),
)

# An assembly site of any kind — used only to REPORT a watched file that
# currently assembles nothing, so a decorative scope row is visible rather than
# silent (`subagent_runtime.py` is one today).
ASSEMBLY_RE = re.compile(r"""["']content["']\s*:|(\bcontent\s*=)""")


def _staged_files(repo_root: str) -> set[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=repo_root, capture_output=True, text=True,
    ).stdout
    return {line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()}


def run_lint(repo_root: str = REPO_ROOT, scan_files=SCAN_FILES,
             staged_only: bool = False) -> int:
    staged = _staged_files(repo_root) if staged_only else None

    # ── SHRINK ARM (GT-F5). A named scan target that is not a file watches
    # nothing, and would watch it again the day the name returned. The old code
    # skipped it and still counted it as checked.
    if not staged_only:
        missing = [rel for rel in scan_files
                   if not os.path.isfile(os.path.join(repo_root, rel))]
        if missing:
            print("context-budget-l3-lint: ERROR — SCAN_FILES entr(ies) not present:",
                  file=sys.stderr)
            for rel in missing:
                print(f"  {rel}", file=sys.stderr)
            print("  A renamed assembly path must not retire its own guard silently.",
                  file=sys.stderr)
            return 2

    violations: list[str] = []
    read = 0
    inert: list[str] = []
    for rel in scan_files:
        if staged is not None and rel not in staged:
            continue
        path = os.path.join(repo_root, rel)
        if not os.path.isfile(path):
            continue  # staged mode only — the arm above covers a full run
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        read += 1
        if not ASSEMBLY_RE.search(text):
            inert.append(rel)
        for rx in VIOLATION_RES:
            for m in rx.finditer(text):
                lineno = text.count("\n", 0, m.start()) + 1
                snippet = text[m.start():m.start() + 60].splitlines()[0]
                violations.append(f"{rel}:{lineno}: {snippet.strip()}")

    # ── REACH FLOOR (GT-F3). With the arm above, the only way to read nothing on
    # a full run is an EMPTY scan list — which is a real way to retire this gate.
    if not staged_only and read == 0:
        print("context-budget-l3-lint: ERROR — 0 turn-loop file(s) read. An empty "
              "SCAN_FILES retires the rule while still exiting 0 (BDR-82).",
              file=sys.stderr)
        return 2

    # ── DISCOVERY ARM (NV-3). The list is enumerated, so a new assembly path is
    # default-uncovered. A genuine one reaches for the funnel; if it does and is
    # not watched, say so.
    unwatched: list[str] = []
    if not staged_only:
        listed = set(scan_files)
        root = os.path.join(repo_root, CHAT_SERVICE_ROOT)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in ("__pycache__", "tests")]
            for fn in filenames:
                if not fn.endswith(".py") or fn.startswith(("test_", "conftest")):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, repo_root).replace(os.sep, "/")
                if rel in listed or rel == FUNNEL_HOME:
                    continue
                try:
                    with open(full, encoding="utf-8") as fh:
                        if FUNNEL_CALL in fh.read():
                            unwatched.append(rel)
                except OSError:
                    continue

    if violations or unwatched:
        if violations:
            print("Context Budget Law L3 violation — tool-result content must use")
            print("tool_result_content() (ensure_ascii=False), not raw json.dumps():")
            print()
            for v in violations:
                print(f"  {v}")
            print()
            print("Fix: replace json.dumps(<payload>) with tool_result_content(<payload>)")
            print("     (from app.services.tool_result_wire). See spec §6a/§14a.")
        for rel in sorted(unwatched):
            print(f"context-budget-l3-lint: FAIL — {rel} uses {FUNNEL_CALL}() but is not in "
                  f"SCAN_FILES. A tool-result assembly path this lint does not read is a "
                  f"bypass waiting to ship (NV-3: an enumerated list is default-uncovered).")
        return 1

    note = f"; {len(inert)} watched file(s) assemble nothing today: {', '.join(inert)}" if inert else ""
    print(f"L3 wire lint clean — {read} of {len(scan_files)} turn-loop file(s) READ{note}.")
    return 0


# ── SELF-TEST ────────────────────────────────────────────────────────────────
CLEAN = ('from app.services.tool_result_wire import tool_result_content\n'
         'def f(p):\n    return {"role": "tool", "content": tool_result_content(p)}\n')


def self_test() -> int:
    import contextlib
    import io
    import tempfile

    failures = 0

    def probe(name: str, want: int, files: dict[str, str], scan=None) -> None:
        nonlocal failures
        scan = SCAN_FILES[:1] if scan is None else scan
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, CHAT_SERVICE_ROOT.replace("/", os.sep)),
                        exist_ok=True)
            for rel, body in files.items():
                full = os.path.join(d, *rel.split("/"))
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "w", encoding="utf-8") as fh:
                    fh.write(body)
            try:
                with contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()):
                    got = run_lint(d, scan)
            except Exception as e:  # noqa: BLE001 - a crash is what this asserts against
                failures += 1
                print(f"  FAIL {name}: raised {type(e).__name__}: {e} — it must return a code")
                return
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: rc={got} (want {want})")

    W = SCAN_FILES[0]          # a watched turn-loop file
    OTHER = "services/chat-service/app/services/other.py"

    print("context-budget-l3-lint --self-test")

    probe("a funnelled tool result passes", 0, {W: CLEAN})

    probe("an inline \"content\": json.dumps( fails", 1, {
        W: 'def f(p):\n    return {"role": "tool", "content": json.dumps(p)}\n'})
    probe("a single-quoted \'content\': json.dumps( fails", 1, {
        W: "def f(p):\n    return {'role': 'tool', 'content': json.dumps(p)}\n"})
    probe("a MULTILINE content: json.dumps( fails", 1, {
        W: 'def f(p):\n    return {\n        "content":\n            json.dumps(p),\n    }\n'})
    probe("the split-variable form fails", 1, {
        W: 'def f(p):\n    content = json.dumps(p)\n    return {"content": content}\n'})

    # …and the shapes that must NOT cry wolf
    probe("...but content_parts = json.dumps( does not", 0, {
        W: 'def f(p):\n    content_parts = json.dumps(p)\n    return content_parts\n'})
    probe("...nor a json.dumps that is not a content site", 0, {
        W: 'def f(p):\n    body = json.dumps(p)\n    return body\n'})
    probe("...nor the same violation in an UNWATCHED file", 0, {
        W: CLEAN,
        "services/chat-service/app/routers/outputs.py":
            'def f(p):\n    content = json.dumps(p)\n    return content\n'})

    # the discovery arm — an enumerated list is default-uncovered
    probe("a NEW funnel user outside SCAN_FILES fails", 1, {W: CLEAN, OTHER: CLEAN})
    probe("...but the funnel's own module does not", 0, {
        W: CLEAN, FUNNEL_HOME: 'def tool_result_content(p):\n    return p\n'})
    probe("...nor a test file", 0, {
        W: CLEAN,
        "services/chat-service/app/services/test_wire.py": CLEAN})

    # shrink arm + reach floor. The shrink-arm case needs a list where ONE entry
    # is present and one is missing: with a single missing entry the floor fires
    # too, and the probe passes whichever rule is live — a degenerate fixture that
    # certifies neither. The bite is what said so (the arm went green).
    probe("a SCAN_FILES entry that is not a file is misuse, not a pass", 2,
          {W: CLEAN}, scan=(W, "services/chat-service/app/services/gone.py"))
    probe("an EMPTY SCAN_FILES is misuse, not a pass", 2, {}, scan=())

    if failures:
        print(f"context-budget-l3-lint --self-test: {failures} rule(s) did not behave")
        return 2
    print("context-budget-l3-lint --self-test: every rule bites, and none cries wolf")
    return 0


def main() -> int:
    if "--self-test" in sys.argv or "--selftest" in sys.argv:
        return self_test()
    rc = self_test()
    if rc:
        return rc
    print()
    return run_lint(REPO_ROOT, SCAN_FILES, "--staged" in sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
