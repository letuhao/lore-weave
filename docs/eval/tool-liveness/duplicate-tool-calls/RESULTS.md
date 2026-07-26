# S2 — duplicate tool calls: measured, split into two defects, partially closed (2026-07-23)

## What the measurement actually showed (and corrected)

I had reported these as "parallel duplicates in one emission". Querying 24h of live
transcripts split that into **two different defects**:

```sql
SELECT session_id, tc->>'tool', count(*) calls, count(DISTINCT tc->'args') distinct_args ...
019f8dbd  glossary_propose_entity_edit  4 calls / 1 distinct args   <- same pass (iteration 0 x4)
019f8cb2  glossary_propose_entity_edit  4 calls / 1 distinct args   <- same pass
019f8dda  glossary_propose_entities     3 calls / 1 distinct args   <- iterations 1,2,3 (RETRIES)
```

Every affected session had `distinct_args = 1` — byte-identical, not a batch of different
requests. But the *iteration* field split them:

- **S2a — same-pass duplicates** (`iteration: 0` ×4): the model emits the identical call
  several times in ONE `tool_calls` array.
- **S2b — cross-iteration retries** (`iteration: 1, 2, 3`): the model calls, *reads the
  result*, and re-issues the identical call. **My earlier "all at iteration 0" claim was
  wrong for this session** — these are retries, and collapsing them would be incorrect.

## S2a — collapse identical calls within one pass

`_collapse_identical_tool_calls` (`stream_service.py`), a sibling of the existing
`_drop_duplicate_empty_tool_calls`. Keys on `(name, canonical-args)` so key order and
whitespace don't defeat it; runs *after* the empty-dropper so a `{}`-args call is never the
survivor. Scope is deliberately **one pass** — a later-iteration repeat is a legitimate
retry and is never touched.

**This is a correctness fix, not a token saving.** `glossary_propose_entities` dedups by
name server-side so the repeats were absorbed — a write tool without its own idempotency
would produce N rows from one user intent.

⚠️ **Honest status: unit-proven, NOT yet live-exercised.** 6 unit tests pass, and the
pattern is documented in the transcripts above — but neither post-fix run happened to emit
a same-pass duplicate, so the collapse has not fired in a live run. Recorded as such rather
than claimed.

## S2b — `created: 0` read as failure → the real retry loop

The cross-iteration retries had a cause. `glossary_propose_entities` answered:

```json
{"results":[{"name":"Lâm Uyên","status":"skipped_exists","entity_id":"019f8cbe-…"}],
 "summary":{"failed":0,"created":0,"skipped":1}}
```

A correct dedup — but a mid-tier model reads `created: 0` as failure and re-issues the
identical call. The entity was in the DB the entire time.

This file **already had** a guard for exactly this loop on the *failed* path, with the
comment *"a caller reads ok:true, never sees the hidden Failed count, and retries forever —
the measured mid-tier loop was proposing entities … 9× in one session, book untouched."*
The **all-skipped** case was the remaining hole. Fix: a `guidance` field asserting success
explicitly (OUT-4 success-discrimination). It stays a NON-error — nothing went wrong, the
desired state already held.

### Measured, live, same scenario + model

| | before | after |
|---|---|---|
| identical `propose_entities` retries | **3** (it 1,2,3) | **2** (it 1,2) |
| max consecutive | 3 | **2** |
| useful work in the same turn | — | also ran `glossary_entity_set_attributes` → `{"updated":["role"]}` |
| **what the user was told** | *"I can't save that information yet…"* | *"**Lâm Uyên is already in the glossary.** Would you like me to add specific details — appearance, personality, role?"* |

The user-facing outcome is now **correct**: it reports the true state and offers the useful
next step, instead of implying failure.

⚠️ **Not fully closed: one retry survives.** The model reads *"Do NOT call this tool again
with the same items"* and still re-issues once before settling. Closing that last one would
need cross-iteration same-args suppression, which risks blocking legitimate retries (state
can change between iterations) — a worse failure than one wasted call. Left open
deliberately; see RUN-STATE `K8`.
