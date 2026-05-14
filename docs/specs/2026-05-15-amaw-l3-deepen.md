# AMAW × ContextHub L3 Deepening — Spec + Design

**Date:** 2026-05-15
**Author:** Claude (default v2.2 mode, no /amaw — meta-paradox avoidance)
**Branch:** `mmo-rpg/zone-map-design-non-human-in-loop`
**Workflow size:** XL (11+ files, 6 logic changes, side effects YES)
**State machine:** `.workflow-state.json` (not committed)
**Predecessor:** Bundle v2.3 deployment (commits `9384eafd`..`23406566`)
**Status:** DESIGN phase — spec frozen pending REVIEW + PLAN

---

## 1. Why this exists

ContextHub MCP is provisioned (8 containers, project `mmo-rpg-zone-map-design-non-human-in-loop`, workspace_root active) but the agentic-workflow bundle barely uses it. Of 12 phases, only RETRO explicitly calls `add_lesson`. Sub-agent prompt templates (Adversary/Scope Guard/Scribe) are "files-as-truth, chat is ephemeral" but treat MCP — which IS files-as-truth (Postgres-backed, durable, cross-session) — as if it didn't exist.

**Two parallel persistence systems:**
1. `docs/audit/AUDIT_LOG.jsonl` — local file, append-only, committed to git
2. ContextHub `lessons` table — Postgres, embedded, cross-session searchable

No bridge between them. Cross-task search via `search_lessons` returns nothing because nothing writes there except RETRO (rare, manual).

L3 deepening: bridge the two systems + give sub-agents MCP access + auto-load context at CLARIFY.

## 2. Locked decisions (CLARIFY phase Q&A, 2026-05-15)

| Decision | Choice | Rationale |
|---|---|---|
| Workflow mode for THIS task | Default v2.2 + `/review-impl` | Meta-paradox: can't use shallow AMAW to build deep AMAW (sub-agents would review their own redefinitions). First real `/amaw` run waits for Phase 0b SSE parser. |
| Scope of L3 changes | AMAW-mode only (default v2.2 untouched) | Default v2.2 has no AUDIT_LOG, no sub-agents — bridge is N/A. AMAW-mode hooks land in AMAW.md, amaw.md slash command, not WORKFLOW.md. |
| Bridge granularity | Selective: `sprint_complete` + `pragmatic_stop` + REJECTED reviews only | High-signal events as lessons. ~3-5 lessons/task. Avoids drowning `search_lessons` results in noise. |
| Sub-agent MCP access | Helper script wrapper `scripts/mcp-query.py` | Predictable CLI surface, language-agnostic, testable, no dependency on subagent_type tool inheritance (untested in this env). |
| Edit safety while modifying AMAW.md | No freeze | Default v2.2 mode = no sub-agents spawned, so file edits cannot mid-flight invalidate any reviewer. |

## 3. Architecture (4 components)

### Component 1 — `scripts/mcp-query.py` (NEW)

A REST-backed CLI wrapper for ContextHub MCP queries. Sub-agents call it via shell:

```bash
python scripts/mcp-query.py search_lessons "guardrail-style topic" --limit 5
python scripts/mcp-query.py add_lesson --type general_note --title "X" --content "Y" --tags amaw,sprint
python scripts/mcp-query.py check_guardrails "git push to main"
python scripts/mcp-query.py reflect "task area X"
```

**Implementation:**
- HTTP client to `http://localhost:3001/api/...` (REST, NOT MCP) — same as ContextHub MCP server's REST surface
- Default `project_id` from env `CONTEXTHUB_PROJECT_ID` (set via export or CLI flag)
- Stdout: pretty-printed JSON or formatted summary (controlled by `--format=json|summary`, default summary)
- Exit code: 0 success, 1 transport error, 2 server error
- Required CLI verbs (MVP): `search_lessons`, `add_lesson`, `check_guardrails`, `reflect`, `search_code_tiered`
- Connection check: `python scripts/mcp-query.py ping` → returns `OK` or fails fast
- Default ContextHub URL: `http://localhost:3001` (override via env `CONTEXTHUB_API_URL`)

