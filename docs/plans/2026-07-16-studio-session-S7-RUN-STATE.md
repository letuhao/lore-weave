# Studio Session S7 — Knowledge, World & Cast — RUN-STATE

> Anchor for the 8-session Writing-Studio completeness build. **Re-read this file FIRST after any
> compaction**, then `git log --oneline -15`, then continue at the first non-DONE slice.
> Framework: docs/plans/2026-07-16-studio-completeness-8-session-orchestration.md (read §2 the bar, §4 your charter, §5 the rules).

## COMMITMENT
S7 is DONE when: the KG write-holes are closed, the world-map + place-graph + cast codex + character-arc are operable — each to the §2 production-ready bar (operable · CRUD · reachable ·
no-silent-fail · agent-parity · loop-connected · live-browser-proven · i18n+responsive · scale).

## SCOPE
- **Persona / files:** features/knowledge, features/world, features/composition/components/WorldMap
- **Panels:** world, world-map, place-graph, cast, character-arc
- **Seam / note:** HEAVIEST session — may sequence its panels. place-graph (work.settings.world_map) != world-map (book-service).

## MANDATE (do this, in order)
1. Role-play a real web-novel author using this tool family — what must they DO?
2. Audit the CURRENT surface against that — what works, what's a skeleton, what's a dead button.
3. Per capability decide PORT / ENHANCE / BUILD — record the call, never silently drop a legacy feature.
4. Write your own detailed design (specs 31–38 are reference; the SOURCE is truth — drift is normal).
5. Build to the §2 bar. `/review-impl` at each panel close, fix what it finds.

## RULES (same-folder)
- Build only under your file subtree. Add catalog rows in your block (catalog.ts, the 8-session section).
- Shared registry (enum/contract/i18n): keep enum == openable == contract; regen `WRITE_FRONTEND_CONTRACT=1 pytest`.
- Never `git add -A`. Commit small + often. `git pull --rebase` before push. Scoped tests during BUILD.
- Stop ONLY for the 4 critical classes: destructive/irreversible · a sealed decision proven wrong ·
  tenancy/security breach · a paid action that charges the user for nothing. Everything else = defer + continue.

## SLICE BOARD  (status: TODO / DOING / DONE — DONE requires an EVIDENCE string, not a checkbox)
| slice | status | evidence (test count / live-smoke line / commit sha) |
|---|---|---|
| S7-A1 · audit current surface (role-play user) | DONE | black-box operability matrix below — code-grounded, file:line |
| S7-A2 · PORT/ENHANCE/BUILD decisions per capability | DONE | 5 decisions below |
| S7-B1 · kg-authoring (s7-1, FS) — Create Entity/Relation + wire delete + 5-kind gate + faction→organization | DONE | 125 FE tests + knowledge pytest 328 pass; kind gate on REST+MCP+3 schema sources |
| S7-B2 · world-map editor (s7-2, Go FS) — 10 REST + 3 MCP update tools + 3-col migration | DONE | book-service go build+vet clean; 388 go tests (30 map-family) inc TestMapUpdateRoundTrip |
| S7-B3 · place-graph port (s7-3, FE) | DONE | leaf-reuse wrapper + worldEffects handler; vitest green |
| S7-B4 · cast + character-arc port + light edit (s7-4, FE) | DONE | CastPanel/CharacterArcPanel + useCastEdit; knowledgeEffect extended w/ composition keys |
| S7-INT · integrator wired registry (catalog/enum/contract/i18n/worldEffects) + verify | DONE (registry UNCOMMITTED — convergence) | tsc EXIT 0; contract regen 20; panelCatalog+effectCoverage 175; enum==openable==contract 63; ai-provider-gate OK |
| S7-VERIFY · live-browser smoke + /review-impl on stack-up | TODO | pending a stack-up (tracked, not skipped) |

**Build committed:** 50 disjoint S7-owned files (components/hooks/tests/backend). The SHARED registry
(catalog.ts, frontend_tools.py enum, contract.json, i18n, handlers/index.ts) is left UNCOMMITTED as
convergence-node work — catalog.ts is co-mingled with S1's SceneComposePanel, so committing it would
entangle tracks. The 4 panels are built+verified but not yet reachable until convergence wires the registry.

