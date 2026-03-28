# ContextHub — Agent Protocol
> Load this file as system prompt or starting context for any AI agent working on this project.
> This file is self-contained. No other file is required to understand the protocol.

---

## 1. Connection

```
MCP endpoint:  http://localhost:3000/mcp   (Streamable HTTP / POST)
project_id:    free-context-hub
workspace_token: optional; required only if `MCP_AUTH_ENABLED=true` → key: CONTEXT_HUB_WORKSPACE_TOKEN
```

First call (recommended): `help` — learn tool parameters + sample workflows.

`project_id` is required for some tools and optional for others when `DEFAULT_PROJECT_ID` is set.
`workspace_token` is optional and only needed when `MCP_AUTH_ENABLED=true`.

---

## 2. Session Protocol (mandatory sequence)

### Session Start — run in this order, every session

| Step | Action | Why |
|---|---|---|
| 1 | Call `get_context(task?)` | Bootstrap minimal refs + suggested next tool calls |
| 2 | (Optional) Read `docs/sessions/SESSION_PATCH.md` | If you need exact “where we left off” details |
| 3 | (Optional) Read Tier docs from `context_refs` | Only if needed; avoid loading everything |
| 4 | Call `search_lessons(query)` | Load relevant prior decisions/preferences/guardrails |
| 5 | Call `search_code(query)` | Find code locations by intent |
| 6 | Read `docs/context/modules/<MODULE>_BRIEF.md` | Only if patching that module |

Do NOT load WHITEPAPER.md unless answering an architectural question unanswered above.

### Session End — required before closing

| Step | Action | Condition |
|---|---|---|
| A | Call `add_lesson(...)` for each significant decision made | If any decision was made |
| B | Call `add_lesson(...)` for any workaround or mistake captured | If any found |
| C | Overwrite `docs/sessions/SESSION_PATCH.md` with current state | Always |

---

## 3. Tool Reference

### `help`
```
When:   First call for any agent integrating with this server.
Params: workspace_token (optional; required only if MCP_AUTH_ENABLED=true)
        output_format
Returns: JSON help: tool inventory, parameter docs, sample workflows, tool-call templates.
```

### `index_project`
```
When:   After significant code changes, or at start of a fresh environment.
Params: project_id, root (directory path), workspace_token (optional; required only if `MCP_AUTH_ENABLED=true`)
        options: { lines_per_chunk?: number, embedding_batch_size?: number }
Returns: { status: "ok"|"error", files_indexed, duration_ms, errors[] }
```

### `search_code`
```
When:   BEFORE using Grep/Glob/Read to find code. Always try this first.
Params: project_id, query (natural language), workspace_token (optional; required only if `MCP_AUTH_ENABLED=true`)
        filters?: { path_glob? }   limit?: number   debug?: boolean
Returns: { matches: [{ path, start_line, end_line, snippet, score, match_type }], explanations[] }
Rule:   If matches.length > 0, use those snippets. Only read full file if more context needed.
```

### `list_lessons`
```
When:   You need to browse lessons by type/tags and paginate through them.
Params: project_id (optional if DEFAULT_PROJECT_ID is set), workspace_token (optional; required only if MCP_AUTH_ENABLED=true)
        filters?: { lesson_type?, tags_any? }  page?: { limit?, after? }
Returns: { items: Lesson[], next_cursor?, total_count }
```

### `search_lessons`
```
When:   You need to find decisions/preferences/guardrails/workarounds by intent.
Params: project_id (optional if DEFAULT_PROJECT_ID is set), query, workspace_token (optional; required only if MCP_AUTH_ENABLED=true)
        filters?: { lesson_type?, tags_any? }  limit?: number
Returns: { matches: [{ lesson_id, lesson_type, title, content_snippet, tags, score }], explanations[] }
Rule:   Use this instead of reading many docs at session start.
```

### `get_context`
```
When:   Session start bootstrap (recommended) or when you want suggested next tool calls.
Params: project_id (optional if DEFAULT_PROJECT_ID is set), workspace_token (optional; required only if MCP_AUTH_ENABLED=true)
        task?: { intent, query?, path_glob? }
Returns: { project_id, context_refs[], suggested_next_calls[], notes[] }
Rule:   This tool does NOT bundle large content; it returns refs + suggestions to reduce noise.
```

