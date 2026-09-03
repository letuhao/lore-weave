# Reconciling `feat/frontend-tools-mcp-migration` into `refactor/kal-and-mcp-runtime`

**Written:** 2026-09-03 · **Target:** `refactor/kal-and-mcp-runtime` @ `87690ed98` (PR #219)
· **Source:** `feat/frontend-tools-mcp-migration` @ `168b4f318`

Reconciles: MCP Tool I/O Standard · Reading/writing entity or KG knowledge · Frontend-Tool
Contract — all three are surfaces the two branches edited from opposite ends. Both touched the
same MCP servers (`knowledge-service/app/mcp/server.py`,
`glossary-service/internal/api/mcp_server.go`), which §1.1 Class A resolves. KAL's
`neo4j_repos`→`graph_repos` sweep *is* the KG read/write path, and §2 is the dead references it
leaves in FE's callers — including FE's own P7 chokepoint. And FE renames the Frontend-Tool
Contract row's own SoT (`contracts/frontend-tools.contract.json` →
`contracts/browser-tools.contract.json`), so that index link dies at the merge; repointing it is
part of §3 Phase 2. No row governs branch reconciliation itself, which is why this is a plan and
not a new standard.

This is not a merge. A trial merge finished in one command with 23 conflicts — and produced a
tree where **the P7 invariant is silently disabled and its own falsifier no longer imports.**
The conflicts are the easy part; this plan is mostly about what merges *clean and wrong*.

Every number below was measured in a throwaway worktree at the two heads above, not estimated.
The trial is reproducible in one command (§1.2).

---

## 0. Position, and the one piece of good news

| | |
|---|---|
| KAL vs `main` | **0 behind**, 1375 ahead — its merge-base *is* main's HEAD `df18e9049` |
| FE vs `main` | 96 behind, 1963 ahead |
| KAL ↔ FE | shared base `de2e0416d` (2026-08-03) · 1700 FE-only / 1207 KAL-only commits |

**Direction is therefore forced: merge FE into KAL.** KAL is current with main and already has
PR #219 open; FE is a month behind. Merging the other way means re-doing main's 96 commits.

**The good news, and it is substantial: KAL's chat-service is main's chat-service.**
`stream_service.py` is 7823 lines on both, `app/agentruntime/` does not exist on KAL, and the v1
`frontend_tools.py` is still present there. KAL's early merge of FE (`50bff49a4`, 2026-08-02)
predates essentially all of FE's MCP work.

So FE's centre of gravity — the v1→v2 migration, the 20-module agentruntime package, the 7000
lines in `stream_service.py`, the twelve-invariant guards — **lands uncontested.** Verified in the
trial: `frontend_tools.py` absent, `browser-tools.contract.json` present, `agentruntime/` present.

KAL's seven new services (`world-service`, `commit-service`, `meta-worker`, `knowledge-gateway`,
`admin-cli`, `publisher`, `game-server`) barely mention MCP — 3 files across 356. **FE's tool
catalogue does not need extending for them.** One worry retired.

---

## 1. What the trial merge actually produced

### 1.1 Twenty-three conflicts, in four classes

**Class A — the rename sweep. MEASURED 2026-09-03, and the first version of this section was
wrong.** KAL renamed `app/db/neo4j_repos/` to `app/db/graph_repos/` (14 files, R100..R061) and
`neo4j_session()` to `graph_session()` so Apache AGE can replace Neo4j. I wrote that all five
files resolve mechanically — FE's content, KAL's rename. **Counting KAL's non-rename lines per
file refutes that for three of them:**

```
file                          KAL non-rename +/-   verdict
app/mcp/server.py                        0         TRUE Class A — pure rename
app/tools/graph_schema_tools.py         28         mostly rename, small real change
app/routers/public/graph_views.py       63         mixed
app/db/graph_repos/facts.py            357         NOT Class A  <- see below
app/db/graph_repos/relations.py        394         NOT Class A
```

