# CP-0 · V-CODE — verdict, ROUND 9

Artifact was to be frozen at `c7dc6195f62d75a854aed354d03501f05def03ea`.

## 🔴 THE ARTIFACT WAS NOT FROZEN. It changed under me, mid-grade, in the files I was grading.

`git status --porcelain` was **empty** at my first call. By the time I finished the gate audit it read:

```
 M contracts/agent-runtime-baseline/baseline-metrics.sql
 M services/chat-service/app/db/migrate.py
 M services/chat-service/app/services/instrument.py
 M services/chat-service/tests/test_cp0_instrument.py
?? .vlive8/
?? docs/specs/.../verification/CP-0-v-metric-round8.md
```

`tests/test_cp0_instrument.py` grew **875 → 919 lines while I was auditing it**, gaining a class
(`TestTheReconcilerCannotImpersonateATerminalPath`) that did not exist when I read the file.
`instrument.py`'s reconciler gained an `outcome_source` column and a second `NOT EXISTS`.
`contracts/agent-runtime-baseline/baseline-metrics.sql` — the **frozen** baseline, item 0.5 — is
modified in the working tree.

**How I handled it, stated so this verdict is auditable.** Everything below is graded against the
blob at `c7dc6195f`, not the working tree. I diffed all seven graded files against the frozen blob
(newline-normalised): `stream_service.py`, `tool_surface.py`, `voice_stream_service.py`,
`routers/internal.py`, `main.py` are **byte-identical** to the frozen SHA, so those results stand as
read. `instrument.py` and `migrate.py` had drifted, so I extracted their frozen blobs with
`git show c7dc6195f:…` and **re-ran every reconciler and every schema mutation against the frozen
text**; the results are unchanged (the drift does not touch a single mutation needle, and I assert
each needle's presence before mutating). The test file I audited is the 875-line frozen version,
which is the correct object.

**Final state, recorded for the audit trail.** By the time I wrote this file the working tree was
clean again and `HEAD` had advanced to `1488b8ad24e8861645ef4649af90f5b365e75248` — the concurrent
session **committed** those four files. So the tree was clean at my first call, dirty through the
whole audit, and clean again at a different SHA at the end. Everything below is graded against
`c7dc6195f`, which is the artifact I was handed.

**And the drift is itself evidence.** The concurrent edit's own comment reads: *"86 of 223 rows this
swept sat in sessions with later activity — the user simply moved on, which is not a crash."* That
is an independent live confirmation of §3.3 below, which I derived from source before seeing it.
**38.6% of what the reconciler stamped at the graded SHA was wrong**, and it was wrong in the
direction I ruled it wrong. I have not credited the fix — it is not in the artifact I was given.

Source-only review. Nothing in the product was run. No tracked file was modified. No commit message
or builder rationale prose was read.

**Method.** Two harnesses over in-memory copies, both reproducing a fully GREEN baseline on the
unmutated tree first (17 transcribed gates + 1 behavioural: all green, printed). `mutate()` asserts
the needle **exists** and that the string **changed**, so a silent no-op cannot masquerade as a blind
spot — the failure my round-4 harness committed twice. Behavioural gates are re-run against modules
compiled from mutated source into fresh module objects.

**30 mutations. 6 caught, 24 blind. The reconciler is 2 of 12.**

---

## 1. Verdict

**Overall: `FAIL`.** Two of the three things handed to me this round are met and one is met *well* —
R8's stated falsifier returned the builder's answer, which is the first time that has happened. The
third, the reconciler, is an asymmetric fix pointed at the right asymmetry whose **evidence-bearing
half cannot fire on any row this code writes** and whose **evidence-free half stamps a fabricated
cause**, guarded by four gates that survive eight of eight semantic mutations of the SQL they exist
to protect.

| item | claim | R6 | R7 | R8 | **R9** |
|---|---|---|---|---|---|
| 0.1 | `advertised_tools` jsonb, one entry per model pass | FAIL | FAIL | FAIL | **FAIL** — unchanged; voice still binds NULL (`voice:639`), withholding registration still pass-1-only for the assembly stages |
| 0.2 | `withheld_tools`; the budget function returns what it dropped | FAIL | FAIL | FAIL | **FAIL** — unchanged residuals; two more stages now register (credited §2.2), voice's INSERT still has **no `withheld_tools` column at all** |
| 0.3 | every `tool_calls[]` entry carries `source` + `latency_ms` | FAIL | FAIL | FAIL | **FAIL** — unchanged; `latency_ms` measured at 4 of ~30 mint sites, **still no gate**, mutation confirmed green |
| 0.4 | every terminal path writes an outcome | FAIL | FAIL | FAIL | **FAIL — improved twice, regressed once.** F-24 (voice) and F-28 (proactive) both genuinely closed. The kill path is now *partly* closed by a mechanism that invents a cause. §3 |
| 0.5 | frozen baseline in `contracts/`, A–E arm scripts committed | PASS | PASS | PASS | **PASS at the SHA** — all three files + `run_arms.py` in `git ls-tree c7dc6195f`. ⚠️ the frozen baseline is **modified in the working tree**; a "frozen" artifact under edit is a finding for whoever owns it, not for this item's letter |
| 0.6 | binding-format measurement scripted **and its output committed** | PASS | PASS | PASS | **PASS** — `eval/arms/binding_format.py` + `results/binding-format-20260804T035320Z.json` + `results/binding-format-FINDING.md`, all tracked at the SHA |
| 0.7 | `runtime_variant` + declaration identity on every recorded call | PASS | PASS | PASS | **PASS** — unchanged, bounded by F-11 |

| property | R9 ruling |
|---|---|
| **P1** — every tool absent from a pass's advertised set registers `{tool, stage, reason, pass}` | **NOT MET, and closer than it has ever been. F-23 is WITHDRAWN — measured.** R8's stated falsifier (delete the ContextVar fallback at `tool_surface.py:397-400`) now goes **RED**; the P1 gate covers the branch production uses. The two new narrowings are real and correctly placed. What still falsifies P1 is **F-26, unchanged**: `domain_not_selected` and `hot_seed` drain once per turn, so passes 2..n re-advertise a narrowed surface with no record. §5.1 |
| **P2** — a call's `source` is assigned structurally, never inferred | **Unchanged from R8.** Load-bearing half holds (re-verified: `chunk["source"]` assigned in exactly two places package-wide); residual countable, not bounded; no reader |
| **P3** — every terminal path writes an outcome | **NOT MET.** The reconciler closes part of the kill path and opens a new hole. Paths #13a (voice exception, writes no row) and #15 (`sweep_expired_runs`, still **zero callers**, re-verified repo-wide) are untouched. §3 |
| **P4** — no CP-0 column bound to a constant at any INSERT reachable from >1 terminal condition | **NOT MET, at a NEW site and at one R8 failed to score.** `instrument.py:528` (reconciler user branch) and `stream_service.py:7495` (`abandoned_by_user`). The two sites R8 scored — `internal.py` and voice — are both **genuinely closed**. §4 |

**What landed, credited before the findings.**

1. **R8's falsifier was executed and it returned the builder's answer.** Deleting the `else:`
   fallback at `tool_surface.py:397-400` and re-running the P1 gate behaviourally: the sink comes
   back **empty**, `assert "domain_not_selected" in stages` goes **RED**. The gate now exercises the
   production branch. **F-23 withdrawn in full** — the condition I wrote for withdrawing it, met
   exactly.
2. **F-24 is closed.** `voice_stream_service.py:503-504` captures `finish_reason` from the chunk
   stream (before the `tool_call` `continue`, after the suspend `break` — the correct order), and
   `:623-624` / `:641` both derive from `_voice_finish_reason`. A voice turn truncated at `length` or
   refused at `content_filter` no longer records `completed`/`'stop'`.
3. **F-28 is closed, and correctly.** `internal.py:945` now binds
   `"stop" if content != _PROACTIVE_STATIC else "static_fallback"` — a comparison against the value
   actually committed, i.e. a measurement of which branch ran, not a claim about it. All three
   conditions (grounded generation / swallowed exception / scaffolding-only reply) are now
   distinguishable in the row. This was my R7 footnote that I failed to score and my R8 finding; it
   is gone.
4. **The two new narrowings are correctly placed.** `catalog_miss` at `stream_service.py:1401` sits
   **before** the `continue` that `_add(None)` would have swallowed, and `permission_tier` at `:1413`
   covers the discovery branch the advertise-chokepoint registration never reached. Both run inside
   `_stream_with_tools` per pass, ahead of the `advertised` chunk yield at `:2256`/`:2286`, so they
   drain into the recorder against the right pass — which is more than the assembly stages manage.

**And the class moved once more, into the newest gate again.** R8's defect was a gate staging its own
precondition. R9's is a gate whose needle is satisfied by the **import statement** of the thing it is
checking has a caller — written into the file whose sibling docstrings document four previous
recurrences, in the same pass as the code it guards. Deleting `await reconcile_crashed_turns(pool)`
from `main.py` leaves `test_the_reconciler_has_a_caller` **green**, because `from
app.services.instrument import reconcile_crashed_turns` supplies both the substring and the ordering.
**The gate written to reject the state `sweep_expired_runs` is in cannot detect the state
`sweep_expired_runs` is in.** Sixth recurrence.

---

## 2. The falsifier

Stated before the findings. What I looked for that would have made each ruling go the other way, and
what each search returned.

1. **Is R8's F-23 still live?** *No — withdrawn.* Search: compiled `tool_surface.py` with the
   `else:` fallback deleted into a fresh module, armed the ContextVar exactly as the gate does, ran
   the real `discovery_seed_for_surface`. Baseline: 2 `domain_not_selected` records. Mutated: **0,
   gate RED**. §5.1.
2. **Can the reconciler's assistant branch fire on a row this code writes?** *No.* Search:
   `grep 'streaming'` over `app/` returns exactly one writer — `stream_service.py:6879` — and that
   call passes `outcome=instrument.OUTCOME_CRASHED` at `:6887`; the upsert's `DO UPDATE SET` at
   `:6299` sets `outcome = EXCLUDED.outcome`, so it cannot be nulled later. I also enumerated all
   **five** callers of `_persist_terminal_assistant` (`:6360, :6872, :7032, :7480, :7528`) and the
   two other assistant INSERTs. `finish_reason='streaming' AND outcome IS NULL` is **unreachable**.
   §3.2.
3. **Can it relabel a completed turn, with no race at all?** *Yes.* Search: `grep 'DELETE FROM
   chat_messages'` returns one site — `routers/messages.py:633`, a user-facing
   `DELETE /{session_id}/messages/{message_id}`. Delete the last assistant reply and the preceding
   user row has `outcome IS NULL` and no assistant above it. §3.3.
4. **Does the `NOT EXISTS` handle branches?** *No — it does not mention `branch_id`, and the table's
   own uniqueness key is `(session_id, sequence_num, branch_id)`.* Search: read the edit-branch
   transaction at `messages.py:433-490`. §3.4.
5. **Can an assistant reply have a LOWER `sequence_num` than its user row?** *No.* Search: all three
   assistant writers compute `SELECT COALESCE(MAX(sequence_num),0)+1 … WHERE branch_id = 0`
   (`stream:6279`, `voice:590`, and the clean finish) **after** the user row is committed. The
   overclaim I was hunting there does not exist; the branch defect is one-directional (a miss).
6. **Can it double-count?** *No.* Both statements are `WHERE … outcome IS NULL`; under READ
   COMMITTED a concurrent second boot blocks on the row lock, re-evaluates the predicate against the
   committed update, and matches nothing. Idempotent by construction, not by luck.
7. **Is the age bound sufficient?** *It is not the guard the docstring thinks it is, and it is not
   reachable today.* Search: `chat_messages` has **no `updated_at` column** (`migrate.py:22-40`), so
   `created_at` measures time-since-first-write, not time-since-activity; the checkpoint fires every
   `_CHECKPOINT_MIN_INTERVAL_S = 1.5`s (`stream_service.py:443`) and writes nothing that could tell
   a live turn from a dead one. Reachability today: `infra/docker-compose.yml` runs one chat-service
   with `uvicorn` and **no `--workers`**, and the reconciler is awaited in `lifespan` before `yield`,
   so at the moment it runs no turn in the system is live. §3.1.
8. **Do the four reconciler gates protect the SQL?** *Two of twelve mutations caught.* Measured
   against the **frozen blob**, §5.0.
9. **Are the two new narrowings gated behaviourally?** *No — all three gates are string checks and
   none calls the code.* Turning both registrations into dead `dict(...)` literals leaves all three
   green. §5.2.
10. **DDL appended to an applied ledger step.** *Not applicable, re-checked a fifth time.*
    `migrate.py:791` re-runs the whole `DDL` string on every boot; all four CP-0 statements are
    `ADD COLUMN IF NOT EXISTS`; deleting `withheld_tools` or the `outcome` CHECK goes red (measured
    against the frozen blob). Renaming `advertised_tools` → `advertised_tools_v2` stays **green** —
    R8's substring finding, carried.

Two things I **cannot determine from source**, unchanged across nine rounds:

- **Whether the recorded values are right.** Re-verified at this SHA: `grep` for `SELECT` lines
  naming any CP-0 column across `app/` returns **nothing at all**, and the repo-wide grep outside
  chat-service returns one hit, in an **untracked** `.vlive8/p1.py` scratch script. Every recording
  is still write-only. **This is why the reconciler could ship**: it writes into a column no code
  reads, so a fabricated `crashed` is contradicted by nothing.
- **The live frequency of each mis-recorded class.** A database question. §7 hands V-LIVE the
  queries; note that the concurrent working-tree edit already answers one of them (86/223).

---

## 3. THE RECONCILER — ruling as an asymmetric fix

**Ruling: the asymmetry is real and correctly identified. The implementation inverts it.** The half
that has evidence cannot fire; the half that fires has no evidence. Four sub-rulings, then the
question I was asked in the order I was asked it.

### 3.1 Can it stamp a turn that is actually still live? — **Not today. The guard is not what the docstring says it is.**

`instrument.py:523` / `:530`: `created_at < now() - interval '{n} minutes'`, `n = 5`.

- **Reachability today: NO.** `reconcile_crashed_turns` is awaited in `lifespan` (`main.py:95`)
  **before** `yield`, so this process serves nothing yet; `infra/docker-compose.yml` runs a single
  chat-service container on `uvicorn` with no `--workers`. At the instant it runs, no turn in the
  system is live. Erring early is **unreachable in the shipped shape**, and I will not score a
  hazard I cannot reach.
- **But the bound does not measure what the docstring claims.** `chat_messages` has **no
  `updated_at`** (`migrate.py:22-40`). `created_at` is set once — at the user-message INSERT, or at
  the *first* tool-boundary checkpoint — and the checkpoint upsert does not touch it. So the field
  reads *time since the turn began*, not *time since anything happened*. A turn that has been running
  six minutes is byte-identical, to this query, to one that died six minutes ago. The signal that
  would separate them exists and arrives every 1.5 seconds — the checkpoint — and is discarded.
  That is the same shape as the `advertised` chunk voice throws away for 0.1 and the `finish_reason`
  it threw away for F-24: **a liveness signal reaching a consumer that does not look at it.**
- **The failure is irreversible on the branch that fires.** Nothing anywhere re-derives a *user*
  row's outcome: `stream_service.py:6233` requires `outcome IS NULL`, and so does the reconciler.
  The assistant branch is self-healing (the clean finish's `DO UPDATE SET outcome = EXCLUDED.outcome`
  at `:6299`/`:7302` corrects it). So the branch with a recovery path is the one that cannot fire,
  and the branch that fires has none.
- Five minutes is also not a large margin against this codebase's own rules: the repo standing rule
  is **no timeout on LLM pipelines**, the deployment target is a **local LLM**, and a multi-pass tool
  loop is routine. A second replica or a `--workers 2` makes this live, guarded by a constant with
  no test (`older_than_minutes: int = 5 → 0` leaves every gate green, measured).

### 3.2 🔴 The evidence-bearing branch is **VACUOUS** — it cannot fire on any row this code writes

`instrument.py:519-526` claims rows with `role='assistant' AND outcome IS NULL AND finish_reason =
'streaming'`.

There is exactly **one** writer of `finish_reason='streaming'` in the entire package —
`stream_service.py:6879`, the mid-turn checkpoint — and that call passes
**`outcome=instrument.OUTCOME_CRASHED`** at `:6887`, deliberately, with a comment explaining why:

> *"a mid-turn checkpoint records `crashed` PESSIMISTICALLY. If the process dies now, this is what
> the row keeps, and that is the correct reading: nothing else will ever run to correct it."*

So the row this branch exists to repair **was already repaired, by the dying process, in R7**. The
predicate `finish_reason='streaming' AND outcome IS NULL` describes only **pre-CP-0 historical
rows**. On the first boot after deploy it drains a backlog; on every boot after that it stamps zero,
forever.

Per the brief's NV rule — *"if a gate's subject never occurs in practice, that is a `FAIL` finding
even if the code is correct"* — this is a FAIL. And it matters more than a normal vacuity finding,
because **it is the half with evidence**. `finish_reason='streaming'` is a fact the runtime recorded
about itself; `crashed` is the correct reading of it, and `outcome_for_finish_reason('streaming')`
already says so. That branch is where a derived, defensible stamp lives — and it is dead.

The docstring's premise, *"the process that died cannot write its own outcome — but the process that
STARTS can, and that asymmetry is the whole mechanism"*, is **false for this branch**: the process
that died did write it.

### 3.3 The branch that fires stamps a cause it has no evidence for — and it relabels completed turns

`instrument.py:527-536` claims every `role='user'` row with `outcome IS NULL`, older than 5 minutes,
with no assistant row at a higher `sequence_num` in the session — and stamps the **literal
`OUTCOME_CRASHED`**.

**Nothing in that predicate is evidence of a crash.** It is evidence of *absence of a reply*. The
distinct conditions that reach it:

| condition | reality | recorded |
|---|---|---|
| process death before the first checkpoint | crashed | `crashed` ✔ |
| **the user deleted the assistant reply** (`messages.py:617-642`) | completed | `crashed` ✘ |
| the request failed before `_emit_chat_turn` ran (auth, model-ref, spend) | failed | `crashed` ✘ |
| **the session simply continued past it / the user moved on** | not a turn loss | `crashed` ✘ |
| a live turn on a sibling replica (§3.1) | in flight | `crashed` ✘ |

**`DELETE /v1/chat/{session_id}/messages/{message_id}` is the one that needs no race.** It is a
shipped, user-facing endpoint that deletes any single message with no companion-row handling. Delete
the last assistant reply of a completed turn and its user row becomes, to this query,
indistinguishable from a turn nobody ever answered. The next boot stamps it `crashed`.

**This is P4's own gate failing at a NEW site.** *An INSERT/UPDATE reachable from more than one
terminal condition must not assert `outcome`; it must be derived from what the turn did.* Five
conditions, one SQL-bound constant. It is the same class as the F-19 defect the run has now fixed
three times in three different files, committed in the fix for a fourth.

And it is the class the module's own opening docstring warns against, three functions up:

> *"an `unclassified` row that shows up in a dashboard is a finding; a row that was never written is
> a question nobody knows to ask."*

A row that was written **with a confident wrong cause** is neither — it is the third option this
module does not name, and the one nobody re-checks. The honest value for the user branch is
`unclassified`, or a distinct `unreconciled`, precisely because the reconciler cannot know why the
reply is missing. `crashed` is a guess wearing the name of a diagnosis.

**Independent corroboration, from outside my review.** The working-tree edit that landed while I was
grading records the live number: *"86 of 223 rows this swept sat in sessions with later activity."*
**38.6% of what this reconciler stamped at the graded SHA is wrong**, measured, in the direction
ruled above. I derived it from source before seeing that comment and I have not credited the fix — it
is not in the artifact.

### 3.4 Does the `NOT EXISTS` identify orphans? — **It misses on branched sessions. It cannot overclaim by sequence.**

```sql
NOT EXISTS (SELECT 1 FROM chat_messages a
            WHERE a.session_id = u.session_id AND a.role = 'assistant'
              AND a.sequence_num > u.sequence_num)
```

**The subquery does not mention `branch_id`** — while the table's own uniqueness key is
`(session_id, sequence_num, branch_id)` (`migrate.py:39`, `:82`) and **branches share the
`sequence_num` space**.

`routers/messages.py:433-490`, the edit-and-regenerate transaction:

1. rows with `sequence_num > edit_from_sequence` on branch 0 are **moved to a new `branch_id`,
   sequence numbers preserved** (`:447-454`);
2. the new user message is numbered `MAX(sequence_num)+1 **WHERE branch_id = 0**` (`:475-481`) — so
   it lands at `edit_from_sequence + 1`, i.e. **below** the superseded branch's rows.

A session `u@1,a@2,u@3,a@4,u@5,a@6`, edited from 3, becomes branch 0 = `u@1,a@2,u@3,u@4(new)` and
branch 1 = `a@4,u@5,a@6`. If that regenerated turn is killed before any assistant row exists, the
genuine orphan `u@4` is masked by branch 1's `a@6` — `sequence_num 6 > 4`, `NOT EXISTS` is false,
**the orphan is not stamped**. Edit-and-regenerate is not an exotic path, and it is a *higher*-risk
moment for a kill, not a lower one.

**The reverse — an assistant reply at a LOWER `sequence_num` — is not reachable**, and I checked
rather than assumed: all three assistant writers (`stream_service.py:6279`, `:7278`'s sibling,
`voice_stream_service.py:590`) compute `COALESCE(MAX(sequence_num),0)+1 WHERE branch_id = 0` after
the user row is committed. So the branch defect is one-directional: **it under-claims, never over-
claims.** The over-claim comes from §3.3, by a different mechanism.

### 3.5 Can it run twice and double-count? — **No.**

Both statements carry `outcome IS NULL`, so the second run's predicate no longer matches. Under READ
COMMITTED a concurrent second boot blocks on the row lock, re-evaluates against the committed
update, and returns zero rows. `WITH t AS (UPDATE … RETURNING 1) SELECT count(*) FROM t` counts
correctly. The `except Exception` is scoped to the whole block and returns `{0, 0}` rather than
raising, which is the right call for a startup path. **This part is well built and I am not going to
spend more words on it.**

### 3.6 Summary ruling

| question | ruling |
|---|---|
| stamps a live turn? | **not reachable today** (single replica, runs before `yield`); the bound measures the wrong thing (`created_at`, no `updated_at`) and is unguarded by any test |
| relabels a completed turn? | **YES — `messages.py:633` message deletion, no race required.** 86/223 live |
| double-counts? | **no** — idempotent by `outcome IS NULL`, verified under READ COMMITTED |
| `NOT EXISTS` correct? | **misses** every branched session (ignores `branch_id`); cannot overclaim by sequence |
| assistant branch | **VACUOUS** — its subject cannot be produced by this code (NV FAIL) |
| user branch | **P4 violation** — `crashed` asserted across ≥5 conditions, irreversibly |

---

## 4. P4 — the asserted values I was asked to hunt

**How I searched.** I enumerated every statement in the package that writes a CP-0 column: six
`INSERT INTO chat_messages` (`grep`, exhaustive) and three `UPDATE … SET outcome`. For the shared
writer `_persist_terminal_assistant` I traced all **five** callers, since the constant is chosen at
the caller, not at the statement. For each I asked the narrowed gate's question: *how many distinct
terminal conditions reach this binding, and is the value a measurement of one of them?*

**Two remaining instances, both scored.**

### F-29 · `instrument.py:528` — `crashed` asserted where the evidence is only absence
§3.3. Five conditions, one constant, no reader, irreversible. **New this round.**

### F-30 · `stream_service.py:7495` — `abandoned_by_user` asserted on a path the module itself documents as two conditions
The cancel handler binds `outcome=instrument.OUTCOME_ABANDONED_BY_USER`. Its own comment, at
`:7490-7493`, says the trigger is *"the user stopped the turn **or the client went away**"*. And the
constant's definition, at `instrument.py:71-80`, is a **recorded measurement that this is wrong**:

> *"🔴 **MEASURED DEFECT, 2026-08-04: this value reproduces that fusion one layer down.** A verifier
> opened a second browser tab, the connection dropped, and the turn was recorded `abandoned_by_user`
> with no user cancel. … this value currently means 'the stream ended from the client side', which is
> NOT what its name claims."*

The module states the defect, states that it is measured, states that the name is wrong — and the
write site binds it anyway. This is the exact structure of F-20 (voice's false comment above its own
refutation) inverted: there the comment was wrong and the code right; here the comment is right and
the code writes the value it says not to trust. **R8 did not score this and it is my correction to
make, not the builder's** — `abandoned_by_user` was on my own list of things I had ruled acceptable.

**Three carried, bounded, not scored** (stated so the search is reproducible rather than
selective): `stream_service.py:4765`'s literal `"finish_reason": "stop"` on the write-budget-
exhausted exit (documented unreachable, D7 forces the final pass tool-free); `:2349`'s
`{"tool": "*"}` pseudo-entry whose `reason` names two mutually exclusive causes joined by *"or"*
when the code holds the variables to tell them apart; and `:6376`'s `abandoned_by_user` on an
abandoned suspend, where an **errored** resume is one of the three routes and is a fault, not a user
walking away.

**And two sites are genuinely closed** — `internal.py:945` and `voice_stream_service.py:623/641`,
both now derived from a signal the code actually holds. Those were the two open P4 rows from R8.

---

## 5. THE GATE AUDIT — 30 mutations, 6 caught, 24 blind

`tests/test_cp0_instrument.py` at the frozen SHA: **875 lines, 52 tests, 12 classes** (the brief said
~46). Baseline: 17 replicated source gates and 1 replicated behavioural gate, **all GREEN on the
unmutated tree**, printed before any mutation ran.

### 5.0 🔴 THE HEADLINE — the reconciler's four gates catch 2 of 12, and the two they miss hardest are the two their docstrings name

Re-run against the **frozen blob** of `instrument.py` after the tree drifted.

| mutation | should be | **is** |
|---|---|---|
| **the CALL deleted from `main.py`, the `import` retained** | red | **GREEN** |
| the call wrapped in `if False:` | red | **GREEN** |
| **the function short-circuits — an early `return`, no UPDATE ever runs** | red | **GREEN** |
| age bound inverted — `now() + interval`, stamps every live turn | red | **GREEN** |
| `older_than_minutes` default `5 → 0` — no margin at all | red | **GREEN** |
| `NOT EXISTS` predicate inverted (`>` → `<`) — claims answered turns, skips orphans | red | **GREEN** |
| `AND a.role = 'assistant'` dropped — a user row counts as a reply | red | **GREEN** |
| session scope dropped — one assistant row anywhere masks every orphan | red | **GREEN** |
| `AND finish_reason = 'streaming'` dropped — stamps every un-outcomed assistant row | red | **GREEN** |
| `OUTCOME_CRASHED` → `OUTCOME_COMPLETED` — a dead turn reads as a success | red | **GREEN** |
| one of the two `created_at <` bounds deleted | red | red ✔ |
| the call moved before `run_migrations` | red | red ✔ |

**The first row is the round's finding.** `test_the_reconciler_has_a_caller` is:

```python
assert "reconcile_crashed_turns" in main
assert main.index("run_migrations(pool)") < main.index("reconcile_crashed_turns")
```

`main.py:94` is `from app.services.instrument import reconcile_crashed_turns`. The import satisfies
the substring **and** sits after `run_migrations(pool)`, so it satisfies the ordering too. Delete
line 95 — the actual call — and both assertions still pass. The docstring above them reads:

> *"REJECTS the state `sweep_expired_runs` is in — a docstring claiming it runs periodically and
> ZERO callers. A reconciler nobody calls is worse than none: it reads as coverage."*

`sweep_expired_runs` still has zero callers at this SHA (re-verified repo-wide; its only other
mentions are this docstring and the one in `instrument.py:513`). **The gate written to reject that
exact state, citing that exact function by name, cannot detect that exact state.** Sixth recurrence
of the mechanism, and the first time the gate has been defeated by the import of the symbol it is
checking.

The other two named-defect misses: `test_it_never_stamps_a_turn_that_might_still_be_live` — whose
docstring says *"erring early INVENTS A FACT"* — is green when the bound is inverted to
`now() + interval`, which is precisely erring early on every row in the table; and
`test_it_only_claims_rows_with_no_outcome_and_no_reply` — whose docstring says *"claiming it would
relabel a turn that completed"* — is green when the predicate is inverted so that it claims **only**
turns that completed. All four gates count substrings in `inspect.getsource(...)`. **Not one of them
calls the function.** The SQL is never parsed, never executed, never asserted over.

### 5.1 R8's stated falsifier — executed, and it returned the builder's answer

`test_tools_outside_the_hot_domains_register_as_withheld` (`:697-731`) now omits `withheld_sink=`
and arms the ContextVar, exercising the branch both production call sites use.

| mutation | should be | **is** |
|---|---|---|
| **delete the `else:` ContextVar fallback at `tool_surface.py:397-400`** | red | **red ✔ — F-23 WITHDRAWN** |
| `domain_not_selected` block disabled (`if False:`) | red | red ✔ |

Measured behaviourally: baseline sink = 2 `domain_not_selected` records; fallback deleted = **0**,
gate RED. This is the condition I set in R8 for withdrawing F-23 and it is met without
qualification. It is the largest narrowing in the system and it is now instrumented **and** guarded.

**What still falsifies P1 is F-26, unchanged.** `domain_not_selected` and the assembly-time
`hot_seed` drops run once per turn and the sink is drained once (`stream_service.py:6903-6907`,
`while _surface_sink: pop`), so passes 2..n carry no record for them. The two *new* narrowings do
not have this problem — `_advertise_discovery_tools` runs per pass at `:2132`, ahead of the
`advertised` yield at `:2256`/`:2286` — which makes the split within the column sharper, not
smaller: some stages are per-pass and some are pass-1-only, in one array, still undocumented at the
column (F-25).

### 5.2 THIS ROUND'S OTHER NEW CODE — the P1 residual gates, 2 of 6

| mutation | should be | **is** |
|---|---|---|
| `catalog_miss` registration deleted outright | red | red ✔ |
| `catalog_miss` reason emptied to `"dropped"` | red | red ✔ |
| **`catalog_miss` becomes a dead `dict(...)` literal — never registers** | red | **GREEN** |
| **`permission_tier` becomes a dead `dict(...)` literal** | red | **GREEN** |
| **`permission_tier` registers on ONE branch only (`if plan:`) — the exact defect being fixed** | red | **GREEN** |
| **the `catalog_miss` record moved AFTER the `continue`** | red | **GREEN** |

The last row is `test_the_catalog_miss_registers_before_the_early_return_swallows_it`, whose entire
docstring is:

> *"REJECTS: registering AFTER the `continue`. `_add(None)` returns at its first line, so a record
> placed downstream of it never runs — the failure mode that made this invisible."*

The gate does `cont = window.index("continue", miss)` and asserts `miss < cont`. Move the record
below its own `continue` and the search simply finds the **next** `continue` — the one belonging to
the `permission_tier` branch 12 lines further down — so `miss < cont` still holds. **Green over the
defect it names, in a window that contains a second instance of its own needle.** Same arithmetic
slack as R8's F-27, in a different shape: there a surplus stamp elsewhere in the file paid for a
missing one; here a surplus `continue` does.

The three dead-literal mutations are the deeper problem: `stage="catalog_miss"` and
`stage="permission_tier"` are asserted as **text present in the file**. No test constructs a
`catalog_index` with a missing name, or a restricted `permission_mode` with a non-R tool, and calls
`_advertise_discovery_tools`. The code is correct — I read it and the placement is right — but the
guard is a spell-check.

### 5.3 Carried gates — R8's blind spots, re-measured, all still blind

| gate | mutation | **is** |
|---|---|---|
| F-19 · clean finish, both fields from one signal | outcome reverts to the `OUTCOME_COMPLETED` constant | **GREEN** |
| F-19 | the `_loop_finish_reason` capture deleted | **GREEN** |
| E · assistant-INSERT outcome | **voice outcome reverted to the `OUTCOME_COMPLETED` constant** | **GREEN** |
| E | **voice discards `finish_reason` again — F-24 reintroduced verbatim** | **GREEN** |
| E | voice binds `outcome = None` | **GREEN** |
| E | voice `finish_reason` re-pinned to the literal `'stop'` | **GREEN** |
| E | **proactive `finish_reason` reverts to the literal `'stop'` — F-28 reintroduced verbatim** | **GREEN** |
| E | proactive outcome flipped to a WRONG constant (`crashed`) | **GREEN** |
| F · vocabulary + columns | delete `withheld_tools`; delete the `outcome` CHECK | red ✔ |
| F | rename `advertised_tools` → `advertised_tools_v2` | **GREEN** (substring) |
| — | `error` no longer maps to `failed` (measured: → `interrupted`) | **GREEN** — no gate |
| — | `latency_unmeasured` reason dropped (measured: key gone) | **GREEN** — no gate |

**Both of this round's genuine closures are ungated.** F-24 and F-28 were the two real fixes; both
can be reverted with one edit each and the full suite stays green. Gate E checks that the word
`outcome` appears in an assistant INSERT's column list and has never checked a value.

### 5.4 Scorecard

| gate | red-able for its own defect? |
|---|---|
| A · budgeter wiring | partly — green over an `_ex` caller that discards `dropped` |
| B · dispatch stamping | yes for its three named sites; blind to a renamed receiver |
| C · outcome/finish_reason lockstep | property TRUE on the tree; needle blind to 4 of its own reintroductions |
| D · surface narrowing | **behavioural half now covers production — the strongest gate in the suite** |
| E · assistant-INSERT outcome | partly — catches a missing column anywhere; **blind to every value, 6/6** |
| F · vocabulary + columns | yes, both directions, except a rename with a preserved prefix |
| **P1 · candidate selection** | **YES — F-23 withdrawn, measured 2/2** |
| **P1 · catalog_miss / permission_tier** | **partly — 2/6; blind to a dead call and to its own stated defect** |
| P2 · structural source | yes — the strongest class in the suite, unchanged |
| P3 · orphan stamp | partly — 3/6 (R8), unchanged |
| **P3 · kill-path reconciler** | **NO — 2/12, and blind to "the call was deleted"** |
| — · voice, everything | **no — 0/4** |
| — · `latency_unmeasured`, `error` mapping | **no — no gate exists** |

---

## 6. Findings

### F-29 · The reconciler's user branch stamps `crashed` on turns that completed
§3.3. `instrument.py:527-536`. Reachable from ≥5 conditions including `messages.py:633` (a user
deleting an assistant reply) with no race at all. Irreversible: nothing re-derives a user row's
outcome. Live corroboration from outside this review: **86 of 223 swept rows were in sessions that
continued.** P4 violated at a new site.

### F-30 · `abandoned_by_user` is asserted on a path the module documents as two conditions
§4. `stream_service.py:7495` vs `instrument.py:71-80`. The constant's own definition records the
measurement showing the name is wrong, and the write site binds it. **My correction, not the
builder's** — R8 ruled this site acceptable.

### F-31 · The reconciler's assistant branch is VACUOUS on every row this code writes
§3.2. `instrument.py:519-526` vs `stream_service.py:6879` + `:6887`. The only writer of
`finish_reason='streaming'` always sets `outcome='crashed'`, so the predicate matches pre-CP-0 rows
only. NV FAIL, and it is the half with evidence.

### F-32 · The reconciler's `NOT EXISTS` ignores `branch_id`
§3.4. `instrument.py:531-534` vs `migrate.py:39`/`:82` and `messages.py:433-490`. Every
edit-and-regenerate orphan is masked by the superseded branch's higher-numbered assistant row.

### F-33 · `test_the_reconciler_has_a_caller` is satisfied by the import statement
§5.0. `test_cp0_instrument.py:837-844` vs `main.py:94-95`. Delete the call, keep the import: green.
Measured. The gate cites `sweep_expired_runs` by name as the state it rejects, and
`sweep_expired_runs` still has zero callers at this SHA.

### F-34 · The reconciler's SQL is guarded by four string checks and 8 of 8 semantic mutations pass
§5.0. Including inverting the age bound, inverting the orphan predicate, and stamping `completed`
instead of `crashed`.

### F-35 · `test_the_catalog_miss_registers_before_the_early_return_swallows_it` is green over its own stated defect
§5.2. `test_cp0_instrument.py:811-819`. `window.index("continue", miss)` finds the *permission_tier*
`continue`, so moving the record below its own `continue` still satisfies `miss < cont`.

### F-36 · Both new narrowings can become dead literals with every gate green
§5.2. Three string gates, no test calls `_advertise_discovery_tools`.

### F-23 · **WITHDRAWN**
§5.1. R8's stated falsifier executed and returned the builder's answer. The P1 gate covers the
production branch; the largest narrowing in the system is instrumented **and** protected.

### F-24 · **RESOLVED** — voice derives both fields from the terminal reason
`voice_stream_service.py:503-504, :623-624, :641`. Ungated (§5.3).

### F-28 · **RESOLVED** — the proactive check-in distinguishes a generation from the fallback
`internal.py:945`. Derived from a comparison against the committed value. Ungated (§5.3).

### F-25, F-26, F-27, F-20, F-21, F-22, F-8, F-11, F-1, F-9 (carried, unchanged)
Two counting conventions and ~44 KB/row in `withheld_tools`; per-pass registration stops after pass
1 for the assembly stages; the F-19 needle blind to reintroductions of its property; voice's false
comment at `:604-608` still directly above its own refutation (**fourth round quoted**); the
recorder's and gate's docstrings still asserting the invariant F-16 corrected; the voice suspend's
own pending call still unrecorded; every recording still write-only (re-verified: zero `SELECT`s);
`RUNTIME_AGENTRUNTIME` still has no producer and `tool_call_source()` still zero callers; voice's
INSERT still has no `withheld_tools` column and `budget_rail_tools`' drops still go to
`logger.warning`; `run_arms.py:114` still claims an assertion it does not make.

---

## 7. Terminal-path enumeration (0.4) — full, not summarised

| # | terminal path | `file:line` | writes? | outcome | R9 |
|---|---|---|---|---|---|
| 1 | clean finish, `stop` | `stream:7254` | yes | `completed` | pass |
| 1b | clean finish, `length`/`tool_calls` | `:7327` ← `:6918` ← `:2778` | yes | `completed`, agrees | pass (closed R8) |
| 1c | clean finish, `content_filter` | same | yes | `failed` | pass |
| 1d | clean finish, unrecognised word | same | yes | `interrupted` — countable, fail-safe | pass |
| 2 | frontend-tool suspend | `:7032` | yes | `awaiting_input` | pass |
| 3 | **cancellation / client disconnect** | `:7480-7495` | yes | ⚠️ `abandoned_by_user` on a dead transport | **FAIL — F-30** |
| 4 | mid-stream exception | `:7528` | yes | `failed` | pass |
| 5/6 | abandoned suspend (± provisional row) | `:6338`/`:6380` | yes | `abandoned_by_user` | pass (bounded, §4) |
| 7 | empty terminal turn | `:6205-6259` | user row stamped | derived | pass (closed R8) |
| 8 | mid-turn checkpoint (crash surrogate) | `:6872-6887` | yes | `crashed`, pessimistic | pass — and it is what makes #9a vacuous |
| **9a** | **process death AFTER a checkpoint** | reconciler assistant branch | n/a | — | **VACUOUS — F-31.** Already stamped by #8 |
| **9b** | **process death BEFORE any checkpoint** | reconciler user branch `instrument:527` | yes | ⚠️ `crashed` — correct here, wrong on 4 sibling conditions | **PARTIAL — F-29** |
| **9c** | **process death during an edit-and-regenerate** | — | **no** | ❌ none — masked by the superseded branch | **FAIL — F-32** |
| 10 | tool-loop pass exhaustion | `:4759` → `"stop"` at `:4765` | yes | ⚠️ `completed` | FAIL — unchanged, documented unreachable |
| 11 | expired / mismatched resume | → #6 | yes | ✅ | pass |
| 12 | voice, clean finish | `voice:593-643` | yes | derived from `_voice_finish_reason` | **pass — CLOSED, was F-24** |
| 12b | voice, `length` / `content_filter` | `voice:623/641` | yes | `completed` / `failed`, agreeing | **pass — CLOSED** |
| 13a | **voice turn, exception** | `voice:792-794` — logs, yields an SSE error, returns | **no** | ❌ none | **FAIL — unchanged** |
| 13b | voice suspend-abort | `voice:496` → `:623` | yes | ⚠️ `awaiting_input` on a turn nothing can resume | FAIL, downgraded — unchanged |
| 14 | proactive check-in, generated | `internal:927-945` | yes | `completed` / `'stop'` | pass |
| 14b | proactive check-in, static fallback | `internal:913` → `:945` | yes | `completed` / `'static_fallback'` | **pass — CLOSED, was F-28** |
| 15 | suspend never resumed, never expired | `db/suspended_runs.py:187` — **zero callers**, re-verified | yes | ❌ `awaiting_input` forever | **FAIL — unchanged** |
| 16/17 | spend-gate refusal · turn-level timeout | searched — neither exists in this service | n/a | n/a | — |

**Six paths fail (#3, #9b-partial, #9c, #10, #13a, #13b, #15); three closed this round (#12, #12b,
#14b); one new vacuity (#9a).** Gate E can see none of them.

**Handoff to V-LIVE, executable:**

```sql
-- F-29: how much of the reconciler's output is a completed turn wearing 'crashed'.
-- (a) the session continued afterwards; (b) the reply was deleted.
SELECT count(*) FILTER (WHERE EXISTS (SELECT 1 FROM chat_messages n
         WHERE n.session_id=u.session_id AND n.sequence_num>u.sequence_num)) AS continued,
       count(*) AS swept
  FROM chat_messages u WHERE u.role='user' AND u.outcome='crashed';
-- F-31: does the assistant branch ever stamp anything after the first boot?
SELECT count(*) FROM chat_messages
 WHERE role='assistant' AND finish_reason='streaming' AND outcome IS NULL;   -- expect 0
-- F-32: orphans hidden behind a superseded branch
SELECT count(*) FROM chat_messages u WHERE u.role='user' AND u.outcome IS NULL
   AND NOT EXISTS (SELECT 1 FROM chat_messages a WHERE a.session_id=u.session_id
                     AND a.branch_id=u.branch_id AND a.role='assistant'
                     AND a.sequence_num>u.sequence_num);
-- F-30: cancels with no user intent behind them
SELECT outcome, finish_reason, count(*) FROM chat_messages
 WHERE outcome='abandoned_by_user' GROUP BY 1,2;
```

---

## 8. Vacuity (NV) — can each new check fire?

| check | realistic firing input? |
|---|---|
| `catalog_miss` registration | **Yes** — a name in the active set with no catalog entry; measured live as the same 4 tools in both runs |
| `permission_tier` registration | **Yes** — every `ask`/`plan` discovery turn, and voice runs `permission_mode="ask"` |
| **reconciler, assistant branch** | **NO — its subject cannot be produced by this code (F-31).** Fires once, on the pre-CP-0 backlog |
| **reconciler, user branch** | **Yes, and too often** — 223 rows swept, 86 of them wrong |
| the reconciler's age bound as a liveness guard | **No — unreachable today** (single replica, runs before `yield`); becomes live with a second replica or `--workers` |
| `domain_not_selected` ContextVar fallback | **Yes — the only branch production uses, and now gated (F-23 withdrawn)** |
| `outcome_for_finish_reason` `case _` | **Yes** — `function_call`, `refusal`, any gateway passthrough word |
| voice non-suspend, non-`stop` termination | **Yes**, and now recorded correctly |
| proactive static fallback | **Yes**, and now distinguishable in `finish_reason` |
| `runtime_variant = 'agentruntime'` | **No** — no producer |
| `tool_call_source()` · `dedupe_recorded_calls` | **No** — zero callers; the latter by design |
| `latency_unmeasured` | **Yes, ~26 of ~30 mint sites** — and still **no gate** |

---

## 9. Bypass table — one row per item

| item | the path that skips it, or the search that found none |
|---|---|
| **0.1** | `voice_stream_service.py:639` still binds NULL with an honest retraction comment; voice receives the `advertised` chunk and swallows it at `:474`. Per-pass registration for the assembly stages stops after pass 1 (F-26). Not bypassed by overwrite — `record_pass` appends, both upserts `COALESCE` (re-verified). |
| **0.2** | voice's INSERT has **no `withheld_tools` column** (`voice:604-608`); `budget_rail_tools`' drops go to `logger.warning` (`tool_surface.py:550-554`); the `{"tool": "*"}` pseudo-entry (`stream:2349`); two counting conventions in one array (F-25). |
| **0.3** | `source` — **no bypass found**, assigned in exactly two places package-wide, `tool` unreachable by inference, inferred rows self-marking (all re-verified by mutation). `latency_ms` measured at 4 of ~30 mint sites with **no gate**; the voice suspend's own pending call unrecorded; nested subagent calls consumed at `:4850-4858` reach no INSERT. |
| **0.4** | Six paths. Write **no row**: `voice:792` (exception), and any edit-and-regenerate kill (F-32). Write a **fabricated cause**: `instrument.py:528` (F-29), `stream:7495` (F-30), `:4765` (pass exhaustion). Write a **stale** value: `suspended_runs.py:187`, zero callers. Full enumeration §7. |
| **0.5** | No bypass at the SHA — `git ls-tree c7dc6195f` confirms all three baseline files and `eval/arms/run_arms.py`. ⚠️ `baseline-metrics.sql` is modified in the working tree. F-9 remains a docstring overstatement. |
| **0.6** | No bypass. `binding_format.py` + both result files tracked at the SHA. |
| **0.7** | No bypass of the literal claim; all three chokepoints route every recorded call through `ensure_tool_call_instrumented`. Bounded by F-11 and by nested subagent calls reaching no INSERT. |

---

## 10. What changed in the failure, and my falsifier for this round

**Three closures, and one of them is the kind that ends an argument.** R8 wrote a falsifier for F-23
with a stated pass condition; the builder changed the code; I executed the falsifier and it went red.
That is the first time in nine rounds a finding has been retired by the procedure it named rather
than by a new reading. F-24 and F-28 are also genuinely fixed, and both were fixed by *deriving from
a signal the code already held* rather than by choosing a better constant — which is the correct
shape.

**And the class moved into the fix itself.** For eight rounds the defect was a confident answer to
something nobody measured. This round it is a **reconciler whose two halves are exactly inverted**:
the branch with evidence (`finish_reason='streaming'`) cannot fire, because the dying process already
recorded it in R7; the branch that fires (a user row with no reply) has no evidence at all and stamps
`crashed` on five conditions, one of which is a user pressing delete. The mechanism was described
correctly — *the process that died cannot write its own outcome, but the process that starts can* —
and then pointed at the one shape where the dying process **had** written it.

The gate story is the same story one level up. Four tests, twelve mutations, two caught; and the one
that matters is that **deleting the call leaves the "it has a caller" test green**, because the
import supplies the substring. The suite now contains a gate that certifies exactly the property its
own docstring says it exists to reject, naming the function that still exhibits it.

**My falsifier for this round's headline ruling, stated so a later round can execute it as R8's
was:**

1. Delete the line `await reconcile_crashed_turns(pool)` from `main.py:95`, leave the import at
   `:94`, and run the suite. If `test_the_reconciler_has_a_caller` goes **red**, F-33 is withdrawn in
   full. If it stays green — which is what I measured against the frozen `main.py` — then the only
   new mechanism P3 gained this round is protected by a test an import statement satisfies.
2. Run `SELECT count(*) FROM chat_messages WHERE role='assistant' AND finish_reason='streaming' AND
   outcome IS NULL` on a database that has booted this build **twice**. If it is non-zero, F-31 is
   withdrawn and I have missed a writer. If it is zero — which is what the source says it must be,
   because `stream_service.py:6887` passes `OUTCOME_CRASHED` on the only path that writes
   `'streaming'` — then half the reconciler is a gate on a shape that cannot occur.

**And one thing I have to record about my own work, again.** I ruled `abandoned_by_user` acceptable
in R7 and did not revisit it in R8, while the constant's own definition three functions above the
write site records the measurement showing its name is wrong. That is the second time I have held
evidence in a docstring and not applied my own gate to it. F-30 is mine.

**Finally, and separately from the verdict: the artifact was not frozen.** Four tracked files
changed during this grading, two of them files under test and one of them the *frozen baseline* that
item 0.5 certifies. I pinned everything to `c7dc6195f` and re-derived the affected results from the
frozen blobs, so this verdict is sound — but a checkpoint that is edited while it is being graded
cannot be closed by the grade, because the thing graded and the thing shipped are no longer known to
be the same thing. That is the same failure mode as freezing the *output* of a live database, which
this run has already recorded once.