### `add_lesson`
```
When:   See Self-Report Protocol (section 4).
Params: workspace_token (optional; required only if `MCP_AUTH_ENABLED=true`)
        lesson_payload: {
          project_id, lesson_type, title, content,
          tags?: string[],  source_refs?: string[],  captured_by?: string,
          guardrail?: { trigger, requirement, verification_method }
        }
lesson_type values: decision | preference | guardrail | workaround | general_note
Returns: { status: "ok", lesson_id }
```

### `check_guardrails`
```
When:   BEFORE: git push, deploy, schema migration, deleting data, force-push.
Params: workspace_token (optional; required only if `MCP_AUTH_ENABLED=true`)
        action_context: { action: string, project_id: string }
Returns: { pass: boolean, rules_checked, needs_confirmation?, prompt?, matched_rules? }
Rule:   If pass=false → show prompt to user, do NOT proceed without explicit approval.
        Never skip this call for the listed action types.
```

### `delete_workspace`
```
When:   ONLY on explicit user instruction.
Params: project_id, workspace_token (optional; required only if `MCP_AUTH_ENABLED=true`)
Returns: { status, deleted, deleted_project_id }
Warning: Deletes ALL data (lessons, chunks, guardrails) for the project. Irreversible.
```

---

## 4. Self-Report Protocol

The agent MUST submit data back to ContextHub to keep team knowledge current.
Use `add_lesson` with the appropriate type. Tags are how knowledge is classified.

### Decision (architectural or technical)
```
lesson_type: "decision"
title:       Short decision statement (e.g., "Use line-based chunking for MVP")
content:     Context: why this was decided, what alternatives were considered
tags:        ["decision-<area>"]   e.g., ["decision-storage", "decision-auth"]
source_refs: file paths or ticket IDs relevant to the decision
```

### Preference (team style or constraint)
```
lesson_type: "preference"
title:       The preference (e.g., "Always use structured JSON responses")
content:     Elaboration and rationale
tags:        ["preference-<topic>"]   e.g., ["preference-api", "preference-typescript"]
```

### Guardrail (rule to enforce before an action)
```
lesson_type: "guardrail"
title:       Rule name
content:     Full description
tags:        ["guardrail-<area>"]
guardrail:   {
  trigger:              "git push" | "deploy" | "/regex pattern/"
  requirement:          Human-readable condition that must be met
  verification_method:  "user_confirmation" | "recorded_test_event" | "cli_exit_code"
}
```

### Workaround (bug or environment fix)
```
lesson_type: "workaround"
title:       What was broken and how it was fixed
content:     Steps taken, root cause if known
tags:        ["workaround-<component>"]   e.g., ["workaround-indexer", "workaround-auth"]
source_refs: file paths changed
```

### General Note
```
lesson_type: "general_note"
title:       Topic
content:     Observation or context worth preserving
tags:        free-form
```

---

## 5. Session Patch Format

At session end, overwrite `docs/sessions/SESSION_PATCH.md` with this structure:

```markdown
---
id: CH-T3  date: YYYY-MM-DD  module: <current-module>  phase: MVP
---

# Session Patch — YYYY-MM-DD

## Where We Are
Phase: MVP · Status: <one-line status>
Last completed: <what was done this session>
Next: <immediate next action>

## Open Blockers
| ID | Blocker | Action |
|---|---|---|
| ... | ... | ... |

## Context to Load Next Session
- Tier 0: docs/context/PROJECT_INVARIANTS.md
- Tier 1: docs/context/MVP_CONTEXT.md
- Tier 2: docs/context/modules/<RELEVANT_MODULE>_BRIEF.md
```

---

## 6. Code Search Decision Tree

```
Need to find code?
    │
    ├─ Do you know the exact file path? → Read file directly
    │
    └─ Do you know intent but not location?
            │
            └─ search_code(query: natural language description)
                    │
                    ├─ matches > 0 → use snippets, Read full file only if needed
                    └─ matches = 0 → fall back to Grep, then check if index is current
```

---

## 7. Quick Reference Card

```
Session start:  get_context(task?) → search_lessons(query) → search_code(query)
Finding code:   search_code() before Grep/Read
Before push:    check_guardrails({action: "git push", project_id})
Decision made:  add_lesson(type: "decision")
Session end:    add_lesson() for any decisions → overwrite SESSION_PATCH.md
```