**`facts.py` and `relations.py` invert the rule.** KAL's work there is **AGE dialect
compatibility** — Cypher rewritten because AGE cannot compile what Neo4j accepts. Its own
comments say so: *"§10.1 — `WITH DISTINCT f` rather than `RETURN DISTINCT f … ORDER BY`. AGE
compiles the … after it. AGE refuses the second form."* Taking FE's content there would
reintroduce Cypher the default engine cannot run — the same shape as the `fact-for-check` 502 in
PR #219.

FE's side of those two files is small and additive: **`facts.py` +166/−1, and it is exactly three
functions** — `query_tokens`, `rank_facts_by_overlap`, `search_facts_by_text`, which together
*are* FE's P7 fix. `relations.py` is +6/−1.

> **Resolution: take KAL's content, port FE's three functions onto it.** Then check the new
> `_SEARCH_FACTS_BY_TEXT_CYPHER` against AGE — it was written against Neo4j and never passed
> through `app/db/cypher_dialect.render`. It carries no `{NOW}` token so it needs no render, but
> `ANY(t IN $tokens WHERE toLower(f.content) CONTAINS t)` and `IN f.source_types` are unverified
> on AGE. **Unverified, not broken — this must be measured, not assumed.**

**Class B — genuine two-sided design; read both (6 files).**

```
services/glossary-service/internal/api/entity_handler.go        KAL 72/26  FE 52/7
services/glossary-service/internal/api/g_pipeline_propose_test.go
services/glossary-service/internal/migrate/ledger.go            <- see 4.3
services/jobs-service/app/contract.py
services/jobs-service/app/routers/jobs.py
services/composition-service/app/engine/name_grounding.py (+ its unit test)
```

**Class C — gates and CI; both sides moved the bar (5 files).**

```
scripts/context-budget-defaults-lint.py    KAL 236/26  FE 149/0
scripts/gate-teeth-gate.py
scripts/llm-budget-ssot-gate.py
.github/workflows/foundation-ci.yml
infra/docker-compose.yml                   <- neither side is a superset
```

**Class D — prose and config; cheap, but do not rubber-stamp (7 files).**
`docs/sessions/SESSION_HANDOFF.md`, `docs/standards/README.md`, `docs/deferred/DEFERRED.md`,
`.gitignore`, `.claude/commands/goal-prompt.md` (**add/add** — absent at base, KAL 116 lines,
FE 87), `services/knowledge-service/tests/unit/test_graph_schema_tools.py`.

### 1.2 Reproducing the trial

```sh
git worktree add --detach <scratch>/trial refactor/kal-and-mcp-runtime
git -C <scratch>/trial merge --no-commit --no-ff origin/feat/frontend-tools-mcp-migration
git -C <scratch>/trial diff --name-only --diff-filter=U     # the 23
```

---

## 2. THE REAL PROBLEM — what merges clean and wrong

Git merges per-file. A file only FE touched takes FE's version, whatever KAL renamed underneath
it. **217 files on FE reference `neo4j_repos`/`neo4j_session`; KAL has 12 left.**

Hard breaks in the merged tree — a dead import or a dead call, not merely the old name inside an
identifier — land in **7 files. Two are conflicted, so git makes you look. Five are silent:**

| file | line | break | silent? |
|---|---|---|---|
| `app/tools/executor.py` | 632, 635 | `from app.db.neo4j_repos.facts import search_facts_by_text` | **YES** |
| `app/routers/public/user_data.py` | 34, 172 | module-level `from app.db.neo4j import neo4j_session` | **YES** |
| `tests/unit/test_a_stored_fact_is_findable_by_memory_search.py` | 30 | dead import | **YES** |
| `tests/unit/test_kind_accepts_the_ordinary_word.py` | 17, 52, 65 | dead import | **YES** |
| `tests/unit/test_the_ordinary_word_reaches_the_alias_map.py` | 28 | dead import | **YES** |
| `app/mcp/server.py` | 67–69 | dead imports | no — conflicted |
| `app/tools/graph_schema_tools.py` | 660, 700, 2205, 2209, 2240 | dead imports + calls | no — conflicted |

