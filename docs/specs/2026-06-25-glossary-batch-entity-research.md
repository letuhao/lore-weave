# Spec — Batch entity-research job (glossary-service)

**Status:** M1 SHIPPED · 2026-06-25 · branch `feat/composition-service`

> **BUILD REFINEMENT (M1):** provider-registry's BYOK web-search returns **no per-call cost**
> (the user's provider bills them; LoreWeave doesn't meter it like LLM tokens). So the spec's
> per-search `max_spend_usd` cap is **unmeasurable** and was replaced by a **`max_entities`** cap
> (each entity = 1 paid search → cost is bounded upfront). `est_cost_usd` is an **indicative**
> display estimate (`items_total × webSearchEstUSDPerQuery`), never a billing/budget driver — no
> silent seam pretending we meter a cost we can't see. This **drops the `paused_budget` state**:
> the job's scope *is* the entity cap, so it runs to completion / `paused_user` / `cancelled` /
> `failed`. A `researchJobMaxEntitiesHardCap=500` is the runaway backstop. Sections below that say
> `max_spend_usd` / `paused_budget` are superseded by this note.

**Origin:** Plan-action Phase-2 "research-orchestration" item. A scout found that wiring it as
a **synchronous plan op** (the `glossary_plan` executor) is the wrong vehicle; the user chose an
**async batch-research job** instead. This spec resolves the architecture + lifecycle so the build
is a straight execution.

---

## 1. Why not a plan op (the rejected approach)

`glossary_plan` → `execute_plan` runs `loreweave_mcp.Execute` **synchronously inside the confirm
HTTP request** ([plan_confirm.go](../../services/glossary-service/internal/api/plan_confirm.go) `effectExecutePlan`).
Three hard mismatches with deep-research over a whole kind:

1. **Long-running paid fan-out.** `descDeepResearch` is ONE paid web search per entity
   ([pipeline_deep_research.go](../../services/glossary-service/internal/api/pipeline_deep_research.go)).
   A kind with N entities = N searches, each seconds long → a minutes-long synchronous request,
   timeout-prone, no progress, no cancel.
2. **Summarizer mismatch.** Deep-research is deliberately *"glossary attaches sourced evidence →
   **the chat agent** reads the sources and proposes the description edit via
   `glossary_propose_entity_edit`"*. The deterministic plan executor has **no agent in the loop**,
   so a plan op could only do the evidence-gathering half.
3. **Idempotency + cost.** The kit requires idempotent ops; one confirm would authorize N paid
   searches with no per-search cost ceiling.

An async **job** solves all three: progress/cancel, a `max_spend` ceiling enforced per-search, and
a clean "gather evidence now, enrich later" decoupling (summarization stays the agent's job, run
afterward over the freshly-attached evidence).

## 2. Where it lives — glossary-service (NOT a knowledge proxy)

The wiki-gen job is a **proxy**: glossary forwards lifecycle to knowledge-service's job framework
([wiki_jobs.go](../../services/glossary-service/internal/api/wiki_jobs.go)). Batch-research is
**different** — its unit of work is *glossary-owned*: it reads `glossary_entities` of a kind, calls
the user's BYOK web-search via provider-registry, neutralizes results (INV-6), and attaches
`reference` evidence to `entity_attribute_values`. Knowledge-service owns none of that. So the job
**lives in glossary-service**, which already runs in-process background consumers
(`internal/events/*` — staleness/grant/revision), establishing the background-worker pattern. The
job-state machine is **modeled on** knowledge's proven extraction-job design (the one the wiki
feature reused), not proxied to it.

## 3. Data model — `entity_research_jobs` (new table, glossary DB)

Forward-only migration in [migrate.go](../../services/glossary-service/internal/migrate/migrate.go).
Tenancy: per-book, owner + grantees (E0), scope key `book_id` + `owner_user_id`.

```sql
CREATE TABLE entity_research_jobs (
  job_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id         uuid NOT NULL,
  owner_user_id   uuid NOT NULL,         -- who confirmed + pays (BYOK)
  kind_id         uuid NOT NULL,         -- book_kinds.book_kind_id — the scope
  query_template  text NOT NULL,         -- per-entity query, "{name}" substituted
  max_results     int  NOT NULL DEFAULT 5,   -- per-entity sources (clampDeepResearchMax)
  max_spend_usd   numeric(10,4) NOT NULL,    -- HARD ceiling; pause when hit
  status          text NOT NULL DEFAULT 'pending',  -- see §4
  items_total     int  NOT NULL DEFAULT 0,
  items_processed int  NOT NULL DEFAULT 0,
  sources_attached int NOT NULL DEFAULT 0,
  cost_spent_usd  numeric(10,4) NOT NULL DEFAULT 0,
  cursor_entity_id uuid,                 -- resume point (last completed entity)
  error_message   text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  completed_at    timestamptz
);
-- One LIVE job per (book, kind) so two runs can't double-bill the same entities.
CREATE UNIQUE INDEX entity_research_jobs_one_live
  ON entity_research_jobs (book_id, kind_id)
  WHERE status IN ('pending','running','paused_budget','paused_user');
```

**Idempotency / no double-spend across runs:** the worker skips an entity that already carries a
`reference` evidence row whose `block_or_line` (the source URL) was attached by *this* feature —
reusing `referenceEvidenceExists`-style dedup. Net effect: re-running a job over a kind only
researches the entities not yet researched. (Tunable: a `force` flag to re-research, default off.)

## 4. Lifecycle (subset of knowledge's state machine — only what we need)

