# LORE BIBLE (`G-S3`) — RUN-STATE

**Opened 2026-08-13** · branch `feat/game-logic` · opened at HEAD `8479a7606`

**Reconciles:** Two-layer glossary↔knowledge · Data & Logic Scope Separation · Reading/writing
entity or KG knowledge · Declared size **`LIM-1`** — a reality declares its own ceilings — and what
the look found, all measured:

* **`lore-enrichment-service` ALREADY IMPLEMENTS THE SWEEP.** 252 Python files, shipping
  `enrichment_job` · `enrichment_proposal` · `enrichment_book_profile` · `enrichment_template` ·
  `enrichment_compose_task`, a glossary client, a **writeback** path, and a proposals review queue
  with `approved`/`rejected`. That is structurally what `07_lore_bible.md` describes — sweep the
  corpus, produce per-entity decisions, let a human adjudicate. **The pipeline is not the gap.**
* **So `G-S3`'s real gap is the AGGREGATION LAYER above it**, and it is exactly the part
  `07_lore_bible.md` argues is computable: `BTG-A19`'s invariant/instance reduction (5,431 entity
  decisions → ~200 lore statements), the `kg_edge_types` frequency/fan-out read that recovers a
  *system* from edges (*"812 `BREAKS_THROUGH_TO` over 40 subjects → 9 objects"*), and the CUTOFF
  (`spoiler_window` / `before_chapter_id`) that makes a bible describe a world at a moment rather
  than one that existed at none. **None of those three has a producer** — measured, `lore_bible`
  occurs 0 times in `crates/ services/ contracts/ scripts/`.
* **No conflict with a sealed decision, but a hard CONSTRAINT.**
  `contracts/ruleset/authorable-surface.v1.yaml` states what the engine accepts — 8 patch types,
  72 keys, `deny_unknown_fields`, unknown keys REFUSED — and says of itself: *"It does not decide
  what SHOULD be authorable. It states what IS, so that the manifest builder `S4`/`S8` need has an
  input that cannot quietly go stale."* A bible whose output has no path into those 72 keys would
  be `S8`'s parked lesson repeating one tier up. **`LB1`'s schema is therefore written against the
  authorable surface, not invented beside it.**
* **§C is not in the field above** because §C is prose in the index, not a table row, and the gate
  resolves table rows. Naming it would be a reference pointing at nothing.

> This file is the commitment. `/goal` holds the session open; **this file holds the work.**
> After any compaction, re-read `§0` FIRST, then `git log`, then continue. Never re-litigate a
> sealed decision from memory — re-read it here.

---

## 0 · HOW TO WORK — BINDING

### 0.1 The execution contract

Adopts **§0.6d of [`2026-08-08-reality-layer-RUN-STATE.md`](2026-08-08-reality-layer-RUN-STATE.md)**
unchanged. That file also holds §0.6c (sealed forks) and §5 (`BDR-57`..`BDR-90`). Read it before
the first batch.

### 0.2 The target, and what is actually true today

`docs/MILESTONE.md` records `G-S3` as **design only**. Measured 2026-08-13:

| claim | measured | command |
|---|---|---|
| 17 design documents | **17** | `ls docs/03_planning/BOOK_TO_GAME/*.md \| wc -l` |
| zero code | **0 producers** | `git grep -lic "lore.bible\|lore_bible" -- crates/ services/ contracts/ scripts/` |

**But the design is NOT speculative — it rests on infrastructure that exists.**
[`07_lore_bible.md`](../03_planning/BOOK_TO_GAME/07_lore_bible.md) states `BTG-A19` —
*"a Lore Bible records the world's INVARIANTS; the book records its INSTANCES"* — and argues the
reduction is **computable** from typed data the platform already produces. Verified, all five:

