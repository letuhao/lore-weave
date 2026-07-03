# Spec — Subagent Write Delegation (lift the read-only clamp) · D-REG-P5-SUBAGENT-WRITE-DELEGATION

**Status:** DESIGN (no build this round — user-gated). Extends the shipped subagent runtime
([`2026-07-03-subagent-runtime.md`](2026-07-03-subagent-runtime.md), `_run_subagent_call` in
`stream_service.py`). Owner surface: chat-service.

---

## 1. Problem

v1 subagents are clamped **read-only** (`permission_mode='ask'` in `_run_subagent_call`) — a
deliberate simplification so a nested Tier-A/W write never hits the human-approval gate, because
the nested `_stream_with_tools` cannot surface a `suspend` (there is no browser mid-nested-loop;
the current code `break`s on a nested suspend). That means a subagent can read + reason but never
perform an approved write, even one the caller could do. This spec lifts the clamp **safely**.

## 2. Goal

A subagent may perform a write **iff** it clears the SAME human-approval gate the main loop uses —
never an escalation. The write is approved once by the human (via the normal `tool_approval` card),
executed, audited as a delegated write, and the delegating turn resumes.

## 3. The crux — bubbling a nested suspend through `run_subagent`

The main loop's approval flow is a **suspend/resume**: a Tier-A un-allowlisted (or
`require_approval`-hooked) tool call yields `{suspend:{working, pending_tool_call, …}}`; the caller
persists the suspended run + emits a pending card; the human approves; a resume request re-enters
`_stream_with_tools` with the approved result appended. A nested sub-run cannot do this today
because its suspend is swallowed inside `_run_subagent_call`.

**Design:** make the nested suspend a **first-class suspend of the PARENT turn**, tagged with the
nesting frame so resume re-enters the sub-run at the right depth.

1. **Clamp becomes `min(caller_mode, write)`** — a subagent in a `write` turn runs in `write` mode
   (so a scoped Tier-A tool reaches the approval gate); in `ask`/`plan` it stays read-only as now.
2. **Nested suspend is captured, not dropped.** When the nested `_stream_with_tools` yields a
   `suspend`, `_run_subagent_call` re-emits it to the parent loop wrapped in a **subagent frame**:
   `{suspend:{…, subagent_frame:{name, sub_working, sub_seed_usage, depth}}}`. The parent loop
   propagates it up as the turn's suspend (the `run_subagent` tool-call itself is the pending
   parent step).
3. **Persisted suspend carries the frame.** `save_suspended_run` stores the parent `working` (with
   the assistant's `run_subagent` tool-call pending) PLUS the `subagent_frame` (persona name,
   scoped tool set key, the sub-run's `working` + usage). The pending card the human sees is the
   normal `tool_approval` card, annotated "requested by subagent «name»".
4. **Resume re-enters the sub-run.** On approve, `resume_stream_response` detects a `subagent_frame`
   and, instead of resuming the main loop, **re-invokes `_run_subagent_call`** with the frame's
   `sub_working` + the approved tool result appended + `subagent_depth` restored. The sub-run
   finishes; its synthesized result becomes the `run_subagent` tool result; the MAIN loop then
   resumes with that result. (Two-level resume: sub-run first, then parent.)
5. **No escalation, ever.** The nested approval gate is the same `is_tool_approved` allowlist +
   Tier-A prompt-once; `permission_mode` is `min(caller, …)`; the scoped `tool_scope` whitelist
   still bounds WHICH tools (a `glossary_*` subagent can still never touch `book_write`); the human
   approves the specific write. Depth stays capped at 1.

## 4. Data / contract changes
- `suspended_runs` gains a nullable `subagent_frame JSONB` (persona name, sub_working, sub_usage,
  scoped-set key, depth). Additive migration.
- The suspend chunk schema gains `subagent_frame`; `resume_stream_response` branches on it.
- Audit: a delegated write emits `subagent_write` (caller→subagent→tool, approved_by) — the
  delegation-chain record the multi-agent access-control literature calls for.

## 5. Edge cases (fold from the runtime spec §7b)
- **Cancel mid-nested-suspend** — cancelling the parent turn discards the persisted subagent_frame
  (no orphaned resume). **Frontend/meta tools** stay scope-excluded (still headless). **Result cap**
  unchanged. **A second nested write in one sub-run** → the sub-run suspends again on the next gate
  (sequential approvals), depth still 1. **Model_ref fallback** unchanged. **Token budget** — the
  sub-run's post-resume tokens still debit the same turn budget.

## 6. Testing
- Unit: the clamp is `min(caller, write)`; the nested-suspend capture wraps a `subagent_frame`;
  `resume` with a frame re-enters the sub-run (fake nested stream).
- Live E2E-P5-D: a `book-editor` subagent (`tool_scope=["book_*"]`) in a WRITE turn → the sub-run
  proposes a book write → the human `tool_approval` card appears ("requested by subagent
  book-editor") → approve → the write executes → the sub-run synthesizes → the main turn reports it;
  and the negative: deny → the write does not happen + the sub-run reports the denial.

## 7. Milestones (when built)
M1 clamp `min(caller,write)` + nested-suspend capture (frame). M2 persist + resume re-entry
(two-level). M3 audit + the delegated-write card annotation. M4 live E2E-P5-D + `/review-impl`
(privilege-boundary + resume-correctness are load-bearing).

## 8. Size / risk
**L**, security-critical (privilege boundary + a novel two-level suspend/resume). `/review-impl`
mandatory. Recommend building only after the maintainer wants write-capable subagents — the
read-only v1 is a safe, shipped default.
