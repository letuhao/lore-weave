# Data & Logic Scope Separation Standard

**Status:** ACTIVE · **Date:** 2026-07-04
**Governs:** how every module/service declares — **at design time** — which data it OWNS and which logic it OWNS, so responsibilities don't overlap or drift across services. Indexed in [`README.md`](./README.md).

> **Why.** With ~46 services, the failure mode is two services both owning the same concept (two writers of an aggregate, a read-model rebuilt in two places, the same logic copy-pasted), producing drift, double-writes, and silent conflicts. This standard makes ownership explicit and singular before code is written. It composes with [SDK-First](./sdk-first.md) (shared *logic* lives in an SDK, not duplicated), [User Boundaries](./README.md#a-platform-build-standards) (tenant *scope keys*), and the existing DB-per-service rule.

## Rules

- **SCOPE-1 · One data owner per concept.** Every table / aggregate / stream / cache-namespace has exactly ONE owning service. No second service writes it. (Generalizes the analytics rule "statistics-service owns engagement aggregates; others only emit" and the MMO feature-ownership-matrix to the whole platform.)
- **SCOPE-2 · Data crosses a boundary only via a contract, never a shared table.** DB-per-service; **no cross-service DB access, no cross-DB FK.** Integration is an HTTP/gRPC call or an outbox event with a **frozen schema** — never reaching into another service's tables. (This is why book-service *emits* `book.viewed` to statistics-service instead of both writing stats.)
- **SCOPE-3 · SSOT vs derived is explicit and one-directional.** Every derived store (projection, cache, index, embedding, snapshot) declares its **single source of truth** and is **regenerable from it with no loss** — derived data is never authored directly. (INV-FACTS: `entity_facts` is truth; the EAV projection + prose snapshot are regenerable caches. Two-layer glossary↔knowledge: glossary is authored SSOT, knowledge is the derived fuzzy/semantic layer anchored via `glossary_entity_id` FK.)
- **SCOPE-4 · One logic owner per capability.** A capability (extraction, salience ranking, translation, injection-sanitize, correction-capture) has one authoritative implementation. If ≥2 services need it, it lives in an **SDK/shared module** ([SDK-First](./sdk-first.md)), imported — not re-implemented. Two divergent implementations of one capability is a defect.
- **SCOPE-5 · Read-model vs write-model separation.** A service that serves an aggregated/denormalized read-model (statistics, catalog, leaderboards) builds it by **consuming events**, not by querying the write-side services synchronously. The write-side owns truth; the read-model owns the projection.
- **SCOPE-6 · Declare the boundary at design time.** A new feature/service names, up front: the data it owns (tables + scope keys), the data it only *reads* (via which contract), the logic it owns, and the logic it *reuses* (from which SDK). This declaration is the design-review gate; overlap with an existing owner must be resolved before build.

## Enforcement

| Rule | Status | Gate |
|---|---|---|
| SCOPE-2 no cross-service DB | **convention → to build** | a lint flagging a service that references another service's DB URL / table names; DB-per-service is architectural |
| SCOPE-1 one owner | **convention → to build (P2)** | a rule/review flag when a non-owner writes an aggregate another service owns (e.g. book-service re-adding local stats) |
| SCOPE-4 one logic owner | **to build** | cross-service near-duplicate detection ([SDK-First](./sdk-first.md) enforcement) |
| SCOPE-3 SSOT/derived | **partly enforced** | INV-FACTS + two-layer FK anchoring (knowledge tests); generalize the "derived is regenerable" assertion |
| SCOPE-6 design-time declaration | **process** | design-review checklist item (mirror the MMO `_boundaries/` ownership-matrix + feature-workflow) |

## Checklist — a new feature / service
- [ ] Names the data it OWNS (tables + scope keys) and the data it only READS (via which contract) (SCOPE-6)
- [ ] Owns each concept singularly; no second writer (SCOPE-1)
- [ ] Reads other services only via HTTP/event contract, never their tables (SCOPE-2)
- [ ] Each derived store declares its SSOT + is regenerable (SCOPE-3)
- [ ] Reused logic imported from an SDK, not re-implemented (SCOPE-4)
- [ ] Read-models built from events, not sync queries into write-side (SCOPE-5)
