# Reconciling `feat/frontend-tools-mcp-migration` into `refactor/kal-and-mcp-runtime`

**Written:** 2026-09-03 · **Target:** `refactor/kal-and-mcp-runtime` @ `87690ed98` (PR #219)
· **Source:** `feat/frontend-tools-mcp-migration` @ `168b4f318`

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

**Class A — mechanical: take FE's content, apply KAL's rename (5 files).** KAL renamed
`app/db/neo4j_repos/` to `app/db/graph_repos/` (14 files, R100..R061) and `neo4j_session()` to
`graph_session()` so Apache AGE can replace Neo4j. Its edits to the MCP surface are almost
entirely that sweep — verified on `mcp/server.py`, `reader_tools.py`, `project_tools.py`. FE's
edits are MCP v2 feature work. **Orthogonal reasons, same lines. Not a design decision.**

```
services/knowledge-service/app/mcp/server.py                    KAL 5/5    FE 514/54
services/knowledge-service/app/tools/graph_schema_tools.py      KAL 32/31  FE 426/38
services/knowledge-service/app/routers/public/graph_views.py    KAL 14/60  FE 75/11
services/knowledge-service/app/db/graph_repos/facts.py          rename/modify
services/knowledge-service/app/db/graph_repos/relations.py      rename/modify
```

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

- [ ] **B0** — baseline KAL: `gate-wiring-gate --run-all`, gate self-tests **bare and
  `--selftest`**, knowledge units, `book-service go build`, `eventgen-validate`. Verify PR #219's
  137/0/25 and 149; do not inherit the claim. (§3 Phase 0)
- [ ] **B1** — baseline FE: `problem_remaining.py` exits 0, and the `scripts/` suite's **18**
  pre-existing failures. This is the attribution baseline. (§3 Phase 0)
- [ ] **M1** — merge `--no-commit`; resolve **Class A**, the 5 mechanical files, by rule: FE's
  content, KAL's rename. (§1.1)
- [ ] **M2** — resolve **Class B**, the 6 two-sided files. `ledger.go` by reading the ledger,
  never by taking a side. (§1.1, §4.3)
- [ ] **M3** — resolve **Class C**, the 5 gate/CI files: union of the bars, every count
  re-derived. `docker-compose.yml` is three-way and must not regain a backend default. (§1.1, §4.2)
- [ ] **M4** — resolve **Class D**, the 7 prose/config files, including the `goal-prompt.md`
  add/add. Commit the merge **without** `--no-verify`. (§1.1)
- [ ] **S1** — fix the **5 silent hard-break** files, `executor.py:632` first — FE's P7
  chokepoint. (§2, §2.1)
- [ ] **S2** — re-point the **2 source-substring assertions**; leave the 19 cosmetic mentions
  alone. (§2.2)
- [ ] **G1** — build the **import-resolution gate**: every `from app.X import Y` resolves.
  Proven RED on `executor.py:632` before green. None of the repo's 133 gates catches this. (§3 Phase 3)
- [ ] **V1** — re-prove the twelve invariants against the merged tree via the **owning suites**,
  not the board, plus the guard-is-called AST gate. (§3 Phase 3)
- [ ] **V2** — KAL's 133 gates over FE's ~2000 files. Attribute every red against B0/B1 before
  changing anything. (§3 Phase 4)
- [ ] **V3** — main's i18n key-resolution gate vs FE's frontend: 52 `t()` calls, zero bundle
  changes. Predicted red. (§3 Phase 4)
- [ ] **V4** — a live run through the real stack. A 502 route is invisible to both boards. (§3 Phase 4)
- [ ] **R1** — **STOP CONDITION** — §4.1: rename `app/db/neo4j.py`, still named for one engine,
  or record it as a named follow-up. Owner's decision; mechanical now, worse per caller. (§4.1)

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