| mechanism | files | first hit |
|---|---|---|
| `kg_edge_types` (49 typed edge types) | 13 | `knowledge-service/app/db/migrate.py` |
| `spoiler_window` | 8 | `knowledge-service/app/db/neo4j_repos/temporal.py` |
| `resolve_before_order` | 8 | `knowledge-service/app/routers/public/entities.py` |
| `before_chapter_id` | 12 | `agent-registry-service/internal/migrate/migrate.go` |
| `glossary_entities` | 156 | — |

So the gap is **schema + producer**, not foundations. That distinction is the whole reason this is
buildable now and not a research task.

### 0.3 `LB0` IS PHASE 0, IT COMES FIRST, AND IT MAY REWRITE THE REST

Seventeen documents have never been reconciled against the LLM_MMO_RPG tier's 25 LOCKED data-plane
documents or [the standards index](../standards/README.md). `phase0-reconcile-gate` refuses a commit
whose spec carries no `Reconciles:` line naming **real index rows** — and it resolves on the FIRST
CELL of an index table row, so a row that is prose (§C) cannot be named.

Answer all three questions **with commands, not memory**:

1. **What already models this?** A lore bible, a world-invariant record, an authored-canon artifact.
   `BTG-*` ids, the glossary two-layer pattern, `contracts/ruleset/authorable-surface.v1.yaml`.
2. **Does it have a PRODUCER?** Measured above: no. Confirm per candidate artifact, not in general.
3. **Does it CONFLICT with a sealed decision?** The one to check hardest — `authorable-surface.v1.yaml`
   already declares what the engine will accept, and a bible that emits a shape the engine refuses is
   `S8`'s parked lesson repeating one tier up.

**If Phase 0 changes the plan, change the plan and record why.** On the last run Phase 0 killed two
queued items on turn one. With 17 unreconciled documents, expect more. That is the batch succeeding.

### 0.4 Per batch, in order

1. State what is being built in one sentence, **from the document**, not from memory.
2. Measure the subject before writing anything.
3. Build the smallest thing that is real — a schema someone can validate against, a producer that
   emits one true row.
4. **Bite it**: GREEN → mutate ONE side → genuine RED → restore **byte-exact** → GREEN. Paste it.
5. Update this board with the evidence string.

### 0.5 A STRING THAT LOOKS LIKE A SUBJECT IS NOT THE SUBJECT

The single lesson of the two runs before this one, five separate instances: a word in an unrelated
README · a symbol inside the oracle that counts it at zero · a `DetRng` from another crate · a doc
comment saying *"unbuilt"* · a document's own filename. Each read as evidence that something exists.

- Measure **existence** in code with comments **stripped**.
- Measure **citation** with comments **counted** — the convention IS a comment beside the guard.
- Never conflate them, and say which one a given check is doing.

**Any new gate ships a `--self-test` AND mutation rows in `gate-bite-harness` in the same commit.**
Bites that live only in a transcript are a defect this project has already paid for twice.

### 0.6 Hazards — every one of these has bitten

- Run any sweep **DETACHED**; read the process's **REAL** exit code, never a task notification's.
- **Edit nothing while a sweep runs.** If one is killed, verify by hand that nothing was stranded.
- **Byte-level I/O**, and read CRLF **from the bytes** rather than assuming it.
- **NEVER use a heredoc for a patch containing backslashes** — it ate them **seven times** in one
  session. Write the patch to a file with the Write tool.
- A non-ASCII byte in a `b"..."` literal is a `SyntaxError`.
- **Never hand bash an absolute Windows path** (backslashes eaten, `rc=127`). Repo-relative.
- `-F <file>` for commit messages. `cargo test --workspace` needs **`-j 4`**.
- `set -euo pipefail` kills a script at a failing substitution **before a guard below can speak**.
- Every board edit uses an **asserted anchor** (`assert count == 1`), never a bare `str.replace`.

### 0.7 Do not stop

A batch finishing, a commit, a green sweep, a POST-REVIEW and an empty turn are **not** stop
conditions. If something genuinely cannot be built, record it in `§4` with what would settle it and
move on. **Commit and push after each batch; report at most once per batch.**

