# Detailed Design — C12 (target-typed extraction) + C13 (glossary pinning)

**Date:** 2026-06-13 · **Purpose:** de-risk the two highest-risk knowledge cycles by designing them in full
*before* the RAID run, so the autonomous cycle executes a known design instead of discovering the SDK
architecture mid-flight. Code-grounded (file:line verified).

> **Net effect of this design pass:** C12 drops from "XL/SDK-rewrite" to **L (well-bounded)** — the SDK already
> dispatches separable extractors via `asyncio.gather`; selective invocation is a conditional task-list, not a
> rewrite. C13 is **M–L** with one genuinely new piece (a glossary stats endpoint for auto-pin).

---

## C12 — Target-typed extraction (`targets: [entities|relations|events|facts|summaries]`)

### Concept
Let a build job extract only a chosen subset of passes instead of always all. Default (unset) = all (backward
compatible). Entity extraction is a **prerequisite** for relations/events/facts (they anchor to entity names).

### The key realisation (de-risks the cycle)
Extraction is monolithic *by default*, but the underlying extractors are already separable: the SDK
`extract_pass2` runs `extract_entities` then `asyncio.gather(extract_relations, extract_events, extract_facts)`
(`sdks/python/loreweave_extraction/pass2.py:136–172`), and the orchestrator mirrors this
(`pass2_orchestrator.py:833–954`). **Selective invocation = build the gather task-list conditionally.** No
extractor internals change.

### Touch-points — (A) additive
| File:line | Change |
|---|---|
| `extraction.py:163` `StartJobRequest` | add `targets: list[Literal[...]] \| None = None` |
| `db/migrate.py` (extraction_jobs) | `ADD COLUMN targets TEXT[] NOT NULL DEFAULT ARRAY['entities','relations','events','facts','summaries']` |
| `repositories/extraction_jobs.py` (`ExtractionJobCreate`/`ExtractionJob`/`_SELECT_COLS`/INSERT) | thread `targets` |
| `pass2.py` SDK `extract_pass2(...)` | add `targets: set[...] \| None = None` |
| `pass2_orchestrator.py` (`_run_pipeline`, `extract_pass2_chapter`) | add `targets` param, thread to SDK |
| `worker-ai/app/runner.py:1261` | read `targets` from job row → pass to `extract_pass2` (minus `summaries`) |
| `worker-ai/app/decoupled_extract.py` (`new_extract_state`, `assemble_trio_submits`) | store + honor `targets` |

### Touch-points — (B) the real logic (localized, ~4 sites)
1. **SDK `pass2.py:136–172`** — wrap entity in `if "entity" in targets`; build the R/E/F gather task-list
   conditionally + zip results back. (≈20 lines)
2. **Orchestrator `pass2_orchestrator.py:833–954`** — same conditional pattern at the orchestrator's own
   gather; gate the no-entity short-circuit.
3. **Summaries `pass2_orchestrator.py:1058`** — add `and "summaries" in targets` to the enqueue condition.
4. **Decoupled `decoupled_extract.py:64,283`** — `apply_entity_result` advances to TRIO only if R/E/F in
   targets; `assemble_trio_submits` builds the submit-dict conditionally. (The trio fan-in already tolerates a
   partial op set — no state-machine change.)

