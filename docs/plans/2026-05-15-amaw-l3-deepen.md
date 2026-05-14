# Plan: AMAW L3 Deepen — task decomposition

**Spec:** [`docs/specs/2026-05-15-amaw-l3-deepen.md`](../specs/2026-05-15-amaw-l3-deepen.md)
**Created:** 2026-05-15
**Status:** PLAN phase complete; awaiting user approval before BUILD
**Workflow mode:** default v2.2 + `/review-impl` (no `/amaw` for THIS task — meta-paradox)
**Size:** XL (4 NEW + 9 MODIFIED = 13 files)

## Discovered REST endpoints (free-context-hub `src/api/routes/`)

| Verb | Endpoint | Body / params |
|---|---|---|
| ping (synthetic) | `GET /api/lessons?project_id=X&limit=1` | (use as cheap reachability check) |
| search_lessons | `POST /api/lessons/search` | `{project_id, query, limit, filters?}` |
| add_lesson | `POST /api/lessons` | `{project_id, lesson_type, title, content, tags?, source_refs?}` |
| list_lessons | `GET /api/lessons?project_id=X&limit=N` | query params |
| check_guardrails | `POST /api/guardrails/check` | `{project_id, action_context: {action, ...}}` |
| search_code_tiered | `POST /api/search/code-tiered` | `{project_id, query, kind?, max_files?}` |

**`reflect` endpoint NOT in REST surface** — it's MCP-only (uses chat model directly). Drop from mcp-query.py MVP; document as "future work" in spec section 7.

## Component breakdown

### Component 1 — `mcp-query.py` (foundation, ~10 sub-tasks)

| ID | Task | File | Verify |
|----|------|------|--------|
| T1.1 | Create `agentic-workflow/scripts/mcp-query.py` skeleton: argparse with subcommands, env handling (`CONTEXTHUB_API_URL`, `CONTEXTHUB_PROJECT_ID`), exit codes 0/1/2, helper `_post(path, body)` + `_get(path, params)` using stdlib `urllib.request` + `json` | `agentic-workflow/scripts/mcp-query.py` (NEW) | `python agentic-workflow/scripts/mcp-query.py --help` → shows subcommands |
| T1.2 | Implement `ping` verb: `GET /api/lessons?project_id=...&limit=1` → exit 0 + print "OK" | same | `python agentic-workflow/scripts/mcp-query.py ping` → "OK" |
| T1.3 | Implement `search_lessons` verb: positional query arg + `--type` `--tags` `--limit` flags → POST `/api/lessons/search` → JSON output | same | `python ... search_lessons "test" --limit 1` → JSON `{"matches":[...],"explanations":[...]}` |
| T1.4 | Implement `add_lesson` verb: `--type --title --content` required, `--tags` optional → POST `/api/lessons` → print returned `lesson_id` | same | `python ... add_lesson --type general_note --title "AC-3 smoke" --content "test"` → prints UUID |
| T1.5 | Implement `list_lessons` verb: `--limit` flag → GET `/api/lessons?...` → JSON output | same | `python ... list_lessons --limit 3` → JSON list |
| T1.6 | Implement `check_guardrails` verb: positional action arg → POST `/api/guardrails/check` → JSON output | same | `python ... check_guardrails "git commit"` → JSON with `pass` field |
| T1.7 | Implement `search_code_tiered` verb: query + `--kind` flag → POST `/api/search/code-tiered` → JSON | same | `python ... search_code_tiered "tilemap" --max-files 3` → JSON |
| T1.8 | Add error handling: connection refused → print to stderr "ContextHub not reachable at <url> — exit 2", any 5xx → "Server error: <code>" exit 2, 4xx → "Bad request: <body>" exit 1 | same | Stop free-context-hub mcp container; run any verb → exit 2 + friendly stderr |
| T1.9 | Add `--format json|summary` flag (default `summary`); summary mode formats output as plain text with section headers | same | `python ... search_lessons "test"` (default summary) vs `python ... search_lessons "test" --format json` |
| T1.10 | Copy to `scripts/mcp-query.py` (deployed); chmod +x both | `scripts/mcp-query.py` (NEW) | `ls -l scripts/mcp-query.py` → executable bit |

**Component 1 acceptance:** AC-1 (ping), AC-2 (search_lessons), AC-3 (add_lesson), AC-4 (check_guardrails), AC-5 (down → exit 2)

