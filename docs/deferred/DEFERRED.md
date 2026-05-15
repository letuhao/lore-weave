# Deferred Items

<!-- Managed by Scribe (AMAW) or main session (default mode). Do not edit manually unless cleaning up. -->
<!-- Next ID: 007 -->

| ID | Origin | Description | Target | Severity |
|---|---|---|---|---|
| 001 | 2026-05-15 amaw-l3-deepen /review-impl #5 | `task_slug` not validated — comma in slug splits into multiple tags downstream (`",".join(tags)` then mcp-query.py splits back on comma). No injection risk (subprocess list form). Fix: normalize comma → dash in `cmd_amaw_enable`, or argparse-validate slug pattern `^[a-z0-9][a-z0-9-]*[a-z0-9]$`. | L4 hardening | LOW |
| 002 | 2026-05-15 amaw-l3-deepen /review-impl #6 | `"REJECTED" in evidence.upper()` substring match in `cmd_complete` bridge logic — false positives on "NOT REJECTED" or "rejected the rejected pattern". Fix: word-boundary regex `\bREJECTED\b` or check evidence prefix `"REJECTED:"` / `"status: REJECTED"`. | L4 hardening | LOW |
| 004 | 2026-05-15 amaw-l3-deepen /review-impl #8 | `cmd_pre_commit` early-exits silent when no STATE_FILE, but `&&`-chained `cmd_amaw_pre_commit` then calls `load_state()` which CREATES `.workflow-state.json` from INITIAL_STATE. Side effect: every commit by an agent NOT in any tracked task creates a stale state file, surfacing confusing `[ ]` markers on next `status`. Fix: in `cmd_amaw_pre_commit`, also early-exit if STATE_FILE absent before `load_state()`. | L4 hardening | LOW |
| 005 | 2026-05-15 amaw-l3-deepen /review-impl #9 | Sub-agent permission prompts may interrupt cold-start when first `python scripts/mcp-query.py ...` call fires from sub-agent's Bash tool. Depends on `.claude/settings.json` allow-list. Fix: add `python scripts/mcp-query.py *` (or `python scripts/mcp-query.py:*`) to project allow-list. Verify on first /amaw dogfood. | First /amaw dogfood (Phase 0b SSE parser, next session) | LOW |

## Recently cleared (within 5 sessions)

| ID | Cleared | How |
|---|---|---|
| 003 | 2026-05-15 amaw-atomic-save-state | First `/amaw` dogfood. `save_state` now writes a PID-unique `.tmp` then `Path.replace()` (atomic rename); `cmd_reset` sweeps stale tmps; `finally`-unlink cleans own tmp. Adversary r1 added 3 hardening WARNs (all fixed). |
| 006 | 2026-05-15 batch pre-flight | AMAW.md Adversary + Scope Guard prompt templates now pre-instruct the Bash-heredoc fallback for writing findings/post-review docs, since the Write tool blocks sub-agents from writing report files. |
