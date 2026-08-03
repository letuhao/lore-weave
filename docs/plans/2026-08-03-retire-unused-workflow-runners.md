# Retire the unused workflow runners — `/warp`, `/raid`, `/amaw`

**Status:** planned, not started · **Author:** 2026-08-03 · **Trigger:** the owner reports using none
of them; `/review-impl` is the only runner still in daily use.

## Why

The repo carries five slash-command runners. Four are effectively dead:

| Runner | Size | Superseded by | Still used? |
|---|---|---|---|
| `/loom` | 43 lines | `aif-plan` (818) + `aif-implement` (987) + `aif-verify` (556) | no — **retired 2026-08-03** |
| `/warp` | 173 lines | `implement-coordinator` + `implement-worker` (real worktree isolation) | no |
| `/raid` | 106 lines | `implement-coordinator`, `plan-coordinator` + `plan-polisher` | no |
| `/amaw` | 73 lines | six read-only sidecars + `aif-review +check` | no |
| `/review-impl` | 200 lines | **nothing** — its standards gate is repo-specific and irreplaceable | **yes, daily** |

The AI Factory equivalents are larger, better engineered, maintained upstream, and now installed for
every agent target. Keeping thin local duplicates of them means two processes for the same job, which
is the exact failure `docs/standards/agent-workflow.md` exists to prevent.

**What is NOT being retired:** the 12-phase workflow itself, `scripts/workflow-gate.py`, the
pre-commit hook, `SESSION_HANDOFF.md`, and `docs/standards/**`. Those are the mechanical part, they
are independent of the runners, and the owner still uses them. Deleting a runner must not touch them.

## Why this needs a plan rather than a delete

`/loom` was genuinely cheap — one command file and three prose mentions, removed the same day. The
other three are not, and an early read of this that called `/warp` "cheap to remove" was wrong. Measured:

**`/warp`**
- `scripts/workflow-gate.py` — a live registered verb: `"slices": cmd_slices` (dispatch table line 732,
  function line 705)
- `scripts/warp/slice-manifest-validate.py`, `scripts/warp/worktrees.py`, `scripts/warp/slice-runner-prompt.md`
- `scripts/test_slice_manifest_validate.py` — a real test, currently green
- `docs/specs/2026-06-12-warp-parallel-mode.md`
- `agentic-workflow/scripts/workflow-gate.py` — the bundle's copy carries the same verb

**`/raid`**
- `scripts/raid/cycle-runner-prompt.md`
- `.raid/active-task.yaml` (per-branch task identity)

**`/amaw`**
- `scripts/workflow-gate.py` — state keys `amaw_enabled`, `amaw_enabled_at`; the `amaw-enable` verb;
  the `AUDIT_LOG.jsonl` append helpers gated on the flag
- `.claude/settings.json` — permission entries
- `.github/workflows/foundation-ci.yml`
- `docs/amaw-workflow.md`, `agentic-workflow/AMAW.md`, `agentic-workflow/.claude/commands/amaw.md`
- `docs/audit/AUDIT_LOG.jsonl` — committed history that must survive the removal

`/amaw` is the deepest: its flag is threaded through the gate that every commit passes. Removing it
carelessly breaks commits for everyone.

## Order, and why

1. **`/raid` first** — shallowest of the three. Delete the command, `scripts/raid/`, and `.raid/`;
   confirm `gate-wiring-gate.py` stays green (it catches a registry row pointing at a deleted script,
   which is exactly how the ContextHub removal was caught).
2. **`/warp` second** — delete the command, `scripts/warp/`, the `slices` verb and its dispatch entry,
   the test, and the spec. **Re-run `scripts/workflow-gate.py status` and the full pre-commit chain**:
   removing a dispatch entry is where a typo silently disables a neighbouring verb.
3. **`/amaw` last, and only deliberately.** Two sub-decisions belong to the human, not the agent:
   - Does AMAW mode get replaced by the `aif-*` sidecars, or dropped outright? The sidecars are
     read-only advisors; AMAW's Scope Guard was a *blocking* gate. That is a behaviour change, not a
     rename.
   - `docs/audit/AUDIT_LOG.jsonl` is committed history. It stays. The writer disappears; the record
     does not.

## Acceptance

- `python scripts/gate-wiring-gate.py` green after each step — no registry row pointing at a deleted script.
- `bash scripts/workflow-gate.sh status` runs, and a full pre-commit chain passes, after each step.
- `python scripts/agent-skills-parity.py` green (removing a runner must not disturb the vendored trees).
- `bash agentic-workflow/install.sh <scratch-repo>` still exits 0 — the bundle ships its own copy of
  the gate, so a verb removed in one and not the other is drift that only appears at install time.
- No orphaned prose: `AGENTS.md`, `CONTRIBUTING.md` and `docs/standards/agent-workflow.md` name no
  command that no longer exists.

## The trap to avoid

`loom` also names a **Rust model-checking crate** used by `conformance-ci.yml`
(`H1-loom CircuitBreaker race-check`) and `breaker-core`. It has nothing to do with the slash command.
A `grep -r loom` sweep during cleanup will hit it. **Do not touch anything under `services/**` or
`.github/workflows/conformance-ci.yml` for this work.**