### 2.1 The one that must not ship

**`executor.py:632` is FE's P7 chokepoint.** P7-FALSE-ABSENCE's invariant is *"a store that
accepts a write must have a read that can find it"*, and its chokepoint is exactly this — the
`search_facts_by_text` fact leg of `memory_search`. It is a **function-level** import, so it does
not fail at startup; it fails when the fact leg runs. And
`test_a_stored_fact_is_findable_by_memory_search.py` — **P7's own falsifier** — breaks at import,
so the suite cannot report it.

That is the precise failure the twelve-invariant loop was built to prevent, reintroduced by a
merge git called clean. `user_data.py:34` is a module-level import, so that router will not load
at all.

### 2.2 Two more of the same family

- `tests/unit/test_multi_query_shape_does_not_change_with_the_outcome.py:40,46` calls
  `body.index("async with neo4j_session()")` — a **source-substring assertion** on a string the
  rename deleted. `.index()` raises, so this one is self-announcing. It still has to be re-pointed.
- 19 further files mention the old names only in identifiers and fixture names
  (`_patch_neo4j_session`, `neo4j_session_mock`). **Cosmetic — do not "fix" them into a diff
  nobody asked for.** They are listed so a later grep does not re-panic.

---

## 3. Sequence

Ordered so every red thing can be *attributed*. PR #219's body is the precedent worth copying: it
measured each side separately and found three of six red gates were already red before that merge
existed. Skipping this step is how a merge gets blamed for a pre-existing failure — or worse,
credited with a pass it did not earn.

### Phase 0 — Baseline both sides BEFORE merging

1. On KAL: `gate-wiring-gate --run-all`, gate self-tests, knowledge unit suite,
   `book-service go build`, `eventgen-validate`. Record the counts. PR #219 claims 137 GREEN /
   0 RED / 25 SKIP and 149 green self-tests — **verify, do not inherit the claim.**
2. On FE: `problem_remaining.py` (exits 0) and the `scripts/` suite — **18 known pre-existing
   failures, down from 22.** That number is the attribution baseline.
3. Note the asymmetry PR #219 records: `--run-all` invokes gates **bare**, the pre-commit hook
   invokes them with `--selftest`, and a gate can pass one while failing the other. Baseline
   **both**.

### Phase 1 — Merge, resolving by class

4. Merge with `--no-commit`. Class A by rule (FE content + KAL rename); Class B by reading both
   sides; Class C by taking the union of the bars and re-deriving every count; Class D by hand.
5. **Do not `--no-verify` the merge commit.** PR #219 records its own `--no-verify` coming due
   later: three gates were red at HEAD and `--run-all` had never seen them.

### Phase 2 — The silent sweep (git will not prompt for any of this)

6. Fix the 5 silent hard-break files, `executor.py` first.
7. Re-point the 2 source-substring assertions.
8. Leave the 19 cosmetic mentions alone.

### Phase 3 — Close the gap so the class cannot recur

9. **Add an import-resolution gate**: every `from app.X import Y` in a service resolves to a
   module that exists. This is the gap — the repo carries 133 gate scripts and not one would have
   caught `executor.py:632`. Prove it red on that exact line first, then green.
10. **Re-prove FE's twelve invariants against the merged tree.** `problem_remaining.py` reads
    contracts, not code, so **it will still exit 0 with P7 broken.** The chokepoint tests are the
    real bar: run each whole owning suite, and confirm every guard is still *called* — the AST
    gate in `test_no_turn_guard_is_defined_and_never_called.py` exists for exactly this.

### Phase 4 — What the merged tree must pass

11. KAL's 133 gates over ~2000 files of FE code that have never faced them. Expect red; attribute
    each against Phase 0 before changing anything.
12. Main's i18n key-resolution gate against FE's frontend: `DisambiguationCard.tsx` and three
    siblings carry **52 `t()` calls** with **zero** changes under `frontend/src/i18n/`.
    Predicted red.