### Locked design decisions
- **[LOCK] Dependency auto-include:** if any of {relations, events, facts} is requested, **entities is forced
  into targets** (don't error — silently include). Encoded once in `StartJobRequest` validation + as an SDK guard.
- **[LOCK] Recovery/filter auto-disable when entities skipped:** `entity_recovery`/`precision_filter` are no-ops
  with no entity set → disable them when `entities ∉ targets`.
- **[LOCK] `targets` storage = `TEXT[]` column, default all.** Null/empty in the request → all (back-compat).
- **[LOCK] Target taxonomy → SDK ops:** `entities·relations·events·facts` map 1:1 to SDK extractors; `lore/wiki`
  target = the wiki-stub generation path (out-of-SDK, orchestrator-gated); `summaries` = the summary enqueue
  (orchestrator-gated, not an SDK op). The FE picker's "events·timeline" label = the `events` op.
- **[LOCK] `concurrency_level`** = a passthrough param to the existing gather (caps parallel LLM calls); default
  current behavior. Additive.

### Test plan
- Unit (SDK): `targets={entities}` → only entities; `{entities,events}` → entities+events, no relations/facts;
  `{relations}` → auto-includes entities; empty → all.
- Unit (orchestrator): summaries gated; recovery/filter disabled when no entities.
- **Live smoke:** start a job with `targets=["events"]` on a real project → only the event pass runs (assert
  via job logs + that relations/facts tables are untouched).

### Size: **L** (well-bounded; ~4 logic sites + additive threading + tests). Not XL.

---

## C13 — Glossary pinning (force-inject entities into every extraction window)

### Concept
Pin a chosen set of glossary entities so they're injected into the `known_entities` prompt context of **every**
extraction window, regardless of whether they appear in that chapter — so sparse-but-critical entities (a god
in ch1 & ch5000) are always anchored.

### Knowledge-service path — ADDITIVE (the easy half)
`known_entities` is already a variable threaded into every window's `extract_entities` call
(`pass2_orchestrator.py:845`) and into the prompt template (`entity_extraction_system.md:17–23` `{known_entities}`).
**Pinning = prepend the pinned names to `known_entities` at each `_run_pipeline` call site** (`:1200`, `:1264`).
- Add `pinned_glossary_entity_ids: list[str]` to `StartJobRequest` (`extraction.py:163`).
- `extraction_jobs` migration: `ADD COLUMN pinned_entity_ids JSONB`.
- At job start, fetch the pinned entities via the existing `glossary_client.fetch_entities_by_ids(...)`
  (`knowledge-service/.../glossary_client.py:403`); pass `pinned_names` as a prefix into every window.

### Worker-ai path — THE GAP (bounded)
`worker-ai/app/runner.py:1263` hardcodes `known_entities=[]` ("worker-ai has no glossary access"). But worker-ai
**already imports `GlossaryClient`** (used for `glossary_sync`, `clients.py:722`) — it just lacks a
batch-fetch-by-ids method.
- **[LOCK]** Add `GlossaryClient.fetch_entities_by_ids(book_id, entity_ids)` to worker-ai (mirror the
  knowledge-service method; same `X-Internal-Token`, no new secret).
- Read `pinned_entity_ids` from the job row → fetch names → replace the `[]` at `runner.py:1263`.

### Auto-pin heuristic — needs ONE new endpoint
The "sparse-but-long-reaching" auto-suggestion needs **mention_count + first/last chapter span**, which
`glossary_client.list_entities` does NOT expose. The data exists in glossary's `chapter_entity_links`
(chapter_id per entity).
- **[LOCK]** New glossary endpoint `GET /internal/books/{book_id}/entities/stats` → aggregates
  `chapter_entity_links`: `{entity_id, name, kind, mention_count (≈link count), first_chapter_index,
  last_chapter_index, coverage_pct}`. Bounded GROUP-BY query.
- Heuristic (FE or BE): pin-suggest where `coverage_pct ≤ 0.15` (sparse) AND `span ≥ 0.5×chapter_count`
  (long-reaching). Thresholds tunable.

### Cost model
`extraction.py:250` estimate: add `pinned_count × ~50 tokens × num_windows` as its own line (the design's
"pinned context injection" cost — it's the dominant driver and must be visible).

### FE (dual-list)
The Step-2 dual-list (available ↔ pinned) with search/type/frequency filters + auto-pin suggestion banner +
per-window token budget. Reuses the existing entity-list patterns; the pinned set posts as
`pinned_glossary_entity_ids`.

### Locked design decisions
- **[LOCK] Pinning is name-prefix injection** into `known_entities` (not a separate prompt block) — reuses the
  proven seam, additive on the knowledge path.
- **[LOCK] Worker-ai gets a `fetch_entities_by_ids` method** (the only new BE dependency; client already wired).
- **[LOCK] Auto-pin ships in C13** via the new glossary stats endpoint (it's the design's headline; manual
  pinning alone is half the value). Bounded glossary-service GROUP-BY.
- **[LOCK] Storage = `pinned_entity_ids JSONB`, default null.** Back-compat.

### Test plan
- Unit (knowledge): pinned names appear in `known_entities` for a window whose chapter text does NOT mention them.
- Unit (worker-ai): `fetch_entities_by_ids` returns names; `known_entities` no longer empty when pinned set present.
- Unit (glossary): stats endpoint returns correct span/coverage on a fixture book.
- **Live smoke:** build with 2 pinned entities absent from chapter N → confirm both appear in chapter N's
  extraction prompt (wire-capture or log assert).

### Size: **M–L** (knowledge additive S; worker-ai client M; glossary stats endpoint S; auto-pin + cost + dual-list FE M).

---

## Sequencing note
C12 and C13 are independent and can be built in either order, but the wizard FE shell (Step 1 target picker /
Step 2 pinning / Step 3 budget) is shared — build the shell in C12, add the Step-2 dual-list in C13. Both depend
only on C5 (build-gate unblock). The `loreweave_extraction` SDK change in C12 is the one cross-package edit —
keep it backward-compatible (`targets=None` ⇒ current behavior) so translation-service and other SDK consumers
are unaffected.