### DEFER rows (from the build)
- **D-CAST-ARC-BUS-SLICE** — the tier-2 bus deep-link (`activeCastEntityId` in host/types.ts) not built
  (shared infra, would collide); deep-link works via params (tier 1) + in-panel picker (tier 3). Gate #1.
- **D-KG-ENTITY-RESTORE** — no FE unarchive route (archive is honest about it). Gate #2 structural.
- **D-CAST-KEYSET-PAGING** — both list routes cap at limit:200. Gate #1.
- **D-KG-EVENT-CREATE-ROUTE** — active→gone band read-only; no createEvent route. Belongs to kg-timeline.
- **D-KG-PREDICATE-VOCAB** — relation predicate stays free-string server-side; GUI enum is the right layer.

### DRIFT (honest near-misses from the build)
- Integrator caught an ORCHESTRATION bug: I told both B's world_map_* AND C's kg_* handlers to live in
  worldEffects.ts → a 2nd kg_* handler would make kg_create_node match 2 → red the repo `<=1` no-double-fire
  assertion. Integrator folded C's keys into knowledgeEffect instead of LOWERING the invariant. Bar held.
- s7-1's `+link` relation builder was drawn ON the kg-graph canvas; Group A placed it in EntityDetailPanel
  (node→detail→+link) to avoid editing the shared GraphCanvas primitive. Functionally equivalent, a deviation.
- Retiring `faction` broke a pinned groupCast ordering test — surfaced by running the leaf test, fixed to canonical order.

## S7-A1 · BLACK-BOX OPERABILITY AUDIT (2026-07-16)

**Q: can a user OPERATE Knowledge/World/Cast, or must they call BE / ask the agent?**
**Verdict: NOT comprehensive — "view-rich, author-poor." The KG is populate-by-agent-extraction,
not populate-by-user.**

| Surface | Studio-reachable? | View | Create | Edit | Delete | Verdict |
|---|---|---|---|---|---|---|
| **KG — 13 panels** (`knowledge`,`kg-*`) | ✅ | ✅✅✅ | ❌ **only `location` via map** | ✅ `EntityDetailPanel`→`EntityEditDialog`+merge | ❓ dead buttons? | view-rich, author-poor |
| **Place-graph** (`WorldMap.tsx`) | ❌ **legacy only** | ✅ | ✅ location (`useWorldMap.createPlace`→`createEntity`) | link+drag-persist+backdrop | ? | ONLY operable author — stranded, location-only |
| **Cast codex** (`CastCodexPanel`) | ❌ legacy | ✅+nav | ❌ | ❌ | ❌ | read/navigate only |
| **Character-arc** (`CharacterArcView`) | ❌ legacy | ✅ | ❌ | ❌ | ❌ | pure view (0 buttons) |
| **World maps — book-service** (`WorldMapsSection`) | ✅ `/worlds` | ✅ select | ❌ **routes `/internal` only** | ❌ | ❌ | view/select only |

**Load-bearing fact:** `knowledgeApi.createEntity/createRelation` exist (`api.ts:1607/1617`) but their
ONLY human caller is `useWorldMap.ts:129/134` (add a location via the map). To add a character/faction/
concept, or any non-location relation → **agent extraction or approving proposals only.** No "New Entity"
form despite the API being ready. World-map markers/regions → not even a clean agent path (REST routes
don't exist; UPDATE at no layer — spec 38).

## S7-A2 · PORT / ENHANCE / BUILD
1. **BUILD** — general Create Entity/Relation authoring on `kg-entities`+`kg-graph` (all kinds; API ready).
2. **PORT** — `WorldMap.tsx`, `CastCodexPanel`, `CharacterArcView` → Studio dock panels (leaf-reuse).
3. **ENHANCE** — cast + character-arc gain light editing (currently pure view).
4. **BUILD (real BE)** — reachable world-map marker/region routes (~8–10; design the missing UPDATE).
5. **VERIFY/FIX** — `kg-overview` dead buttons + the KG delete/archive path (the ❓ cells).

## RESUME after compaction: re-read this file → git log -15 → continue at first build slice after A2.

## REGISTERS  (append as you go — an empty DRIFT log at the end is dishonest, not clean)
### DECISIONS
### PARKED  (blocker -> defer row + continue)
### DEBT
### DRIFT  (near-misses, bars nearly lowered, tests nearly skipped)