13. A live run. Neither branch's board can see a route that 502s — PR #219 found `fact-for-check`
    answering 502 to every caller while the 16-route sweep was green.

---

## 4. Refactors this merge should carry, not defer

### 4.1 The rename is not yet an abstraction

`app/db/neo4j.py` now exports `graph_session()` — the module is still named for one engine. FE
adds callers, and every one bakes in the old path. Renaming the module is mechanical *now* and
gets more expensive with each caller. **Owner's call:** in scope, or a named follow-up.

### 4.2 `docker-compose.yml` is three-way, not two

KAL's overlay design (`docker-compose.knowledge-pg.yml` selects AGE), plus FE's federated MCP
wiring, plus main's 21 lines. No side is a superset. PR #219 warns that
`${KNOWLEDGE_GRAPH_BACKEND:-age}` passing an **explicit** `age` moved every install onto a
database it had never created — **do not reintroduce a default here while resolving the conflict.**

### 4.3 `glossary-service/internal/migrate/ledger.go`

Both sides edited it, and main separately *restored a ledger an earlier commit reverted by
accident*. Repo lore: DDL added to an already-applied ledger step is a silent no-op, and a test
calling a step function directly reverts a later chain step. **Merge by reading the ledger, never
by taking a side.**

---

## 5. Explicitly out of scope

- Landing either branch on `main`. This produces one reconciled branch; the PR is a separate call.
- FE's `docs/eval` corpus — 5.88M insertions across 842 files — merges without conflict, since
  neither main nor KAL ever touched it. **Carry it.** It is the evidence behind the
  twelve-invariant report, nothing reads it at runtime, and deleting a measurement record to save
  bytes is not a saving. Flagged only because it will dominate the diffstat.
- The four residues in the twelve-invariants report §5 (the LM Studio TTL stall, P16's missing
  live evidence, seven tools below the selection bar, 18 pre-existing `scripts/` failures). All
  predate this merge; none should be attributed to it.

---

## 6. The one thing to hold onto

The trial merge succeeded, the conflicts were few, and the tree it produced had a broken invariant
and a broken falsifier for it. **On this repo, a green suite after a large merge is not evidence.**
PR #219 already documents three defects its own merge introduced while the tests stayed green — a
gate that "reported a clean scan of nothing", two `main()` definitions silently shadowing each
other, and a lost shrink arm found only by `gate-bite-harness`. Phase 3's import gate exists so
this specific class is caught by a machine next time, rather than by a person reading a grep.

---

## 7. Board

The queue for `/goal` derives from these rows — a ticked row leaves it by itself. Detail for each
lives in the section it cites.

- [x] **B0** — baseline KAL: `gate-wiring-gate --run-all`, gate self-tests **bare and
  `--selftest`**, knowledge units, `book-service go build`, `eventgen-validate`. Verify PR #219's
  137/0/25 and 149; do not inherit the claim. (§3 Phase 0 · evidence §8)
- [x] **B1** — baseline FE: `problem_remaining.py` exits 0, and the `scripts/` suite's **18**
  pre-existing failures. This is the attribution baseline. (§3 Phase 0 · evidence §8)
- [x] **M1** — merge `--no-commit`; resolve the rename-sweep files. **Only `mcp/server.py` is
  mechanical**; `facts.py`/`relations.py` invert the rule — take KAL, port FE's three functions.
  (§1.1, as corrected by B0)
- [x] **M2** — resolve **Class B**, the 6 two-sided files. `ledger.go` by reading the ledger,
  never by taking a side. (§1.1, §4.3)
- [x] **M3** — resolve **Class C**, the 5 gate/CI files: union of the bars, every count
  re-derived. `docker-compose.yml` is three-way and must not regain a backend default. (§1.1, §4.2)
- [x] **M4** — resolve **Class D**, the 7 prose/config files, including the `goal-prompt.md`
  add/add. Commit the merge **without** `--no-verify`. (§1.1)
- [x] **S1** — fix the **5 silent hard-break** files, `executor.py:632` first — FE's P7
  chokepoint. (§2, §2.1)