**Why REST not MCP:**
- MCP tools require Claude-Code-managed deferred-load via ToolSearch. Sub-agents spawned via Agent tool may or may not inherit that registration. REST works regardless.
- Sub-agents in cold-start mode can't call tools they don't know about; CLI is universal.
- Helper script can be run from main session, sub-agents, or CI alike.

### Component 2 — AUDIT_LOG → ContextHub bridge (workflow-gate.py extension)

Extend `workflow-gate.py` so when an AMAW-mode event is appended to AUDIT_LOG.jsonl, **selective high-signal events** also call `add_lesson` via `mcp-query.py`.

**Trigger events** (only these get bridged):
- `sprint_complete` — task summary as `general_note` lesson
- `pragmatic_stop` — workaround/residual-risk record as `workaround` lesson
- `review` event with `status=REJECTED` — finding pattern as `general_note` lesson tagged `adversary-rejection`

**Event → lesson mapping:**

| AUDIT_LOG event | Lesson type | Title template | Content | Tags |
|---|---|---|---|---|
| `sprint_complete` | `general_note` | `Sprint complete: <task>` | task summary, files touched, key decisions | `amaw`, `sprint`, task-slug |
| `pragmatic_stop` | `workaround` | `Pragmatic stop: <task> r<N>` | residual risk, why stopped | `amaw`, `pragmatic-stop`, task-slug |
| `review` (REJECTED) | `general_note` | `Adversary REJECTED: <task> r<N>` | finding summary | `amaw`, `adversary-rejection`, task-slug |

**Implementation:**
- New helper function `_bridge_to_contexthub(event_dict)` in `workflow-gate.py`
- Called from `cmd_complete()` and any other event-write path
- Best-effort: if mcp-query.py fails or ContextHub down, log warning to stderr but don't block workflow
- Gated by `state['amaw_enabled'] = True` — only fires when /amaw was invoked. New state field; default false.

**New CLI verb:** `workflow-gate.sh amaw-enable` — sets `amaw_enabled=true` in state. Called by `/amaw` slash command flow.

### Component 3 — Sub-agent MCP-aware prompts (AMAW.md edits)

Update 3 sub-agent prompt templates in AMAW.md to call `mcp-query.py` as part of their cold-start protocol.

**Adversary** (REVIEW design + REVIEW code):

```diff
 Read ONLY:
 - docs/specs/<your-design-file>.md
 - docs/audit/AUDIT_LOG.jsonl (for prior context if review round > 1)
 - The relevant code files for code-review variants
+- Run `python scripts/mcp-query.py search_lessons "<task topic>" --type guardrail --limit 10`
+  to surface captured rules. Treat returned lessons as adversarial-question seeds.
+- Run `python scripts/mcp-query.py search_lessons "<changed-file pattern>" --tags adversary-rejection --limit 5`
+  to find prior REJECTED findings on similar code. If you find recurrence, frame
+  finding as "this regressed prior fix X".
```

**Scope Guard** (POST-REVIEW):

```diff
 Read ONLY:
 - docs/specs/<task-spec>.md
 - docs/specs/<task-design>.md
 - docs/audit/AUDIT_LOG.jsonl (all prior phase events)
 - Latest diff or relevant code files
+- Run `python scripts/mcp-query.py check_guardrails "ready-to-commit"` and respect
+  its verdict. If BLOCKED → escalate to BLOCKED in your output, name the guardrail.
+- Run `python scripts/mcp-query.py search_lessons "<task area>" --type guardrail --limit 5`
+  to verify no captured rule is being violated by the diff.
```

**Scribe** (CLARIFY session-start scan):

```diff
 (a) CLARIFY session-start scan: read DEFERRED.md, list any items whose trigger
     condition is now met. Report each as a candidate "should we handle this now?"
     line for the main session.
+    Also: run `python scripts/mcp-query.py reflect "<task-area>"` if topic is
+    non-trivial — synthesizes prior lessons into a 1-paragraph context primer.
+    Run `python scripts/mcp-query.py search_lessons "<task intent>" --limit 8` and
+    print top 3 most-relevant titles for the main session to consider.
```

