# Creation-Unblock RAID — Completion Design

> **Date:** 2026-06-15 · **Phase:** DESIGN · **Size:** XL (multi-service: knowledge-service schema + rollup, composition-service route, FE wiring) · **HEAD:** `b16e670a`
> **Resolves:** [gap analysis](2026-06-15-creation-unblock-raid-gap-analysis.md) — G1, G2, G3, G4, G5, and deferral D-C16-NULL-WORK-ROUTE.
> **Boundary:** in-RAID gaps only. World-core refactor, MMO-RPG, collaboration remain out of scope.

## 1. Goal

Close every in-boundary gap so the creation-unblock RAID is genuinely usable end-to-end: a user can create a world, populate it with books and what-ifs **without leaving the workspace**, see a world-wide knowledge graph that rolls up its books, pick projects/worlds with a real picker, reach every creation surface from adjacent ones, and never hit a dead-ended null-project Work.

## 2. Locked decisions (CLARIFY)

| Decision | Choice |
|---|---|
| Scope | **Fullest in-boundary pass** — Tier 1 (G1–G3) + G4 + G5 + D-C16 BE route |
| World↔knowledge model | **Dedicated world-level knowledge project** (G4) — books roll up into it; new `world_id` binding + schema in knowledge-service |

## 3. Architecture — the world-level knowledge project (G4)

### 3.1 Model

The world's **bible book project IS the world-level project**, promoted to first-class:

