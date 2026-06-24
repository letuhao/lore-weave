# Cycle 18: Graph subgraph endpoint (BE knowledge)

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** BUILD the missing project-wide subgraph read API. Today only a **per-entity 1-hop** read exists (`GET /entities/{id}`); there is **no** project-level subgraph endpoint, which the visual graph canvas (C19) needs. This cycle builds `GET /v1/knowledge/projects/{id}/subgraph` — a **Neo4j n-hop, node-capped** query returning nodes + edges for the project partition `(user_id, project_id)`. Read-only, capped, with an "expand"/"load-more" affordance via params (e.g. `hops`, `limit`, optional `center`/`entity_id`). **Cross-service** — carries a real live-smoke (query a built project → capped subgraph). BE knowledge-service only.
- **Acceptance gate:** `scripts/raid/verify-cycle-18.sh` exits 0
- **Top 3 LOCKED decisions consumed:** G5, partition `(user_id, project_id)`, read-only-MVP
- **DPS count:** 2
- **Estimated wall time:** 4h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C5
- Files expected to exist (grep-able paths): knowledge-service Neo4j graph repository/query layer + the existing per-entity 1-hop `GET /entities/{id}` handler (the pattern to generalize); a project with a **built** graph (C5 unblocks build-graph).

## Scope (IN)
- New route `GET /v1/knowledge/projects/{id}/subgraph` — Neo4j n-hop traversal scoped to `(user_id, project_id)`; returns `{nodes:[], edges:[]}` typed for the canvas.
- **Node cap** (hard maximum) + params: hop depth, node limit, optional `center`/`entity_id` for ego-expansion (powers C19's expand-hop / load-more). Deterministic cap (e.g. highest mention_count / anchor first) so the cap is stable, not random.
- Partition scoping enforced server-side — the query MUST filter by the caller's `user_id` AND the route `project_id` (no cross-project bleed).
- `scripts/raid/verify-cycle-18.sh` (acceptance gate — the runner creates it) + the live-smoke evidence artifact.

## Scope (OUT — explicitly)
- **No FE.** The graph canvas is C19 — this cycle ships the endpoint only.
- No new graph library / no Neo4j schema change — generalize the existing 1-hop query pattern.
- No write/edit surface — read-only (editing reuses existing entity/relation dialogs, C19).
- No layout computation server-side — layout (force/radial) is hand-rolled FE in C19; the endpoint returns raw nodes+edges.
- No subgraph for derivative two-project merge (that is the packer, C25) — single project partition only here.

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: `scripts/raid/verify-cycle-18.sh` exits 0 — asserts (1) the route exists + returns `{nodes, edges}`, (2) node count never exceeds the cap, (3) cross-project scoping: a project_id the user doesn't own / a different project returns no foreign nodes, (4) `hops`/`limit`/`center` params shape the result.
- Lints pass: knowledge-service lint/format + type check; `pytest` for the new query + handler green.
- Integration smoke: **live-smoke (cross-service, REQUIRED)** — stack up, query a **built** project → returns a capped subgraph with real nodes+edges. Evidence string MUST contain `live smoke: query built project subgraph → capped nodes+edges`.

## DPS parallelism plan
- DPS 1: Neo4j n-hop query + node-cap + partition scoping in the graph repository (generalize the 1-hop pattern) (return budget: 1500 tokens summary).
- DPS 2: route handler + request/response schema + param validation (hops/limit/center) + the live-smoke harness against a built project.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **Mock-only false-green:** unit pass but no real Neo4j call ran — confirm the live-smoke token reflects a genuine query against a built project's partition.
- **Cross-project bleed:** the Cypher missing the `(user_id, project_id)` filter → returns another project's / another user's nodes (the exact leak C23 guards elsewhere). Verify both keys are bound.
- **Unbounded traversal:** n-hop with no effective cap → a hub node explodes the result / OOMs Neo4j. Confirm the cap is enforced *in the query*, not post-filtered after fetching everything.
- **Non-deterministic cap:** capping by arbitrary order so the same query returns different nodes each call — breaks C19 expand/load-more stability.
- **Hardcoded model/values:** N/A for models here, but watch for hardcoded project/user ids or magic caps without a param.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present (subgraph route, n-hop, node cap, partition scoping, expand params)
- No OUT items touched (no FE, no graph lib, no schema change, no write surface, no two-project merge)
- All acceptance criteria met; `verify-cycle-18.sh` exits 0 + live-smoke token present
- Cross-cycle invariants not violated (partition scoping; read-only)

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Cycle row: `docs/plans/2026-06-13-creation-unblock/CYCLE_DECOMPOSITION.md` — C18 (Graph subgraph endpoint).
- LOCKED: `docs/plans/2026-06-13-creation-unblock/OPEN_QUESTIONS_LOCKED.md` — G5 (read-only navigable MVP, reuse `GraphCanvas`, build a subgraph endpoint; Neo4j `(user_id, project_id)` partition).
- Spec: `docs/specs/2026-06-13-writer-core-flow-P0.md`, `docs/specs/2026-06-13-writer-persona-use-cases-scenarios.md`.

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Top LOCKED 1:** G5 → BUILD `GET /v1/knowledge/projects/{id}/subgraph` (Neo4j n-hop, node-capped); none exists today (only per-entity 1-hop).
- 🔴 **Top LOCKED 2:** Partition scoping → the Cypher MUST bind both `user_id` AND `project_id`; no cross-project bleed.
- 🔴 **Top LOCKED 3:** Read-only MVP + a deterministic node cap with expand/load-more params (powers C19).
- 🔴 **Acceptance MUST include:** live-smoke token `live smoke: query built project subgraph → capped nodes+edges` (cross-service rule) — mock-only is a false-green.
- 🔴 **Do NOT touch:** any FE (C19), Neo4j schema, write/edit endpoints, derivative two-project merge (C25).
- 🔴 **Fresh session reminder:** this is a new `/raid 18` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
