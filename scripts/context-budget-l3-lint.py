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
  python scripts/context-budget-l3-lint.py            # full scan (CI / manual)
  python scripts/context-budget-l3-lint.py --staged   # only git-staged files

Exit 0 = clean. Exit 1 = a raw tool-result json.dumps slipped in.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The turn-loop files that assemble model-facing tool-result messages. A new
# assembly path (a third stream service) MUST be added here — a missing file is
# how a bypass ships silently.
SCAN_FILES = (
    "services/chat-service/app/services/stream_service.py",
    "services/chat-service/app/services/voice_stream_service.py",
    "services/chat-service/app/services/subagent_runtime.py",
)

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


def _staged_files() -> set[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    ).stdout
    return {line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()}


def main() -> int:
    staged_only = "--staged" in sys.argv
    staged = _staged_files() if staged_only else None

    violations: list[str] = []
    for rel in SCAN_FILES:
        if staged is not None and rel not in staged:
            continue
        path = os.path.join(REPO_ROOT, rel)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for rx in VIOLATION_RES:
            for m in rx.finditer(text):
                lineno = text.count("\n", 0, m.start()) + 1
                snippet = text[m.start():m.start() + 60].splitlines()[0]
                violations.append(f"{rel}:{lineno}: {snippet.strip()}")

    if violations:
        print("Context Budget Law L3 violation — tool-result content must use")
        print("tool_result_content() (ensure_ascii=False), not raw json.dumps():")
        print()
        for v in violations:
            print(f"  {v}")
        print()
        print("Fix: replace json.dumps(<payload>) with tool_result_content(<payload>)")
        print("     (from app.services.tool_result_wire). See spec §6a/§14a.")
        return 1

    print(f"L3 wire lint clean ({len(SCAN_FILES)} turn-loop files checked).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
