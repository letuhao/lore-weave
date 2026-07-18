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
3. **Assert BOTH directions** (over `/v1/*` routes only — non-`/v1` is prefix-exempt per SD-1):
   - **No undocumented `/v1` route** — every walked `/v1` route is in the contract OR in the per-route
     `route_coverage_exempt.txt` backfill list (SD-4/SD-5).
   - **No phantom contract path** — every documented path+method is actually routed (catches a contract that
     describes a renamed/removed route).
4. **Red on drift:** add a public route without a contract entry (and without an allowlist reason) → the test
   fails at the point of the violation. This is what makes contract-first *lived*, not aspirational.

**Why an allowlist, not "document everything at once":** ~120 undocumented routes can't be specced in one PR
without unreviewable bulk. The allowlist lets the gate ship GREEN immediately with the current gap made
**explicit and shrinking** — every documented family is removed from the allowlist, so the list is a visible
debt counter that only goes down.

## 3a. CLARIFY — sealed decisions + edge cases (verified against code 2026-07-18)

**Feasibility confirmed:**
- **The router walks with NO DB.** `NewServer(pool, cfg)` and `Router()` only *register* handlers; the pool is
  dereferenced only *inside* handlers at request time (e.g. `/health` guards `if s.pool != nil`). So the gate
  builds `api.NewServer(nil, &config.Config{JWTSecret: <32-char dummy>}).Router()` and walks it — pure
  introspection, no Postgres. (AdminJWTPublicKeyPEM empty ⇒ admin endpoints disabled — fine, they're `/mcp/admin`,
  exempt.)
- **`go.yaml.in/yaml/v2`** is already in the module graph (indirect) — promote to direct; no new dependency.
- **OpenAPI paths carry the full `/v1/...` prefix** (`openapi: 3.0.3`, standard `paths:` map). Two namespaces:
  `/v1/glossary/*` (main API) + `/v1/canon/*` (the canon RPC contract, `canon_*.yaml`). Both are `/v1/` → both
  in scope, no special-casing.

**Sealed decisions:**
- **SD-1 · "Contract-subject" = any route whose pattern starts with `/v1/`.** Everything else is exempt
  **by prefix rule** (not a per-route allowlist), each with a one-line reason: `/health`, `/health/ready`,
  `/metrics` (infra), `/mcp`, `/mcp/admin` (MCP, opaque `r.Handle` — Walk does not recurse into them),
  `/internal/*` (service-to-service; a SEPARATE contract-consumer story — deferred). ⇒ the shrinking allowlist
  holds ONLY undocumented **`/v1/*`** routes, not internal/infra.
- **SD-2 · Compare param-name-AGNOSTIC templates.** Normalize both sides: method→lowercase; every path param
  `{book_id}`/`{bookId}` and every chi regex param `{name:regex}` and trailing `/*` → `{}`; strip a trailing
  slash. So chi `/v1/glossary/books/{book_id}/entities/{entity_id}` and OpenAPI `.../books/{bookId}/entities/{id}`
  both key to `get /v1/glossary/books/{}/entities/{}`. Param-name drift is cosmetic and must NOT red the gate.
  (Edge: `canon_read.yaml`'s `/v1/canon/{book_id}/{attribute_path}` — if chi registers a `:.*` wildcard, the
  normalization collapses it to `{}` on both sides.)
- **SD-3 · Coverage is per `(method, normalized-path)` pair.** A path documented for GET but not DELETE ⇒ the
  DELETE route is flagged (that is the point). Methods enumerated: GET/POST/PUT/PATCH/DELETE; HEAD/OPTIONS and
  any `*`/all-method leaf are ignored (none exist under `/v1/`; `/mcp`'s `r.Handle` is exempt anyway).
- **SD-4 · The allowlist is a checked-in `internal/api/testdata/route_coverage_exempt.txt`** (sorted
  `method /normalized/path` lines), **regenerated by `REGEN_ROUTE_ALLOWLIST=1 go test -run TestOpenAPIRouteConformance`**
  — the repo's `WRITE_FRONTEND_CONTRACT=1` idiom. Without the env, the test asserts against the file.
- **SD-5 · The allowlist is kept HONEST (no dead entries).** The gate also asserts every allowlist entry is a
  route that is STILL walked AND STILL undocumented. A route that was removed, or has since been documented,
  but left in the allowlist ⇒ RED ("stale exemption — regenerate"). So the list can only shrink; it can't hide
  a removed route or double-cover.
- **SD-6 · Failure message names the exact offender.** On red: the `(METHOD path)` that is undocumented-and-not-
  exempt, with "add it to `contracts/api/glossary-service/` OR, for a deliberate exemption, run
  `REGEN_ROUTE_ALLOWLIST=1`." Ergonomics = a dev knows precisely what to do.
- **SD-7 · Scope is path+method only** (P1–P4). Request/response **schema** conformance is a heavier, optional
  P5. The drift this gap is about is "undocumented route," not "wrong field."
- **SD-8 · P1 will likely surface PHANTOM contract paths — reconcile them, don't allowlist them.** The
  "no phantom contract path" direction checks the ~30 already-documented paths against the live routes; if any
  was renamed/removed since 2026-06-21, it reds. That is the gate earning its keep on day one. P1 resolves each:
  fix the YAML to the real route, or delete the stale entry. (The phantom direction has NO backfill allowlist —
  a documented path that isn't routed is always a bug in the doc.) Rare "documented-but-unbuilt" intent is
  handled case-by-case, not by a blanket exemption.
- **SD-9 · Two exemption classes in one file, by comment.** `route_coverage_exempt.txt` lines may carry a
  trailing `# backfill` (a `/v1` route awaiting docs — the shrinking debt) or `# permanent: <reason>` (a `/v1`
  route that legitimately never gets a public contract entry — rare). Both keep the gate green; only `# backfill`
  is the debt counter. SD-5's honest-check applies to both (a stale entry of either class reds).

**`chi.Walk` mechanics (confirmed):** `chi.Walk(router, walkFn)` (go-chi/v5, already a dep) recurses the full
tree incl. nested `r.Route` groups and composes the FULL path (mount prefix prepended) — so `/v1/glossary/...`
arrives complete. Opaque `r.Handle` leaves (`/mcp`) are NOT recursed into (we don't want their tool routes).

## 4. Phased slices (each: BUILD → QC)
- **P1 · The gate + generated allowlist.** Build `TestOpenAPIRouteConformance`: `NewServer(nil, cfg).Router()`
  → `chi.Walk` → the walked `(method, normalized-path)` set; parse `contracts/api/glossary-service/*.yaml` →
  the documented set; apply the SD-1 `/v1/` prefix predicate (infra/mcp/internal exempt by prefix); the SD-2
  normalization; the two-direction check (no undocumented `/v1` route, no phantom contract path) + the SD-5
  honest-allowlist check. Generate `testdata/route_coverage_exempt.txt` via `REGEN_ROUTE_ALLOWLIST=1` (SD-4) so
  the test is GREEN with the `/v1` gap explicit + checked in.
  *DoD (paste the output):* `go test ./internal/api/ -run TestOpenAPIRouteConformance` → PASS; the allowlist
  file's line count == the undocumented `/v1` route count; a deliberately-added fake `/v1` route (temporarily)
  reds it with the SD-6 message (proves teeth); a stale allowlist entry reds it (proves SD-5).
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
