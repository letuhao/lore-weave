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
| _(build slices appended after A2)_ | | |

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