```
pending ──drive──▶ running ──┬─ all items done ─────▶ complete
                             ├─ cost ≥ max_spend ───▶ paused_budget ──resume(raise cap)──▶ running
                             ├─ user pause ─────────▶ paused_user    ──resume──────────────▶ running
                             ├─ web-search error ───▶ failed (error_message; retryable)
                             └─ user cancel ────────▶ cancelled
```

- **Cost ceiling is enforced per-search**, BEFORE each outward call: if `cost_spent + next_est >
  max_spend` → `paused_budget` (never overshoot). Mirrors the knowledge extraction job's budget pause.
- **Crash-safety:** `cursor_entity_id` + `items_processed` let a restarted worker resume from the
  last completed entity. Entities are ordered by a stable key (entity_id) so the cursor is total.
- Cost metering rides the existing `record_spending` path (per-search, best-effort, non-blocking).

## 5. Worker

In-process goroutine + a claim/lease pattern (a `running` row older than a lease TTL is reclaimable —
single-replica today, but lease-safe for scale). Loop per claimed job:
1. Resolve entities of `kind_id` in the book (live, ordered by entity_id, after `cursor_entity_id`).
2. For each: skip-if-already-researched → budget pre-check → `webSearch(owner_user_id, query, max)`
   (BYOK, caller-paid) → neutralize (INV-6) → attach top sources as DRAFT `reference` evidence
   (reusing the `effectDeepResearch` inner loop, extracted into a shared `researchOneEntity` core) →
   `record_spending` → advance cursor + counters in one tx.
3. Terminal: `complete` (cursor exhausted) / `paused_budget` / `failed`.

**Refactor:** extract the per-entity body of `effectDeepResearch` into `researchOneEntity(ctx,
userID, bookID, entityID, query, max) (sourcesAttached int, costUSD float64, err error)` so BOTH
the existing synchronous `glossary_deep_research` confirm AND the batch worker call the same core
(no logic fork, INV-6 neutralization in one place).

## 6. API (public, under the book context — owner/grant gated)

| Method | Route | Purpose | Grant |
|---|---|---|---|
| POST | `/v1/glossary/books/{book_id}/kinds/{kind_id}/research-jobs` | create (body: query_template, max_results, max_spend_usd) → returns job + a **cost estimate** (entity_count × per-search est) | Manage |
| GET  | `/v1/glossary/books/{book_id}/research-jobs/{job_id}` | status poll (counters, cost, state) | View |
| GET  | `/v1/glossary/books/{book_id}/research-jobs?status=` | list | View |
| POST | `/v1/glossary/books/{book_id}/research-jobs/{job_id}/pause` | user pause | Edit |
| POST | `/v1/glossary/books/{book_id}/research-jobs/{job_id}/resume` | resume (optional raised cap) | Edit |
| POST | `/v1/glossary/books/{book_id}/research-jobs/{job_id}/cancel` | cancel | Manage |

A **pre-flight cost estimate** (entity count × per-search price, resolved from provider-registry) is
returned by create + a dry GET so the FE shows it next to the spend cap — mirrors
`getWikiGenConfig` (D-WIKI-P2B-COST-ESTIMATE).

## 7. FE — a job progress card

Model on knowledge's `ProjectStateCard` (the 13-state dispatcher): a `ResearchJobCard` with
pending / running (progress + cost-so-far / cap) / paused_budget (raise-cap + resume) / paused_user
/ complete (N sources attached across M entities) / failed (retry) / cancelled. Lives in the
ontology/kind management surface (the same Manage workspace that now deletes kinds, Case 2). Polls
the status endpoint. i18n ×4. **Where to launch it:** a "Research all entities of this kind" action
on the kind row/column.

## 8. Open product decisions (resolve at CLARIFY of the build)

1. **Default `max_spend_usd`** and whether to hard-cap entity_count per job (e.g. ≤200) regardless
   of cap, as a runaway backstop.
2. **`force` re-research** toggle (default OFF = skip already-researched) — surface in the create UI?
3. **Auto-summarize follow-up?** Out of scope for v1 (keeps the agent-as-summarizer boundary). v2
   could enqueue a per-entity `propose_entity_edit` suggestion from the attached evidence — but that
   re-introduces the LLM-in-glossary question; defer.

## 9. Phasing (each a shippable milestone, risk-boundary commits)

- **M1 — core + schema (BE):** table + migration, `researchOneEntity` refactor (shared with the
  existing sync tool), create/status/list endpoints + cost estimate, **no worker yet** (jobs sit
  `pending`). VERIFY: real-PG round-trip on the CRUD + estimate; the refactor keeps the sync
  `glossary_deep_research` green.
- **M2 — worker + lifecycle (BE):** in-process worker, budget pause, cursor resume, cancel, cost
  metering. VERIFY: real-PG job drains a seeded kind with a stubbed web-search; budget-pause +
  resume + cancel + crash-resume covered; **live cross-service smoke** (real provider-registry
  web-search on ≥1 entity).
- **M3 — FE:** `ResearchJobCard` + launch action + polling + i18n ×4. VERIFY: card render tests per
  state; tsc; browser smoke.

## 10. Reuse map (don't reinvent)

- web search + neutralize + evidence attach: `effectDeepResearch` internals → `researchOneEntity`.
- cost metering: existing `record_spending`.
- job-state machine shape + budget pause + FE card: knowledge extraction-job design (pattern, not code).
- owner/grant gating + per-book lock + proxy ergonomics: `wiki_jobs.go`.
- entity-of-kind enumeration: existing entity-list queries (kind-scoped).
