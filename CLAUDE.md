# CLAUDE.md — ContextHub Development Guide

## What This Project Is
Self-hosted MCP server providing persistent memory + semantic code search + guardrails for AI agents.
MCP server: `http://localhost:3000/mcp` (must be running before session starts).
Source of truth for architecture: `WHITEPAPER.md`. Source of truth for current status: `docs/sessions/SESSION_PATCH.md`.

> Full agent protocol (portable, tool-agnostic): `AGENT_PROTOCOL.md`
> This file adds Claude Code-specific behavior on top of that protocol.

---

## Session Start Protocol (required every session)

Run these steps in order at the start of EVERY session:

1. **Read** `docs/sessions/SESSION_PATCH.md` → orient to current module state, active work, and open blockers
2. **Call** `help` → learn tool parameters + sample workflows (1-time per environment)
3. **Call** `get_context` (with `task.intent` + optional `task.query/path_glob`) → bootstrap minimal refs + suggested next calls
4. **Call** `search_lessons` → load relevant prior decisions/preferences/guardrails for the task
5. **Call** `search_code` → find relevant code locations by intent
6. **Read** the relevant module brief from `docs/context/modules/` ONLY if patching that module

Do NOT load `WHITEPAPER.md` unless there is an architectural question not answered by the docs above.

`workspace_token` is optional and only needed when `MCP_AUTH_ENABLED=true` (key: `CONTEXT_HUB_WORKSPACE_TOKEN`).

---

## Tool Usage Rules

### `search_code` — use BEFORE reading files
```
When: you need to find where something is implemented, before using Glob/Grep/Read
How:  search_code(project_id, query="what you're looking for", limit=5)
Why:  semantic search finds by intent, not by filename
```
Examples of when to call:
- "where is auth handled?" → `search_code(query: "workspace token authentication")`
- "where do we write chunks?" → `search_code(query: "chunk embedding storage write")`
- "find the guardrail trigger logic" → `search_code(query: "trigger match guardrail rule")`

### `help` — call first (agent onboarding)
```
When: first time an agent connects to this MCP server
How:  help(output_format: "json_pretty")
Why:  provides parameter docs + sample workflows + tool-call templates
```

### `get_context` — bootstrap session start
```
When: session start (recommended)
How:  get_context(task: {intent: "...", query?: "...", path_glob?: "src/**/*.ts"})
Why:  returns refs + suggested next tool calls (no noisy bundle)
```

### `search_lessons` / `list_lessons` — use instead of get_preferences
```
When: find previous decisions/preferences/guardrails/workarounds by intent OR browse lessons
How:  search_lessons(query: "...") or list_lessons(filters/page)
Why:  lessons are now queryable by semantic search across all types
```

### `add_lesson` — call after any significant decision
```
When: a new architectural decision is made, a workaround is found, a mistake is captured
How:  add_lesson with appropriate lesson_type and tags
Why:  persists knowledge across sessions — future AI agents will read these
```
Example triggers:
- Team decides on a pattern → `lesson_type: "decision"`
- A bug workaround is applied → `lesson_type: "workaround"`
- A new team preference is stated → `lesson_type: "preference"`, tag: `"preference-*"`
- A rule is established → `lesson_type: "guardrail"` + `guardrail` field

### `check_guardrails` — call before risky actions
```
When: BEFORE any of these actions: git push, deploy, schema migration, deleting data
How:  check_guardrails(action_context: {action: "git push", project_id: "free-context-hub"})
Why:  enforces captured team rules — do NOT skip even if you think it's safe
```
If result has `pass: false` → show the `prompt` to the user and wait for explicit approval.

### `index_project` — call when source changes significantly
```
When: after significant code additions or after a fresh clone
How:  index_project(project_id: "free-context-hub", root: "<cwd>")
Why:  keeps search_code results current
```

### `delete_workspace` — only on explicit user instruction
```
When: ONLY when user explicitly asks to reset all ContextHub data for a project
How:  delete_workspace(project_id: "...")
Why:  destructive — deletes all lessons, chunks, guardrails for the project
```

---

## Session End Protocol

At the end of each session, update `docs/sessions/SESSION_PATCH.md` with:
- What was completed
- What is next
- Any new open blockers

If any architectural decisions were made during the session, call `add_lesson` BEFORE updating the patch.

---

## Phase Checkpoint Protocol (update SESSION_PATCH at each phase)

Update `docs/sessions/SESSION_PATCH.md` whenever a meaningful phase boundary is crossed — not only at session end:

| Trigger | What to update in SESSION_PATCH |
|---|---|
| A sub-phase (SP-N) completes | Mark sub-phase as done in the M05 roadmap table |
| A module backend is finished | Flip Backend column to ✅ in Module Status Matrix |
| A module frontend is finished | Flip Frontend column to ✅ |
| A new blocker is discovered | Add row to Open Blockers table |
| A blocker is resolved | Remove or mark resolved in Open Blockers |
| A commit batch closes a named work item | Add row to Session History and update "Current Active Work" |

**Rule:** if you complete more than one commit's worth of work, update SESSION_PATCH before moving to the next phase — do not batch all updates to session end.

---

## Lean Context Loading Rules

| Situation | Load |
|---|---|
| Any session start | help() (once) + get_context() + search_lessons() + search_code() |
| Working on specific module | + relevant MODULE_BRIEF.md |
| Architectural question | + WHITEPAPER.md (specific section only) |
| Finding code | search_code() first, then Read if needed |
| Before risky action | check_guardrails() — mandatory |

**Do NOT load all module briefs at once.** Load only the module you are working on.

---

## Project Constants
```
project_id:    free-context-hub
mcp_url:       http://localhost:3000/mcp
workspace_token: optional; required only if `MCP_AUTH_ENABLED=true` → CONTEXT_HUB_WORKSPACE_TOKEN
db:            PostgreSQL + pgvector (vector dim: 1024)
embedding:     mxbai-embed-large-v1 via LM Studio (localhost:1234)
```
