# Glossary-service — restore contract-first (document the entity route family + enforce it)

> **Origin:** the S-06 audit ([`../plans/2026-07-18-S06-glossary-attr-value-RUN-STATE.md`](../plans/2026-07-18-S06-glossary-attr-value-RUN-STATE.md))
> found the S-06 add/delete routes are contract-absent — but so is the **entire entity route family**, and
> the contract is **stale + unenforced**. This spec is the buildable home for that gap. **Gate #2 (structural):
> a phased effort, not an S-06 patch.** Service: glossary-service (Go). Size: **L** (phased).

## 1. The gap (measured 2026-07-18)
- **Coverage ≈ 20%:** `~149` public `/v1/glossary` routes are registered in `server.go`; the 5 contract YAMLs
  (`contracts/api/glossary-service/`, last touched **2026-06-21**) document `~30` paths — canon, ontology
  (attribute **definitions**), seed. **The whole entity route family is absent**: entity CRUD, attribute-**value**
  PATCH/POST/DELETE (S-06) + translations/evidences/items, revisions, chapter-links, genres, status, scope.
- **Zero enforcement:** nothing in `services/`, `scripts/`, or `.githooks/` references these contracts. They are
  doc-only and **not checked against the code** — so they rot (the entity family grew for weeks with no doc, no
  test caught it). The repo's "Contract-first" invariant is aspirational here, not lived.

## 2. Goal
Restore contract-first as a LIVED discipline for glossary: (a) the public route surface is documented in
OpenAPI, and (b) a **machine gate reds when a public route lacks a contract entry** (or a contract path has no
route) — so drift can't silently recur. Mirrors the service's existing `mcp_tool_schema_contract_test.go`
philosophy (enumerate expected, assert reality over the real surface, red on drift).

## 3. The load-bearing piece — the conformance gate (design)
A pure Go unit test `TestOpenAPIRouteConformance` (NO DB — route/YAML introspection only, so it runs in the
normal `go test` fast lane and the pre-commit hook):
1. **Enumerate registered routes** via `chi.Walk(s.Router(), func(method, route, ...) {...})` (go-chi/v5
   standard) → the set of `(METHOD, path-pattern)` the service actually serves. Normalize chi's `{param}` to
   the OpenAPI `{param}` form.
2. **Parse the contract** — load every `contracts/api/glossary-service/*.yaml`, collect documented
   `(METHOD, path)` pairs (a minimal YAML walk; no full OpenAPI validator needed for the path/method set).
3. **Assert BOTH directions:**
   - **No undocumented public route** — every walked public route is in the contract OR in a small, explicit
     `exempt` allowlist (health, `/mcp`, `/internal/*` if scoped out — each with a one-line reason).
   - **No phantom contract path** — every documented path+method is actually routed (catches a contract that
     describes a renamed/removed route).
4. **Red on drift:** add a public route without a contract entry (and without an allowlist reason) → the test
   fails at the point of the violation. This is what makes contract-first *lived*, not aspirational.

**Why an allowlist, not "document everything at once":** ~120 undocumented routes can't be specced in one PR
without unreviewable bulk. The allowlist lets the gate ship GREEN immediately with the current gap made
**explicit and shrinking** — every documented family is removed from the allowlist, so the list is a visible
debt counter that only goes down.

## 4. Phased slices (each: BUILD → QC)
- **P1 · The gate + full allowlist.** Build `TestOpenAPIRouteConformance` with `chi.Walk` + YAML parse + the
  two-direction check. Seed `exempt` with EVERY currently-undocumented route (generated once, checked in) so
  the test is GREEN and the gap is an explicit checked-in list. Decide `/internal/*` scope here (recommend:
  exempt internal for now — internal contracts are a separate consumer concern; a follow-up covers them).
  *DoD:* test passes; the allowlist's length == the measured undocumented count; a deliberately-added fake route
  reds it (proves teeth).
- **P2 · Document the entity + attr-value family** (the S-06-adjacent surface first, since that's the live gap):
  a new `entity_attributes.yaml` + `entities.yaml` covering entity CRUD + attribute-value PATCH/POST/DELETE +
  translations/evidences/items + revisions/chapter-links/genres/status/scope. Remove each from the allowlist as
  documented. *DoD:* the S-06 add/delete + PATCH are contracted; allowlist shrinks by the family's count.
- **P3 · Document the remaining public families** (canon extensions, search, bulk, display-names, …), shrinking
  the allowlist toward only genuine exemptions. *DoD:* allowlist == {health, /mcp, (internal if scoped out)}.
- **P4 · Flip to strict + wire CI.** With the allowlist down to true exemptions, the gate now enforces
  contract-first for every NEW public route. Add the test to the service's CI lane (it already runs in
  `go test ./internal/api/`); note it in `CLAUDE.md`'s contract-first rule as the enforcement point for
  glossary. *DoD:* a new undocumented public route reds pre-commit.

## 5. Scope / decisions to seal at P1
- **Public first; `/internal/*` deferred** to a follow-up (internal routes serve other services, a distinct
  contract-consumer story). Recorded as an allowlist reason, not silently skipped.
- **Path+method set, not full schema validation.** P1–P4 enforce that every route is *documented at all*
  (path+method). Response/request-body schema conformance is a heavier, separate follow-up (P5, optional) — the
  80/20 is "no undocumented route," which is the drift this gap is about.
- **The gate is the deliverable, the docs are the backfill.** P1 (the gate) is what prevents *future* rot; P2–P3
  pay down the *existing* debt. Shipping P1 alone already stops the bleeding.

## 6. Adherence / tests
- The gate is a unit test (no DB) — fits the fast lane + pre-commit. Mirrors `mcp_tool_schema_contract_test.go`.
- `chi.Walk` is already a transitive dep (go-chi/v5); no new dependency.
- Each documented family gets its YAML reviewed for path/method accuracy against `server.go` (the gate proves
  the pairing; a human reviews the request/response shapes).

## 7. Out of scope
- Full request/response **schema** conformance (P5, optional follow-up).
- `/internal/*` route documentation (separate follow-up).
- Other services' contracts (this is glossary-only; the pattern is reusable if it proves out).

## 8. Definition of done (this spec)
P1 shipped (the gate, green, with teeth) is the **minimum** that clears the "unenforced" half. Full closure =
P4 (allowlist down to true exemptions, strict, CI-wired) so contract-first is lived. Track P1 as the priority;
P2–P4 are the backfill.
