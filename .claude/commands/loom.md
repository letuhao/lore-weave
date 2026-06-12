---
description: Run the 12-phase v2.2 human-in-loop workflow on a task — classify size, then drive CLARIFY→…→RETRO with PO checkpoints and the workflow-gate. General-purpose, for any service/track.
---

# /loom — Run the human-in-loop 12-phase workflow

`/loom` weaves a task through the **12-phase v2.2 human-in-loop workflow**. The phases, roles, size table, and anti-skip rules live in **`CLAUDE.md` → "Task Workflow"** — that file is the SSOT; this command is just the invocation harness around it. `/loom` is **general-purpose**: it is NOT tied to any one feature, service, or track.

**Argument** (optional): what to work on — a free-text task, a ticket/milestone id, or `continue`.
- A task/id → scope the workflow to it.
- `continue` or empty → read the relevant **▶ NEXT SESSION** block (default `docs/sessions/SESSION_HANDOFF.md`; or a track-specific `docs/**/SESSION_HANDOFF.md` if the task clearly belongs to one) and resume there.

## The 12 phases
`CLARIFY → DESIGN → REVIEW → PLAN → BUILD → VERIFY → REVIEW → QC → POST-REVIEW → SESSION → COMMIT → RETRO`
- **PO checkpoints — STOP and WAIT for the human:** end of **CLARIFY** and at **POST-REVIEW**.
- Phases may be skipped **only** per the size-table allowances in `CLAUDE.md` (XS: CLARIFY+PLAN · S: PLAN). Never self-authorize a skip — STOP and ask.

## Process when /loom is invoked
1. **Scope** the task from the argument (or the ▶ NEXT block on `continue`/empty). State the task + its goal in one line.
2. **Classify size** — from the **repo root only** (a subdir invocation splits the state file):
   `bash scripts/workflow-gate.sh size <XS|S|M|L|XL> <files> <logic> <sideeffects>`
   (count files touched · logic changes · side effects, per the `CLAUDE.md` size table).
3. **`/amaw` opt-in** when the task is **L+ and load-bearing**: data migrations, schema changes, tenant/isolation boundaries, security-critical paths, multi-system contracts. Announce + invoke `/amaw` before BUILD. Don't invoke for everyday work.
4. **Enter CLARIFY** (`bash scripts/workflow-gate.sh phase clarify`); recover the acceptance criteria from the task's spec/plan row. **STOP at CLARIFY end** for the PO checkpoint (skip the stop only when resuming a phase already past it).
5. Drive the phases with the gate (`phase <name>` / `complete <name> "<evidence>"`). **VERIFY is an evidence gate** — run the command, read the full output, *then* claim. If the change touches **≥2 services**, the VERIFY evidence needs a **live-smoke token** (or `LIVE-SMOKE deferred to D-<NAME>` / `live infra unavailable: <reason>`).
6. **REVIEW (code)** is 2-stage (spec compliance + code quality). **At POST-REVIEW:** present a concise summary (files, decisions, verify evidence), **STOP and WAIT**. Proactively suggest **`/review-impl`** for load-bearing code (auth/credentials, tenant isolation, destructive ops, injection defenses, new service boundaries, concurrency, migrations).
7. **SESSION:** overwrite the **▶ NEXT SESSION** block in the relevant `SESSION_HANDOFF.md` (date/HEAD, NEXT items, Deferred). Land it in the **same commit** as the code.
8. **COMMIT:** stage only changed files (no `git add -A`); message names the phase/milestone + review fixes + test count. **Push only with explicit user approval.**
9. **RETRO:** non-obvious decisions or workarounds → `add_lesson` to ContextHub if available, else a note in the handoff. Skip if nothing notable.

## Operational notes
- Run `scripts/workflow-gate.sh` (or `python scripts/workflow-gate.py`) **from the repo root** — a subdir invocation splits the `.workflow-state.json`.
- This monorepo ships many services as **separate service + worker images**. When verifying a change live, rebuild **both** (stale-image false-greens are a recurring trap); `scripts/build-stack.sh` stamps a git-SHA freshness label.
- Cross-service contracts hide bugs that unit/mocks miss — prefer a real live-smoke at VERIFY when ≥2 services are touched.

## What /loom does NOT do
- Does NOT skip phases or the PO checkpoints.
- Does NOT self-authorize a size/skip change — if the task turns out bigger than classified, STOP, reclassify, announce.
- Is NOT tied to any single track, service, or feature — scope comes from the argument or the handoff.