### Component 4 — Pre-commit hook calls check_guardrails

Modify `.claude/settings.json` PreToolUse hook so AMAW commits also pass `check_guardrails`. Default v2.2 commits unaffected (gate only fires when `state['amaw_enabled']==True`).

```diff
 {
   "hooks": {
     "PreToolUse": [{
       "matcher": "Bash",
       "hooks": [{
         "type": "command",
-        "command": "bash -c 'if echo \"$CLAUDE_TOOL_INPUT\" | grep -qE \"git commit\"; then bash ./scripts/workflow-gate.sh pre-commit; fi'",
+        "command": "bash -c 'if echo \"$CLAUDE_TOOL_INPUT\" | grep -qE \"git commit\"; then bash ./scripts/workflow-gate.sh pre-commit && bash ./scripts/workflow-gate.sh amaw-pre-commit; fi'",
         "timeout": 10000,
-        "description": "Block git commit if VERIFY or SESSION phases not completed"
+        "description": "Block git commit if VERIFY/POST-REVIEW/SESSION not done; also check_guardrails when AMAW mode active"
       }]
     }]
   }
 }
```

**New workflow-gate verb:** `amaw-pre-commit`:
- If `state['amaw_enabled'] == False` → exit 0 (no-op for default v2.2)
- If `state['amaw_enabled'] == True` → call `mcp-query.py check_guardrails "git commit"` → propagate exit code
- If ContextHub down → warning to stderr, exit 0 (don't block on infra)

## 4. File-level changes

### NEW files (4)

| Path | Purpose |
|---|---|
| `agentic-workflow/scripts/mcp-query.py` | REST CLI wrapper (canonical bundle copy) |
| `scripts/mcp-query.py` | Same content (deployed copy) |
| `docs/specs/2026-05-15-amaw-l3-deepen.md` | This spec |
| `docs/plans/2026-05-15-amaw-l3-deepen.md` | PLAN file (Phase 4 output) |

### MODIFIED files (7)

| Path | Change |
|---|---|
| `agentic-workflow/scripts/workflow-gate.py` | Add `_bridge_to_contexthub()`, `cmd_amaw_enable()`, `cmd_amaw_pre_commit()`; extend `cmd_complete()` to bridge selective events |
| `scripts/workflow-gate.py` | Same as bundle (copy) |
| `agentic-workflow/AMAW.md` | Update Adversary/Scope Guard/Scribe prompt templates to include mcp-query.py calls; add Component-1/2/3/4 reference |
| `docs/amaw-workflow.md` | Same as bundle (copy) |
| `agentic-workflow/.claude/commands/amaw.md` | Workflow steps 3-5 mention mcp-query.py calls |
| `.claude/commands/amaw.md` | Same as bundle (copy) |
| `agentic-workflow/.claude/settings.json` | Pre-commit hook chains amaw-pre-commit |
| `.claude/settings.json` | Same as bundle (copy) |
| `agentic-workflow/install.sh` | Copy mcp-query.py |
| `agentic-workflow/README.md` | Note L3 integration in customizations table |

(Total: 4 NEW + 9 MODIFIED = 13 files. Honest count for reclassification check: still XL bracket.)

## 5. Acceptance criteria (for Phase 8 QC)

| ID | Criterion | Verification |
|---|---|---|
| AC-1 | `python scripts/mcp-query.py ping` returns OK with ContextHub running | Manual run, expect "OK" stdout, exit 0 |
| AC-2 | `python scripts/mcp-query.py search_lessons "test"` returns valid JSON or summary | Manual run with test query |
| AC-3 | `python scripts/mcp-query.py add_lesson --type general_note --title "AC-3 test" --content "..."` creates lesson, returns lesson_id | Manual run + verify via `list_lessons` |
| AC-4 | `python scripts/mcp-query.py check_guardrails "test action"` returns verdict | Manual run, expect JSON with `pass` field |
| AC-5 | `mcp-query.py` exits 1 cleanly when ContextHub is down (not crash) | Stop mcp container, run query, expect exit 1 + stderr msg |
| AC-6 | `workflow-gate.sh amaw-enable` flips state field, idempotent | Run twice, second is no-op |
| AC-7 | `workflow-gate.sh complete <phase> "..."` for `sprint_complete`-class events bridges to add_lesson when amaw_enabled=true | Run with amaw_enabled=true, verify lesson created |
| AC-8 | Same `complete` call in default v2.2 mode (amaw_enabled=false) does NOT call mcp-query | Verify no lesson created, no errors |
| AC-9 | Pre-commit hook chain (`pre-commit && amaw-pre-commit`) passes when amaw_enabled=false (default) | Run mock commit cycle |
| AC-10 | Pre-commit hook calls check_guardrails when amaw_enabled=true | Set amaw_enabled, mock commit, verify call happens |
| AC-11 | AMAW.md sub-agent prompts include `python scripts/mcp-query.py` lines for all 3 templates | Grep AMAW.md, expect 3+ matches |
| AC-12 | All bundle changes mirror to deployed copies (no drift) | `diff` between `agentic-workflow/<file>` and deployed `<file>` for 4 mirror pairs |

## 6. Open questions / risks

**Risks:**

1. **Subagent_type MCP inheritance untested.** We chose helper-script wrapper to sidestep this. If future deepening wants direct MCP tool calls from sub-agents, need to verify Agent tool subagents inherit MCP config. Defer to L4.

2. **mcp-query.py adds Python deps.** Use stdlib only (`urllib.request` + `json`) — no requests/httpx — so no requirements.txt churn. Validate this assumption in BUILD phase.

3. **Bridge noise in long-run lessons table.** Selective triggers reduce risk but multi-month accumulation may degrade `search_lessons` precision. Defer mitigation (lesson archival, lifecycle management) to L4.

4. **REST URL hardcoded localhost:3001.** Fine for dev; not for CI/remote. Override via env `CONTEXTHUB_API_URL`. Document in mcp-query.py `--help`.

5. **AMAW.md prompt edits may bloat token cost** of sub-agent cold-start by adding 2-3 MCP CLI calls per spawn. Estimate +5-10% tokens. Acceptable for L+ tasks; track in dogfood.

**Open questions** (not blocking, deferred to L4):

- Should `check_guardrails` results from POST-REVIEW Scope Guard get logged to AUDIT_LOG too? (Probably yes, but not in scope here.)
- Should `mcp-query.py` support `--workspace_token` for auth-enabled deployments? (Bundle assumes auth disabled; matches current ContextHub config.)
- Should there be an `mcp-query.py reflect-after-task` post-task synthesis pass? (Worth measuring after dogfood.)

## 7. Out of scope (NOT this task)

- L4 features: sub-agent direct MCP tool inheritance, lesson lifecycle management, CI/remote deployment support
- Default v2.2 mode integration with MCP (e.g. CLARIFY auto-`search_lessons` for non-AMAW tasks) — different design
- ContextHub workflow-state mirror (e.g. publish current phase to MCP for cross-session visibility) — interesting but separate
- Tests for mcp-query.py beyond smoke (would need test ContextHub instance) — accept smoke-only validation

## 8. Reviewer self-checklist (for Phase 3 REVIEW design)

- [ ] PO question: does this meet the "evaluate effectiveness of ContextHub MCP" goal user stated?
- [ ] PO question: are AC-1..12 testable as written, or do they need refinement?
- [ ] Lead question: is the dependency order (Component 1 → 2/3/4) honest, or are there hidden cross-dependencies?
- [ ] Lead question: does helper-script wrapper have hidden costs (process spawn per call, ~50-100ms overhead)?
- [ ] Lead question: does any part of this conflict with bundle v2.3 patterns just deployed?
- [ ] Architect question: is this scope tractable for one task or should it split?

(Self-review fills these in Phase 3.)
