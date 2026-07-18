# Glossary contract-first restoration — RUN-STATE

## COMMITMENT
Build [`../specs/2026-07-18-glossary-contract-first-restoration.md`]: restore contract-first as a LIVED
discipline for glossary-service — (a) a machine gate that reds when a public `/v1` route lacks an OpenAPI
entry (or a documented path isn't routed), (b) phased backfill of the ~20%-documented contract. Service:
glossary-service (Go). Size **L** (phased). Each slice: BUILD → review-impl → QC (VERIFY evidence pasted).

## INVESTIGATION — verified against code 2026-07-18
- `NewServer(nil, &config.Config{JWTSecret:<32ch>}).Router()` walks with **no DB** — the pool is dereferenced
  only inside handlers at request time. Confirmed by a green walk.
- `chi.Walk` is at go-chi/v5 v5.2.5 (tree.go:833); composes the FULL mounted path; skips method `*` and does
  NOT recurse opaque `r.Handle` leaves (`/mcp`). `go.yaml.in/yaml/v2` in the graph (unused — see below).
- OpenAPI YAMLs are 3.0.3, paths carry the full `/v1/` prefix. **A strict YAML parse FAILS** on unquoted
  colons in prose (`description: … Authorization: Bearer <svid>`) → the gate **line-scans the `paths:` block**
  (path keys @2-space, method keys @4-space) instead. Robust: description block-scalars are @8-space.
- Only two route namespaces exist in server.go: `/v1/glossary/*` (+ `/internal/*`, `/mcp`, `/mcp/admin`,
  `/health`, `/metrics`). **`/v1/canon/*` is NOT served here** (see DRIFT — falsified a spec assumption).

## SLICE BOARD (each: BUILD → review-impl → QC → evidence)
| slice | gain | status | evidence |
|---|---|---|---|
| **P1 · gate + generated allowlist** | contract drift reds automatically | **DONE** | `TestOpenAPIRouteConformance` (chi.Walk + YAML line-scan + SD-1 prefix + SD-2 normalize + 2-direction + SD-5/SD-8 honesty). `go test -run … -count=1` **PASS**; allowlist **113** == undocumented /v1 count; fake route **reds w/ SD-6 msg**; `# permanent:` **survives regen** (review-impl fix); bogus entry reds `(route no longer exists)` (SD-5). vet+build clean. |
| **P2 · document entity + attr-value family** | S-06 add/delete/PATCH + entity CRUD contracted | **DONE** | `entities.yaml` — 30 routes (entity CRUD, attr-value add/PATCH/delete, translations/evidences/items, chapter-links, revisions, merge/reassign/pin, bulk). Gate `-count=1` green; allowlist **113→83**; **0 phantoms** (all 30 paths match walked routes). review-impl: fixed a **fabricated `relevance` enum** (`[primary,secondary,mentioned]`→`[major,appears,mentioned]`, verified vs code); merge `loser_ids` + confidence enum verified correct; YAML full-parse valid (OpenAPI 3.0.3). |
| **P3 · document remaining public families** | allowlist → 0 (fully documented) | **DONE** | 5 new YAMLs — `actions.yaml` (6), `system_tier_admin.yaml` (13), `user_kinds.yaml` (13), `wiki.yaml` (25), `book_operations.yaml` (26) = 83 routes. Gate `-count=1` green; **allowlist 83→0** (every public /v1 route documented, ~20%→100% path+method); **0 phantoms** (no typos across 83). review-impl: fixed a 2nd fabricated enum (wiki suggestion review body `{status:[…]}`→`{action:[accept,reject]}`, verified vs `req.Action+"ed"`). |
| **P4 · flip strict + wire CI + CLAUDE.md note** | new undocumented route reds pre-commit | **TODO** — allowlist already 0 so the gate is DE-FACTO strict; remaining: CLAUDE.md contract-first note names this gate + the `-count=1` CI requirement | — |

## REGISTERS
### DECISIONS (sealed)
- SD-1..SD-9 in the spec §3a (contract-subject = `/v1/*`; param-name-agnostic normalize; per-(method,path);
  regen'd allowlist; honest allowlist; offender-naming; path+method only; phantom reconcile; SD-9 classes).
- **P1 discovery — phantom-exempt mechanism (concrete form of SD-8's "case-by-case"):** a named, honest
  `testdata/route_phantom_unbuilt.txt` holds documented-but-unbuilt paths (today the 6 `/v1/canon/*` L5.F RPC
  paths). Reds if one becomes routed or its YAML is deleted. NOT a blanket skip.
- **Allowlist is HEAD-consistent, never coupled to uncommitted convergent work.** A convergent S-09 W5 session
  added 2 wiki-suggestion routes mid-build; I regen'd only AFTER it committed (server.go clean at HEAD), so the
  113-line allowlist matches committed HEAD.

### DEBT
- **0 backfill routes** — allowlist fully drained (113→83→0 across P2+P3). Every public /v1 route is documented
  at path+method. The file now holds only header comments + the 6 phantom-exempt canon entries live separately.
- **Request-body shapes are best-effort at P2, not exhaustively verified** — SD-7 scopes P1–P4 to path+method;
  full request/response schema conformance is optional P5. Response schemas came from the real Go structs;
  concrete write-body fields were verified (createEntity/addAttr/bulk/merge/translation/evidence/reassign);
  a few (apply-edit `changes`, EntityPatch subset, evidence PATCH fields) are reasonable-but-unverified,
  flagged for the human schema review the spec §6 calls for.
- **CI must run the gate with `-count=1`** — it reads the YAML + testdata at runtime (not compiled inputs), so
  `go test`'s cache can mask a contract/allowlist change (a false green). Wire this into P4.
- **YAML lib now unused** (`go.yaml.in/yaml/v2` stays indirect) — the line-scan replaced it. No action.
- **Canon RPC YAMLs may be mis-homed** — `/v1/canon/*` contracts sit under `contracts/api/glossary-service/`
  but no glossary route serves them (L5.F separate sub-program). Follow-up (not this build): relocate to the
  owning track if confirmed. Tracked via the phantom-exempt file's honesty (reds when built).

### DRIFT
- **Spec §3a assumed `/v1/canon` is served by glossary — FALSE.** The gate's phantom direction (SD-8) proved
  it on day one: 6 `/v1/canon/*` phantoms, zero canon routes registered. Reconciled via the phantom-exempt
  file; spec §3a SD-8 updated with the finding.
- **review-impl caught a silent-revert bug:** REGEN rewrote every route as `# backfill`, clobbering a hand-set
  `# permanent:` (SD-9) class. Fixed: REGEN now preserves an existing comment for a still-present route.

## RESUME
Re-read THIS → `git log --oneline -8` → continue at P2 (document the entity + attr-value family; remove each
documented route from the allowlist so 113 shrinks).
