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
| S7-VERIFY · live-browser blackbox smoke on a REBUILT stack | DONE | **4/4 blackbox author-journeys PASS on the real app** (vite :5199 → gateway :3123, rebuilt backends): cast+arc 4.9s · kg-authoring 5.7s · place-graph 12.0s · world-map 5.9s = 4 passed (30.1s) |

## S7-VERIFY · BLACKBOX-USER EVALUATION (2026-07-17, on the REAL app)

**Question the goal posed: is S7 actually USABLE, or does it only answer to the BE/agent?**
**Answer: USABLE. All 4 surfaces pass a blackbox author-journey end-to-end on the real running app.**

Setup: infra rebuilt (postgres/neo4j/redis/rabbitmq/minio), **knowledge-service + book-service images
REBUILT** (they were baked ~10h stale — see the finding below), gateway :3123, frontend on vite dev :5199
(the S7 working-tree code). Test account logs in through the real UI; each journey seeds via the real API
(incl. S7's own createEntity/createWorld routes) and drives the app as a user.

| Journey | Verdict | What a real user proved they can DO |
|---|---|---|
| KG authoring | ✅ 5.7s | reach kg-entities from the palette → hand-author a character with the kind ENUM → open its detail (a row OPENS, not a dead tile) → edit → create a relation → **archive → Undo → restore round-trip** → deep-link from the graph. |
| World-map | ✅ 5.9s | reach world-map → create a map + upload a base image → drop & DRAG a pin (persists on a stable id) → relabel/rebind → draw & RESHAPE a region (the Phase-B dead-read fix) → book→world→map loop. |
| Place-graph | ✅ 12.0s | reach place-graph (was legacy-stranded) → add a place → link two with a predicate (the edge lands) → DRAG a node (persists) → deep-links to cast + kg-entities. |
| Cast + arc | ✅ 4.9s | reach cast → the codex groups the seeded cast → open a character's arc → switch subject via the bus → light-edit → +Add-event lands on the timeline. |

🔴 **THE FINDING that this blackbox run exists to catch** (the `live-smoke-rebuild-stale-images-first` law):
the first run FAILED at KG STEP 6 (restore → 404) and looked like a real bug. Root cause: the deployed
knowledge-service/book-service were **baked images built 12:09, ~10h OLDER than the S7 route commits
(21:50)** — so `POST /entities/{id}/restore` hit FastAPI's no-such-route 404, and `kind:'item'` would have
422'd on the stale 4-kind gate. The restore route + the 5-kind gate + createEvent + the world-map routes
were all correct on disk (unit tests green); they just weren't deployed. **Rebuilding the two images made
all 4 journeys pass** and the archive→restore round-trip return 204. A mock-only suite would never have
caught that the *deployed* backend was stale — the exact value of a real-app blackbox smoke.

**Remaining honest gaps** (do not affect the "usable" verdict): the 4 journeys run SERIALLY (parallel on
the one shared dev account collides — `shared-dev-db-not-clean-fixture-e2e`); the SVG edge assertion uses
`toBeAttached` not `toBeVisible` (SVG `<g>` has no CSS box — a Playwright quirk, not a product issue).

**Build committed:** 50 disjoint S7-owned files (components/hooks/tests/backend). The SHARED registry
(catalog.ts, frontend_tools.py enum, contract.json, i18n, handlers/index.ts) is left UNCOMMITTED as
convergence-node work — catalog.ts is co-mingled with S1's SceneComposePanel, so committing it would
entangle tracks. The 4 panels are built+verified but not yet reachable until convergence wires the registry.

### DEFER rows — DISPOSITIONED (2026-07-16, "clear defers first")
- ✅ **D-KG-ENTITY-RESTORE — CLEARED.** The `restore_entity` repo function already existed (engine present
  ⇒ buildable, not blocked). Added `POST /v1/knowledge/me/entities/{id}/restore` + `restoreMyEntity` client
  + `useRestoreEntity` hook + an **Undo** action on the archive success toast (archive is no longer a
  one-way trap). Also updated the confirm copy that used to say "no restore button". 4 backend tests pass.
- ✅ **D-CAST-KEYSET-PAGING — silent part CLEARED, full keyset kept deferred.** `useCast` caps at limit:200;
  a silent cut let a large cast look complete. Added a **truncation notice** (the silent-success law) when
  the count hits 200. Full keyset paging past the cap remains its own slice (Gate #1) — a >200 cast is rare.
- ↪ **D-CAST-ARC-BUS-SLICE — RECLASSIFIED to convergence-node.** The tier-2 bus deep-link touches SHARED
  `host/types.ts` (S1/S5 also use the bus); editing it mid-multi-session risks a race. The deep-link is
  fully functional via tier-1 (params) + tier-3 (in-panel picker), so this is a live-update polish, not a
  gap — done safely at the convergence node, not raced now. (Gate #1: shared-infra convergence work.)
- ✅ **D-KG-EVENT-CREATE-ROUTE — EARNS its row (out of scope).** Creating timeline events is a `kg-timeline`
  surface concern, not cast/arc; no createEvent route at any layer. Gate #1 (different surface).
- ✅ **D-KG-PREDICATE-VOCAB — CLOSED (conscious won't-fix, Gate #5).** The relation predicate stays a free
  string server-side (server enforcement would break agent `kg_propose_edge` + extraction edges); the GUI
  enum is the correct layer. This is a design decision, not debt.

### DEBT DISPOSITION (2026-07-17, "continue clearing debt, non-lazy")
Investigated every remaining debt item; built what was buildable, and for the rest verified WHY it's
legitimately not a fix (not a lazy dodge):
- ✅ **place-graph delete — CLEARED.** The blocker was "id-equivalence unproven". Proven LIVE on the
  running stack: a place node's `id` == the createEntity id == the id `DELETE /me/entities/{id}` accepts
  (204). Wired a delete affordance → `archiveMyEntity` + places invalidation.
- ✅ **D-WORLDMAP-POLY-SIMPLIFY — CLEARED (bounded).** A very-high-vertex region rendered one drag handle
  per vertex silently; added a vertex-handle cap + an honest notice above the cap (mirrors the cast-paging
  pattern). The polygon still renders/selects/deletes; only per-vertex reshape is capped. Full
  Douglas-Peucker simplify stays gate #4 (perf-when-profiled).
- 🚫 **D-WORK-SETTINGS-OCC — DISSOLVED (not a real debt).** Investigation showed `works.py` ALREADY merges:
  `settings = COALESCE(settings,'{}'::jsonb) || $n::jsonb` — so concurrent writers to DIFFERENT sub-keys
  (place-graph positions vs style/voice vs model refs) do NOT clobber each other (the REPLACE-vs-merge bug
  was already fixed by BE-18). The only residue is two devices writing the SAME sub-key concurrently
  (e.g. dragging the same place-graph on two devices) → last-write-wins, which is acceptable UX for a
  position drag. **Conscious-accept (gate #5), no spec needed.** (The "server replaces" comment in
  `CompositionSettingsView.tsx:7` is stale — the server merges.)
- ↪ **i18n other-locales — convergence translate-pass (not lazy).** The new S7 keys are in `en` and every
  component uses `t(key, {defaultValue})`, so all 17 other locales render the English fallback — the app is
  fully USABLE in every locale today. Translating is a single `scripts/i18n_translate.py` pass at
  convergence for ALL sessions' new keys at once; running it per-session on the co-mingled locale files
  would be 8× the LLM cost and 8× the collision risk on shared files. Deferred to the convergence i18n pass.

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