- **New binding:** `knowledge.projects.world_id UUID NULL` (FK-by-convention to book-service `worlds.id`; no cross-DB FK — services own their DBs). Set ONLY on the world-level project.
- **Provisioning:** deterministic. When a world is created, provision its world-level project bound to `(book_id = bible_book_id, world_id = world_id, project_type = 'book')` via the existing idempotent `create_or_get` (dedup key `(user, book_id)` already guarantees one). Provisioned **FE-orchestrated** at world-create time (consistent with today's on-demand pattern), with a **lazy `create_or_get` fallback** on first workspace open so it can never be missing.
- **Member books stay book-scoped.** A book attached to a world keeps its own per-book project (`book_id`-scoped, `world_id` NULL). World **membership is owned by book-service** (`books.world_id`) — the single source of truth — and resolved at read time. We do **not** duplicate membership into knowledge-service (no write-time cross-service coupling, no event bus needed).
- **Visibility (decision ④):** the world-level project is hidden from the normal `/knowledge/projects` HOME browser — same treatment `is_bible` books get in the library — so a phantom "World Bible" project never appears. The projects list filters out projects whose `world_id IS NOT NULL` (or whose `book_id` is a bible book); the world surfaces it only through the world workspace.

> Rationale: `world_id` gives the world's own canon partition (the bible lore) a stable identity independent of "the project whose book_id happens to be the bible book," and future-proofs a world project not tied to a book. Membership-by-derivation keeps book-service as SSOT and avoids a sync seam with no event pipeline.

### 3.2 Rollup read (the "books roll up into the world graph")

New **`GET /v1/knowledge/worlds/{world_id}/subgraph`** in knowledge-service:

1. **Resolve membership (auth, decision ①):** knowledge-service calls a **new book-service internal route** `GET /internal/worlds/{world_id}/books?user_id={user_id}`, authenticated with the shared `X-Internal-Token` (the established service-to-service pattern — glossary/knowledge already use it). book-service owner-scopes by `user_id` → returns the member books or 404. We do **not** trust a client-supplied book/project list (would be the [worker-loaded-id-needs-parent-scoping] trap).
2. Resolve projects: for the world-level project (via `world_id` filter) **plus** each member book (`get_by_book`), collect `project_id`s, **deduped** (the world-level project IS the bible book's project — it would otherwise appear twice). `get_by_book` already excludes `is_derivative` (C23-fix), so dị bản branches are automatically out of the canon rollup (they surface in the C28 living-world tree instead).
3. Union: run the existing C18 `get_project_subgraph` per `(user_id, project_id)` partition, **merge app-side**, re-sort the merged nodes by the global `(anchor_score DESC, mention_count DESC, id ASC)` key (every node carries these — [relations.py:649](../../services/knowledge-service/app/db/neo4j_repos/relations.py#L649)) and apply the node cap to the **union**; tag each node with its source `project_id` so the FE can legend per-book. `node_cap_hit` is OR'd across members **plus** set true if the union re-cap trimmed (decision ③ — a large book can crowd out a small one; this is flagged, never silent).
4. Partition safety is unchanged: every sub-query still binds `(user_id, project_id)`; the union never issues a cross-partition Cypher.

> **Graph semantics (decision ②) — union of per-book islands, by design.** C18 edges are intra-partition only, so the world graph is **each member book's canon graph rendered together as disconnected components**, NOT a connected cross-book graph. The same character in two books stays two nodes. Cross-book entity unification (entity-merge across projects) is a large knowledge-service feature deliberately **out of this RAID boundary** (world-core territory). The FE legends nodes by source book so the islands read as intentional.

Timeline rollup (`/worlds/{id}/timeline`) follows the same shape but is **deferred to a follow-up** to keep this pass bounded — M0 ships the graph rollup.

### 3.3 Schema changes (knowledge-service)

```sql
ALTER TABLE projects ADD COLUMN IF NOT EXISTS world_id UUID;          -- nullable, additive
CREATE INDEX IF NOT EXISTS idx_projects_world ON projects(world_id) WHERE world_id IS NOT NULL;
```
- `ProjectCreate` / `ProjectUpdate` gain optional `world_id`. `create_or_get` stamps it when present (idempotent; a re-call with the same `(user, book_id)` updates `world_id` if newly supplied, never duplicates).
- List filter gains `world_id` (closed param, mirrors `book_id`) → returns the world-level project.
- Migration is **additive + idempotent + reversible** (down drops index then column), matching the C20/C23 house pattern. No backfill.

## 4. D-C16 — null-project Work addressability (composition-service)

### 4.1 Diagnosis

A null-project Work is reachable only by surrogate `id` (`get_by_id`), but every downstream route keys on `project_id`, and outline/scene/canon/job rows are all `project_id NOT NULL`. So the writer cannot proceed until backfill — and backfill only fires on a **second** `POST /work`. The pending state is a dead-end, not a transient.

### 4.2 Design — make pending *transient, observable, self-healing* (NOT a nullable outline)

We keep the outline model project-anchored (rejecting the heavier "nullable outline_node.project_id" option — it churns 4 tables for a state that should last seconds). Instead:

1. **Id-addressable resolve route:** `GET /works/by-id/{work_id}` → returns the Work by surrogate `id` (reuses `get_by_id`; works for pending). The FE holds `work.id` after `POST /work`.
2. **Self-healing backfill route:** `POST /works/by-id/{work_id}/resolve-project` → if the Work is pending and knowledge-service is healthy, run the normal `create_or_get` against knowledge and **backfill the same row** (reuse `backfill_project`); returns the now-stamped Work (or 409 `STILL_PENDING` if knowledge still down). Idempotent: a non-pending Work returns itself.
3. **FE flow:** when `POST /work` returns `pending_project_backfill: true`, CompositionPanel shows a "finishing setup…" state and polls `resolve-project` (bounded backoff). On success it has a real `project_id` and proceeds through the existing project-keyed routes unchanged. **On timeout (decision ⑥):** show "knowledge service unavailable — retry"; the Work stays pending and backfills on the next attempt. There is **no background sweep** (no event bus — consistent with the rest of the system). No new outline semantics.

> Net: the null-project Work becomes a brief, visible, retried state that converges to a normal project-backed Work. The derivative guard (a derivative never takes the null path) and the C16 partial-unique invariants are untouched.

### 4.3 Schema

None. Pure additive routes + repo reuse (`get_by_id`, `get_pending_for_book`, `backfill_project` all already exist).

## 5. FE design

### 5.1 G1 — world-workspace populate

[WorldWorkspacePage](../../frontend/src/features/world/pages/WorldWorkspacePage.tsx) / [LivingWorldTree](../../frontend/src/features/world/components/LivingWorldTree.tsx) empty + populated states gain real CTAs:

- **"Add a book"** → a combined `AddBookToWorldModal`: tab/segment to **attach existing** (reuse `BookPicker`) OR **create new** (reuse the `/books` FormDialog flow). On confirm → `worldsApi.moveBookIntoWorld` (existing C20 `POST /v1/worlds/{id}/books`) → invalidate `listWorldBooks` → tree repopulates. **Create-new is two steps (decision ⑧):** create book → attach; if attach fails the book exists standalone and is re-attachable (no orphan loss). No new BE.
- **"Create a what-if"** → routes to the divergence wizard (existing, [CompositionPanel.tsx:307](../../frontend/src/features/composition/components/CompositionPanel.tsx#L307)) seeded with a canon Work in the world. **Source selection (decision ⑦):** one canon book → auto-selected; >1 → a source-Work pick step. If the world has no canon book yet, the CTA guides to "Add a book" first (a what-if needs a source — C23 invariant).
- **"Build world knowledge"** → the world-level rollup graph (G4): renders `GET /worlds/{id}/subgraph` via the C19 `ProjectGraphView` canvas, **replacing** the current bible-only `WorldGraphSection` (decision ⑤ — the rollup becomes *the* world graph). Empty → a "Build the bible / extract a book" prompt (no silent blank).

All state changes via explicit handlers (no useEffect-for-events); panels stay mounted (CSS-hidden), per FE rules.

### 5.2 G2 — reusable pickers

- **`ProjectPicker`** (mirror [BookPicker](../../frontend/src/components/shared/BookPicker.tsx)): debounced search over `knowledgeApi.listProjects({search})`, emits `project_id`, empty=valid, "＋ Create new project" inline option (opens `ProjectFormModal`). Replaces the raw `<select>` in chat `SessionSettingsPanel` and is the standard project-pick affordance.
- **`WorldPicker`** (same shape over `worldsApi.listWorlds`): emits `world_id`, "＋ Create new world" inline. Used by G3.

### 5.3 G3 + G5 — cross-linking & onboarding

- **From book/composition:** an "Add to world" action (`WorldPicker`) + "Open in world" link when a book has a `world_id`.
- **From knowledge project:** surface its book and (if any) its world.
- **G5:** with G1 landed, onboarding's "Build a world" → `/worlds` → workspace is now a usable funnel (create world → add book → build knowledge → branch a what-if). The world-create flow also provisions the world-level project (§3.1) so "Build world knowledge" isn't confusingly empty.

## 6. Cross-service contracts (new / changed)

| Service | Endpoint | Status | Notes |
|---|---|---|---|
| knowledge | `GET /v1/knowledge/worlds/{world_id}/subgraph` | **new** | rollup union read; calls book-service internal for membership; gateway proxy already covers `/v1/knowledge/*` |
| knowledge | `projects` create/list/patch gain `world_id` | **changed** | additive optional field + list filter; world-level project hidden from HOME list |
| book | `GET /internal/worlds/{world_id}/books?user_id=` | **new** | internal membership route, `X-Internal-Token` (decision ①); owner-scoped by `user_id` |
| composition | `GET /works/by-id/{work_id}` | **new** | id-addressable resolve |
| composition | `POST /works/by-id/{work_id}/resolve-project` | **new** | self-healing backfill |
| book | `POST /v1/worlds/{id}/books`, `GET /v1/worlds/{id}/books` | reuse | G1 attach + tree (C20, already proxied) |

No new gateway proxy needed (worlds, knowledge, books, composition all already proxied). No new provider/model config; the world project reuses `embedding_model` via provider-registry (provider-gate clean).

## 7. Build slicing (proposed milestones)

Sliced for risk boundaries; each is a checkpoint/commit per the budget-driven cadence.

| Slice | Title | Service(s) | Size | Risk gate |
|---|---|---|---|---|
| **W1** | World-level project: `world_id` schema + ProjectCreate/list/create_or_get binding | knowledge BE | M | migration round-trip (up→down→up), real-PG |
| **W2** | World rollup subgraph (union read) + book-service `/internal/worlds/{id}/books` membership route | knowledge BE + book BE | M | cross-service live-smoke (consumer path); 2 services touched |
| **W3** | D-C16: id-addressable resolve + self-healing backfill routes + FE pending poll | composition BE + FE | M | live-smoke: knowledge-down→pending→recover→resolve→generate |
| **W4** | ProjectPicker + WorldPicker (G2), replace chat raw `<select>` | FE | S | vitest + a11y |
| **W5** | World-workspace populate CTAs (G1) + world graph rollup render (G4 FE) | FE | M | Playwright: create world→add book→build knowledge→graph shows rollup |
| **W6** | Cross-linking (G3) + onboarding funnel close (G5) | FE | S | Playwright: onboarding "Build a world" → usable funnel |

**Dependency order:** W1 → W2 → (W5 consumes W2); W3 independent; W4 before W5/W6. W1+W2 are the load-bearing BE; W3 is isolated; W4–W6 are FE.

Per the RAID memory [new-cross-service-contract-needs-consumer-live-smoke]: **W2 and W3 each introduce a new cross-service contract and MUST live-smoke through the consumer's path** before DONE — not unit-only.

## 8. Invariants to preserve (review checklist)

- **Neo4j partition** `(user_id, project_id)` on every sub-query; rollup unions in app code, never a cross-partition Cypher. No cross-user/cross-project bleed.
- **G2 (derivative own project)** — `is_derivative` projects excluded from the canon rollup; dị bản stay in the C28 living-world tree.
- **Additive/idempotent/reversible** migration (W1), real-PG round-trip.
- **No write-time cross-service coupling** — world membership stays book-service SSOT, resolved at read time.
- **C16 invariants** — derivative never takes the null path; partial-unique `(project_id) WHERE NOT NULL` and `(user,book) WHERE pending` intact; backfill stamps the same row.
- **Provider/model invariants** — no hardcoded model; world project embedding via provider-registry; provider-gate green.
- **FE rules** — no useEffect-for-events, no stateful unmount, hooks self-contained, ≤100-line components.

## 9. Risks & open questions

- **R1 — rollup cost.** A world with many large member books unions many subgraphs. Mitigation: the union node cap is applied server-side (bounded); per-member subqueries already cap in Cypher. If a world is huge, `node_cap_hit` signals truncation (logged, not silent).
- **R2 — membership skew.** A book moved out of a world between the membership read and the project union → a stale project in the union. Low impact (read-only graph); acceptable for M0.
- **R3 — world project provisioning race.** Two concurrent world-create/open calls → `create_or_get` advisory lock on `(user, bible_book_id)` already serializes (C9/C16 pattern). Safe.
- **OQ1 — timeline rollup** (`/worlds/{id}/timeline`) deferred to a follow-up (M0 ships graph rollup only). Track as `D-WORLD-TIMELINE-ROLLUP` after this pass.
- ~~OQ2~~ **Resolved (⑦):** what-if CTA with no canon book → guide-to-add-book (keeps the C23 derivative-needs-source invariant).

### Resolved clarifications (design REVIEW, 2026-06-15)

① membership auth = new book-service `/internal/worlds/{id}/books` + `X-Internal-Token` · ② world graph = union of per-book islands (no cross-book merge) · ③ union re-cap fairness flagged via `node_cap_hit` · ④ world-level project hidden from HOME browser · ⑤ rollup replaces bible-only `WorldGraphSection` · ⑥ D-C16 pending self-heals on poll/retry, no background sweep · ⑦ what-if guides to add-a-book when sourceless · ⑧ create-new-book attach is two-step, no orphan loss.

## 10. Verify strategy

- **W1:** pytest + real-PG migration round-trip; `world_id` dedup/stamp idempotence.
- **W2:** pytest union/exclusion/cap + **live cross-service** rollup over a built graph (≥2 member books).
- **W3:** pytest routes + **live** knowledge-down→pending→recover→resolve→generate (the C16 smoke, extended).
- **W4–W6:** vitest + **Playwright** smokes on `:5174` (rebuild the frontend image first — [frontend-5174-is-baked-prod-nginx-not-vite]): create-world→add-book→build-knowledge→graph-rollup; onboarding "Build a world" funnel.