### Component 2 — workflow-gate.py extensions (~9 sub-tasks)

| ID | Task | File | Verify |
|----|------|------|--------|
| T2.1 | Update `INITIAL_STATE` dict to include `"amaw_enabled": False, "amaw_enabled_at": None` | `agentic-workflow/scripts/workflow-gate.py` | `bash scripts/workflow-gate.sh reset && cat .workflow-state.json` → contains amaw_enabled |
| T2.2 | Add `cmd_amaw_enable(_args)` function: sets `state['amaw_enabled']=True, ['amaw_enabled_at']=now()`, save_state, print "OK: AMAW mode enabled". Idempotent. | same | `bash scripts/workflow-gate.sh amaw-enable` → success; second call → no-op |
| T2.3 | Add `cmd_amaw_pre_commit(_args)`: load_state; if `amaw_enabled==False` → exit 0 silent; if True → shell out to `python scripts/mcp-query.py check_guardrails "git commit"`, propagate exit code; if helper exits 2 (server down) → warn stderr + exit 0 (don't block on infra) | same | With `amaw_enabled=false` → exit 0; with true + ContextHub up → exit 0; with true + ContextHub down → warn + exit 0 |
| T2.4 | Add `_bridge_to_contexthub(event_type, task_slug, content_dict)` helper: shells out to `python scripts/mcp-query.py add_lesson --type <mapped> --title <generated> --content <json> --tags amaw,<event_type>,<task_slug>`. Best-effort: catch all exceptions, print warning, continue. | same | Manual: with amaw_enabled, simulate sprint_complete → mcp-query.py invoked, lesson appears in list |
| T2.5 | Extend `cmd_complete(args)`: after existing logic, IF `state['amaw_enabled']` AND phase in `{retro}` → call `_bridge_to_contexthub('sprint_complete', task_slug, {evidence, phase, completed_at})`. IF phase in `{review-design, review-code}` AND evidence contains "REJECTED" → call `_bridge_to_contexthub('review_rejected', ...)` | same | Run AMAW-mode complete retro → bridge fires; default-mode complete retro → no bridge |
| T2.6 | Add `cmd_pragmatic_stop(args)` (args: task_slug, reason): appends event to AUDIT_LOG.jsonl with action=pragmatic_stop, calls `_bridge_to_contexthub` if amaw_enabled | same | `bash scripts/workflow-gate.sh pragmatic-stop "task-X" "stopped because guardrails contradicted spec"` → AUDIT_LOG entry + lesson |
| T2.7 | Update CLI dispatcher / help: register `amaw-enable`, `amaw-pre-commit`, `pragmatic-stop` | same | `bash scripts/workflow-gate.sh` (no args) → help shows new verbs |
| T2.8 | Update `cmd_status` to display `amaw_enabled` field | same | `bash scripts/workflow-gate.sh status` → shows AMAW: enabled/disabled |
| T2.9 | Copy bundle's `.py` to `scripts/workflow-gate.py` (sync deployed) | `scripts/workflow-gate.py` (MODIFIED) | `diff agentic-workflow/scripts/workflow-gate.py scripts/workflow-gate.py` → empty |

**Component 2 acceptance:** AC-6 (amaw-enable), AC-7 (bridge fires when enabled), AC-8 (no bridge when disabled)

### Component 3 — Sub-agent prompt updates (~6 sub-tasks)

| ID | Task | File | Verify |
|----|------|------|--------|
| T3.1 | Update Adversary template (lines ~98-129 in AMAW.md): add new "Step 0: Load captured rules" with 2 mcp-query.py calls (search_lessons --type guardrail; search_lessons --tags adversary-rejection) | `agentic-workflow/AMAW.md` | `grep "mcp-query.py search_lessons" agentic-workflow/AMAW.md` → 2+ matches in Adversary section |
| T3.2 | Update Scope Guard template (lines ~135-158): add Step 0 with check_guardrails call + search_lessons --type guardrail | same | `grep "check_guardrails" agentic-workflow/AMAW.md` → 1+ match in Scope Guard section |
| T3.3 | Update Scribe template (lines ~165-198): add `search_lessons` to CLARIFY scan task type (a) | same | `grep "mcp-query.py search_lessons" agentic-workflow/AMAW.md` (Scribe section) → 1+ match |
| T3.4 | Add new "## L3 ContextHub integration" section near end of AMAW.md: brief overview of mcp-query.py, bridge, hook chain, link to spec | same | Section heading exists; ≥40 words |
| T3.5 | Copy bundle's AMAW.md to `docs/amaw-workflow.md` | `docs/amaw-workflow.md` (MODIFIED) | `diff agentic-workflow/AMAW.md docs/amaw-workflow.md` → empty |
| T3.6 | Verify all 3 templates updated via grep | both | grep returns ≥4 mcp-query.py mentions |

**Component 3 acceptance:** AC-11 (sub-agent prompts include mcp-query.py)

### Component 4 — Hook chain + slash command updates (~5 sub-tasks)

| ID | Task | File | Verify |
|----|------|------|--------|
| T4.1 | Update `agentic-workflow/.claude/settings.json` PreToolUse hook command to chain: `bash ./scripts/workflow-gate.sh pre-commit && bash ./scripts/workflow-gate.sh amaw-pre-commit` | `agentic-workflow/.claude/settings.json` | Read file → command field has `&&` chain |
| T4.2 | Copy bundle's settings.json to `.claude/settings.json` (deployed) | `.claude/settings.json` (MODIFIED) | `diff agentic-workflow/.claude/settings.json .claude/settings.json` → empty |
| T4.3 | Update `agentic-workflow/.claude/commands/amaw.md`: in "Process when /amaw is invoked" step 1, append `bash scripts/workflow-gate.sh amaw-enable` after the acknowledge step. Add new "What this command does NOT do" item: "Does NOT bypass `pre-commit` hook chain — both default + AMAW gates run." | `agentic-workflow/.claude/commands/amaw.md` | Read file → contains `amaw-enable` reference |
| T4.4 | Copy bundle's amaw.md to `.claude/commands/amaw.md` (deployed) | `.claude/commands/amaw.md` (MODIFIED) | `diff agentic-workflow/.claude/commands/amaw.md .claude/commands/amaw.md` → empty |
| T4.5 | Mock pre-commit cycle test: `reset → size XL ... → without amaw-enable → run pre-commit && amaw-pre-commit → both exit 0`; then `amaw-enable → run again → both exit 0 (because guardrails empty = pass)` | n/a | Both scenarios exit 0 |

**Component 4 acceptance:** AC-9 (default chain passes), AC-10 (AMAW mode triggers check_guardrails)

### Component 5 — install.sh + README + bundle README (~3 sub-tasks)

| ID | Task | File | Verify |
|----|------|------|--------|
| T5.1 | Update `agentic-workflow/install.sh`: add `cp` for `mcp-query.py` to `$TARGET/scripts/` with chmod +x; print `[x] scripts/mcp-query.py (ContextHub MCP REST helper)` | `agentic-workflow/install.sh` | grep `mcp-query.py` install.sh → match |
| T5.2 | Update `agentic-workflow/README.md` "Repo customizations applied" table: add row for `scripts/mcp-query.py` and bridge integration | `agentic-workflow/README.md` | grep `mcp-query.py` README.md → match in customizations table |
| T5.3 | Re-run install: `bash agentic-workflow/install.sh .` (idempotent — should not overwrite existing customized files except the explicitly-managed mcp-query.py and workflow-gate.{sh,py}) | n/a | `[x] scripts/mcp-query.py` line in output; existing files NOT overwritten |

**Component 5 acceptance:** AC-12 (bundle/deployed mirror sync)

### Component 6 — VERIFY pass (run all 12 AC) (~12 sub-tasks)

| AC | How verified |
|---|---|
| AC-1 | `python scripts/mcp-query.py ping` → "OK" exit 0 |
| AC-2 | `python scripts/mcp-query.py search_lessons "smoke" --limit 1` → JSON exit 0 |
| AC-3 | `python scripts/mcp-query.py add_lesson --type general_note --title "AC-3 verify" --content "L3 deepen smoke test"` → UUID returned; `python scripts/mcp-query.py list_lessons --limit 5` → lesson appears |
| AC-4 | `python scripts/mcp-query.py check_guardrails "git commit"` → JSON with `pass` field |
| AC-5 | `docker stop free-context-hub-mcp-1`; `python scripts/mcp-query.py ping` → exit 2 + stderr "ContextHub not reachable"; `docker start free-context-hub-mcp-1` |
| AC-6 | `bash scripts/workflow-gate.sh reset; bash scripts/workflow-gate.sh amaw-enable; cat .workflow-state.json | grep amaw_enabled` → true |
| AC-7 | (with amaw_enabled set) `bash scripts/workflow-gate.sh complete retro "L3 deepen test sprint"` → mcp-query lesson visible via list_lessons |
| AC-8 | `bash scripts/workflow-gate.sh reset; bash scripts/workflow-gate.sh complete retro "default mode test"` → no new lesson via list_lessons |
| AC-9 | (with amaw_enabled=false) Mock commit cycle (size+phases+complete to session) → `bash scripts/workflow-gate.sh pre-commit && bash scripts/workflow-gate.sh amaw-pre-commit` → exit 0 |
| AC-10 | (with amaw_enabled=true + empty guardrails table) Same mock cycle → exit 0 (CLEAR); inject guardrail row → BLOCKED → exit 1 |
| AC-11 | `grep -c "python scripts/mcp-query.py" agentic-workflow/AMAW.md` → ≥4 |
| AC-12 | `diff agentic-workflow/scripts/workflow-gate.py scripts/workflow-gate.py` → empty; same for AMAW.md, amaw.md, settings.json, mcp-query.py |

### Component 7 — Cleanup test lessons

| ID | Task | Verify |
|---|---|---|
| T7.1 | Delete AC-3 + AC-7 test lessons via SQL (DELETE FROM lessons WHERE title IN ('AC-3 verify', 'L3 deepen test sprint')) so production lesson set isn't polluted | `python scripts/mcp-query.py list_lessons --limit 20` → no test lessons |
| T7.2 | Reset workflow-state.json back to clean (we'll re-init for the actual task on this branch's commit) | `cat .workflow-state.json` → empty/initial |

## Dependency graph (build order)

```
T1.1 (skeleton) → T1.2 (ping) → T1.3..T1.7 (verbs) → T1.8 (errors) → T1.9 (formats) → T1.10 (deploy)
                                                                                          ↓
                                                                          T2.1..T2.9 (workflow-gate ext)
                                                                                          ↓
                                                                ┌─────────┬────────────┐
                                                                ↓         ↓            ↓
                                                              T3.1..T3.6 T4.1..T4.5  T5.1..T5.3
                                                                          ↓
                                                                Component 6 VERIFY pass
                                                                          ↓
                                                                Component 7 cleanup
```

**Estimated wall-clock:** ~2.5-3 hours for components 1-7 sequentially. Could parallelize 3+4+5 after 2 lands.

## Risks rediscovered during planning

1. **`reflect` endpoint missing from REST.** Spec mentioned `reflect` as out-of-scope but Component 3 Scribe template was going to call it. **Decision:** drop reflect from Scribe template; replace with `search_lessons` for context primer.
2. **`add_lesson` REST contract.** Verified body shape matches MCP tool: `{project_id, lesson_type, title, content, tags?}`. No discrepancy with what mcp-query.py needs to send.
3. **`check_guardrails` returns shape unknown.** Need to inspect during T1.6 and adapt summary formatter. Live JSON probe before formalizing.
4. **`amaw_enabled` flag in shared state file.** Bundle ships state file as gitignored; flag is per-clone, per-task. Re-running `/amaw` on a fresh clone requires fresh enable. Document in amaw.md.

## Out-of-plan (intentionally NOT in this PR)

- Tests for mcp-query.py (smoke-only validation, no pytest harness)
- CI integration (free-context-hub URL hardcoded localhost; no CI assumption)
- `reflect` verb (deferred — not in REST surface; would need MCP-tool path)
- Documentation auto-generation (docs/amaw-workflow.md is manual sync via `cp`; could add a sync script later)

## Session boundary recommendation

13 files + 12 AC + 7 components is XL. Suggest stopping after each Component 6 (VERIFY) checkpoint to give human review window. If stamina permits, single-session BUILD → VERIFY → REVIEW is feasible (~2.5hr); else split:

- **Session A (now):** BUILD components 1+2 (foundation + workflow-gate ext) + VERIFY AC-1..8
- **Session B (next):** BUILD components 3+4+5 + VERIFY AC-9..12 + POST-REVIEW + COMMIT

User to decide at BUILD checkpoint.