- [x] **S2** — re-point the **2 source-substring assertions**; leave the 19 cosmetic mentions
  alone. (§2.2)
- [x] **G1** — build the **import-resolution gate**: every `from app.X import Y` resolves.
  Proven RED on `executor.py:632` before green. None of the repo's 133 gates catches this. (§3 Phase 3)
- [x] **V1** — re-prove the twelve invariants against the merged tree via the **owning suites**,
  not the board, plus the guard-is-called AST gate. (§3 Phase 3)
- [ ] **V2** — KAL's 133 gates over FE's ~2000 files. Attribute every red against B0/B1 before
  changing anything. (§3 Phase 4)
- [x] **V3** — main's i18n key-resolution gate vs FE's frontend: 52 `t()` calls, zero bundle
  changes. Predicted red. (§3 Phase 4)
- [ ] **V4** — a live run through the real stack. A 502 route is invisible to both boards. (§3 Phase 4)
- [ ] **R1** — **STOP CONDITION** — §4.1: rename `app/db/neo4j.py`, still named for one engine,
  or record it as a named follow-up. Owner's decision; mechanical now, worse per caller. (§4.1)

---

## 8. Evidence

### B0 — KAL at `87690ed98`, measured 2026-09-03

| check | result |
|---|---|
| `gate-wiring-gate --run-all` | **135 GREEN / 2 RED / 23 SKIP** |
| gate self-tests (hook's `--selftest` set) | **20/20 scripts pass**, 347 individual PASS lines |
| knowledge unit suite | **4502 passed**, 19 warnings, 86s |
| `book-service go build ./...` | exit **0** |
| `eventgen-validate` | **PASS** — 26 generated Python modules import cleanly |

**PR #219 claims 137 GREEN / 0 RED / 25 SKIP. It does not hold at HEAD, and both deltas are
explained rather than waved away:**

1. **`phase0-reconcile-gate` was red because of THIS DOCUMENT.** It requires a `Reconciles:` line
   on every spec dated ≥ 2026-08-06, and the plan had none. Self-inflicted an hour before the
   measurement. Fixed in the same commit; the gate then exits 0 over 38 specs against 132 index
   rows. It also caught a second mistake: I had written `A — why A · B — why B`, copying an
   anti-pattern from its own docstring, so only `A` was checked. The field is
   `A · B · C — prose`.
2. **`raw-sql-lint` was red on two GITIGNORED local files** — `_smoke_a2s1b2.py:51` and
   `_smoke_a2s1b2_fullchain.py:135`, neither tracked, both leftover debris in the working tree.
   **Bitten, not deduced:** moved aside → exit **0** ("no unparameterized SQL value interpolation,
   3693 files scanned"); restored byte-exact → exit **1**. Not KAL's state.

With both accounted for, KAL is **137 GREEN / 0 RED** — the claim verified rather than inherited.
`SKIP` is 23 not 25 because a stack was reachable and two live gates ran.

> **Finding worth keeping: `raw-sql-lint` scans untracked, gitignored files**, so its verdict
> depends on whose working tree it runs in. That is the same family as PR #219's gate that
> "reported its interpreter, not the tree". Not fixed here — it is not this merge's bug — but V2
> must not attribute it to the merge.

Knowledge units are **4502**, not PR #219's 4489: the suite grew. Measured, not assumed.

### B1 — FE at `168b4f318`, measured 2026-09-03

| check | result |
|---|---|
| `problem_remaining.py` | exit **0** — `problems=16 cleared=16`, `tools 65/65 proven` |
| `scripts/` suite | **18 failed, 958 passed, 1 skipped** in 744s |

The 18 matches the recorded pre-existing count exactly. **Any 19th failure after the merge is
mine.** (The background task line read "exited with code 0" because my command ended in `tail`,
which reports the pipe's exit, not pytest's — the counts are the evidence, not that line.)

### M1 + S1 + S2 — the knowledge-service half, 2026-09-03

`git merge --no-commit --no-ff` produced **23 conflicts**, exactly as the trial predicted.

**Knowledge unit suite: 4705 passed, 0 failed** (KAL baseline 4502 — the merge adds 203 tests).

**S1/S2 were pulled forward into M1, and the decision is recorded rather than deferred:**
`user_data.py:34`'s module-level dead import — predicted in §2 — blocked *collection of the whole
knowledge-service suite*, so M1 could not be verified without it. The sequence exists to serve
attribution, not to block evidence.

What the resolutions actually were:

| file | resolution |
|---|---|
| `app/mcp/server.py` | pure rename; dropped `AuthorableKind`, unused in the merged body |
| `app/db/graph_repos/facts.py` | **union** — KAL's AGE dialect + FE's three P7 functions |
| `app/db/graph_repos/relations.py` | **union** — see below |
| `app/routers/public/graph_views.py` | KAL's side; the Cypher lives in `graph_repos` now (T17) |
| `app/db/graph_repos/graph_views.py` | FE's isolated-node Cypher rehomed here |
| `app/tools/graph_schema_tools.py` | FE's feature work + KAL's paths; imports repointed |
| `tests/unit/test_graph_schema_tools.py` | **three-way** — neither branch's fake works alone |

**Four things this found that a conflict list cannot.**

1. **`coalesce($valid_until, …)` — taking either side alone loses something real.** KAL had the
   AGE dialect token but the *pre-fix* form; FE had the idempotency fix (a repeat must not rewrite
   history, measured through `memory_forget`) but `datetime()`, which stores the wrong type on
   AGE. Resolved to the union in both `facts.py` and `relations.py`. Checked the two bulk
   invalidations too — they filter `valid_until IS NULL`, so the defect cannot fire there. **No
   change made where none was needed.**
2. **A silent regression in the timeline order.** KAL's T17 move of `_TIMELINE_CYPHER` carried
   `ORDER BY coalesce(r.valid_from, 2147483647)` — **wall-clock**, the order the extractor wrote
   the edges. FE had fixed it to `coalesce(r.valid_from_ordinal, 9223372036854775807)` —
   narrative position, 64-bit sentinel. Taking KAL's file wholesale would have shipped timelines
   ordered by extraction time. Caught by FE's test, restored.
3. **A dead symbol my own grep could never have found.** `user_data.py` had a *second* broken
   import — `purge_project`, which KAL **moved** from `neo4j_helpers` to
   `graph_repos/project_graph.py`. §2 searched for two renamed *names*; a moved symbol matches
   neither. It surfaced only because the suite would not collect. **This is Phase 3's argument,
   measured: 133 gates and not one of them looks at whether an import resolves.**
4. **A guard re-anchored, then bitten.** `test_the_merge_really_bumps_version_unconditionally`
   anchored on `ON MATCH SET` and a bare assignment; KAL replaced both with `CASE WHEN existed`
   because AGE has neither `ON CREATE SET` nor `ON MATCH SET`. Behaviour preserved, anchors stale.
   Re-anchored on the CASE — then **proven still red**: making the bump conditional fails it,
   restoring passes, `git diff` byte-identical.

### M2 + M3 + M4 — the rest of the 23, 2026-09-04

Merge commit `8958c839a`, two parents, pre-commit hook run (no `--no-verify`). **0 FE commits
outstanding.**

| conflict | resolution |
|---|---|
| `glossary entity_handler.go` | **ours** — its `setEntityStatusCore` already appends the lifecycle ledger via `emitEntityStatusChangedTx`, in-transaction and with `prior_status`. Theirs inlined the INSERT. Their DQ-T1 concern is met, better. |
| `glossary migrate/ledger.go` | **renumbered** — see the commit; 70 steps, no duplicates |
| `jobs contract.py` / `routers/jobs.py` | **union** — `detail_status` suppresses every cap on an owner-lost row; `_retry_blocked` withdraws only `retry`. Different questions. |
| `composition name_grounding.py` | **ours** — its tokeniser is Unicode-aware; theirs was the Latin-1 regex that could not see Vietnamese names |
| `context-budget-defaults-lint.py` | **ported**, not picked — see below |
| `gate-teeth-gate.py` | 1,2 ours · 3 **theirs** (the red-ability sweep reader) |
| `docs/standards/README.md` | **a mix** — our Multilingual row (carries main's new i18n gate) + THEIR Artifact Language row, which points at `AGENTS.md`; ours pointed at `CLAUDE.md`, which says of itself it is "a pointer, deliberately kept empty of rules" |
| `.gitignore`, `DEFERRED.md` | union — both are additive registers |
| `docker-compose.yml`, `foundation-ci.yml`, `llm-budget-ssot-gate.py`, `goal-prompt.md` | ours; each is the superset or the corrected version |
| `SESSION_HANDOFF.md` | PR #219's own convention — live section kept, theirs preserved verbatim as history |

**The `Reconciles:` line predicted one of these.** The standards index cited
`contracts/frontend-tools.contract.json` as the Frontend-Tool Contract's SoT, and this merge
renames it. Zero references to the dead path remain; two point at `browser-tools.contract.json`.

**A defect neither branch had.** `scan_file` and `scan_go_file` both recorded a subject only
*after* the ALLOW check, so an exempted tool was never counted — and the shrink arm, which calls
a row dead when no scanned tool bears its name, declared **ten live exemptions deletable**. The
tempting fix was to delete ten live exemptions. Latent here (no row named a selectorless tool),
exposed by their nine Go-service rows. Fixed in both halves; subjects **8 → 39**. Bitten: remove
the one line and the gate goes red with 10 dead-row findings, restore it and it exits 0.

**A ratchet moved, with the reason written in.** `NO_PROOF_BASELINE` 4 → 5 for
`scripts/toolloop/t_derivative_gate_probe.py`, which is not a gate — it is a live MCP probe that
matches the sweep only because "gate" is in its filename. The baseline moved rather than the
discovery narrowing, because excluding by name pattern would let a real gate escape.

### G1 — the import-resolution gate, 2026-09-04

`scripts/import-resolution-gate.py`. Every in-repo `from app.… import …` must resolve to a
module **and** a name, read from the AST, function-level imports included — which is the point,
since the defect that motivated it is one.

**Proven RED on both original instances, then restored byte-exact:**

```
executor.py:632:  no module `app.db.neo4j_repos.facts` under services/knowledge-service/app
user_data.py:35:  `app.db.neo4j_helpers` has no `purge_project`
```

The first is FE's P7 chokepoint. The second is the case a grep cannot reach: a symbol that
**moved** while both modules kept existing, so the module resolves and the line reads ordinary.

**Its first run over the tree found a defect in itself and one in the repo.**

- *In itself:* `fleiss_kappa, kappa_interpretation = _resolve()` binds two names by tuple
  unpacking, and reading only `ast.Name` targets reported a module that exports them as
  exporting neither. Fixed, plus a literal `__all__` is now trusted as the module's own
  assertion of what it provides.
- *In the repo:* `backfill_entity_alias_map.py:138` imported `init_knowledge_pool`, which has
  **never existed** — `app.db.pool` provides `create_pools`, which is what `app/main.py:179`
  calls. That CLI entry point could not have run since it was written, and its own docstring
  says no test covers it. Fixed at the call site rather than baselined.

Now **1076 files across 10 services, every import resolving, `BASELINE = 0`.** Wired into
`foundation-ci.yml` rather than only the hook: the hook is opt-in per checkout, and the defect
arrives through a merge — exactly when nobody is looking. `gate-teeth` counts it, 145 CI-invoked
gates with 140 proven; `gate-wiring-gate` 187 discovered, all wired or exempt.

### V1 — the twelve invariants re-proved on the merged tree, 2026-09-04

**By the suites, not the board.** `problem_remaining.py` exits 0 — and would have exited 0 with
P7 broken, because it reads contracts rather than code. That is why it is not the bar.

| bar | result |
|---|---|
| `test_no_turn_guard_is_defined_and_never_called.py` | **9 passed** — all eight end-of-turn guards still *called*, plus the arm that keeps the list honest |
| chat-service suite (whole) | **3911 passed, 7 skipped, 0 failed** |
| knowledge-service units (whole) | **4705 passed, 0 failed** (KAL baseline 4502) |
| `problem_remaining.py` | exit 0 — `problems=16 cleared=16`, `tools 65/65 proven` |

`stream_service.py` is **14495** lines on the merged tree — FE's 14490 plus main's additions —
and `app/agentruntime/` has its 20 modules. The centre of gravity landed intact, as §0 predicted.

### V3 — the i18n gate, predicted red and red, 2026-09-04

§5's prediction was exact. `i18n-key-resolution-gate` failed on **7 keys**, five of them from
FE's new `DisambiguationCard.tsx` and two from its edit to `DefaultModelsCard.tsx` — components
written before main's gate existed, in a branch that touched no bundle.

Fixed the way the standard says, not the way that would have been quicker:

1. The 7 `en` entries were added **verbatim from the `defaultValue` at each call site**, so the
   string a reader sees is the string the code already had. Key-resolution then passed:
   6509 literal keys resolve.
2. That broke `i18n-completeness-gate` — 38 gaps, because `en` gained keys 19 locales lacked.
   The standard forbids hand-editing those (*"never hand-edited, never a one-off translator"*),
   so the gap-fill ran through `scripts/i18n_translate.py`.
3. **`$0`.** That script targets LM Studio at `localhost:1234`; no cloud call was made.
   34 namespaces written, 0 skipped, **0 keys needing review**.

Both gates now green: key-resolution OK, completeness OK at *"20 locale-dirs x 37 namespaces at
full `en` parity"*.

### What B0 refuted

Counting KAL's non-rename churn per file **killed this plan's own Class A rule** for three of its
five files — see §1.1, corrected. `facts.py` (357 lines) and `relations.py` (394) are AGE dialect
work, not a rename, and taking FE's content there would ship Cypher the default engine cannot
compile. The rule now inverts for those two.

---

```goal-prompt
goal: one reconciled branch whose merge broke nothing it cannot name
po_decisions: [R1]
rules: |
  1 Baseline BOTH sides BEFORE merging. A red thing you cannot attribute gets fixed on the wrong branch.
  2 A green suite after this merge is NOT evidence. The trial merge was clean and shipped a dead P7 AND a dead P7 falsifier.
  3 problem_remaining.py reads CONTRACTS, not code — it exits 0 with P7 broken. The owning SUITE is the bar.
  4 Class A is a rule, not a judgement: FE's content, KAL's rename (neo4j_repos->graph_repos, neo4j_session->graph_session).
  5 Never --no-verify. PR #219 records its own coming due as three gates red at HEAD that --run-all had never seen.
  6 A gate's baseline moves in the SAME COMMIT as the code that moved it, and every count is re-derived.
  7 Prove the import gate RED on executor.py:632 before trusting it green.
  8 Leave the 19 cosmetic neo4j_* identifier mentions alone. A diff nobody asked for hides the 7 that matter.
  9 Anything that WRITES goes to a throwaway database, never the dogfood book.
discipline: |
  NO "BLOCKED" meaning "I would have to build it". Decide it, write the decision down, keep going.
  Commit every row, and tick the box in the commit that does the work.
  A gate you disabled is a gate that failed. Record near-misses as they happen.
stop: |
  a resolution needs a design decision neither branch's docs answer
  the import gate cannot be made red on executor.py:632
  KNOWLEDGE_GRAPH_BACKEND would regain a default in docker-compose.yml
note: |
  The 23 conflicts are the easy part. FIVE files merge CLEAN and broken, and executor.py:632 is
  FE's own P7 chokepoint with its own falsifier breaking at import beside it.
```

**RESUME: B0 — baseline KAL before touching anything, so every later red can be attributed**

