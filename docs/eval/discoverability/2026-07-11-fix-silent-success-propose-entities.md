# Fix: `glossary_propose_entities` silent success (P0) — root cause + live verify

**Date:** 2026-07-11 · **Origin:** the S01 baseline/re-test loop (a mid-tier agent proposing entities of a
kind that doesn't exist, 9× in one session, book untouched, no failure signal).
**Fix:** `services/glossary-service/internal/api/entity_batch_tools.go` · test
`entity_batch_tools_test.go::TestProposeEntities_AllFailed_MarksIsError`.

## Root cause

`glossary_propose_entities` is per-item independent (each item created or failed on its own). The handler
built a per-item `Results[]` with a `Summary{Created,Skipped,Failed}` and then **always** returned
`return nil, out, nil` — the third value (the MCP Go `error`) was `nil` regardless of outcome. The go-sdk
(`AddTool`, v1.6.1) treats `err==nil` as success → envelope **`ok:true` / `isError:false`**. So even when
**every** item failed (e.g. all `unknown kind: cultivation_system`), the tool reported success with a
hidden `Failed` count.

Effect on a mid-tier agent (measured, S01): it reads `ok:true`, believes the entities were added, never
learns it must adopt kinds first, and retries the identical failing call — a silent loop the book never
leaves. It also corrupts any metric that counts "successful tool calls" as writes.

## Fix

After the per-item loop, if the batch **created nothing AND at least one item genuinely errored**, return
a result with `IsError: true` plus an actionable message; otherwise unchanged:

```go
if out.Summary.Created == 0 && out.Summary.Failed > 0 {
    // ... message; if every failure is "unknown kind", point at glossary_adopt_standards / propose_kinds
    return &mcp.CallToolResult{IsError: true, Content: [...]}, out, nil
}
return nil, out, nil
```

Precise by design — the guard fires ONLY on total failure:
- **Partial success** (something was created) stays `ok` — the created entity is real; per-item errors are
  in `Results`. (Locked by `TestProposeEntities_UnknownKind_PerItemError…`.)
- **All-skipped-because-they-exist** (`Failed==0`) stays `ok` — the entities *are* there; re-proposing a
  known batch is a no-op, not a failure.
- **Nothing created + a real error** → `IsError`.

Per-item detail is **preserved alongside `IsError`**: verified against go-sdk `server.go:384` — it marshals
the typed `out` into `structuredContent` whenever `err==nil`, even when the handler returns a non-nil
`CallToolResult`. So the agent gets both the failure signal AND which kinds were unknown.

## Verification

**Unit** (`GLOSSARY_TEST_DB_URL` against dev PG): the 4 batch tests pass, including the new
`TestProposeEntities_AllFailed_MarksIsError` (all-unknown-kind → `res.IsError==true`, `Failed==2`, per-item
errors intact) and the preserved partial-success assertion. Neighborhood suite
(`Propose|Entity|Batch|Confirm|Action|Ontology`) green, no regression.

**Live** (gemma-4-26b-a4b-qat, S01 on a fresh book, glossary-service rebuilt):

| | before fix (`…-S01-warm-autoapprove`) | after fix (`…-S01-postfix`) |
|---|---|---|
| `propose_entities` returning `ok:true` (lying) | **9** | **0** |
| `propose_entities` returning `isError` (honest) | 1 | **9** |
| harness `silent_success_calls` | **9** | **0** |

The tool now returns, verbatim: *"no entities were created — every proposed item failed (see
structuredContent for each item's error). Each failure is an 'unknown kind': that category does not exist
in this book yet. Create the categories first (glossary_adopt_standards … or glossary_propose_kinds …),
then retry."*

## Scope of the silent-success class (surveyed)

Only `glossary_propose_entities` had the agent-facing bug. Siblings checked:
- `glossary_propose_batch` (`toolProposeBatch`) — **not affected**: validates the plan and returns a Go
  `error` on invalid ops (fails loudly), else mints a confirm card.
- `action_confirm_batch` (`/actions/confirm-batch`) — a **REST** handler consumed by the FE (reads the
  per-child `Failed` count), not the agent's MCP loop. Different consumer; `writeJSON(200)` with a failed
  count is FE-surfaced, not an agent lie. (Noted, not changed.)
- `captureCanon` (WS-4C) — a **REST** internal auto-capture handler, not model-facing.

## Still open (separate finding — NOT this fix)

The fix removes the *lie*; it does not make S01 pass. Even with the honest `isError` + the explicit
"adopt kinds first" guidance, mid-tier gemma still retried `propose_entities` instead of calling
`glossary_adopt_standards`, and `book_kinds` stayed 0. **A mid-tier model needs the sequence enforced by a
rail, not merely suggested by an error** — that is WS-5 (the `glossary-bootstrap` / `vision-to-book`
workflow). The silent-success fix is a prerequisite (it makes the loop *detectable*), not a substitute.