### 0.8 A note on scope honesty

`G-S3` is a *design-and-build* task, not a sweep. The temptation is to produce documents. **A
document is not the deliverable** — a schema something validates against and a producer that emits a
real row are. If a batch ends with only prose, it has not closed.

### 0.9 DONE

All of the following, or 45 turns, whichever comes first:

- [ ] `LB0` closed — Phase 0 answered with commands, `Reconciles:` line naming real index rows,
      `phase0-reconcile-gate` **green with its exit code pasted**
- [ ] `LB1` closed — the lore-bible **schema** exists as a contract artifact, and something
      **machine-checks** a document against it
- [ ] `LB2` closed — a **producer** exists and has emitted at least one real row from real data,
      with the output pasted
- [ ] `LB3` closed — the `§9` **floor** is countable (*"every glossary entity decided or explicitly
      deferred"*), and its gate ships with a `--self-test` **and** mutation rows, all red
- [ ] `cargo test --workspace -j 4` — **real exit code pasted**
- [ ] detached `gate-wiring-gate --run-all` — **real exit code pasted**

> **Claiming a check passed without pasting its output does NOT satisfy this condition.** The `/goal`
> evaluator reads the transcript and cannot run commands; it enforces persistence, not honesty.

---

## 1 · THE BOARD

| batch | subject | state |
|---|---|---|
| ~~`LB0`~~ | Phase 0 reconcile | ✅ **CLOSED, and it narrowed the run.** The sweep pipeline already ships in `lore-enrichment-service`; the gap is the aggregation layer above it. `LB1` is now written against `authorable-surface.v1.yaml` rather than inventing a shape |
| `LB1` | the SCHEMA: a lore-bible **section** — an invariant statement, its evidence, its cutoff — machine-checkable, and shaped so it can reach the engine's 72 authorable keys | ⬜ |
| `LB2` | the PRODUCER: the `§5`/`§6` aggregate — edge-type frequency and fan-out over the DECIDED entities `lore-enrichment` already produces, at a cutoff. **Consumes that service, does not re-implement it** | ⬜ |
| `LB3` | the FLOOR: `§9`'s countable completion number, gated and bitten | ⬜ |

**`LB1`–`LB3` were provisional and `LB0` revised them**, which is the batch working. The original `LB2` said *"aggregate over glossary + kg_edge_types"* as though from scratch; the sweep it implied is a shipped service, and re-implementing it would have been the orphan shape `Phase 0` exists to prevent.

---

## 2 · CARRIED IN

| id | what | source |
|---|---|---|
| `G-S4` | the pre-manifest stub is **not a named artifact anywhere in the repo**. Adjacent to this work and probably clarified by it; not this run's deliverable | `MILESTONE.md` |
| `DPD-6` | the standards index says `DP-Ch1–Ch37`; the docs declare `Ch1..Ch53`. 16 ids read as ungoverned | data-plane run-state §5 |

---

## 3 · CLOSED

*(nothing yet)*

---

## 4 · OPEN ROWS — each must carry a MECHANISM, not prose

| id | what | mechanism / what would settle it |
|---|---|---|

---

## 5 · DRIFT REGISTER

**A run that ends with an empty drift log is not clean — it is dishonest.**

| id | what happened |
|---|---|
| `LBD-1` | **Phase 0 found a 252-file service doing the thing I was about to plan.** `MILESTONE.md` records `G-S3` as *"17 docs, zero code"*, which is true of the lore-bible ARTIFACT and misleading about the work: `lore-enrichment-service` already sweeps the corpus, emits per-entity proposals, takes an approve/reject decision and writes back to glossary. Had I read *"zero code"* as *"nothing exists"* — the obvious reading — `LB2` would have rebuilt a shipped pipeline. The gap is one layer up: nothing turns DECIDED ENTITIES into WORLD INVARIANTS. |
