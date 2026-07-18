# Wave 8 — KG + World — adjudicated decisions

> 75 items · 68 DECIDED · 7 not-a-question · 0 deferred · 0 escalated.

> **These are INSTRUCTIONS, not suggestions.** Each was settled by reading source. Do not re-open a
> decided question. Where this contradicts the wave plan, **this file wins.**

---

## Decisions

### Q-38-OQ3-RETIRE-DEAD-INTERNAL-IMAGE-ROUTE
RETIRE the internal route. §3.3.2's "mount it twice" is stale — do NOT mount twice; the grep is re-verified as of this commit (zero callers outside book-service itself). In slice M8b.1, do exactly this:

1. `services/book-service/internal/api/maps_image.go` — change the handler signature to take identity from the JWT instead of `?user_id`. Replace lines 30-39:
   - Keep `func (s *Server) uploadWorldMapImage(w http.ResponseWriter, r *http.Request)` as the single (public) entrypoint.
   - Body becomes: `mapID, ok := parseUUIDParam(w, r, "map_id"); if !ok { return }` then `userID, ok := s.requireUserID(r); if !ok { writeError(w, http.StatusUnauthorized, "BOOK_UNAUTHORIZED", "authentication required"); return }` (mirror the exact 401 code string used by the other `requireUserID` call sites at server.go:639/658/727/822).
   - DELETE the `uuid.Parse(r.URL.Query().Get("user_id"))` block and its 400 `"user_id query param required"` error. Everything from the `s.minio == nil` check (line 40) down is unchanged — the owner-scoped SELECT/UPDATE already filter on `owner_user_id=$2/$5`, so the tenancy guarantee is preserved verbatim. No shared-handler extraction is needed; there is only one caller shape.

2. `services/book-service/internal/api/server.go` — DELETE line 200 entirely (`r.Post("/worlds/maps/{map_id}/image", s.uploadWorldMapImage)` from the `/internal` group). ADD, inside the existing `r.Route("/v1/worlds", …)` group at line 381 and BEFORE the `r.Route("/{world_id}", …)` subroute: `r.Post("/maps/{map_id}/image", s.uploadWorldMapImage)  // BE-15f — map base-image upload (JWT-scoped)`. (chi resolves the static `maps` segment ahead of the `{world_id}` param, but keep it above for readability.)

3. `services/book-service/internal/api/mcp_maps.go:5` — update the doc comment: the route is now `POST /v1/worlds/maps/{map_id}/image`, not `/internal/...`.

4. Tests, `services/book-service/internal/api/mcp_maps_test.go`:
   - `mapImageReq` (line ~139): change `url := "/internal/worlds/maps/" + mapID + "/image"` to `"/v1/worlds/maps/" + mapID + "/image"` and drop the `?user_id` param plumbing.
   - REPLACE `TestUploadWorldMapImage_BadUserID_400` with `TestUploadWorldMapImage_NoJWT_401` (no `Authorization` header ⇒ 401).
   - ADD `TestUploadWorldMapImage_RoutedOnV1` — build the full router and assert `POST /v1/worlds/maps/{uuid}/image` (valid JWT, no MinIO) reaches the handler (503 MEDIA_UNAVAILABLE), AND that `POST /internal/worlds/maps/{uuid}/image` now returns 404 (route gone).
   - ADD a regression assert that `GET /v1/worlds/{world_id}` still routes to `getWorld` (proves the new static `maps` sibling didn't shadow the `{world_id}` param route).

5. NO gateway change: `services/api-gateway-bff/src/gateway-setup.ts:90` already proxies every `/v1/worlds*` path to book-service, and express's json/urlencoded parsers do not consume `multipart/form-data`, so the upload streams through. VERIFY this in the wave's live smoke: real JWT → `POST /v1/worlds/maps/{id}/image` through the gateway (:3123) with a small PNG → expect 200 `{image_object_key, image_url, image_w, image_h}` and a non-null `world_maps.image_object_key`. If the proxy is found to buffer/mangle the multipart body, that is a defer row (D-BE15F-GATEWAY-MULTIPART), not a stop.

Default being taken (PO may veto): no BFF-mediated/service-to-service upload path is kept. Rationale — agents cannot upload binaries (the handler's own comment at maps_image.go:9 says so), the only realistic uploader is the browser holding a JWT, and if a future internal caller ever appears the route is 12 lines to re-add. A dead internal route is a standing tenancy-audit false-positive (a `?user_id`-trusting write surface with no caller).

*Evidence:* services/book-service/internal/api/server.go:200 — the sole registration, inside the `/internal` group. Zero callers: `grep -rn "worlds/maps\|/image" services/ frontend/src` hits only book-service's own maps_image.go (handler), server.go:200 (mount), mcp_maps.go:5 (doc comment), mcp_maps_test.go:141 (its own test) — nothing in api-gateway-bff, no other service, no frontend. Public mount point exists: services/book-service/internal/api/server.go:381 (`r.Route("/v1/worlds", …)`); JWT helper: server.go:415 (`requireUserID`). Gateway passthrough already covers it: services/api-gateway-bff/src/gateway-setup.ts:90 (`pathFilter: (pathname) => pathname.startsWith('/v1/worlds')`) + :592-593.

### Q-38-OQ1-WORLD-CONTAINER-OWNER
**(a) — Wave 8b BUILDS the `world` container panel + `world-map`. Track C's P-5 "W10 world container" is RE-SCOPED (not deleted) to the workflow RAIL only.** The M8b.0 gate is SATISFIED BY THIS ROW — the builder does NOT wait for a Track C reply, does NOT stop, and starts 8b immediately after 8a.

WHY THIS IS NOT A REAL COLLISION (the code settles it):
• Track C's "W10" is a *journey/rail*, not a dock panel — arch spec :383 defines it as "Worldbuilding-first 'world container' (prose-less lore/graph/map authoring)". Track C's own Phase-3 close-out re-scoped it OUT of the rails: "The remaining W8/W10/W11 are FE surfaces (P-5), not rails" (RUN-STATE:210).
• Track C P-5 is PARKED (gate #2) with ZERO code: TRACK-C-AUDIT.md:87 → "| W10 world-container surface | ❌ | no files |". `git log -- frontend/src/features/studio/panels/catalog.ts` shows Track C has NEVER touched the dock catalog. There is nothing to collide with.
• **PO-2 already sealed this.** Its consequence column (plan 30:20) reads "Wave 8 = KG write holes **and world maps only**". The `world` container IS the map's host (spec 38 §2.3). Assigning world maps to Wave 8 necessarily assigns their container. An answer of (b) would contradict a §0 SEALED decision — wrong by construction.
• Dependency is one-directional: Track C's W10 rail CONSUMES 8b's panels/REST (book-service maps have zero public REST — spec 38 §1.2). 8b consumes NOTHING from Track C.

CONCRETE BUILDER INSTRUCTIONS:

1. **Record the handoff** (this is all M8b.0 ever asked for). Append verbatim to the Decisions block of `docs/sessions/SESSION_HANDOFF.md`:
   > **OWNERSHIP HANDOFF — `world` container (Q-38-OQ1, resolved 2026-07-13).** Plan 30 **Wave 8b builds** the `world` dock panel + `world-map` panel + book-service's public `/v1/worlds/maps*` REST. **Track C's P-5 "W10 world container" is re-scoped to the WORKFLOW RAIL ONLY** — a row in the `workflows` catalog + its `done_when` steps (Track C's own Phase-3 vocabulary); it builds **no dock panel**. Grounds: Track C P-5 is PARKED with zero files (`TRACK-C-AUDIT.md:87`); Track C has never touched `catalog.ts`; and **PO-2 already sealed "Wave 8 = KG write holes and world maps only"**, which entails the map's host container. Track C's rail consumes 8b's surface; 8b consumes nothing from Track C.

2. **Edit `docs/specs/2026-07-01-writing-studio/38_kg_and_world.md`:** at :428 change **M8b.0** from `GATE — not code` to `✅ SATISFIED (Q-38-OQ1, 2026-07-13 — see SESSION_HANDOFF handoff row)`, and DELETE the clause "BUILD does not start without it". At :456 mark **OQ-1 → RESOLVED (a)**.

3. **Edit `docs/specs/2026-07-09-agent-discoverability-and-workflow/tracks/TRACK-C-AUDIT.md`:** at :63 and :87 and :118, annotate the W10 rows — "surface OWNED-BY-PLAN-30 WAVE 8b; Track C retains the RAIL only." Same annotation on `2026-07-12-track-c-completion-RUN-STATE.md:212` (P-5 row). This prevents Track C re-raising it as its own hole.

4. **Build 8b in the spec's existing order, unchanged:** 8b.1 (book-service public REST + the UPDATE semantics + `version` column) → 8b.2 (`world` container) → 8b.3 (`world-map`).

5. **8b.2 is a PORT, not a build (GG-3).** `frontend/src/features/world/**` already ships `WorldsBrowser`, `LivingWorldTree`, `WorldRollupGraph`, `WorldTimelineSection`, `WorldLorePanel`, `worldsApi`, `useWorlds`/`useWorld`. Register a new panel id `world` in `frontend/src/features/studio/panels/catalog.ts` that HOSTS those existing components. Do not rewrite them. Register in all four places the dock standard requires: catalog row + agent panel enum + `contracts/frontend-tools.contract.json` + i18n.

6. **Close the DOCK-7 leak while you are there.** Add `'/worlds': 'world'` (and the `:worldId` param form) to `PATH_PANELS` in `frontend/src/features/studio/host/studioLinks.ts:46-67`. Today `/worlds/:id` is unmapped → `resolveStudioLink` falls through to `{ kind: 'external' }` (:113), so `KgOverviewPanel.tsx:48` and `BookSettingsPanel.tsx:52` both **pop a new browser tab out of the studio**. The `:id`-safety caveat in the KG comment at :50-57 does NOT apply here — the world id comes from the panel's own data, i.e. the user's own world. Update the two existing tests (`KgOverviewPanel.test.tsx:133`, `BookSettingsPanel.test.tsx:123`) which currently assert the external-tab behavior.

7. **Wave DoD (PO policy #2):** `/review-impl` runs at 8b close; every bug it finds is fixed before the wave closes.

DEFAULT FLAGGED FOR VETO: I picked (a) rather than (c)/split because a split would give two tracks a claim on one `catalog.ts` panel id — the exact concurrent-overwrite class this repo has already been bitten by twice (`efc9fa96e`, `a8700878c` are both "restore catalog/i18n additions dropped by a concurrent session"). One owner for one panel id.

*Evidence:* docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:20 (PO-2 SEALED: "Wave 8 = KG write holes and world maps only" — entails the map's host container) · docs/specs/2026-07-09-agent-discoverability-and-workflow/tracks/TRACK-C-AUDIT.md:87 ("| W10 world-container surface | ❌ | no files |") · docs/plans/2026-07-12-track-c-completion-RUN-STATE.md:210 ("The remaining W8/W10/W11 are FE surfaces (P-5), not rails") and :212 (P-5 PARKED, gate #2) · docs/specs/2026-07-09-agent-discoverability-and-workflow/2026-07-09-agent-discoverability-and-workflow-architecture.md:383 (W10 = a worldbuilding JOURNEY, not a panel) · frontend/src/features/studio/host/studioLinks.ts:46-67 (PATH_PANELS has no /worlds row) + :113 (falls through to kind:'external') · frontend/src/features/studio/panels/KgOverviewPanel.tsx:48 + BookSettingsPanel.tsx:52 (followStudioLink('/worlds/…') → pops a browser tab out of the studio today) · `git log --oneline -- frontend/src/features/studio/panels/catalog.ts` (zero Track C commits)

### Q-38-OQ8-WEBP-NULL-PIXEL-DIMS
ADOPT the spec's answer (render nothing when dims are NULL) — but the code shows OQ-8 understates the defect, so M8b.3 must ship THREE things, not one.

(1) FE — MANDATORY. In the new `world-map` inspector (new code; no panel exists yet), render the dimensions row ONLY when `image_w` and `image_h` are both non-null AND > 0. Otherwise OMIT the row entirely — do NOT render "0 × 0", and do NOT render "unknown" (a placeholder for advisory metadata is noise; the spec offered both, pick omission). Guard: `{m.image_w && m.image_h ? <span>{m.image_w} × {m.image_h}</span> : null}`. Vitest, 2 cases: `{image_w: null, image_h: null}` renders no `×` node; `{image_w: 2048, image_h: 1024}` renders "2048 × 1024".

(2) BE — MANDATORY, and this is the real bug. `image_w`/`image_h` are WRITE-ONLY today: `worldMapDetail` (mcp_maps.go:73-79) has no `ImageW`/`ImageH` fields, and `world_map_get` (mcp_maps.go:264) + `world_map_list` (mcp_maps.go:350) never SELECT them. Only the upload response returns dims, so the inspector would show them right after upload and lose them on reload — for EVERY format, not just WebP. Fix in the same slice: add `ImageW *int \`json:"image_w"\`` / `ImageH *int \`json:"image_h"\`` to `worldMapDetail`; add `image_w, image_h` to both SELECTs and both Scans (mcp_maps.go:264-265 and :350/:360). This is the same stored-but-unread rule the spec already applied to `updated_at` at line 316. Go test: upload a PNG via BE-15f, then assert `world_map_get` returns non-nil `image_w`/`image_h`; assert a map created via `world_map_create` with `image_ref` returns NULL dims.

(3) WebP decoder — CONSCIOUS WON'T-FIX, no defer row (a defer row costs more than the finding is worth). Do NOT add `golang.org/x/image/webp`. Two reasons from code: (a) it is not in book-service's go.mod or the module cache — a new third-party dep for an advisory display string; (b) it would NOT eliminate the NULL case anyway, because `world_map_create` with `image_ref` (mcp_maps.go:116-118) inserts `image_object_key` with no dims at all, so agent-created maps have NULL dims in every format. The FE guard in (1) is required unconditionally; the decoder would buy nothing the guard doesn't already handle. Keep the existing explanatory comment at maps_image.go:16-19 — it is accurate.

Rationale for the builder: markers/regions use relative [0,1] coords (maps_image.go:3-10), so dims are advisory metadata for display only. Nothing in the render path divides by them, so a NULL is never a correctness hazard — only a cosmetic one. Do not add a fallback dim value (e.g. 1000×1000); a fabricated dimension is worse than an absent one.

PO veto point: if you actually want true WebP dims surfaced (e.g. for a future "fit image to canvas" feature), say so and (3) flips to a two-line change — but it still won't cover the `world_map_create` path, which would need its own dim-probe on the referenced object.

*Evidence:* services/book-service/internal/api/maps_image.go:16-19 (no stdlib webp decoder — comment) + :84-88 (imgW/imgH stay nil when DecodeConfig fails) + :107-110 (writes NULL to image_w/image_h) + :120-125 (upload response is the ONLY place dims are returned). THE LOAD-BEARING FINDING: services/book-service/internal/api/mcp_maps.go:73-79 (`worldMapDetail` has ImageObjectKey + ImageURL, NO ImageW/ImageH) + :264-265 (`world_map_get` SELECT omits image_w/image_h) + :350,:360 (`world_map_list` SELECT omits them) ⇒ dims are write-only; the inspector cannot render them at all after reload, for any format. AND services/book-service/internal/api/mcp_maps.go:116-118 (`world_map_create` INSERTs image_object_key from image_ref with no dims) ⇒ NULL dims are NOT webp-specific. Spec ruling this mirrors: docs/specs/2026-07-01-writing-studio/38_kg_and_world.md:316 (write-only column is a banned bug class). Dep check: services/book-service/go.mod has no golang.org/x/image, and it is absent from the local module cache.

### Q-38-OQ7-MARKER-TYPE-VOCAB
SHIP THE FE-LOCAL VOCABULARY IN M8b.3. Retire D-WORLD-MARKER-TYPE-VOCAB — it is answered, not deferred. No BE work.

**1 · BE: change NOTHING.** `marker_type` stays nullable free TEXT (migrate.go:421), a free string in the MCP arg (mcp_maps.go:136), and a free string in BE-15g/BE-15h (spec 38 :300-301). Do NOT add a CHECK constraint, a `marker_kinds` table, or an `enum` on the MCP arg.

**2 · Correct the spec's framing — this is NOT an exception to the closed-set discipline.** Replace the "deliberate, recorded exception" note in 38_kg_and_world.md:463 and the draft hint (screen-world-map.html:837-840) with: the IN-* / `CLOSED_SET_ARGS` enum rule binds **frontend tools** (chat-service `frontend_tools.py` + `contracts/frontend-tools.contract.json`), where an unknown value SILENTLY NO-OPS the GUI (the `panel_id:"editor"` bug). `world_map_add_marker` is a **book-service domain tool**: its value is stored verbatim and rendered, so an unknown value degrades to "default pin", not a silent no-op. The rule demands an enum *for closed sets*; a worldbuilder's pin kinds are genuinely open. No exception is being granted — the rule does not reach here.

**3 · The control: `<input list> + <datalist>`, NOT `<select>` + a "free text…" escape option.** The draft's select-with-escape needs an `isFreeText` mode toggle and a second input, and shadcn `Select` cannot do free text. The repo already has a TESTED native datalist precedent: `frontend/src/features/enrichment/components/compose/ComposeTarget.tsx:74-83` (tests at `ComposeTarget.test.tsx:60,87`). One control = suggestions + free text, zero extra state. Mirror it exactly.

**4 · The vocabulary — ONE home, one name.** New file `frontend/src/features/studio/panels/world/markerTypes.ts`:
`export const MARKER_TYPE_SUGGESTIONS = ['city','town','landmark','ruin','stronghold','temple','battle','region'] as const;`
`city` and `landmark` MUST lead and MUST be spelled exactly as in mcp_maps.go:136 — otherwise the agent writes `city` and the human picks `City` and the data forks into two vocabularies. No other consumer re-declares this list.

**5 · Normalize on write:** `trim().toLowerCase()`; empty string ⇒ send explicit `null` (BE-15h "null = clear"), matching `nullableString()` at mcp_maps.go:169.

**6 · Union with what's already on the map (~3 lines, makes free-text actually usable):** the datalist options = `MARKER_TYPE_SUGGESTIONS` ∪ the distinct non-null `marker_type`s of the markers in the loaded `world_map_get`/BE-15c payload. A user's own custom type then reappears next session without any BE vocabulary existing.

**7 · Render unknowns safely:** the pin icon/colour map is keyed on the 8 known values with a DEFAULT fallback for unknown-or-null. Never blank, never throw.

**8 · Tests (`WorldMapInspector.test.tsx`), all four required:** (a) datalist renders suggestions ∪ existing map types; (b) typing a custom value + blur PATCHes `marker_type` with the trimmed/lowercased custom string (proves it is NOT dropped to a closed set); (c) clearing the field PATCHes explicit `null`; (d) a marker whose `marker_type` is an unknown string renders the default pin (no crash, no blank).

Default I am picking (PO may veto): the 8 words in §4. Any 6-10 word list works; what is load-bearing is that `city`/`landmark` match the tool description verbatim, and that free text survives the round-trip.

*Evidence:* services/book-service/internal/migrate/migrate.go:421 (`marker_type TEXT` — nullable, no CHECK, no vocabulary table); services/book-service/internal/api/mcp_maps.go:136 ('city'/'landmark' exist ONLY inside a jsonschema description string) and :169 (`nullableString(in.MarkerType)` — empty ⇒ NULL); frontend/src/features/enrichment/components/compose/ComposeTarget.tsx:74-83 (existing tested `<input list>`+`<datalist>` suggestions-plus-free-text precedent; tests ComposeTarget.test.tsx:60,87); docs/specs/2026-07-01-writing-studio/38_kg_and_world.md:300-301 (BE-15g/BE-15h carry marker_type as a free string, `null` = clear) and :463 (OQ-7). Sealed §0 PO-1..4 of plan 30 do not touch marker_type — no conflict.

### Q-38-OQ9-LEGACY-WORLDMAP-PLACE-GRAPH-NOT-PORTED
DO NOT port `WorldMap.tsx` as a Studio panel — ever. Conscious won't-fix (CLAUDE.md defer gate #5), recorded here so it stops re-surfacing. Reason from code: the place-graph's two capabilities are each strictly absorbed by a panel Wave 8 ITSELF ships, and porting it would put two panels named "world map" in one dock over two different data models — the exact "one name for one concept" violation PO-3 sealed against.

(a) AUTHORING (add place / link places) → `kg-entities` + `kg-graph` after M8a.1 (A1 create entity, A2 create relation). `useWorldMap.ts:129,134` are the only callers of `createEntity`/`createRelation`; M8a.1 moves that capability into the KG panels, which is exactly what OQ-9 already says.
(b) SPATIAL ARRANGEMENT (drag positions + backdrop image) → the NEW `world-map` panel (spec 38 step 1b). It is the same idea with a better model: world-scoped + versioned + MCP-paired (BE-15m) + `map_markers.entity_id` / `map_regions.entity_id` already in the DDL, vs. the place-graph's untyped `composition_work.settings.world_map` JSON blob that has zero MCP tools (a live GG-2 inverse-gap).

TWO CONCRETE EDITS THE BUILDER MAKES:

1. SPEC EDIT (do first — the current text is WRONG). In `docs/specs/2026-07-01-writing-studio/38_kg_and_world.md:465`, replace OQ-9's resolution. It currently says the place-graph "belongs to plan 30's Wave 6 editor-craft ports". It does not: spec 36 is written, and Wave 6's panels are `style-voice` · `reference-shelf` · `divergence` · book-settings-Composition · plan-hub decompose (`30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:426-436`), with no place-graph gap row. Leaving OQ-9 pointed at Wave 6 is a silent drop. New resolution text: "RESOLVED — won't-port. Superseded by `kg-entities`/`kg-graph` (authoring, M8a.1) + the `world-map` panel (spatial, M8b). See D-WORLDMAP-PLACE-GRAPH-WONTPORT."

2. BUILD SLICE — fold into M8b (the `world-map` panel), because it closes the ONE capability that would otherwise have no replacement: `WorldMap.tsx:44-48` lets the writer click a place node and open it in the codex (`onViewCast`). In `frontend/src/features/studio/panels/WorldMapPanel.tsx`, the marker/region inspector MUST (i) expose an entity picker that sets `entity_id` (the field already exists end-to-end: `map_markers.entity_id` at `services/book-service/internal/migrate/migrate.go:417`, `map_regions.entity_id` at `:431`, and it is already in the BE-15g/BE-15h/BE-15j/BE-15k payloads specced at `38_kg_and_world.md:300-305`) — the picker reads entities from `knowledgeApi.listEntities({ kind: 'location' })`, the same query `useWorldMap.ts:70` runs; and (ii) when a marker carries `entity_id`, render an "Open in codex" action that opens `kg-entities` focused on that entity via `followStudioLink` (NOT `<Link>` — DOCK-7 hygiene reds on it). Tests: a vitest asserting the picker PATCHes `entity_id` and that a bound marker renders the open-in-codex action; a Go handler test asserting `entity_id` round-trips through BE-15h (absent = unchanged, `null` = clear, per the spec's PATCH semantics).

TRACKING ROW (add to spec 38's defer table + `docs/deferred/DEFERRED.md`): `D-WORLDMAP-PLACE-GRAPH-WONTPORT` — origin Wave 8 / OQ-9 — `features/composition/components/WorldMap.tsx` + `useWorldMap.ts` + `PlaceNode.tsx` and the `composition_work.settings.world_map` blob are NOT ported; they die with `ChapterEditorPage`. Gate reason #5 (conscious won't-fix). Trigger: delete the three files in the same commit that retires `ChapterEditorPage` (spec 36 OQ-2 keeps the page as a deprecated fallback for now, so NOTHING is lost before then — GG-4 is satisfied). No DB migration is owed: `settings.world_map` is a JSON key on a per-work blob; it is orphaned, not corrupting. Note explicitly that location↔location relation EDGES (`contains`/`borders`/`route_to`, `useWorldMap.ts:19`) survive in `kg-graph`, which renders relations — they are KG data, not place-graph data, so deleting the component deletes no user content.

PO VETO NOTE: the default I picked is "no ninth panel — the world-map panel IS the place map". If the PO actually wants an edge-drawing spatial canvas (pins connected by `borders`/`route_to` lines on the backdrop), that is a strict superset of the `world-map` panel and belongs there as a v2 overlay on top of the same `world_maps` tables — still not a port of the legacy blob-backed component.

*Evidence:* frontend/src/features/composition/hooks/useWorldMap.ts:129,134 (the only human writers of createEntity/createRelation; M8a.1 supersedes them) · useWorldMap.ts:94-115 (positions+backdrop live in composition_work.settings.world_map, a JSON blob with zero MCP tools) · frontend/src/features/composition/components/WorldMap.tsx:44-48 (onNodeActivate → onViewCast, the one affordance needing a replacement) · CompositionPanel.tsx:775 + PowerViewOverlay.tsx:95 (both mount sites are legacy-page-only; zero Studio refs) · services/book-service/internal/migrate/migrate.go:417,431 (map_markers.entity_id / map_regions.entity_id already exist — the pin↔location binding is unbuilt FE work, not a missing schema) · docs/specs/2026-07-01-writing-studio/38_kg_and_world.md:331 (WorldMapPanel is already in Wave 8's registration checklist) · docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:426-436 (Wave 6's panel+gap list contains no place-graph — the spec's stated candidate answer is false)

### Q-38-OQ4-NO-UN-FORGET
BUILD RESTORE IN M8a.2 — kill the D-KG-FACT-RESTORE defer row. The spec's gate-#2 claim ("needs a new engine fn + route + tool") is exactly CLAUDE.md's anti-laziness case: an engine fn + route you can write in this repo is unbuilt work, not a blocker. The whole thing is ~60 BE lines in files BE-14b already opens, plus an FE undo. Builder does exactly this:

(1) BE engine — services/knowledge-service/app/db/neo4j_repos/facts.py, immediately after invalidate_fact (which ends at line 700). Add the exact mirror:
    _RESTORE_FACT_CYPHER = "MATCH (f:Fact {id: $id}) WHERE f.user_id = $user_id SET f.valid_until = NULL, f.updated_at = datetime() RETURN f"
    async def restore_fact(session, *, user_id: str, fact_id: str) -> Fact | None  — raise ValueError on empty fact_id; return None when no row (→404); idempotent (restoring a live fact returns it unchanged). Add "restore_fact" to __all__ (the list at facts.py:56).
    HARD CONSTRAINT: restore touches ONLY valid_until (the transaction-time axis invalidate_fact closed at facts.py:669). Do NOT touch archived_at (entity-archive axis) and do NOT touch valid_to_ordinal / valid_to_ordinal_eff (the story-time chain owned by temporal.maintain_chain, facts.py:186-191) — reopening those would corrupt the interval chain.

(2) BE routes — new file services/knowledge-service/app/routers/public/facts.py, copying the shape of routers/public/relations.py:42-93 (facts_router = APIRouter(prefix="/v1/knowledge", tags=["facts"], dependencies=[Depends(get_current_user)])). TWO endpoints, both owner-keyed off the JWT so cross-user collapses to 404 (KSA §6.4, same reasoning as executor.py:713-716):
    POST /facts/{fact_id}/invalidate → {invalidated: true, fact_id}   ← this is BE-14b, it had no home file yet
    POST /facts/{fact_id}/restore    → {restored: true, fact_id}      ← the un-forget
    Emit NO outbox event from either — there is no FACT_CORRECTED type (outbox_emit.py:63-65 has entity/relation/event only) and memory_forget emits none today. Do not invent one.
    Register in services/knowledge-service/app/main.py next to public_relations.relations_router (main.py:771).

(3) BE list — make restored/forgotten facts reachable, else the restore route is dead surface. In facts.py _LIST_FACTS_FOR_ENTITY_BODY change line 599 from `AND f.valid_until IS NULL` to `AND ($include_invalidated OR f.valid_until IS NULL)`; add `include_invalidated: bool = False` to list_facts_for_entity (default False = byte-identical current behavior for the L2 loader) and pass it through. Add `include_invalidated: bool = Query(default=False)` to GET /entities/{entity_id}/facts (entities.py:635-659). The Fact model already carries valid_until (facts.py:114), so the FE gets the flag for free.

(4) FE — frontend/src/features/knowledge/api.ts: add invalidateFact(factId, token) + restoreFact(factId, token) next to invalidateRelation (api.ts:1721-1727); add `valid_until?: string | null` to EntityFact; thread `include_invalidated` into getEntityFacts (api.ts:1903-1914) and useEntityFacts.ts (put it in the queryKey). EntityDetailPanel.tsx facts list (~:135): A4 Forget row action → confirm dialog → on success show an UNDO TOAST (10s, closes over the fact_id) that calls restoreFact and invalidates the ['knowledge-entity-facts', userId, entityId] query. Plus a "Show forgotten" checkbox that flips include_invalidated; forgotten rows render muted with a Restore button.

(5) COPY — the A4 confirm dialog no longer lies. Replace spec line 153's "there is no un-forget button" with: "Forgetting hides this fact from future context loads. It is not deleted — you can restore it from Show forgotten." Update 38_kg_and_world.md OQ-4 to RESOLVED-BUILT and delete the D-KG-FACT-RESTORE row.

(6) SEPARATE BUG THIS EXPOSES — fix it in the same slice, it is a 1-line change and a "silent success is a bug" instance: merge_fact's ON MATCH (facts.py:200-243) does NOT clear valid_until, while create_relation's ON MATCH does (relations.py:1292-1299, "RESURRECTS a previously-invalidated tuple"). Because the fact id is content-keyed (facts.py:307), re-remembering a forgotten fact hits the same invalidated node and memory_remember still answers {"remembered": true} (executor.py:702-707) though the fact stays hidden forever. Do NOT blanket-resurrect in the extraction path (that would let re-extraction silently undo a human's Forget — the F5 rule relations already respects). Instead: add a `resurrect: bool = False` kwarg to merge_fact whose ON MATCH clause sets `f.valid_until = CASE WHEN $resurrect THEN NULL ELSE f.valid_until END`, and pass resurrect=True ONLY from _handle_memory_remember (executor.py:692-701) — a human/agent explicitly re-asserting the fact is the same intent as recreate_relation. Test: forget → remember same text → fact is live again and appears in list_facts_for_entity.

TESTS (all must exist before the wave closes): unit — restore_fact returns None for unknown/cross-user id; restore is idempotent; restore does not mutate archived_at or valid_to_ordinal. Integration (tests/integration/db/test_facts_repo.py, next to test_k11_7_invalidate_fact_sets_valid_until at :327) — invalidate → restore → fact reappears in list_facts_for_entity with default filters. Router unit — POST /facts/{id}/restore 404s for another user's fact. merge_fact resurrect test per (6). FE — vitest on the undo toast calling restoreFact with the forgotten fact's id and refetching.

DEFAULT I AM PICKING (veto-able): NO MCP `memory_restore` agent tool in v1. Un-forget is a human mis-click recovery, not agent logic; the MCP-first invariant governs agentic capabilities, and the REST mirror is already the sanctioned GUI path (BE-14b). If an agent ever needs it, the engine fn is there and a tool is a 10-line handler.

*Evidence:* services/knowledge-service/app/db/neo4j_repos/facts.py:666-700 (invalidate_fact — the only writer of valid_until; nothing clears it) · facts.py:200-243 + :307 (merge_fact ON MATCH never clears valid_until, id is content-keyed ⇒ forget→re-remember silently no-ops) vs services/knowledge-service/app/db/neo4j_repos/relations.py:1292-1299 (create_relation's ON MATCH DOES `r.valid_until = NULL` — the resurrect pattern already exists in this codebase) · services/knowledge-service/app/routers/public/relations.py:63-93 (the invalidate-route template to mirror; recreate/resurrect route at :106-149) · services/knowledge-service/app/tools/executor.py:710-723 (_handle_memory_forget — owner-keyed, emits no event) · facts.py:599 (`AND f.valid_until IS NULL` — why a forgotten fact is unreachable from the list) · services/knowledge-service/app/routers/public/entities.py:631-659 (GET /entities/{id}/facts) · services/knowledge-service/app/events/outbox_emit.py:63-65 (no FACT_CORRECTED — do not invent one) · services/knowledge-service/app/main.py:771 (router registration site)

### Q-38-OQ5-MANUAL-NODE-NO-ANCHOR
NO anchor-on-create in v1 — `POST /v1/knowledge/entities` keeps its current body `{project_id, name, kind}` (no `glossary_entity_id`). Ship the A1 warning as spec'd, BUT the spec's copy is FACTUALLY WRONG and must not be shipped verbatim. The code proves a manual node can NEVER surface as `conflicted`: manual create (`merge_entity`) and the projection (`upsert_glossary_anchor_counted`) derive the SAME `entity_canonical_id(user_id, project_id, canonicalize_entity_name(name), kind, canonical_version)`, so a later projection MERGE-MATCHES the manual node and its `ON MATCH SET e.glossary_entity_id = $glossary_entity_id` ADOPTS it (counted as `existing`). And `entity_glossary_fk_unique` is NULL-exempt, so a NULL-FK manual node cannot raise the ConstraintError that `conflicted` counts. The real risk is narrower — a DUPLICATE node when name-canonicalization or kind differs (`_AUTHORABLE_KINDS = {character, location, faction, concept}` is narrower than the glossary's kind set).

BUILDER INSTRUCTIONS (3 concrete changes, all in M8a.1):

(1) FE — `frontend/src/features/knowledge/components/EntitiesTab.tsx` (create-entity form, per spec 38 §3.1 A1): render a persistent one-line note inside the form (not a toast), i18n key `knowledge.createEntity.anchorNote`, EN copy EXACTLY:
"This creates a graph-only node — it carries no glossary link. Authoring lore? Create it in the glossary and press Seed from glossary, which anchors it. A later seed adopts this node only if the name AND kind match exactly — otherwise you get two nodes for the same thing."
Plus an inline link/button "Open glossary" → `host.openPanel('glossary')` (studio panel host, same pattern A2 uses for `host.openPanel('kg-schema')`). Do NOT say "conflicted"; do NOT say "shadow". The form still exposes only `name` + `kind` (kind `<select>` fed from BE-14c) — no `glossary_entity_id` field.

(2) FE test — `frontend/src/features/knowledge/components/__tests__/EntitiesTab.test.tsx`: assert the note renders whenever the create form is open (query by the i18n key's text), assert the "Open glossary" control calls `host.openPanel('glossary')`, and assert the submitted body has NO `glossary_entity_id` key (guards against a builder "helpfully" adding it).

(3) SPEC correction (do this, don't skip it — a false claim in a spec propagates): edit `docs/specs/2026-07-01-writing-studio/38_kg_and_world.md` line 117 (§3.1 A1 anchor-warning bullet) and line 460 (OQ-5 row) to strike "can shadow ... surfacing as conflicted" and replace with the code-grounded statement: "a same-name+same-kind manual node is ADOPTED by a later projection (`entities.py:487-492`); the real hazard is a DUPLICATE node when kind or canonical name differ. `conflicted` is unreachable from a manual node (NULL FK is exempt from `entity_glossary_fk_unique`, `neo4j_schema.cypher:62-63`)." Cite the file:line evidence in the spec edit.

DEFER row D-KG-MANUAL-NODE-ANCHOR is still filed (gate #2, large/structural) but with the CORRECTED rationale — its value is not "prevents a conflict" (there is none) but "lets a user bind an existing graph-only node to a glossary entity whose kind/name it does NOT match", which is genuinely structural: the route has no `book_id` (would need `projects_repo.project_meta` + a cross-service glossary grant-check to validate the FK), needs `merge_entity_at_id`-style handling, and must return 409 on the `entity_glossary_fk_unique` clash. Not v1.

PO can veto: if you'd rather ship anchor-on-create now, say so — but the code shows the bug it was supposed to prevent doesn't exist, so the warning + duplicate-avoidance copy is the correct v1.

*Evidence:* services/knowledge-service/app/db/neo4j_repos/entities.py:339-347 (merge_entity → entity_canonical_id) · :568-575 (upsert_glossary_anchor_counted → SAME entity_canonical_id) · :487-492 (_UPSERT_ANCHOR_CYPHER ON MATCH SET e.glossary_entity_id — the adoption) · services/knowledge-service/app/db/neo4j_schema.cypher:62-63,71 (entity_glossary_fk_unique = (user_id,project_id,glossary_entity_id) UNIQUE; "Neo4j exempts rows with ANY NULL in the key") · services/knowledge-service/app/extraction/anchor_loader.py:231-244 (conflicted++ ONLY inside `except ConstraintError`) · services/knowledge-service/app/routers/public/entities.py:975 (_AUTHORABLE_KINDS = {character,location,faction,concept}) and :999-1032 (POST /entities body has no glossary_entity_id; calls merge_entity with source_type='manual')

### Q-38-BE-15a-MAP-CREATE
BUILD IT — the route does not exist (the `/v1/worlds` chi group at `services/book-service/internal/api/server.go:381-392` mounts only worlds + `/books`; no `/maps` subtree anywhere). This is unbuilt work, not a question. Concrete instruction for M8b.1:

1) NEW FILE `services/book-service/internal/api/maps.go` (REST siblings of the `world_map_*` MCP tools; keep `mcp_maps.go` for the tools).

2) Extract ONE core so the tool and the route provision identically (mirror the `createWorldCore` precedent, `mcp_worlds.go:31`):
   `func (s *Server) createMapCore(ctx context.Context, ownerID, worldID uuid.UUID, name, imageRef string) (worldMapDetail, error)` in `maps.go` — body lifted verbatim from `toolWorldMapCreate` (`mcp_maps.go:93-124`): world-ownership `SELECT EXISTS(SELECT 1 FROM worlds WHERE id=$1 AND owner_user_id=$2)`, then `INSERT INTO world_maps(owner_user_id, world_id, name, image_object_key) VALUES($1,$2,$3,$4) RETURNING id, version, updated_at` (`nullableString(imageRef)`), then `s.withImageURL(&d)`. Rewrite `toolWorldMapCreate` to call it (no behavior change; its existing tests in `mcp_maps_test.go` must stay green). Widen `worldMapDetail` (`mcp_maps.go:70-76`) with `Version int \`json:"version"\`` and `UpdatedAt time.Time \`json:"updated_at"\`` — that is the SAME struct BE-15b/15c/15d return, so the create 201 body and the list/get bodies cannot drift.

3) HANDLER `func (s *Server) createWorldMap(w http.ResponseWriter, r *http.Request)`:
   - `worldID, ok := parseUUIDParam(w, r, "world_id")` (`server.go:432`); then `ownerID, ok := s.requireWorldOwner(w, r, worldID)` (`worlds.go:333`) — it already writes the uniform 401 `BOOK_FORBIDDEN` and the no-oracle 404 `WORLD_NOT_FOUND` for foreign-OR-missing, exactly as the spec demands. Do NOT hand-roll the ownership query.
   - Decode `{name string, image_ref string}`; a decode failure OR `strings.TrimSpace(name) == ""` ⇒ `writeError(w, http.StatusUnprocessableEntity, "MAP_VALIDATION_ERROR", "name is required")`. DEFAULT I AM SETTING (veto-able): the map routes use **422** per the spec table even though the older world handlers use 400 `BOOK_VALIDATION_ERROR` — the spec's contract is what the FE will code against; do not "harmonize" it to 400.
   - Call `createMapCore`; on error `writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to create map")`; on success `writeJSON(w, http.StatusCreated, map[string]any{"map": d})` — i.e. the body is `{map: {...}}`, matching `worldMapCreateOut`.
   - `image_ref` is trusted-as-given (an already-uploaded MinIO key), same as the tool — no blob existence check.

4) ROUTES in `server.go` inside `r.Route("/v1/worlds", ...)`: add the static `/maps/{map_id}` subtree BEFORE/alongside `r.Route("/{world_id}", ...)` (chi prefers static over param — the `/internal/worlds/maps/{map_id}/image` mount at `server.go:200` already proves the shape), and inside the `{world_id}` group add `r.Post("/maps", s.createWorldMap)` (+ `r.Get("/maps", s.listWorldMaps)` for BE-15b). Zero gateway changes: `worldsProxy` already passes everything under `/v1/worlds` (`services/api-gateway-bff/src/gateway-setup.ts:82-90, 592`).

5) MIGRATION (same slice, needed for the `version` field this response returns): `ALTER TABLE world_maps ADD COLUMN IF NOT EXISTS version INT NOT NULL DEFAULT 1;` in `services/book-service/internal/migrate/migrate.go` next to the `world_maps` DDL (line ~401 — `updated_at` already exists there; `map_markers`/`map_regions` still need their `updated_at` for BE-15c).

6) TESTS `services/book-service/internal/api/maps_test.go` (Go, table-driven, next to `worlds_test.go`): (a) 201 — body has `map.map_id`, `world_id`, `name`, `image_object_key`, `image_url` (non-null when `image_ref` given), `version==1`, `updated_at`; (b) 401 no Bearer; (c) 404 world owned by another user AND 404 world_id that does not exist — assert the response bodies are BYTE-IDENTICAL (no existence oracle); (d) 422 on `name: "   "`; (e) the row lands with `owner_user_id == caller`. Plus a curl smoke through the gateway on :3123 as M8b.1's row already requires.

*Evidence:* services/book-service/internal/api/server.go:381-392 (the `/v1/worlds` route group — proves POST /v1/worlds/{world_id}/maps does NOT exist today); services/book-service/internal/api/mcp_maps.go:93-124 (`toolWorldMapCreate` — the logic to lift, incl. the owner-EXISTS world gate and the INSERT); services/book-service/internal/api/worlds.go:333 (`requireWorldOwner` — the ready-made 401/404-no-oracle gate); services/book-service/internal/migrate/migrate.go:401-412 (`world_maps` DDL — has `updated_at`, lacks `version`); services/api-gateway-bff/src/gateway-setup.ts:82-90 (worldsProxy pathFilter `/v1/worlds` ⇒ no gateway change needed)

### Q-38-OQ10-EDGE-DELETE-FROM-CANVAS
BUILD IT — hard-commit to the spec's v1 option ("expose the existing RelationEditDialog from the canvas edge"), in slice M8a.1 alongside A2. NO "say so in the UI" apology copy: draw-with-no-erase never ships. Two clarifications on the spec's wording, both grounded below: (a) bind BOTH left-click AND contextmenu, not right-click only (right-click is unreachable on touch and a left-click on an edge is a no-op today, so there is no conflict); (b) the wiring is NOT "zero backend, one wiring" — it is one wiring PLUS a cache-coherence fix, because the mutation hooks cannot reach the canvas's hand-rolled state.

EXACT BUILDER INSTRUCTIONS (4 files, ~40 lines):

1. frontend/src/features/composition/components/RelationEdge.tsx — add an OPTIONAL prop `onSelect?: (edge: GraphEdge, ev: React.MouseEvent) => void`. Attach it to the EXISTING fat transparent hit-line (line 26-28; the visible line is pointerEvents="none", so the hit-line is the only target): `onClick={(ev) => { if (!onSelect) return; ev.stopPropagation(); onSelect(edge, ev); }}` and `onContextMenu={(ev) => { if (!onSelect) return; ev.preventDefault(); ev.stopPropagation(); onSelect(edge, ev); }}`; `style={{ cursor: onSelect ? 'pointer' : 'help' }}`. The prop MUST be optional — the other three call sites (RelationshipMap.tsx:100, WorldMap.tsx:194, WorldRollupGraph.tsx:156) pass nothing and stay read-only.

2. frontend/src/features/knowledge/hooks/useProjectSubgraph.ts — add `dropEdge(edgeId: string)` to the returned object. It MUST do all three: (i) `setAccreted(prev => ({ ...prev, edges: prev.edges.filter(e => e.id !== edgeId) }))`; (ii) prune the edge from the react-query caches — `queryClient.setQueriesData({ queryKey: ['knowledge-subgraph', userId] }, old => old ? { ...old, edges: old.edges.filter(e => e.id !== edgeId) } : old)` and the same for the `['knowledge-subgraph-ego', userId]` prefix (a cached ego payload within its 30s staleTime would otherwise re-inject the dead edge on the next expand); (iii) `void baseQuery.refetch()` to reconcile with server truth (a Correct mints a NEW edge id — only the refetch brings it in). Also add `['knowledge-subgraph', userId]` to the prefix list invalidated by `useDetailInvalidation()` in useRelationMutations.ts:17-26 — that fixes the base query for the ALREADY-LATENT case where the user marks an edge wrong from the canvas's EntityDetailPanel (ProjectGraphView.tsx:170) and the edge stays drawn.

3. frontend/src/features/knowledge/components/RelationEditDialog.tsx — add `onMutated?: (rel: EntityRelation, verb: 'create' | 'correct' | 'invalidate') => void`, fired from all three mutations' onSuccess (A2 already adds the `create` verb + `useCreateRelation` to this same dialog per spec §3.1 A2; reuse that callback, do not add a second one). The dialog otherwise needs no change — the schema-fed `<select>` A2 installs for the predicate is inherited by this path for free (closes OQ-6's FE half on the canvas edge too).

4. frontend/src/features/knowledge/components/ProjectGraphView.tsx — (a) `const [editingEdgeId, setEditingEdgeId] = useState<string | null>(null)`; (b) line 149 becomes `renderEdge={(e, from, to) => <RelationEdge edge={e} from={from} to={to} onSelect={(edge) => setEditingEdgeId(edge.id)} />}`; (c) a pure local helper `subgraphEdgeToRelation(e, byId)` that synthesizes the `EntityRelation` the dialog wants (api.ts:497 — id/subject_id/object_id/predicate/confidence from the GraphEdge; subject_name/object_name/kinds from the existing `byId` node map at ProjectGraphView.tsx:76; source_event_ids: [], the nullable timestamps null, pending_validation false); (d) mount a second `<RelationEditDialog open={!!editingEdgeId} relation={editingRelation} onOpenChange={o => { if (!o) setEditingEdgeId(null); }} onMutated={(rel, verb) => { if (verb === 'invalidate') sg.dropEdge(rel.id); else { sg.dropEdge(editingEdgeId!); } }} />` next to the existing EntityDetailPanel mount (line 170) — invalidate drops the edge; correct drops the OLD id and the dropEdge refetch brings in the new one. (e) Update the toolbar hint at line 127 (`graph.hint`) to add "· click an edge to fix or remove it" (new i18n key or extend the defaultValue; WorldRollupGraph.tsx:132 shares the key — give the graph panel its own key `graph.hintEditable` rather than mutating the shared one, per the css-var-duplicated-drifts lesson).

TESTS (all three are the Definition of Done for this item):
- frontend/src/features/knowledge/components/__tests__/ProjectGraphView.test.tsx (exists) — `fireEvent.contextMenu` AND `fireEvent.click` on the edge hit-line each open the dialog with the predicate prefilled; then click `relation-edit-invalidate` (stub window.confirm true) and assert `screen.queryAllByTestId('relmap-edge')` goes 1 → 0 WHILE THE MOCKED BASE QUERY STILL RETURNS THE EDGE. That last clause is the whole point: it proves dropEdge pruned the accreted/cached copy and not merely that a refetch happened. A test that also changes the mocked payload proves nothing.
- frontend/src/features/composition/components/__tests__/RelationshipMap.test.tsx — assert no-handler ⇒ contextMenu on the edge does NOT preventDefault / opens nothing (the other three call sites stay read-only).
- frontend/tests/e2e/specs/studio-kg-write.spec.ts (already mandated by §9 DoD #4) — do the "Mark wrong on that edge and assert it is gone" leg FROM THE CANVAS EDGE (right-click the edge in kg-graph), then RELOAD and assert it is still gone.

PO VETO POINT (stated so it can be overridden without re-opening the design): left-click-on-edge is added on top of the spec's right-click. If the PO wants right-click only, delete the onClick binding — everything else stands.

*Evidence:* ProjectGraphView.tsx:149 (`renderEdge={(e, from, to) => <RelationEdge edge={e} from={from} to={to} />}` — the view owns edge rendering; GraphCanvas needs no change) · RelationEdge.tsx:26-28 (the fat transparent hit-line, cursor:'help', already exists — the handler target; visible line is pointerEvents="none") · RelationEdge call sites RelationshipMap.tsx:100, WorldMap.tsx:194, WorldRollupGraph.tsx:156 (⇒ the prop must be optional) · THE TRAP: useRelationMutations.ts:17-26 invalidates ONLY ['knowledge-entity-detail', userId], while the canvas renders ['knowledge-subgraph', userId, projectId] MERGED WITH hand-rolled useState `accreted` (useProjectSubgraph.ts:98, merged at :133) — so invalidateQueries alone cannot un-draw the edge (the `invalidatequeries-cannot-reach-hand-rolled-state` bug class), and this is ALREADY LATENT today for Mark-wrong via the canvas's EntityDetailPanel mount at ProjectGraphView.tsx:170 · spec 38_kg_and_world.md:128 already states the requirement inside A2 ("the kg-graph canvas must expose the dialog from an edge right-click too"), so this is a hard-commit, not a new design · RelationEditDialog.tsx:69-76 (markWrong → useInvalidateRelation) and api.ts:497 (EntityRelation shape the dialog needs).

### Q-38-BE-14a-GRANT-LEVEL
CONFIRMED as the spec states it — BE-14a gates on `Depends(require_project_grant(GrantLevel.EDIT))`, NOT the raw JWT. The code verifies every premise of the concern, so this is a build instruction, not an open question.

CONCRETE INSTRUCTION FOR THE BUILDER (M8a.2 / BE-14a):

1. FILE: add the route to `services/knowledge-service/app/routers/public/entities.py`, on `entities_router` (prefix `/v1/knowledge`, already carries a router-level `Depends(get_current_user)` for authN — entities.py:131-134). Path: `@entities_router.post("/projects/{project_id}/project-entities")`. Sibling project-scoped routes already live there (`/projects/{project_id}/gaps` at :688, `/subgraph` at :747), so the prefix and path shape land exactly on the spec's `POST /v1/knowledge/projects/{project_id}/project-entities`.

2. GATE (the load-bearing line):
   `from app.auth.grant_deps import GrantLevel, require_project_grant`
   `owner_user_id: UUID = Depends(require_project_grant(GrantLevel.EDIT))`
   Do NOT use `get_current_user` as the authorization identity. The router-level `get_current_user` stays (it only authenticates); the per-route grant dep is the authorization.

3. USE THE RETURNED VALUE AS THE OWNER, NOT THE CALLER — this is the half of the fix that is easy to miss. `require_project_grant` is **resolve-to-owner**: it returns the PROJECT OWNER's user_id (grant_deps.py:108-122, `_resolve_owner` at :91-105), not the caller's. Pass it straight through as `user_id=str(owner_user_id)` to `project_glossary_entities_to_nodes(...)` (`app/extraction/anchor_loader.py:193-200`), which is precisely what the tool does with `owner = await _resolve_project_owner(ctx, GrantLevel.EDIT)` (graph_schema_tools.py:1638) → `user_id=str(owner)` (graph_schema_tools.py:1660). If you pass the caller's id instead, an EDIT-collaborator's projection lands in the WRONG graph partition — a silent data bug on top of the authz one.

4. DO NOT use `require_project_principals` here. That factory (grant_deps.py:125-147) exists for BYOK dual-identity billing (extraction bills the caller's key). BE-14a makes zero provider calls — it is a deterministic glossary→Neo4j upsert — so it needs one identity (the owner) and `require_project_grant` is the right dependency.

5. FREE ERROR SEMANTICS you inherit from the dep, do not re-implement: missing project / non-grantee / book-less-non-owner → uniform **404**; grantee below EDIT → **403** (grant_deps.py:82-105, anti-oracle). Only the `book_id is None` case needs a hand-written **409** carrying the tool's own message ("this project isn't linked to a book, so it has no glossary entities to project — link a book to the project first", graph_schema_tools.py:1643-1647); resolve it with `projects_repo.project_meta(project_id)` exactly as the tool does at :1639.

6. TEST (the regression lock — assert the effect, not the decorator): in the knowledge-service suite, `test_project_entities_route_honors_edit_grant` — three cases against the route: (a) owner → 200; (b) a caller holding EDIT on the project's book (fake `GrantClient.resolve_grant` → `GrantLevel.EDIT`) → 200 **and** the engine is called with `user_id == owner`, not the caller (assert on the spy's kwargs — this catches the step-3 mistake, which a status-code-only test cannot); (c) a caller holding VIEW → 403; a stranger → 404. Mark it `pytest.mark.xdist_group("pg")` if it touches the shared dev DB.

DEFAULT NOTED FOR PO VETO: EDIT (not MANAGE/OWNER) — chosen solely to make the button exactly as strong as the sentence. Raising the GUI above EDIT would re-open the same asymmetry in mirror image (a collaborator who CAN do it via the agent could not do it via the button), so EDIT is the only level that closes GG-2 in both directions.

*Evidence:* services/knowledge-service/app/tools/graph_schema_tools.py:1638 — `owner = await _resolve_project_owner(ctx, GrantLevel.EDIT)` inside `_handle_kg_project_entities_to_nodes` (:1625), with `user_id=str(owner)` passed to the engine at :1660 → the MCP tool DOES admit an EDIT-grantee and DOES run under the project owner. || services/knowledge-service/app/auth/grant_deps.py:108-122 `require_project_grant(need)` + `_resolve_owner` (:91-105) → returns the project OWNER user_id after checking caller==owner OR book-grant >= need; 404 for missing/non-grantee, 403 for under-tier. || Existing in-repo precedent for the identical pattern: app/routers/public/drawers.py:152, app/routers/public/extraction.py:335 and :1054 (`user_id: UUID = Depends(require_project_grant(GrantLevel.X))`). || Route home + prefix: app/routers/public/entities.py:131-134 (`entities_router`, prefix `/v1/knowledge`, router-level `Depends(get_current_user)`), siblings at :688 and :747. || Engine signature (needs book_id + user_id): app/extraction/anchor_loader.py:193-200 `project_glossary_entities_to_nodes(session, glossary_client, *, user_id, project_id, book_id, entity_ids)`. || Spec agreement: docs/specs/2026-07-01-writing-studio/38_kg_and_world.md:281, :286, :391.

### Q-38-OQ2-MARKER-ENTITY-PICKER-SOURCE
ANSWER = (a), now VERIFIED against code, with a bounded fan-out rule. The world-bible entity model DOES hold: the bible is a real `books` row (is_bible=true, world_id set) auto-provisioned with the world, so glossary entities are per-book AND world-level lore at the same time — they live in the bible BOOK.

BUILD INSTRUCTION for M8b.3 (`world-map` inspector entity picker) — no new backend routes needed:

1. RESOLVE THE SOURCE. The panel already has world_id (world_maps is world-scoped). Call the existing `GET /v1/worlds/{world_id}` — its response carries `bible_book_id` (services/book-service/internal/api/worlds.go:188 SQL, :202 worldResponse). Do NOT add a route; do NOT use the internal `/internal/worlds/{id}/bible` (that is internal-token only, server.go:199).

2. DEFAULT LIST = the world bible's location entities. Reuse the EXISTING FE fn `glossaryApi.listEntities(bibleBookId, {kindCodes:['location'], status:'active', searchQuery:q, limit:50}, token)` (frontend/src/features/glossary/api.ts:85-96 → `GET /v1/glossary/books/{book_id}/entities?kind_codes=location&search=…`, glossary-service/internal/api/server.go:486). Do not write a new api fn.

3. SECOND TIER = a "Source" <select> in the picker header, defaulting to "World bible", whose other options are the world's member books from the EXISTING `worldsApi.listWorldBooks(token, worldId)` (`GET /v1/worlds/{world_id}/books` — bible books already excluded by the BE, worlds.go:477). Selecting a member book re-runs the SAME listEntities call with that book_id. LAZY, one book at a time: do NOT eagerly fan out over all member books (there is no cross-book entity route and building one is out of scope for M8b.3). This is the sane default the PO may veto: bible-first, member books opt-in via the selector — never a silent single-book limitation.

4. FILTER BY CODE, NEVER BY KIND ID. Kinds are per-book rows (`book_kinds`; adopt-per-book at glossary server.go:370, and createEntity 404s "kind not found in this book's ontology" at entity_handler.go:377). A kind UUID from the bible book is meaningless in a member book, so the picker must pass `kind_codes=location` and must never cache/pass a kind_id across books.

5. NULL-SAFE BY CONTRACT. `map_markers.entity_id` / `map_regions.entity_id` are NULLABLE soft cross-service UUIDs with no FK (book-service/internal/migrate/migrate.go:416, :430). The picker MUST offer "No entity (label only)" and clearing an existing link (PATCH entity_id=null). On read, a stored entity_id that no longer resolves in glossary renders the marker's own `label` plus a muted "linked entity not found" hint — never a blank marker and never an error toast (silent-success/blank-panel class).

6. EMPTY STATE, NOT ERROR. A fresh world's bible book may have no adopted ontology / zero location entities. 0 results ⇒ render "No locations in this world's bible yet — add one in the World panel", with the source selector still usable. A 404/empty from glossary is an empty state, not a failure.

TEST (per wave DoD): `frontend/src/features/studio/panels/__tests__/WorldMapInspector.test.tsx` — (i) mock `GET /v1/worlds/{id}` → bible_book_id, assert the picker's first fetch is `/v1/glossary/books/{bible_book_id}/entities?kind_codes=location…`; (ii) switching the Source select to a member book re-fetches against that book_id and NOT the bible; (iii) selecting "No entity (label only)" PATCHes entity_id=null; (iv) a marker whose entity_id resolves to nothing still renders its label + the not-found hint.

SEPARATE OBSERVATION (not blocking this picker, read-only path unaffected): `frontend/src/features/world/hooks/useWorldLore.ts` feeds `createBibleEntity` a kind_id taken from the GLOBAL `/v1/glossary/kinds` list (a system-kind id), while glossary `createEntity` validates the id against THIS book's `book_kinds` (entity_handler.go:363-377). That world-lore WRITE path is likely broken today; whoever builds the `world` container panel (M8b.1) should resolve kinds via the bible book's own ontology instead.

*Evidence:* services/book-service/internal/api/worlds.go:51-126 (createWorld provisions world + hidden is_bible BOOK + sort_order-0 bible CHAPTER in one tx) · worlds.go:186-192 + :195-204 (GET /v1/worlds/{id} already returns bible_book_id / bible_chapter_id) · worlds.go:477 (GET /v1/worlds/{id}/books, is_bible=false filtered) · services/book-service/internal/migrate/migrate.go:401-434 (world_maps is world-scoped; map_markers.entity_id / map_regions.entity_id are NULLABLE soft cross-service UUIDs, no FK) · services/glossary-service/internal/api/server.go:485-486 (GET /v1/glossary/books/{book_id}/entities) · frontend/src/features/glossary/api.ts:85-96 (listEntities supports kind_codes + search + status) · frontend/src/features/world/api.ts:90-96 (createBibleEntity already treats the bible book as a normal glossary book) · services/glossary-service/internal/api/entity_handler.go:363-377 (kinds are per-book book_kinds — filter by CODE, not id)

### Q-38-BE-14b-FACT-INVALIDATE-ROUTE
BUILD IT — the repo function and the tool handler both exist; only the REST router is missing. Size S, no gateway work, no migration, no new event.

1) NEW FILE `services/knowledge-service/app/routers/public/facts.py`. Copy the shape of `routers/public/relations.py:41-46`:
   - `facts_router = APIRouter(prefix="/v1/knowledge", tags=["facts"], dependencies=[Depends(get_current_user)])`
   - `from app.db.neo4j_repos.facts import invalidate_fact`; `from app.db.neo4j import neo4j_session`; `from app.middleware.jwt_auth import get_current_user`.
   - Response model: `class FactInvalidateResponse(BaseModel): invalidated: bool; fact_id: str; reason: str | None = None`.
   - Handler:
     ```
     @facts_router.post("/facts/{fact_id}/invalidate", response_model=FactInvalidateResponse)
     async def invalidate_fact_endpoint(
         fact_id: str = Path(min_length=1, max_length=200),
         user_id: UUID = Depends(get_current_user),
     ) -> FactInvalidateResponse:
         async with neo4j_session() as session:
             fact = await invalidate_fact(session, user_id=str(user_id), fact_id=fact_id)
         if fact is None:
             return FactInvalidateResponse(invalidated=False, fact_id=fact_id, reason="no matching fact found")
         return FactInvalidateResponse(invalidated=True, fact_id=fact.id)
     ```
   - HARD RULE (spec §BE-14b, and it mirrors executor.py:718-719): an owner-keyed MISS returns **200 `{invalidated:false, reason:"no matching fact found"}`**, NEVER 404. Do NOT copy relations.py's `raise HTTPException(404)` — that is the one line that must differ from the template. Missing/cross-user JWT still 401 (from the router-level `get_current_user` dep).
   - DEFAULT I AM SETTING (PO may veto): the REST response echoes `fact_id` from the path even on a miss (the tool omits it), because the FE row action in M8a.2/A4 needs to know which row the response belongs to. `reason` is omitted (null) on success. Everything else is byte-identical to the tool.
   - DO NOT emit an outbox event. `app/events/outbox_emit.py:63-66` defines ENTITY_CORRECTED / RELATION_CORRECTED / EVENT_CORRECTED / CONFIG_ADJUSTED — there is **no FACT_CORRECTED**, and `memory_forget` emits nothing. Adding an event type + learning-service consumer is out of scope for this row.
   - DO NOT wire this to `pending_facts.py` (`/v1/knowledge/pending-facts/{id}/confirm|reject`) or `/internal/admin/.../reject-fact` — different object, different lifecycle (spec 38_kg_and_world.md:155).

2) `services/knowledge-service/app/main.py`: add `from app.routers.public import facts as public_facts` next to the sibling imports (~line 56) and `app.include_router(public_facts.facts_router)` next to `app.include_router(public_relations.relations_router)` (line 771).

3) NO gateway change: `services/api-gateway-bff/src/gateway-setup.ts:206-207` (`pathFilter: pathname.startsWith('/v1/knowledge')`) and `:645` already proxy the whole `/v1/knowledge/*` prefix to knowledge-service. Do not add a controller.

4) NEW TEST `services/knowledge-service/tests/unit/test_public_facts_invalidate.py`, modeled on `tests/unit/test_relation_correction.py` (TestClient + `patch("app.routers.public.facts.invalidate_fact", AsyncMock(...))`, `patch(... .neo4j_session)` with an `asynccontextmanager`). Three asserts, all mandatory:
   - HIT → 200 `{"invalidated": true, "fact_id": "<id>"}`, and `invalidate_fact` was called with `user_id=str(jwt_user)` (owner keying is the tenancy boundary — assert the kwarg).
   - MISS (repo returns None) → **status_code == 200** and body `{"invalidated": false, "fact_id": "<id>", "reason": "no matching fact found"}`. Add the comment `# regression-lock: MISS is 200, not 404 — mirrors executor.py:718`.
   - No/!valid Authorization header → 401.
   Run: `python -m pytest tests/unit/test_public_facts_invalidate.py -q` (knowledge suite needs the PYTHONPATH sdk prefix per repo convention).

Unblocks M8a.2 / A4 (forget-fact row action). No defer row.

*Evidence:* services/knowledge-service/app/db/neo4j_repos/facts.py:665-699 (`_INVALIDATE_FACT_CYPHER` = MATCH (f:Fact {id:$id}) WHERE f.user_id=$user_id SET f.valid_until=coalesce($valid_until, datetime()); `invalidate_fact(...) -> Fact | None`, returns None on miss) · services/knowledge-service/app/tools/executor.py:708-721 (`_handle_memory_forget`: "invalidate_fact is OWNER-keyed (user_id scoped) … The owner boundary here is the user_id, not a project"; returns {"invalidated": False, "reason": "no matching fact found"} on None) · services/knowledge-service/app/routers/public/relations.py:41-93 (the router template: APIRouter(prefix="/v1/knowledge", dependencies=[Depends(get_current_user)]) + POST /relations/{id}/invalidate — copy it, but drop its 404) · services/knowledge-service/app/main.py:56,771 (import + include_router registration site) · services/api-gateway-bff/src/gateway-setup.ts:206-207,645 (/v1/knowledge/* already proxied → no gateway change) · services/knowledge-service/app/events/outbox_emit.py:63-66 (no FACT_CORRECTED event type exists → emit nothing) · services/knowledge-service/app/routers/public/ (no facts.py — the route is genuinely absent; pending_facts.py is a different object)

### Q-38-BE-14a-PROJECT-ENTITIES-ROUTE
BUILD IT — it is unbuilt work, not a question. Exact instruction (M8a.2, size S):

(1) EXTRACT THE SHARED EFFECT (mandatory — the "thin" hides a third trap the spec missed). New file `services/knowledge-service/app/kg/project_entities.py`:
    `async def run_project_entities_to_nodes(pool, glossary_client, *, owner: UUID, project_id: UUID, book_id: UUID, entity_ids: list[str] | None) -> ProjectionResult` — lift the body of `_handle_kg_project_entities_to_nodes` (graph_schema_tools.py:1648-1680): open `neo4j_session()`, call `project_glossary_entities_to_nodes(...)`, then best-effort `reconcile_project_stats(pool, session, owner, project_id)` inside `try/except` (log-and-continue). Rewrite `_handle_kg_project_entities_to_nodes` to call it. REASON: `reconcile_project_stats` is called from exactly ONE place in production — the MCP tool (graph_schema_tools.py:1669-1673) — and it is the only writer of `stat_updated_at` (D-KG-STAT-CACHE-DEAD). If the REST route calls the engine directly it leaves `entity_count` UNKNOWN and the seed-from-glossary rail stalls at STOP_UNKNOWN for GUI users but not for agent users. Sharing one effect function is the only way both paths keep the recount.

(2) MAKE 503 POSSIBLE (the spec's 503 is currently unimplementable). In `app/extraction/anchor_loader.py`: add `glossary_unreachable: bool = False` to `ProjectionResult` (additive, defaulted — no caller breaks); change `_load_projection_rows` to return `(rows, truncated, unreachable)` and set `unreachable=True` on the `if page is None:` branch (anchor_loader.py:308-313, i.e. `list_all_entities` first-page failure); thread it into the returned `ProjectionResult`. The `entity_ids` subset path stays as-is (`fetch_entities_by_ids` returns `[]` best-effort by contract — glossary_client.py:527) ⇒ `unreachable=False` there; 0 rows on the subset path legitimately means "those ids aren't in the glossary". Also surface it in the MCP tool as a `note` so tool and route tell the same story.

(3) THE ROUTE — add to `services/knowledge-service/app/routers/public/projects.py` (its router prefix is ALREADY `/v1/knowledge/projects`, projects.py:105-109, so declare the path as `/{project_id}/project-entities`; no new router, and NO gateway work — the BFF blanket-proxies `/v1/knowledge/*`, gateway-setup.ts:207):

    class ProjectEntitiesRequest(BaseModel):
        entity_ids: list[str] | None = Field(default=None, max_length=1000)

    @router.post("/{project_id}/project-entities")
    async def project_entities_to_nodes(
        body: ProjectEntitiesRequest,
        project_id: UUID = Path(),
        owner: UUID = Depends(require_project_grant(GrantLevel.EDIT)),   # NOT get_current_user
        meta: ProjectMeta | None = Depends(project_meta_dep),            # FastAPI caches the dep → project_meta runs ONCE
        pool = Depends(get_knowledge_pool),
        glossary = Depends(get_glossary_client),
    ):

    - AUTH: `require_project_grant(GrantLevel.EDIT)` from `app.auth.grant_deps` — matches the tool's `_resolve_project_owner(ctx, GrantLevel.EDIT)` (graph_schema_tools.py:1638) and returns the project OWNER for the graph partition (resolve-to-owner). This closes Q-38-BE-14a-GRANT: gating on the raw JWT would make the button strictly weaker than the sentence (an EDIT-grantee could seed via the agent but not via the GUI) — a GG-2 inverse gap created by this very wave. The dep already 404s a non-grantee / missing project and 403s an under-tier grantee (grant_deps.py:82-104), which satisfies the "401 · 404 uniform" requirement for free.
    - book_id: take it from the cached `project_meta_dep` — do NOT re-fetch. `if meta is None: raise HTTPException(404, "not found")` (defensive; the gate already covered it). `owner_id, book_id = meta`; `if book_id is None: raise HTTPException(409, detail="this project isn't linked to a book, so it has no glossary entities to project — link a book to the project first")` (the tool's exact wording, graph_schema_tools.py:1643-1647).
    - sanitize `entity_ids` exactly as the tool does: `[e.strip() for e in (body.entity_ids or []) if e and e.strip()] or None`.
    - call `run_project_entities_to_nodes(...)`; then `if res.glossary_unreachable: raise HTTPException(503, detail="couldn't read the glossary — try again in a moment")` (NOT "nothing to project").
    - RESPONSE — every key ALWAYS PRESENT (zero-filled; the tool omits the falsy ones and an FE reading `res.conflicted` would get `undefined`): `{"nodes_created": res.created, "nodes_existing": res.existing, "entities_seen": res.seen, "skipped": res.skipped, "nodes_conflicted": res.conflicted, "truncated": res.truncated, "note": <str|None>}` — `note` non-null only when truncated or conflicted (reuse the tool's two sentences), else `None`.

(4) TESTS — `services/knowledge-service/tests/unit/test_project_entities_route.py` (mirror the dependency_overrides pattern in tests/unit/test_public_graph_views.py + tests/conftest.py which already override `project_meta_dep`), 6 cases: 200 happy path with all 7 keys present and zeros not omitted; 200 with `conflicted`/`truncated` set → keys + `note` present; 409 when `project_meta` returns `book_id=None`; 404 when `project_meta` returns None; 503 when the glossary client's `list_all_entities` returns None (asserts the new `glossary_unreachable` flag, and asserts the body is NOT the all-zero "nothing to project" 200); 403 for an EDIT-under-tier grantee (VIEW) and 200 for an EDIT grantee who is not the owner (the anti-GG-2 assertion — this test is the point of the grant decision). Plus one test in tests/unit/test_anchor_loader.py for the new `glossary_unreachable` flag, and a spy test asserting `reconcile_project_stats` is invoked on the ROUTE path (not just the tool path) — a nil-tolerant/besteffort wrapper needs a wiring test or the recount silently drops out again.

(5) If `contracts/api/knowledge-service/` documents the other `/v1/knowledge/projects/*` paths, add this one there too (contract-first rule).

Run `python -m pytest tests -q -n auto --dist loadgroup` in services/knowledge-service, then `/review-impl` at wave close per the PO policy ("/review-impl runs at the completion of EVERY wave"). Cross-service live-smoke for M8a.2: project a real book's glossary through the gateway into an empty graph and confirm `nodes_conflicted`/`truncated` render.

*Evidence:* services/knowledge-service/app/routers/public/projects.py:105-109 (router prefix is already /v1/knowledge/projects) · services/knowledge-service/app/auth/grant_deps.py:105-119 (require_project_grant → owner; 404/403 uniform) + :82-104 (_resolve_owner) · services/knowledge-service/app/tools/graph_schema_tools.py:1638-1647 (tool gates EDIT + resolves book_id via projects_repo.project_meta; 'not linked to a book' message) and :1669-1673 (reconcile_project_stats — the ONLY production writer of the stat cache; a route that skips it re-opens D-KG-STAT-CACHE-DEAD for GUI users) · services/knowledge-service/app/extraction/anchor_loader.py:194 (engine) + :308-313 (`if page is None: … return out, False` — the glossary failure is SWALLOWED into an all-zero result, so 503 is impossible without adding `glossary_unreachable`) · services/knowledge-service/app/clients/glossary_client.py:407-429 (list_all_entities returns None only on first-page failure) + :527-528 (fetch_entities_by_ids is best-effort [] by contract) · services/api-gateway-bff/src/gateway-setup.ts:207 (BFF already proxies /v1/knowledge/* → no gateway change)

### Q-38-OQ6-RELATION-PREDICATE-FREE-STRING-BE
DO NOT DEFER THE BE HALF — build it in M8a.1 next to BE-14d (call it **BE-14e**). The spec's stated defer reason ("widening the ontology check is a knowledge-service design call") is FALSE against the code: the design call was already made and coded by the ontology epic, and the agent path already honours it. The predicate closed-set is NOT a global enum — it is the project's `kg_edge_types` under the resolved graph schema, with `allow_free_edges` as the explicit escape hatch. `validate_edge()` (app/ontology/validation.py:111-147) already implements the rule exactly (`predicate ∈ edge_types` → check endpoint kinds; `∉ AND allow_free_edges` → OK; `∉ AND closed` → `unknown_edge_type`), and it ALREADY has a production caller: `kg_propose_edge` (graph_schema_tools.py:1541-1559) resolves the schema, validates, and parks off-schema edges to triage WITHOUT writing Neo4j (INV-K1). So the spec's premise "an agent ... can still mint an off-ontology edge" is wrong — the agent CANNOT. The ONLY unvalidated direct edge-writes in knowledge-service are the two REST endpoints (relations.py:127 correct, :204 create). The REST surface is LOOSER than the tool. Nothing is missing but the wiring.

=== BE-14e (knowledge-service, ~40 LOC + tests) ===
FILE: services/knowledge-service/app/routers/public/relations.py
Add one helper `_assert_predicate_on_schema(session, *, user_id, subject_id, object_id, predicate)` and call it from BOTH `correct_relation_endpoint` (:106) and `create_relation_endpoint` (:186), BEFORE `recreate_relation`:
1. Load subject + object entity nodes for `user_id` (app/db/neo4j_repos/entities.py — they already carry `project_id` (:95, :248) and `kind`). If the subject's `project_id` IS NULL → return (no schema in scope; accept, today's behavior).
2. `resolved = await ontology_resolver.resolve(project_id)` — inject the SAME `OntologyResolver` the tool uses (app/ontology/resolver.py) via a `Depends`, so the TTL cache is shared. Do not call GraphSchemasRepo directly.
3. `issue = validate_edge(resolved, predicate=predicate, source_kind=subject.kind, target_kind=object.kind)`.
4. `issue is not None` → raise HTTP **422** with `detail={"error": issue.item_type, "predicate": predicate, "allowed": [e.code for e in resolved.edge_types]}`. Comment WHY this diverges from the fail-soft extraction path: extraction/`kg_propose_edge` parks to triage because an LLM pass must not lose work; a REST write is a deliberate assertion by a human/curl who can pick a valid predicate → hard reject. This mirrors entity `kind` exactly (REST enforces `_AUTHORABLE_KINDS` at entities.py:975; extraction triages).
5. Validation runs BEFORE the recreate, so `/relations/correct` keeps its no-half-applied-state property (relations.py:123-127 deliberately orders recreate-before-invalidate; a 422 must leave the OLD edge live).
NON-BREAKING BY CONSTRUCTION — no migration, rejects nothing today: `allow_free_edges` defaults TRUE (migrate.py:1279; seed_graph_schemas.py:45,92) and the degenerate resolve returns `allow_free_edges=True` (graph_schemas.py:257). It only bites for a project whose owner deliberately closed their schema.
TESTS (new services/knowledge-service/tests/test_relations_public_schema.py; needs `pytestmark = pytest.mark.xdist_group("pg")`): (a) open schema + garbage predicate → 201 [regression guard: today's behavior preserved]; (b) closed schema + off-vocab predicate → 422, body carries `allowed`; (c) closed schema + valid predicate, wrong endpoint kinds → 422 `edge_kind_mismatch`; (d) `/relations/correct` closed schema + off-vocab → 422 AND the old edge is STILL valid (`valid_until IS NULL`); (e) entity with `project_id = NULL` → 201 (no schema in scope).

=== FE half — the spec's literal wording is a SHIPPED BUG; build this instead ===
🔴 The `general` seed is `edge_types: []` + `allow_free_edges: True` (seed_graph_schemas.py:37-56), and a project with no schema degenerates to the same (graph_schemas.py:257). A literal "schema-fed `<select>`" therefore renders **ZERO options** for every project on the default schema — making A2's *create* impossible AND **regressing** the shipped free-text *correct* field (RelationEditDialog.tsx:127-134) to an empty dropdown. Do not ship a bare `<select>`.
Build ONE shared `PredicateField` component used by all three verbs of `RelationEditDialog` (no fork — DOCK-2), fed by `ontologyApi.getResolvedSchema(projectId)` (frontend/src/features/knowledge/api/ontology.ts:143; projectId from the entity's `project_id`, already rendered at EntityDetailPanel.tsx:375):
- `edge_types` non-empty → `<select>` over `edge_types[].code`;
- AND `resolved.allow_free_edges === true` → append a final "Custom…" option that reveals the existing `<input maxLength={100}>`;
- `edge_types` empty OR the entity has no `project_id` → free-text input only (exactly today's control — never an empty select).
This keeps create+correct unified (A2's real intent: closed set when the schema IS closed) without ever shipping an empty dropdown, and it makes the GUI exactly as strict as the BE — which after BE-14e is the same rule, from the same `ResolvedSchema`, on both sides.
PO veto point: if you want the predicate hard-closed for everyone regardless of `allow_free_edges`, say so — that is a policy change to the ontology epic's Q2 default and would need the seeds flipped, not a FE tweak.

*Evidence:* services/knowledge-service/app/ontology/validation.py:111-147 (validate_edge already implements the rule incl. the allow_free_edges escape hatch) · services/knowledge-service/app/tools/graph_schema_tools.py:1541-1559 (the AGENT path already resolves the schema + validate_edge → parks to triage, never writes Neo4j — so an agent CANNOT mint an off-ontology edge, contra the spec) · services/knowledge-service/app/routers/public/relations.py:102,178 (predicate: str Field(max_length=100)) and :127,:204 (the ONLY unvalidated direct Neo4j edge-writes in the service — grep of recreate_relation|create_relation callers returns only these two plus extraction/pass2_writer.py:716, pattern_writer.py:271 and the human-gated ontology/triage_apply.py:200) · services/knowledge-service/app/db/seed_graph_schemas.py:37-56 (`general` seed: edge_types: [] + allow_free_edges: True → the empty-<select> trap) and :92 ("Q2 default; tighten per-project as opt-in") · services/knowledge-service/app/db/repositories/graph_schemas.py:257 (degenerate resolve → allow_free_edges=True ⇒ BE-14e rejects nothing today) · services/knowledge-service/app/db/neo4j_repos/entities.py:95,248 (entity node carries project_id ⇒ the resolve seam the REST path needs) · services/knowledge-service/app/routers/public/entities.py:975 (_AUTHORABLE_KINDS — the precedent: REST enforces the closed set, extraction triages) · frontend/src/features/knowledge/api/ontology.ts:143 (getResolvedSchema — the FE already has the schema feed) · frontend/src/features/knowledge/components/RelationEditDialog.tsx:127-134 (the shipped free-text input)

### Q-38-BE-15d-MAP-RENAME-OCC
BUILD IT in M8b.1 exactly as spec'd — it is ~40 LOC of unbuilt work, not a blocker, and every piece it needs already exists to copy. book-service has ZERO If-Match/ETag code today (only a comment at chapter_reorder.go:16), so this is the first OCC in Go; mirror knowledge-service's Python contract verbatim.

(1) MIGRATION — services/book-service/internal/migrate/migrate.go, append to the forward-only DDL after the world_maps block (~line 412):
    ALTER TABLE world_maps ADD COLUMN IF NOT EXISTS version INT NOT NULL DEFAULT 1;
Existing rows correctly land on 1 (DEFAULT is right for the backfill, so the repo's `ADD COLUMN never revisits a bad default` trap does not apply).

(2) NEW FILE services/book-service/internal/api/maps_rest.go — port the two Python helpers to Go:
    parseIfMatch(h string) (int, error)  — "" => sentinel "missing"; accept W/"3", "3", AND bare 3 (be lenient: a curl/Go caller sending the bare int must not 422); anything else => 422 BOOK_VALIDATION_ERROR "If-Match must be an ETag with an integer version".
    etag(v int) string => fmt.Sprintf(`W/"%d"`, v)   // weak, exactly like entities.py:111-116

(3) HANDLER patchWorldMap(w,r):
    - parseUUIDParam("map_id"); s.requireUserID(r) -> 401 BOOK_FORBIDDEN.
    - If-Match absent  -> 428 {"code":"MAP_PRECONDITION_REQUIRED","message":"If-Match header required — GET the map first to obtain an ETag"}.
    - body {name?}: name is the ONLY patchable field. Absent -> 400 BOOK_VALIDATION_ERROR "name required"; blank/whitespace -> 400 (mirror worlds.go:280-283).
    - ONE atomic conditional UPDATE (no read-then-write race):
        UPDATE world_maps SET name=$3, version=version+1, updated_at=now()
        WHERE id=$1 AND owner_user_id=$2 AND version=$4
        RETURNING id, world_id, name, image_object_key, image_w, image_h, version, created_at, updated_at
    - On pgx.ErrNoRows, disambiguate with ONE re-SELECT scoped by (id, owner_user_id):
        * row absent  -> 404 {"code":"MAP_NOT_FOUND"}. A FOREIGN owner's map with a CORRECT version must ALSO 404, never 412 — no existence oracle (same discipline as mcp_maps.go:264,432).
        * row present -> 412 with the CURRENT map object as the BARE response body (same JSON shape as the 200 — not wrapped in an error envelope; this is exactly entities.py:1078-1084) + header ETag: W/"<current.version>".
    - Success -> 200 {map} + header ETag: W/"<new version>".

(4) SCOPE OF THE COUNTER (the thing the spec left implicit — settling it now): world_maps.version guards the MAP ROW ONLY.
    * Marker/region create/patch/delete (BE-15g..l) DO NOT bump it and take no If-Match. If they bumped it, dragging a marker would 412 an open rename dialog — that is the wrong product behavior.
    * The image upload (BE-15f) DOES mutate world_maps (image_object_key/w/h) -> it bumps version + updated_at and returns the fresh `ETag` header; the canvas refreshes its cached etag from that response.
    * MCP tools (mcp_maps.go) have no rename tool, so none of them need If-Match; world_map_create just inserts at DEFAULT 1.

(5) SERIALIZER: add `version` and `updated_at` to the REST map shape used by BE-15b/15c/15d/15f. Leave the MCP tool output structs UNCHANGED (no contract churn on tools nobody asked to change).

(6) ROUTING — services/book-service/internal/api/server.go inside the existing r.Route("/v1/worlds", …) block (:381-391), as a sibling of r.Route("/{world_id}"):
        r.Route("/maps/{map_id}", func(r chi.Router) { r.Get("/", s.getWorldMap); r.Patch("/", s.patchWorldMap); r.Delete("/", s.deleteWorldMap); … })
    chi prioritizes the static "maps" segment over the "{world_id}" param, but this is exactly the kind of thing that silently mis-routes — add a routing test asserting GET /v1/worlds/maps/<uuid> hits getWorldMap and NOT getWorld.

(7) NO GATEWAY WORK. gateway-setup.ts:56 already CORS-allows If-Match, :62 already exposes ETag, :86-90/:592 already raw-proxy /v1/worlds*. Do not touch it.

(8) TESTS (Go, pgxmock harness per the repo's go-db-mock-harness pattern) — all seven, they are the Definition of Done for this slice:
    a. 428 when no If-Match.
    b. 200 happy path: version 1 -> response ETag == W/"2", body.version == 2.
    c. 412: body is the CURRENT map (OLD name, UNCHANGED version) + ETag header == current version.
    d. TENANCY: another user's map + a CORRECT version -> 404, never 412 (no cross-owner oracle).
    e. 422 on malformed If-Match ("abc").
    f. bare-int If-Match (`3`) accepted.
    g. the routing test in (6).
    Live smoke at M8b.1 close: rename via curl with a stale If-Match -> 412 carrying the current name.

(9) FE (per spec 38 line 413): on 412 the rail shows "renamed on another device" + the current name from the 412 body, and re-arms with the ETag from the 412 response so the user's re-apply succeeds.

DEFAULT THE PO MAY VETO: item (4) — marker/region edits do not bump the map version. If the PO wants map version to be a whole-aggregate counter instead, say so; everything else stands either way.

*Evidence:* services/book-service/internal/migrate/migrate.go:401-412 (world_maps DDL — has updated_at, NO version; only the new column is missing) · services/knowledge-service/app/routers/public/entities.py:90-116 (_parse_if_match accepts W/"N" and "N"; _etag emits W/"N") and :1043-1084 (428 missing / 422 malformed / 412 body = the CURRENT object bare + ETag header — the exact contract to copy) · services/book-service/internal/api/worlds.go:258-304 (patchWorld: UPDATE keyed on id+owner_user_id, RowsAffected()==0 -> 404 — the owner-scoping pattern) · services/book-service/internal/api/mcp_maps.go:264,432 (uniform not-found via owner JOIN) · services/api-gateway-bff/src/gateway-setup.ts:56 (If-Match already CORS-allowed), :62 (ETag already exposed), :86-90 and :592 (/v1/worlds* raw passthrough — zero gateway work) · grep -rn "If-Match|ETag" services/book-service --include=*.go -> single hit at internal/api/chapter_reorder.go:16 and it is a COMMENT, confirming this is the first Go OCC (new semantics, but ~40 LOC, buildable).

### Q-38-BE-15c-MAP-GET
BUILD IT — the route genuinely does not exist (it is unbuilt work, not a blocker), and its shape is fully determined by the existing MCP tool. Builder instructions, no further thought required:

1) MIGRATION (`services/book-service/internal/migrate/migrate.go`, forward-only, append to the existing idempotent DDL block near :401-434, house pattern):
   ALTER TABLE world_maps  ADD COLUMN IF NOT EXISTS version INT NOT NULL DEFAULT 1;
   ALTER TABLE map_markers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
   ALTER TABLE map_regions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
   (`world_maps.updated_at` already exists at migrate.go:410 — do NOT re-add. Get defaults right first time: ADD COLUMN IF NOT EXISTS never revisits a bad default on an already-migrated DB.)

2) ONE LOADER, TWO TRANSPORTS (the only real design call — take it): refactor the body of `toolWorldMapGet` (mcp_maps.go:252-334) into
   `func (s *Server) loadWorldMap(ctx context.Context, mapID, ownerID uuid.UUID) (mapGetOut, error)` — owner-keyed SELECT (`WHERE id=$1 AND owner_user_id=$2` → pgx.ErrNoRows = not-yours-or-missing, no enumeration oracle), keep the existing "a markers/regions read error is a TOOL FAILURE, not an empty list" behavior verbatim. `toolWorldMapGet` becomes a 5-line wrapper over it; the new REST handler calls the same fn. This is what stops the GG-2 tool/GUI drift the spec's other rows keep fixing.

3) SHAPE (extend the existing structs in mcp_maps.go — additive, so `world_map_get` gains the same fields; that is intended, not a leak):
   - `markerOut` += `UpdatedAt time.Time \`json:"updated_at"\`` ; SELECT becomes `SELECT id, label, x, y, entity_id, marker_type, updated_at FROM map_markers WHERE map_id=$1 ORDER BY created_at` (mcp_maps.go:280).
   - `regionOut` += `UpdatedAt time.Time \`json:"updated_at"\`` ; SELECT becomes `SELECT id, name, polygon, entity_id, updated_at FROM map_regions WHERE map_id=$1 ORDER BY created_at` (mcp_maps.go:303).
   - `worldMapDetail` (mcp_maps.go:73-79) += `Version int \`json:"version"\``, `UpdatedAt time.Time \`json:"updated_at"\``, `ImageW *int \`json:"image_w"\``, `ImageH *int \`json:"image_h"\`` (pointers — WebP stores NULL per maps_image.go:16-19; the inspector must show "—", never "0 × 0"). Map SELECT becomes `SELECT id, world_id, name, image_object_key, image_w, image_h, version, updated_at FROM world_maps WHERE id=$1 AND owner_user_id=$2`. `version` is NOT optional here: BE-15d's `If-Match` has no other way to learn the current version, so the GET must hand it out. Keep `s.withImageURL(&d)`.
   Response body: `200 {map: {...}, markers: [...], regions: [...]}` — markers/regions always `[]`, never null (already guaranteed by the `mapGetOut{Markers: []markerOut{}, Regions: []regionOut{}}` init).

4) ROUTE (new file `services/book-service/internal/api/worlds_maps.go`, handler `getWorldMap`): register inside the existing `/v1/worlds` block at server.go:381, as the FIRST child so it reads unambiguously against `/{world_id}`:
   `r.Route("/maps/{map_id}", func(r chi.Router) { r.Get("/", s.getWorldMap) })`   // BE-15c
   Handler: `mapID, ok := parseUUIDParam(w, r, "map_id")` (malformed → 400 BOOK_VALIDATION_ERROR, server.go:432 — consistent with getWorld); `ownerID, ok := s.requireUserID(r)` else `writeError(w, 401, "BOOK_FORBIDDEN", "unauthorized")` (mirror worlds.go:214-218); then `loadWorldMap` → on pgx.ErrNoRows `writeError(w, 404, "MAP_NOT_FOUND", "map not found")` (uniform foreign-or-missing, mirroring `requireMapOwner`), on other error `writeError(w, 500, "BOOK_CONFLICT", "failed to get map")`, else `writeJSON(w, 200, out)`.
   NO gateway change — `/v1/worlds*` already proxies to book-service (gateway-setup.ts:86-90).

5) TESTS (Go, alongside `services/book-service/internal/api/mcp_maps_test.go`): (a) 200 returns map+markers+regions with `updated_at` present on every marker and region and `version` on the map; (b) another user's map_id → 404 with the same body as a missing one; (c) no JWT → 401; (d) the write-only-column guard the spec demands: after BE-15h's marker PATCH, a re-GET shows the marker's `updated_at` strictly ADVANCED (assert `after.After(before)`), and same for a region PATCH — this is the test that proves the new columns are read, not shipped write-only.

PO-visible default I picked (veto if you disagree): the MCP tool `world_map_get` returns the SAME enriched payload (updated_at / version / image_w / image_h), because it shares the loader. The alternative — a REST-only projection — means two SELECTs that will drift. Additive fields are safe for MCP consumers.

*Evidence:* services/book-service/internal/api/server.go:381-392 (the /v1/worlds chi block has NO /maps/* route → BE-15c truly MUST-BUILD); services/book-service/internal/api/mcp_maps.go:252-334 (toolWorldMapGet = the exact {map, markers[], regions[]} shape to lift, incl. the "read error is a failure, not an empty list" guard) and :73-79 (worldMapDetail struct to extend), :280 + :303 (the two child SELECTs missing updated_at); services/book-service/internal/migrate/migrate.go:401-434 (world_maps already has updated_at:410; map_markers:422 and map_regions:433 have created_at ONLY, and no version column anywhere); services/api-gateway-bff/src/gateway-setup.ts:86-90 (worldsProxy pathFilter '/v1/worlds' ⇒ zero gateway changes); services/book-service/internal/api/worlds.go:209-220 + :167-173 (the requireUserID → 401 / owner-keyed ErrNoRows → 404 handler pattern to mirror).

### Q-38-BE-15e-MAP-DELETE
BUILD IT — it is unbuilt work, not a question, and the engine already exists (lift `toolWorldMapDelete`). Exact instruction:

1) FILE: new `services/book-service/internal/api/maps_rest.go` (the home for BE-15a..15l; the delete handler is `func (s *Server) deleteWorldMap(w http.ResponseWriter, r *http.Request)`).

2) HANDLER — a verbatim lift of `mcp_maps.go:378-407` with HTTP status codes instead of tool errors:
   - `userID, ok := s.requireUserID(r)` → `401 BOOK_UNAUTHORIZED` if !ok (the house pattern, `server.go:414`).
   - `mapID, ok := parseUUIDParam(w, r, "map_id")` → returns 400 on a non-UUID (same as `maps_image.go:31`).
   - ONE owner-scoped read that both proves ownership and grabs the blob key:
     `SELECT image_object_key FROM world_maps WHERE id=$1 AND owner_user_id=$2` → `pgx.ErrNoRows` ⇒ `404 MAP_NOT_FOUND "map not found"` (uniform for foreign-or-missing — no enumeration oracle, mirroring `requireMapOwner`, `mcp_maps.go:45-54`). Other err ⇒ 500.
   - `DELETE FROM world_maps WHERE id=$1 AND owner_user_id=$2` — DO NOT hand-delete markers/regions: the FKs are already `ON DELETE CASCADE` (`internal/migrate/migrate.go:416` map_markers, `:429` map_regions), so CASCADE is a DB fact, not code to write.
   - Best-effort blob sweep AFTER the row is gone, and it MUST NOT fail the request: `if imageKey != nil && *imageKey != "" && s.minio != nil { _ = s.minio.RemoveObject(ctx, mediaBucket, *imageKey, minio.RemoveObjectOptions{}) }` (`mediaBucket` = `media.go:28`). A MinIO hiccup ⇒ a stray object, never a 5xx.
   - Respond `w.WriteHeader(http.StatusNoContent)` — no body (do not use writeJSON).

3) ROUTE: inside the existing `r.Route("/v1/worlds", …)` block in `services/book-service/internal/api/server.go:381-391`, add a sibling static sub-route BEFORE/alongside `r.Route("/{world_id}", …)`:
   `r.Route("/maps/{map_id}", func(r chi.Router) { r.Delete("/", s.deleteWorldMap) /* + BE-15c GET, BE-15d PATCH, BE-15f image, markers/regions */ })`
   chi's trie matches the static segment `maps` ahead of the `{world_id}` param node, so this does not collide — but ADD A TEST that asserts `DELETE /v1/worlds/maps/<uuid>` does not fall through to the `{world_id}` handlers. Gateway: NO change — `gateway-setup.ts:90` already proxies everything under `/v1/worlds` to book-service.

4) SEALED DEFAULT (veto-able by PO): **DELETE takes NO `If-Match`/OCC.** The `version` column BE-15d adds gates PATCH only; a delete is terminal and the FE guards it with a confirm dialog. So the error set stays exactly 401 · 404 (+400 on a malformed UUID) — no 428/412 on this route. Deleting an already-deleted map is a 404, not a 204 (owner-scoped read misses).

5) TEST: `services/book-service/internal/api/maps_rest_db_test.go` (pg-marked, house DB-test pattern): seed world → map (with a non-null `image_object_key`) → 1 marker + 1 region; assert (a) 204 + `world_maps`/`map_markers`/`map_regions` rows all gone (proves CASCADE), (b) a second user's JWT ⇒ 404 and the row SURVIVES (tenancy), (c) unknown map_id ⇒ 404, (d) no Authorization header ⇒ 401, (e) `s.minio == nil` ⇒ still 204 (blob sweep is best-effort, never load-bearing).

*Evidence:* services/book-service/internal/api/mcp_maps.go:378-407 (`toolWorldMapDelete` — the exact owner-scoped read + delete + best-effort `s.minio.RemoveObject(ctx, mediaBucket, …)` to lift); services/book-service/internal/migrate/migrate.go:416 & :429 (`map_id UUID NOT NULL REFERENCES world_maps(id) ON DELETE CASCADE` — CASCADE already exists, no child deletes to write); services/book-service/internal/api/server.go:381-391 (the `/v1/worlds` chi block where the route mounts — today it has NO `/maps` sub-route: the only map REST anywhere is the internal `POST /internal/worlds/maps/{map_id}/image`, server.go:200); services/book-service/internal/api/media.go:28 (`mediaBucket = "loreweave-media"`); services/api-gateway-bff/src/gateway-setup.ts:90 (`pathname.startsWith('/v1/worlds')` — zero gateway work).

### Q-38-BE-15b-MAP-LIST-WITH-COUNTS
BUILD IT — it is unbuilt work, not a blocker, and nothing in it is a product call. Everything BE-15b needs already exists in book-service; only `version` is genuinely new. Concrete instruction:

**1 · Migration** — append to the idempotent DDL block in `services/book-service/internal/migrate/migrate.go` (right after the map DDL that ends at :434):
```sql
ALTER TABLE world_maps  ADD COLUMN IF NOT EXISTS version    INT NOT NULL DEFAULT 1;
ALTER TABLE map_markers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE map_regions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
```
`world_maps.updated_at` ALREADY EXISTS (migrate.go:410) — do not re-add it. `version` is the only new column on `world_maps`.

**2 · Route** — new file `services/book-service/internal/api/world_maps.go` (home for all 12 BE-15 REST handlers). Register in `server.go` inside the EXISTING `r.Route("/v1/worlds")` → `r.Route("/{world_id}")` block, as a sibling of `r.Get("/books", s.listWorldBooks)` (server.go:388):
```go
r.Get("/maps", s.listWorldMaps)
```
**Zero gateway work**: `api-gateway-bff` already blanket-proxies anything under `/v1/worlds` (`gateway-setup.ts:90` `pathname.startsWith('/v1/worlds')`), so the route is reachable at :3123 the moment it is mounted.

**3 · THE COUNTS — do NOT write the two-way `LEFT JOIN … GROUP BY` the spec's parenthetical suggests. It is WRONG.** Joining BOTH child tables in one statement fans out to m×r rows, so `COUNT(mk.id)` returns m*r: a map with 3 markers and 4 regions would report `marker_count: 12, region_count: 12`. Mirror this repo's OWN precedent instead — `worldSelectSQL` (worlds.go:185-193) computes `book_count` with a **correlated scalar subquery**, no GROUP BY:
```sql
SELECT m.id, m.world_id, m.name, m.image_object_key, m.version, m.updated_at,
  COALESCE((SELECT COUNT(*) FROM map_markers mk WHERE mk.map_id=m.id),0) AS marker_count,
  COALESCE((SELECT COUNT(*) FROM map_regions rg WHERE rg.map_id=m.id),0) AS region_count
FROM world_maps m
WHERE m.world_id=$1 AND m.owner_user_id=$2
ORDER BY m.created_at DESC
```
(If a builder insists on a JOIN it MUST use `COUNT(DISTINCT mk.id)` / `COUNT(DISTINCT rg.id)` — but the subquery form is the house pattern and needs no GROUP BY.) Indexes `idx_map_markers_map` (:424) and `idx_map_regions_map` (:434) already serve these — **no new index**. One query, one round-trip: the GET-storm the spec forbids is solved.

**4 · Auth / scope** — `ownerID, ok := s.requireWorldOwner(w, r, worldID)` (worlds.go:333): 401 `BOOK_FORBIDDEN` unauthenticated, 404 `WORLD_NOT_FOUND` if the world isn't yours (no existence oracle). Then the SELECT is *doubly* owner-scoped via `AND m.owner_user_id=$2`, matching `toolWorldMapList` (mcp_maps.go:351).

**5 · Response** — `writeJSON(w, http.StatusOK, map[string]any{"maps": items})`. Key is **`maps`** (the spec's FE contract), not `items`. `items := make([]…, 0)` so an empty world yields `{"maps": []}`, never `null`. Per row set `image_url` from `s.mediaURL(key)` — that is a pure string builder with no network/presign call (mcp_maps.go:83), so per-row is free; leave `image_object_key`/`image_url` nullable.

**6 · Scan errors are a 500, NOT a dropped row.** Do NOT copy `toolWorldMapList`'s `if rows.Scan(...) == nil { append }` (mcp_maps.go:360) — that silently omits a map when a scan fails, which is this repo's own `pgx-discarded-scan-zeroes-row` / silent-success bug class. Check the scan error explicitly and check `rows.Err()` after the loop; both → 500. (Fix the same latent bug in `toolWorldMapList` while you're in the file — one-line, in-scope, FIX-NOW.)

**7 · Tests** — `services/book-service/internal/api/world_maps_test.go`:
- **the fan-out regression test (mandatory):** seed one map with 3 markers AND 2 regions → assert `marker_count == 3 && region_count == 2`. This is the test that kills the LEFT-JOIN cartesian bug; without both children populated on the same map, the buggy SQL passes.
- world with zero maps → `200 {"maps": []}`.
- freshly-created map → `version == 1`, `updated_at` non-empty.
- another user's world id → 404, body byte-identical to a nonexistent world id.
- curl smoke through the gateway (`:3123`) per M8b.1's evidence bar.

Default I am setting (veto-able): the counts are **unfiltered raw child counts** (no soft-delete/archive filter) because `map_markers`/`map_regions` have no lifecycle column — deletes are hard + CASCADE (migrate.go:416/428). If a tombstone column is ever added, the count predicate must be updated with it.

*Evidence:* services/book-service/internal/api/worlds.go:185-193 (`worldSelectSQL` — the correlated-scalar-subquery count precedent, `COALESCE((SELECT COUNT(*) …),0) AS book_count`) · services/book-service/internal/migrate/migrate.go:401-434 (`world_maps` has `updated_at` at :410 but NO `version`; `idx_map_markers_map` :424 / `idx_map_regions_map` :434 already index the count predicates) · services/book-service/internal/api/mcp_maps.go:340-368 (`toolWorldMapList` — existing MCP list returns no counts/version, and swallows scan errors at :360) · services/book-service/internal/api/server.go:388 (`r.Get("/books", s.listWorldBooks)` — the sibling mount point under `/v1/worlds/{world_id}`) · services/api-gateway-bff/src/gateway-setup.ts:90 (`pathname.startsWith('/v1/worlds')` — blanket passthrough, no gateway change needed)

### Q-38-BE-14c-ENTITY-KINDS-ROUTE
BUILD IT AS SPECCED — this is unbuilt work, not a question. The route does not exist (only `_AUTHORABLE_KINDS` at `entities.py:975` does), it is XS, and every prerequisite is already in the repo. Exact build:

1) NEW FILE `services/knowledge-service/app/entity_kinds.py` (top-level small-module precedent: `app/effort.py`, `app/spoiler_window.py`, `app/pricing.py`):
   `AUTHORABLE_ENTITY_KINDS: tuple[str, ...] = ("character", "concept", "faction", "location")`  # alphabetical = the wire order
   `AUTHORABLE_ENTITY_KINDS_SET = frozenset(AUTHORABLE_ENTITY_KINDS)`
   This is the ONE home (BE-14d's "hoist one constant"). Serve the tuple verbatim — do NOT `sorted(set)` per request.

2) `services/knowledge-service/app/routers/public/entities.py`: replace line 975 with `_AUTHORABLE_KINDS = AUTHORABLE_ENTITY_KINDS_SET` (keeps the `sorted(...)` 422 message at :994 byte-identical, so the existing validator tests stay green), and add the route on the EXISTING `entities_router` (declared :131-135, `prefix="/v1/knowledge"`, `dependencies=[Depends(get_current_user)]` — that dep IS the 401, no new auth code):
   ```python
   class EntityKindsResponse(BaseModel):
       kinds: list[str]

   @entities_router.get("/entity-kinds", response_model=EntityKindsResponse)
   async def list_entity_kinds() -> EntityKindsResponse:
       """System-tier, read-only, admin-owned constant. No write route (CLAUDE.md User Boundaries)."""
       return EntityKindsResponse(kinds=list(AUTHORABLE_ENTITY_KINDS))
   ```
   Full path = `GET /v1/knowledge/entity-kinds` → `200 {"kinds":["character","concept","faction","location"]}`. NO POST/PATCH/DELETE — ever.

3) NO GATEWAY CHANGE. `gateway-setup.ts:207` already proxies every `pathname.startsWith('/v1/knowledge')` to knowledge-service; the route is reachable through `:3123` the moment it exists.

4) NO UNIFICATION with glossary-service. Its `entity_kinds` table was already RENAMED to `system_kinds` (`glossary-service/internal/migrate/migrate.go:23`) precisely because of the tenancy bug — different object, different service, different tier. Do not touch it, do not join them, do not name the knowledge route `/v1/kinds`.

5) TESTS — new `services/knowledge-service/tests/unit/test_entity_kinds_route.py`:
   a. 200 body equals EXACTLY `{"kinds":["character","concept","faction","location"]}` (order asserted — the FE `<select>` order is the wire order);
   b. no Authorization header ⇒ 401;
   c. THE DRIFT GUARD (the whole point of BE-14c): one test asserting the route's payload set == the set `CreateEntityRequest` validates against == the closed set on `KgCreateNodeArgs.kind`. This is what makes the hand-copied FE array impossible to re-introduce.

6) FE consumer (M8a.1, A1): add to `frontend/src/features/knowledge/api.ts` (beside `createEntity`, :1600) `listEntityKinds(token): Promise<{kinds: string[]}>` → `GET ${BASE}/entity-kinds`; A1's `kind` `<select>` maps over the fetched array. Zero hard-coded kind arrays in the A1 form. (Note: `composition/components/CastCodexPanel.tsx:11 KIND_ORDER` is a *display sort order*, not the write closed-set — leave it alone this slice.)

DEFAULT I AM PICKING (veto-able): no `Cache-Control`/ETag on the route — it is a 4-element constant behind an authed proxy; a normal TanStack Query cache is enough. If the PO wants HTTP caching, add `Cache-Control: public, max-age=3600` later; it changes nothing else.

COUPLING NOTE for the builder (not a blocker): BE-14d closes the same constant over the MCP transport. `KgCreateNodeArgs.kind` is a free `str(max_length=100)` (`app/tools/graph_schema_tools.py:460-463`) AND the FastMCP signature re-declares it as `Annotated[str, ...]` (`app/mcp/server.py:1125-1127`). Per the repo's own lesson (`knowledge-mcp-three-schema-sources-fastmcp-strips`), a `Literal` must be applied to BOTH the Pydantic args class and the FastMCP handler signature or the tool schema still advertises a free string. BE-14c's constant is what both import.

*Evidence:* services/knowledge-service/app/routers/public/entities.py:975 (`_AUTHORABLE_KINDS = {"character","location","faction","concept"}` — the constant to serve; no route reads it today) · entities.py:131-135 (`entities_router = APIRouter(prefix="/v1/knowledge", dependencies=[Depends(get_current_user)])` — mount point + the 401 for free; registered at app/main.py:770) · services/api-gateway-bff/src/gateway-setup.ts:207 (`pathname.startsWith('/v1/knowledge')` — already proxied, no BFF change) · services/glossary-service/internal/migrate/migrate.go:23 (`ALTER TABLE entity_kinds RENAME TO system_kinds` — the name collision is already resolved on the glossary side; do not unify) · services/knowledge-service/app/tools/graph_schema_tools.py:460-463 + app/mcp/server.py:1125-1127 (the free-string `kind` BE-14d must close using the same constant) · grep `AUTHORABLE` over services/knowledge-service returns only entities.py:975/992/994 — no hoisted constant and no `/entity-kinds` route exist yet.

### Q-38-BE-15g-MARKER-CREATE
BUILD IT — exactly as the spec states. It is unbuilt work, not a blocker: the MCP tool `toolWorldMapAddMarker` (services/book-service/internal/api/mcp_maps.go:142) already encodes every semantic; the REST handler is a lift of it. No gateway change (gateway-setup.ts:90 proxies all `/v1/worlds*` to book-service).

BUILDER INSTRUCTIONS (size XS-S, one file + one route line + one test file):

1) NEW FILE `services/book-service/internal/api/world_maps.go` (public REST siblings of the map MCP tools; BE-15g..15i and 15j..15l land here too). Handler `func (s *Server) createMapMarker(w http.ResponseWriter, r *http.Request)`:
   - Auth: `ownerID, ok := s.requireUserID(r)` (server.go:415); !ok => `writeError(w, 401, "BOOK_FORBIDDEN", "unauthorized")` — same string as worlds.go:55.
   - `mapID, err := uuid.Parse(chi.URLParam(r, "map_id"))`; on parse error => **404** (NOT 422 — an unparseable id must not be distinguishable from a foreign one; preserves the no-oracle rule).
   - Ownership: `if err := s.requireMapOwner(r.Context(), mapID, ownerID); err != nil { writeError(w, 404, "WORLD_MAP_NOT_FOUND", "map not found"); return }` — reuse mcp_maps.go:45 verbatim; foreign map and missing map are the SAME 404.
   - Body DTO — coords MUST be pointers: `type createMarkerReq struct { Label string `json:"label"`; X *float64 `json:"x"`; Y *float64 `json:"y"`; MarkerType *string `json:"marker_type"`; EntityID *string `json:"entity_id"` }`. **This is the load-bearing deviation from the MCP tool**: the tool declares `X float64` (mcp_maps.go:133), so an OMITTED `x` decodes to 0.0, passes the `[0,1]` check, and silently pins the marker to the top-left corner with a 201. With `*float64`, absent x or y => 422.
   - 422 (`writeError(w, 422, "WORLD_MAP_INVALID", <reason>)`) when ANY of: malformed JSON; `strings.TrimSpace(label) == ""`; `X == nil || Y == nil`; `!(*X >= 0 && *X <= 1) || !(*Y >= 0 && *Y <= 1)` — write it in that positive form so NaN/±Inf fail too (`x > 1` alone lets NaN through); `entity_id` present-and-non-empty but not a UUID (reuse `parseOptionalEntityID`, mcp_maps.go:55).
   - `marker_type`: stays FREE-FORM (spec 38 §4.2 BE-15m explicitly says so). Trim; empty => NULL.
   - INSERT and return the WHOLE row, not just the id: `INSERT INTO map_markers(map_id, entity_id, label, x, y, marker_type) VALUES($1,$2,$3,$4,$5,$6) RETURNING id, map_id, label, x, y, marker_type, entity_id, created_at, updated_at`. Respond `201` with `{marker: {marker_id, map_id, label, x, y, marker_type, entity_id, created_at, updated_at}}` — the SAME marker shape BE-15c returns, so the FE can splice the new pin into the cached list without a refetch. (The MCP tool returns only `marker_id`; do not copy that here.) `updated_at` comes from the wave's own migration (`ALTER TABLE map_markers ADD COLUMN IF NOT EXISTS updated_at ...`) — this slice depends on it landing first; if the column is not there yet, add it in this slice.

2) `services/book-service/internal/api/server.go` — inside the existing `r.Route("/v1/worlds", ...)` block (:381), add a sibling subtree ABOVE/BESIDE `{world_id}` (chi resolves the static segment `maps` ahead of the `{world_id}` param, so there is no conflict):
   `r.Route("/maps/{map_id}", func(r chi.Router) { r.Post("/markers", s.createMapMarker) })`

3) NEW TEST `services/book-service/internal/api/world_maps_test.go`, mirroring the mcp_maps_test.go split (pure-validation tests run with no DB; round-trip tests gated on BOOK_TEST_DATABASE_URL). Cases, all required: no Bearer => 401 · valid JWT + someone else's map_id => 404 with body `map not found` · garbage map_id => 404 (not 422) · blank label => 422 · x=1.5 => 422 · **x omitted entirely => 422** (the regression this DTO exists to prevent — a plain `float64` would 201 at (0,0)) · entity_id="not-a-uuid" => 422 · happy path => 201 AND assert the response body carries label/x/y/created_at/updated_at, not merely marker_id.

Default I am setting (veto-able by PO): `marker_type` remains an open string with no enum, matching the tool and spec 38 §4.2's explicit note.

*Evidence:* Route absent: services/book-service/internal/api/server.go:381-390 (`/v1/worlds` registers only `/`, `/{world_id}`, `/{world_id}/books` — no `/maps`). Logic to lift: services/book-service/internal/api/mcp_maps.go:142-172 (`toolWorldMapAddMarker`) + the uniform-404 owner gate at mcp_maps.go:45 (`requireMapOwner`) + optional-entity parse at mcp_maps.go:55. The omitted-coord trap: mcp_maps.go:133 declares `X float64` (non-pointer). Table: services/book-service/internal/migrate/migrate.go:414-423 (map_markers, no updated_at yet). Gateway needs no change: services/api-gateway-bff/src/gateway-setup.ts:90 (`pathname.startsWith('/v1/worlds')`). Auth/error helpers: server.go:407 (writeError), server.go:415 (requireUserID); 401 wording precedent worlds.go:55.

### Q-38-BE-15i-MARKER-DELETE
BUILD IT — this is a work item, not an open design question, and the engine already exists to lift. One latent trap must be decided, and I decide it here: **the REST DELETE must key on (marker_id AND map_id AND owner), NOT on marker_id alone.** The MCP tool's SQL (`mcp_maps.go:431-433`) constrains only `m.id=$1 AND m.map_id=wm.id AND wm.owner_user_id=$2` — it never checks that the marker is on the map named in the path (the tool has no map in its args). Lifting that SQL verbatim into `DELETE /v1/worlds/maps/{map_id}/markers/{marker_id}` would let `DELETE /maps/A/markers/<marker-on-your-map-B>` succeed with 204, silently deleting a pin off a different map — and it would contradict BE-15h's explicit "404 (foreign map **or** marker not on this map)" semantics, which BE-15i must match.

BUILDER INSTRUCTION (exact):

1. FILE — new `services/book-service/internal/api/world_maps.go` (the home for all 12 BE-15 REST handlers; the MCP tools stay in `mcp_maps.go`). Add:

```go
// deleteMapMarker — DELETE /v1/worlds/maps/{map_id}/markers/{marker_id} → 204.
// Owner-scoped via a JOIN to world_maps.owner_user_id AND keyed on map_id, so a
// marker on a DIFFERENT map (even one you own) is a 404, not a silent cross-map
// delete. 0 rows affected → uniform 404 (no existence oracle; mirrors requireMapOwner).
func (s *Server) deleteMapMarker(w http.ResponseWriter, r *http.Request) {
	mapID, ok := parseUUIDParam(w, r, "map_id")
	if !ok {
		return
	}
	markerID, ok := parseUUIDParam(w, r, "marker_id")
	if !ok {
		return
	}
	ownerID, ok := s.requireUserID(r)
	if !ok {
		writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized")
		return
	}
	tag, err := s.pool.Exec(r.Context(), `
DELETE FROM map_markers m USING world_maps wm
WHERE m.id=$1 AND m.map_id=$2 AND m.map_id=wm.id AND wm.owner_user_id=$3`,
		markerID, mapID, ownerID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to delete marker")
		return
	}
	if tag.RowsAffected() == 0 {
		writeError(w, http.StatusNotFound, "MAP_MARKER_NOT_FOUND", "marker not found")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
```
(`requireUserID` + `parseUUIDParam` + `writeError` are the existing house helpers — see `worlds.go:334` / `worlds.go:426-455`, and copy `removeBookFromWorld`'s 204 shape exactly: `w.WriteHeader(http.StatusNoContent)`, no body.)

2. REGISTER — `services/book-service/internal/api/server.go`, inside the existing `r.Route("/v1/worlds", …)` block (line 381-392), as a SIBLING of `/{world_id}` (the path is `/v1/worlds/maps/{map_id}/…`, map-keyed, not world-keyed). Register the literal `/maps` subrouter BEFORE the `/{world_id}` wildcard route so chi does not swallow `maps` as a world_id:

```go
r.Route("/maps/{map_id}", func(r chi.Router) {
    // … BE-15c/d/e/f/g/j land here too
    r.Delete("/markers/{marker_id}", s.deleteMapMarker)   // BE-15i
})
r.Route("/{world_id}", func(r chi.Router) { … })          // existing — keep AFTER
```
(chi routes static segments before wildcards regardless of order, but declare it first anyway so the intent is readable and a future `{world_id}`-prefixed pattern can't shadow it.)

3. NO GATEWAY CHANGE — `/v1/worlds*` already passthrough-proxies to book-service (`services/api-gateway-bff/src/gateway-setup.ts:90`, `pathFilter: pathname.startsWith('/v1/worlds')`). Do not add a route there.

4. NO MIGRATION — `map_markers` already exists (`internal/migrate/migrate.go:401-434`) with FK CASCADE from `world_maps`. BE-15i touches no new column.

5. TESTS — add to a new `services/book-service/internal/api/world_maps_test.go` (DB-backed, mirroring `mcp_maps_test.go`), four cases:
   - happy: own map + own marker → **204**, body empty, row gone from `map_markers`.
   - **cross-map**: marker belongs to map B, DELETE via map A (both owned by caller) → **404**, and assert the marker STILL EXISTS (this is the bug the map_id key prevents — a test that only asserts 404 would pass against the buggy verbatim-lift SQL only by accident; assert the row survives).
   - foreign owner: map+marker owned by user2, caller user1 → **404** (not 403 — no existence oracle).
   - idempotency: delete twice → 204 then **404**.
   Plus a no-JWT case → **401** (add `deleteMapMarker` to the existing auth-matrix table test at `worlds_test.go:148-155`).

DEFAULT NOTED FOR PO VETO: second DELETE returns 404, not 204 — the spec's error list for BE-15i says `401 · 404`, and BE-15e/15h use the same uniform-404 model, so a non-idempotent 404 is the consistent choice. The FE should treat a 404 on delete as "already gone" and just drop the pin from local state rather than surfacing an error toast.

*Evidence:* services/book-service/internal/api/mcp_maps.go:436-438 (`toolWorldMapRemoveMarker`'s SQL — `DELETE FROM map_markers m USING world_maps wm WHERE m.id=$1 AND m.map_id=wm.id AND wm.owner_user_id=$2` — owner-scoped but NOT map_id-scoped: the lift trap) · services/book-service/internal/api/mcp_maps.go:43-54 (`requireMapOwner` — the uniform-404 no-oracle model to mirror) · services/book-service/internal/api/server.go:381-392 (the `/v1/worlds` chi Route block where `/maps/{map_id}` mounts) · services/book-service/internal/api/worlds.go:426-455 (`removeBookFromWorld` — the exact 204 handler shape + `parseUUIDParam`/`requireWorldOwner`/`writeError` house helpers) · services/api-gateway-bff/src/gateway-setup.ts:90 (`/v1/worlds` passthrough — zero gateway work) · services/book-service/internal/migrate/migrate.go:401-434 (`map_markers` table + CASCADE already exist — no migration) · docs/specs/2026-07-01-writing-studio/38_kg_and_world.md:301-302 (BE-15h's "404 = foreign map **or** marker not on this map" — the semantics BE-15i must match)

### Q-38-BE-14d-UNIFY-AUTHORABLE-KINDS
BUILD IT — narrow the tool to the EXISTING 4-value REST set (do NOT widen to the 8 seeded graph node-kinds). Rationale the PO may veto: the 4-set is what plan 30 pins twice (§4.1 BE-14c response literal + §6.3 gap #1), and narrowing costs the agent nothing it cannot get the RIGHT way — for `item`/`event`/`organization` the sanctioned path is author-in-glossary → `kg_project_entities_to_nodes`, which is also the *anchored* path spec 38 §3.1 A1 already tells the human to prefer (a manual node has no `glossary_entity_id` and can shadow — the `kg-glossary-fk-is-globally-unique` class). `kg_create_node` is an unblock-an-endpoint escape hatch, not the lore-authoring door.

EXACT CHANGES (7):

1. NEW FILE `services/knowledge-service/app/entity_kinds.py` (a leaf module beside `pricing.py`/`effort.py` — importable by both `routers/` and `tools/` with no cycle). ONE declaration, both shapes derived — no second list to drift:
```python
"""BE-14d — the ONE closed set of entity kinds a HUMAN (REST) or an AGENT (MCP)
may author directly into the KG. System-tier, admin-owned, read-only (CLAUDE.md
User Boundaries): no per-user tier, no write route. NOT glossary's entity_kinds
(those are per-user/per-book and editable) — different object, same word."""
from typing import Literal, get_args

AuthorableEntityKind = Literal["character", "concept", "faction", "location"]
AUTHORABLE_ENTITY_KINDS: tuple[str, ...] = get_args(AuthorableEntityKind)

def normalize_entity_kind(v: object) -> object:
    """Pydantic mode='before' normalizer — one normalization for both transports
    (today the tool strips and REST does not, so ' Character ' passes one and 422s
    the other)."""
    return v.strip().lower() if isinstance(v, str) else v
```

2. `routers/public/entities.py:975` — delete the local `_AUTHORABLE_KINDS` literal; import the constant. In `CreateEntityRequest` (`:977-996`) change `kind: str = Field(min_length=1, max_length=50)` to `kind: AuthorableEntityKind` + `@field_validator("kind", mode="before")(normalize_entity_kind)`; drop the manual `if self.kind not in ...` branch from `_validate` (keep the blank-name check). Wire text stays a 422 naming the set.

3. `tools/graph_schema_tools.py:459-463` — `kind: AuthorableEntityKind = Field(description="the entity kind (closed set)")` (drop min_length/max_length — invalid on a Literal) + the same `mode="before"` normalizer.

4. `tools/graph_schema_tools.py:841-846` (OpenAI function schema — source #2) — replace with `{"type": "string", "enum": list(AUTHORABLE_ENTITY_KINDS), "description": "the entity kind (closed set)"}`; drop minLength/maxLength. ALSO fix the tool description at `:829-833`: delete "item" — after the Literal, an `item` example is a guaranteed 422 the model will walk straight into.

5. `mcp/server.py:1126-1128` (FastMCP — source #3; FastMCP STRIPS extras, so the enum only reaches `tools/list` if it is IN the annotation) — `kind: Annotated[AuthorableEntityKind, "the entity kind — one of: character, concept, faction, location"]`. Also delete "item" from the description at `:1115-1116`.

6. `tools/graph_schema_tools.py:1720-1723` — `kind = args.kind` (already normalized); the `not kind` half of the non-empty guard is now dead — keep the `name` half.

7. BE-14c (`GET /v1/knowledge/entity-kinds`) returns `{"kinds": list(AUTHORABLE_ENTITY_KINDS)}` — it IMPORTS the constant, never re-lists it. Same for the FE `<select>` (it fetches BE-14c; no hard-coded array).

TESTS (in `services/knowledge-service/tests/unit/test_graph_schema_tools.py`, beside the existing `kg_create_node` block at `:1537`, plus the REST test module):
- `execute_tool(ctx, "kg_create_node", {"name": "Sword", "kind": "item"})` → `res.success is False` and the error names the closed set. THIS is the inverse gap; it must go red before the fix.
- ONE 4-way drift guard (the machine check that kills the 3-schema-source class): the OpenAI schema's `kind["enum"]` == the FastMCP tools/list JSON schema's `kind.enum` == the accepted set of `CreateEntityRequest` == BE-14c's `kinds` == `list(AUTHORABLE_ENTITY_KINDS)`.
- `kg_create_node {"kind": " Character "}` and `POST /v1/knowledge/entities {"kind": "Character"}` BOTH succeed and BOTH persist `character` (the normalization is now shared).
- Existing `test_tool_count == 37` is unaffected (no new tool).

BLAST RADIUS: none on data (no migration; `merge_entity` is unchanged) and none on the shipped World-Map "+ add place" path (it sends `kind='location'`). Only behavior change: an agent can no longer mint an off-set kind — intended.

NOTE FOR THE REGISTER (do not fix in this slice — out of scope, gate #1): the constant's `faction` is glossary's ALIAS for the canonical `organization` (`services/glossary-service/internal/migrate/migrate.go:203` seeds `('faction','organization')`), and knowledge's `concept` maps to glossary's `terminology` (`app/extraction/entity_resolver.py:69-74`). So a manually authored `faction` node carries a kind_code that will never anchor. That is a pre-existing KG↔glossary vocabulary drift, NOT something BE-14d should silently rename on a shipped REST route.

*Evidence:* services/knowledge-service/app/tools/graph_schema_tools.py:459-463 (`kind: str = Field(min_length=1, max_length=100)` — the free string) · :841-846 (OpenAI function schema, `"type":"string"`, no enum) · :1720-1723 (handler only strips) · services/knowledge-service/app/mcp/server.py:1126-1128 (`kind: Annotated[str, ...]` — FastMCP source) · services/knowledge-service/app/routers/public/entities.py:975 (`_AUTHORABLE_KINDS = {"character","location","faction","concept"}`) + :992-995 (the REST-only gate) · widening rejected on: services/knowledge-service/app/db/seed_graph_schemas.py:93-103 (8 seeded node kinds incl. `item`) vs docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md §4.1 BE-14c (pins `["character","concept","faction","location"]`) · alias evidence: services/glossary-service/internal/migrate/migrate.go:203

### Q-38-BE-15l-REGION-DELETE
BUILD IT — this is unbuilt work, not a question. No REST map surface exists today (book-service exposes maps ONLY as MCP tools + one dead `/internal` image route), so BE-15l is a route the builder writes. Concrete instruction:

1) NEW FILE `services/book-service/internal/api/world_maps.go` (REST sibling of `worlds.go`; mirrors the SQL in `mcp_maps.go`). Add:

```go
// deleteMapRegion — DELETE /v1/worlds/maps/{map_id}/regions/{region_id} → 204.
// Owner-scoped via JOIN to world_maps.owner_user_id AND gated on the region's
// parent map (rg.map_id=$2), so a region on ANOTHER map addressed under your
// map_id deletes 0 rows → the same uniform 404 (no cross-map/cross-owner oracle).
func (s *Server) deleteMapRegion(w http.ResponseWriter, r *http.Request) {
	mapID, ok := parseUUIDParam(w, r, "map_id")
	if !ok { return }
	regionID, ok := parseUUIDParam(w, r, "region_id")
	if !ok { return }
	ownerID, ok := s.requireUserID(r)
	if !ok { writeError(w, http.StatusUnauthorized, "BOOK_FORBIDDEN", "unauthorized"); return }
	tag, err := s.pool.Exec(r.Context(), `
DELETE FROM map_regions rg USING world_maps wm
WHERE rg.id=$1 AND rg.map_id=$2 AND rg.map_id=wm.id AND wm.owner_user_id=$3`, regionID, mapID, ownerID)
	if err != nil { writeError(w, http.StatusInternalServerError, "BOOK_CONFLICT", "failed to delete region"); return }
	if tag.RowsAffected() == 0 { writeError(w, http.StatusNotFound, "MAP_REGION_NOT_FOUND", "region not found"); return }
	w.WriteHeader(http.StatusNoContent)
}
```
The ONLY delta from the MCP tool `toolWorldMapRemoveRegion` (mcp_maps.go:443-461) is the added `rg.map_id=$2` clause — the tool keys on region_id alone, but the REST path carries `map_id`, and a path segment that is not enforced is a scope hole (repo lesson "gate on the loaded row's parent"). This is exactly the marker rule the spec already states at 38_kg_and_world.md:301 ("404 = foreign map **or** marker not on this map"); apply it to regions identically.

2) MOUNT it in `services/book-service/internal/api/server.go` inside the existing `r.Route("/v1/worlds", …)` block (server.go:381-388), as a sibling group to `/{world_id}`:
```go
r.Route("/maps/{map_id}", func(r chi.Router) {
    // … BE-15c/d/e/f/g/j siblings land here too …
    r.Delete("/regions/{region_id}", s.deleteMapRegion)
})
```
chi resolves the static `maps` segment before the `{world_id}` param node, so there is no collision — but add one routing assertion that `DELETE /v1/worlds/maps/<uuid>/regions/<uuid>` reaches `deleteMapRegion` and not the world handlers.

3) NO gateway change needed — `gateway-setup.ts:90` already proxies everything under `/v1/worlds` (`pathFilter: pathname.startsWith('/v1/worlds')`), so the route is public the moment it is mounted. Do NOT add a per-route proxy entry.

4) TESTS — `services/book-service/internal/api/world_maps_rest_db_test.go` (xdist/DB-style, mirroring `mcp_maps_test.go`): (a) 204 + row gone from `map_regions`; (b) repeat DELETE ⇒ 404 (not idempotent-204 — the spec's error list is 401·404 and `deleteWorld` at worlds.go:319-329 sets the house precedent); (c) region belongs to map B, called under map A's id ⇒ **404 and the row still exists**; (d) map owned by another user ⇒ 404 with a byte-identical body to (c); (e) no Authorization header ⇒ 401.

Defaults I picked (veto-able): repeat-DELETE returns 404 rather than 204, and the error code string is `MAP_REGION_NOT_FOUND`. Both follow existing book-service convention.

*Evidence:* services/book-service/internal/api/mcp_maps.go:443-461 (`toolWorldMapRemoveRegion` — the owner-scoped `DELETE FROM map_regions rg USING world_maps wm` to lift; note it does NOT gate on map_id) · services/book-service/internal/api/server.go:381-388 (the `/v1/worlds` chi block where the route mounts; no `/maps` group exists yet) · services/book-service/internal/api/server.go:432 (`parseUUIDParam`) · services/book-service/internal/api/worlds.go:309-330 (`deleteWorld` — the 401/404/204 house pattern) · services/book-service/internal/migrate/migrate.go:425-434 (`map_regions`, FK `map_id → world_maps ON DELETE CASCADE`) · services/api-gateway-bff/src/gateway-setup.ts:90 (`/v1/worlds*` passthrough already covers it) · docs/specs/2026-07-01-writing-studio/38_kg_and_world.md:305 (BE-15l contract) + :301 (the not-on-this-map ⇒ 404 rule being extended to regions)

### Q-38-BE-15k-REGION-PATCH
BUILD IT AS SPEC'D — the spec's semantics are correct and the code confirms every premise (no OCC substrate on map_regions; polygon is a single JSONB column; the uniform-404 owner-join already exists). Concrete instruction:

1) ROUTE — `services/book-service/internal/api/server.go:381`, inside the existing `r.Route("/v1/worlds", …)` block, add (alongside the other 8b routes): `r.Patch("/maps/{map_id}/regions/{region_id}", s.patchMapRegion)`. No gateway change (`gateway-setup.ts:86-90` already proxies all `/v1/worlds`).

2) HANDLER — new file `services/book-service/internal/api/world_maps_rest.go` (home for BE-15a..l), `func (s *Server) patchMapRegion(w http.ResponseWriter, r *http.Request)`. Body copies `patchWorld` (`worlds.go:260-303`) exactly:
   - `parseUUIDParam(w,r,"map_id")` + `parseUUIDParam(w,r,"region_id")`; `s.requireUserID(r)` ⇒ 401 `BOOK_FORBIDDEN`.
   - `s.requireMapOwner(ctx, mapID, ownerID)` (mcp_maps.go:45) ⇒ 404 `MAP_NOT_FOUND` "map not found" (no existence oracle).
   - Decode into `map[string]any` — NOT a pointer struct. Key-presence is the contract: **absent = unchanged · explicit `null` = clear** (only `entity_id` is clearable).
   - Build `setClauses := []string{"updated_at=now()"}` then:
     * `name` present ⇒ must be a non-blank string, else **422** `BOOK_VALIDATION_ERROR`; `SET name=$n`.
     * `polygon` present ⇒ **REPLACE-WHOLE**. `null` ⇒ **422** ("polygon cannot be cleared" — the column is `JSONB NOT NULL`, migrate.go:430). Otherwise re-use the validation lifted from `toolWorldMapAddRegion` (mcp_maps.go:199-206): ≥3 points, each an `[x,y]` pair with x,y ∈ [0,1], else **422**. `json.Marshal` the whole array and `SET polygon=$n`. There is **no** per-vertex/merge path and no point-index addressing — the FE already holds the full ring from BE-15c and re-sends it.
     * `entity_id` present ⇒ `null` ⇒ `SET entity_id=NULL`; a string ⇒ `uuid.Parse` (invalid ⇒ **422**) ⇒ `SET entity_id=$n`.
     * No recognized key ⇒ do NOT error: the `updated_at=now()` touch runs and the row is returned 200 (same as `patchWorld`).
   - ONE owner-scoped statement (mirrors the region DELETE at mcp_maps.go:452-455, plus the map-binding predicate):
     `UPDATE map_regions rg SET <sets> FROM world_maps wm WHERE rg.id=$1 AND rg.map_id=$2 AND rg.map_id=wm.id AND wm.owner_user_id=$3 RETURNING rg.id, rg.map_id, rg.name, rg.polygon, rg.entity_id, rg.created_at, rg.updated_at`
     `pgx.ErrNoRows` ⇒ **404** `REGION_NOT_FOUND` — this single 404 covers foreign map, missing region, AND a region that exists but belongs to a *different* map (including another map of the same owner). Return `200 {region}` on success.

3) NO OCC — deliberate and grounded: `map_regions` has no `version` column and the spec's migration adds only `updated_at`. Do NOT require/accept `If-Match` here, and do NOT return 412/428. Reshape is last-write-wins on the whole polygon (a per-vertex merge across two writers would produce a self-intersecting ring — strictly worse than LWW). Corollary the builder must respect: **a region PATCH must NOT bump `world_maps.version` or `world_maps.updated_at`** — if it did, an FE holding an If-Match for BE-15d (map rename) would spuriously 412 after any drag.

4) ONE HOME / GG-2 — hoist two helpers so REST and BE-15m's `world_map_update_region` MCP tool cannot drift: `validateRegionPolygon(pts [][]float64) ([]byte, error)` (lifted verbatim from mcp_maps.go:199-206, now also used by `toolWorldMapAddRegion`) and `updateRegionOwned(ctx, ownerID uuid.UUID, mapID *uuid.UUID, regionID uuid.UUID, patch regionPatch) (regionOut, error)` — the MCP tool passes `mapID=nil` (it is keyed on region_id only, like `world_map_remove_region`), the REST route passes the path map_id.

5) TESTS — `world_maps_rest_db_test.go` (pattern: `mcp_maps_test.go`), all against the real pool: (a) seed a 5-point region, PATCH with 3 points ⇒ the stored polygon has exactly 3 points (proves REPLACE-WHOLE, not merge/append); (b) 2-point polygon ⇒ 422; (c) a coord of 1.5 ⇒ 422; (d) `polygon: null` ⇒ 422; (e) `{"entity_id": null}` ⇒ entity_id NULL, name+polygon untouched; `{}` ⇒ nothing changed but `updated_at` advanced; (f) `updated_at` strictly advances across a PATCH (the spec's mandated assertion — read before/after); (g) another owner's region ⇒ 404, and a region on a DIFFERENT map of the SAME owner ⇒ 404; (h) two sequential PATCHes with no `If-Match` both return 200 (pins "no OCC").

Default I am choosing (veto-able): "no recognized key ⇒ 200 no-op touch" rather than 422, matching `patchWorld`.

*Evidence:* services/book-service/internal/migrate/migrate.go:426-433 (map_regions: polygon JSONB NOT NULL, no version ⇒ no OCC substrate) · services/book-service/internal/api/mcp_maps.go:199-206 (polygon ≥3 pts, each in [0,1] — validation to lift) · mcp_maps.go:452-460 (owner-joined region write + uniform "region not found") · mcp_maps.go:45-55 (requireMapOwner) · services/book-service/internal/api/worlds.go:260-303 (map[string]any presence-based PATCH; updated_at=now() first SET clause) · services/book-service/internal/api/server.go:381 (/v1/worlds route block) · services/api-gateway-bff/src/gateway-setup.ts:86-90 (worldsProxy already covers the path)

### Q-38-BE-15j-REGION-CREATE
BUILD IT — it is unbuilt work, not a blocker. Everything but the HTTP surface already exists (table + validation + owner-scoping live inside the MCP tool). Builder instruction, exactly:

1) SHARED VALIDATOR (kill drift between MCP + REST). In `services/book-service/internal/api/mcp_maps.go`, extract the body of `toolWorldMapAddRegion` lines 194-215 into one func in that same file:
   `func validateRegionInput(name string, polygon [][]float64, entityID string) (cleanName string, polygonJSON []byte, entity any, err error)` — trims name (empty ⇒ err "name is required"), rejects `len(polygon) < 3` ("polygon needs at least 3 [x,y] points"), rejects any `len(pt)!=2 || pt[0]<0 || pt[0]>1 || pt[1]<0 || pt[1]>1` ("each polygon point must be [x,y] with x,y in [0,1]"), calls the existing `parseOptionalEntityID`, and `json.Marshal`s the polygon. Rewrite `toolWorldMapAddRegion` to call it (behavior identical; its existing tests in `mcp_maps_test.go` must stay green).

2) MIGRATION (additive, non-destructive) in `services/book-service/internal/migrate/migrate.go`, appended as a new numbered step (base tables are at :401-434, which have no `updated_at`):
   `ALTER TABLE map_regions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();`
   `ALTER TABLE map_markers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();`
   (spec 38 line 311; BE-15c requires `updated_at` on every marker/region in the GET payload, and BE-15k's last-write-wins PATCH needs it.)

3) NEW FILE `services/book-service/internal/api/maps.go` — the REST siblings of the map MCP tools. For BE-15j add:
   `func (s *Server) createMapRegion(w http.ResponseWriter, r *http.Request)`:
   - `ownerID, ok := s.requireUserID(r)`; !ok ⇒ `writeError(w, 401, "BOOK_FORBIDDEN", "unauthorized")`.
   - `mapID, ok := parseUUIDParam(w, r, "map_id")` (server.go:432); !ok ⇒ it already 400s.
   - Decode `{ Name string `json:"name"`; Polygon [][]float64 `json:"polygon"`; EntityID string `json:"entity_id"` }`; decode error ⇒ 422 `BOOK_VALIDATION_ERROR`.
   - `validateRegionInput(...)` err ⇒ `writeError(w, 422, "BOOK_VALIDATION_ERROR", err.Error())`.
   - `s.requireMapOwner(r.Context(), mapID, ownerID)` (mcp_maps.go:45) err ⇒ `writeError(w, 404, "MAP_NOT_FOUND", "map not found")` — a foreign map is a 404, NOT a 403 (no cross-owner existence oracle; identical to `maps_image.go:52`). map_regions has no owner column, so this JOIN-to-world_maps ownership check is the ONLY tenancy gate — it is mandatory (spec 38 line 403).
   - `INSERT INTO map_regions(map_id,name,polygon,entity_id) VALUES($1,$2,$3,$4) RETURNING id, created_at, updated_at` then `writeJSON(w, 201, map[string]any{"region": {"region_id","map_id","name","polygon" (the [][]float64 as sent),"entity_id" (null when absent),"created_at","updated_at"}})`. Shape mirrors `regionOut` (mcp_maps.go:240) plus `updated_at`. DB error ⇒ 500 `BOOK_CONFLICT`.

4) ROUTE in `services/book-service/internal/api/server.go`, inside the existing `r.Route("/v1/worlds", ...)` block (:380-390), as a SIBLING of `/{world_id}` (chi ranks the static segment `maps` above the `{world_id}` param, so there is no collision):
   `r.Route("/maps/{map_id}", func(r chi.Router) { r.Post("/regions", s.createMapRegion) })` — the same group later carries BE-15c/15g..15l.

5) GATEWAY: no change. `services/api-gateway-bff/src/gateway-setup.ts:90` already prefix-proxies every `/v1/worlds*` path to book-service.

6) TESTS — new `services/book-service/internal/api/maps_rest_test.go` (copy the pgxmock+httptest harness from `mcp_maps_test.go`): (a) no Bearer ⇒ 401; (b) map owned by another user ⇒ 404 `MAP_NOT_FOUND` (assert NOT 403); (c) 2-point polygon ⇒ 422; (d) a point at 1.5 ⇒ 422; (e) happy path ⇒ 201 with `region.region_id`, `region.polygon` round-tripped exactly, `region.updated_at` present, `entity_id` null when omitted.

DEFAULTS I chose (veto if you disagree): validation errors are 422 `BOOK_VALIDATION_ERROR` (spec 38 line 303 says 422); `entity_id` is NOT validated against glossary — it is a soft cross-service UUID by design (spec 38 line 229, migrate.go:429), so a bad id stores fine and the FE resolves it leniently.

*Evidence:* services/book-service/internal/api/mcp_maps.go:186-225 (toolWorldMapAddRegion — all validation + INSERT already written, MCP-only); mcp_maps.go:45 (requireMapOwner — the tenancy JOIN); services/book-service/internal/api/server.go:379-391 (the /v1/worlds chi group has NO /maps routes — the REST surface simply does not exist); services/book-service/internal/migrate/migrate.go:425-434 (map_regions: id, map_id, name, polygon JSONB, entity_id, created_at — no updated_at); services/book-service/internal/api/maps_image.go:44-56 (the 404-not-403 owner-scoped pattern to copy); services/api-gateway-bff/src/gateway-setup.ts:90 (BFF already proxies /v1/worlds* — no gateway work).

### Q-38-BE-15f-PUBLIC-IMAGE-UPLOAD
BUILD the public route and RETIRE the internal one (do NOT mount it twice). OQ-3's premise is verified in code: `POST /internal/worlds/maps/{map_id}/image` has zero callers repo-wide. Concrete builder steps (M8b.1):

1. `services/book-service/internal/api/maps_image.go` — extract the body into a shared core:
   `func (s *Server) writeWorldMapImage(w http.ResponseWriter, r *http.Request, mapID, userID uuid.UUID)` containing everything currently at lines 40–125 (MinIO-nil 503 → owner-scoped SELECT 404 → multipart → 415/413 → dims → PutObject → UPDATE → old-object sweep → 200 JSON). Keep every error code/body byte-identical: `MEDIA_UNAVAILABLE`/503, `MAP_NOT_FOUND`/404, `UNSUPPORTED_MEDIA_TYPE`/415, `MEDIA_TOO_LARGE`/413, `MEDIA_UPLOAD_FAILED`/500.
2. New public handler in the same file:
   `func (s *Server) uploadWorldMapImagePublic(w http.ResponseWriter, r *http.Request)` → `userID, ok := s.requireUserID(r)` (server.go:415); `!ok` ⇒ `writeError(w, 401, "UNAUTHORIZED", "authentication required")`; `mapID, ok := parseUUIDParam(w, r, "map_id")`; then `s.writeWorldMapImage(w, r, mapID, userID)`. DELETE the old `?user_id`-parsing entry function (maps_image.go:30-39) — no `user_id` query param survives anywhere.
3. `services/book-service/internal/api/server.go` — DELETE line 200 (`r.Post("/worlds/maps/{map_id}/image", s.uploadWorldMapImage)`) from the `/internal` group. Mount the public route inside the existing `r.Route("/v1/worlds", …)` (server.go:381-392) as a STATIC `maps` sub-router registered BEFORE the `/{world_id}` sub-route (the `/v1/books` `/diary` precedent, server.go:255): `r.Route("/maps/{map_id}", func(r chi.Router){ … ; r.Post("/image", s.uploadWorldMapImagePublic) })` — the same sub-router that will hold BE-15c/d/e and the markers/regions children.
4. FIX THE 413 CONTRACT while extracting (spec 38:299 promises 413, code returns 400): in `writeWorldMapImage`, before `ParseMultipartForm`, set `r.Body = http.MaxBytesReader(w, r.Body, int64(maxImageSize)+(1<<20))` and map a `ParseMultipartForm` failure to `writeError(w, http.StatusRequestEntityTooLarge, "MEDIA_TOO_LARGE", …)` instead of the current 400 (maps_image.go:59-62). Keep the `fh.Size > maxImageSize` 413 check as-is.
5. Repoint the existing test: `services/book-service/internal/api/mcp_maps_test.go:141` builds `"/internal/worlds/maps/"+mapID+"/image"` — change it to `"/v1/worlds/maps/"+mapID+"/image"` with a Bearer JWT, and ADD two cases: no Authorization header ⇒ 401; a map owned by another user ⇒ 404 with the identical `MAP_NOT_FOUND` body (no enumeration oracle, matching `requireMapOwner`, mcp_maps.go:45).
6. Update the now-stale docstrings that point at the internal route: `maps_image.go:3-10` header comment and `mcp_maps.go:5`.
7. Gateway: ZERO changes — `worldsProxy` (gateway-setup.ts:86-91, dispatch :592) already forwards `/v1/worlds*` to book-service, and the app runs `bodyParser:false` (`json()` is mounted only on `/v1/ai/tools` :402 and `/v1/assistant` :406), so multipart streams through untouched, exactly as `booksApi.uploadChapterMedia` proves for `/v1/books/**/media`.
8. FE (M8b.3) calls `POST /v1/worlds/maps/{map_id}/image` with a `FormData` `file` field + the Bearer token — mirror `booksApi.uploadChapterMedia` (frontend/src/features/books/api.ts:410); do NOT set Content-Type manually (let the browser set the multipart boundary). Inspector must not render "0 × 0" when `image_w`/`image_h` are null (webp has no stdlib decoder, maps_image.go:16-19).

Default chosen (PO may veto): retire, not dual-mount. Rationale — a second front door with a `?user_id` identity param and no caller is a standing tenancy foot-gun and an audit false-positive; if a BFF-mediated or worker upload ever needs it, re-adding a thin `/internal` mount over `writeWorldMapImage` is a 3-line change because the core is already extracted in step 1.

*Evidence:* services/book-service/internal/api/maps_image.go:30-39 (identity from `?user_id`) + :59-62 (oversize ⇒ 400, contradicting spec 38:299's 413); services/book-service/internal/api/server.go:200 (the ONLY mount, under `/internal`) vs server.go:381-392 (the `/v1/worlds` public group) and server.go:415 (`requireUserID`); zero callers: `grep -rn "worlds/maps" services/ frontend/src contracts/` returns only book-service's handler, mcp_maps.go:5 docstring, mcp_maps_test.go:141; gateway needs no change: services/api-gateway-bff/src/gateway-setup.ts:86-91 (`worldsProxy` pathFilter `/v1/worlds`) + :592 (dispatch) + :402/:406 (json() scoped to two non-proxy paths only, app is bodyParser:false).

### Q-38-UPDATEDAT-MUST-BE-READ
CONFIRMED — and it is worse than the spec says: `world_maps.updated_at` is ALREADY a write-only column at HEAD (it exists at `migrate.go:409`, and `grep -n "updated_at" services/book-service/internal/api/mcp_maps.go` returns ZERO matches — no SELECT reads it, no UPDATE bumps it). Ship all four legs in M8b.1+M8b.3, exactly as follows. Nothing here is deferrable; it is ~40 lines.

(1) MIGRATION — `services/book-service/internal/migrate/migrate.go`, forward-only block, as spec §4.2 already prescribes:
    ALTER TABLE world_maps  ADD COLUMN IF NOT EXISTS version INT NOT NULL DEFAULT 1;
    ALTER TABLE map_markers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
    ALTER TABLE map_regions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
  (`world_maps` already has `updated_at` — only `version` is new there.)

(2) WRITE (a) — every PATCH handler sets it. BE-15d `UPDATE world_maps SET name=$1, version=version+1, updated_at=now() WHERE id=$2 AND version=$3`. BE-15h `UPDATE map_markers SET …, updated_at=now() WHERE id=$n AND map_id=$m`. BE-15k `UPDATE map_regions SET …, updated_at=now() WHERE id=$n AND map_id=$m`. Do it in the SET clause of the same statement — never a second round-trip.

(3) WRITE — THE HOLE THE SPEC LEAVES, decided here (PO may veto): a marker/region write (BE-15g/h/i/j/k/l) MUST also bump the PARENT map row, in the same tx: `UPDATE world_maps SET updated_at=now() WHERE id=$1`. Reason: BE-15b feeds the rail's "edited X ago" per map — if only rename bumps it, a map whose pins were all dragged this morning renders "edited 3 weeks ago", i.e. the read consumer lies. TRAP: the child write must bump `updated_at` ONLY, **never `version`** — `version` is the OCC token for BE-15d's If-Match, and bumping it on a pin-drag would 412 the user's unrelated rename for no reason. Put that as a comment on the line.

(4) READ (b) — extend the SHARED structs (they back the MCP tool AND the REST route, so one edit buys agent+human parity): add `UpdatedAt time.Time \`json:"updated_at"\`` to `worldMapDetail` (`mcp_maps.go:74-78`), `markerOut` (`:233-238`) and `regionOut` (`:241-244`), and add the column to ALL FOUR existing SELECTs that build them — `mcp_maps.go:264` (map detail), `:280` (markers), `:303` (regions), `:350` (list). Add `version` to `worldMapDetail` + the `:264`/`:350` SELECTs for the same reason (BE-15d's If-Match is unusable if the client is never told the version). This makes BE-15c/BE-15b return it and makes `world_map_get` return it too — additive, no MCP schema break.

(5) READ (c) — FE. In `WorldMapPanel.tsx`'s inspector, render `formatRelative(marker.updated_at)` / `formatRelative(region.updated_at)` as a muted "edited 5m ago" line under the selected marker/region; in the map rail row (fed by BE-15b) render `formatRelative(map.updated_at)`. REUSE the existing exported helper `formatRelative` from `frontend/src/features/jobs/lib.ts:69` (it already returns exactly "just now"/"5m ago"/"2h ago"/"3d ago"). Do NOT hand-roll a fourth copy — three private ones already exist (SessionSidebar.tsx:59, VersionSidebar.tsx:13, NotificationItem.tsx:54) and CLAUDE.md's one-home rule applies. This line is ALSO the drag-PATCH's landing proof: after a pin drag the inspector must flip to "just now", which distinguishes "the PATCH landed" from "the canvas merely repainted optimistically".

(6) TEST (d) — Go, in `services/book-service/internal/api/` (mirror `mcp_maps_test.go`'s harness): `TestMarkerPatchAdvancesUpdatedAt` — create map + marker, read `updated_at` via BE-15c, sleep ~5ms (or assert strict `>` on the timestamptz), PATCH x/y, re-read, assert `after.After(before)` AND that the PARENT map's `updated_at` also advanced AND that the parent's `version` did NOT change. Same shape for region PATCH and for BE-15d (map rename: `updated_at` advances AND `version` increments by exactly 1). NOTE: bind Go `time.Time`, not a string — asyncpg-style `timestamptz`-vs-string binding bugs bite here (see the repo lesson `asyncpg-timestamptz-param-needs-datetime`; pgx is stricter than you expect).

(7) FE test: one vitest case in the WorldMapPanel suite asserting the inspector shows "just now" after a mocked PATCH response whose `updated_at` is now — i.e. the field is CONSUMED, proven by rendered effect, not merely present in the payload.

DoD for M8b.1/M8b.3 gains one literal line: "`updated_at` is read by a rendered consumer and its advance is asserted by a Go test — no write-only column ships."

*Evidence:* services/book-service/internal/api/mcp_maps.go — `grep -n "updated_at|UpdatedAt"` = ZERO matches, while `migrate.go:409` declares `world_maps.updated_at TIMESTAMPTZ NOT NULL DEFAULT now()` → the column is ALREADY write-only at HEAD. The four SELECTs that would carry it: mcp_maps.go:264 (`SELECT id, world_id, name, image_object_key FROM world_maps WHERE id=$1 AND owner_user_id=$2`), :280 (`SELECT id, label, x, y, entity_id, marker_type FROM map_markers …`), :303 (`SELECT id, name, polygon, entity_id FROM map_regions …`), :350 (list). Structs to extend: worldMapDetail mcp_maps.go:74-78, markerOut :233-238, regionOut :241-244 (shared by MCP `world_map_get` + REST BE-15c). Child tables lack the column entirely: migrate.go:414-434 (`created_at` only). FE helper to reuse: frontend/src/features/jobs/lib.ts:69 `export function formatRelative(iso, now): string | null` → "just now" / "5m ago". Spec text being adjudicated: docs/specs/2026-07-01-writing-studio/38_kg_and_world.md:316 (the 🔴 note) + :295-296 (BE-15b/BE-15c) + :310-314 (migration).

### Q-38-CHILD-ROUTE-SCOPE-GATE
CONFIRMED — implement exactly as the concern states, and extend it to the INSERT routes (which the concern misses and which are the same defect). Binding rule for M8b.1: **no map-child SQL statement may name `map_markers`/`map_regions` without joining `world_maps wm` and constraining `wm.owner_user_id = $caller`. There is no pre-check SELECT on the map — the gate IS the single statement.**

**(1) Child WRITE by id — BE-15h/i/k/l — ONE statement, BOTH legs (`m.id=$marker` AND `m.map_id=$map` AND `m.map_id=wm.id` AND `wm.owner_user_id=$caller`):**
```sql
-- BE-15h PATCH /v1/worlds/maps/{map_id}/markers/{marker_id}
UPDATE map_markers m
SET label = COALESCE($4, m.label), x = COALESCE($5, m.x), y = COALESCE($6, m.y),
    marker_type = ..., entity_id = ..., updated_at = now()
FROM world_maps wm
WHERE m.id = $1 AND m.map_id = $2 AND m.map_id = wm.id AND wm.owner_user_id = $3
RETURNING m.id, m.map_id, m.label, m.x, m.y, m.marker_type, m.entity_id, m.created_at, m.updated_at;
-- BE-15i DELETE …/markers/{marker_id}
DELETE FROM map_markers m USING world_maps wm
WHERE m.id = $1 AND m.map_id = $2 AND m.map_id = wm.id AND wm.owner_user_id = $3;
-- BE-15k / BE-15l: identical shape on map_regions rg.
```
`pgx.ErrNoRows` (PATCH) / `RowsAffected() == 0` (DELETE) ⇒ 404. Note `m.map_id = $2` is the leg the existing tools do NOT have and the one this concern is about: without it, a marker id from another of YOUR maps still patches (owner passes, containment doesn't).

**(2) Child CREATE — BE-15g/j — the same defect, gate the INSERT with `INSERT … SELECT` (never `VALUES` with a path-supplied `map_id`):**
```sql
INSERT INTO map_markers (map_id, label, x, y, marker_type, entity_id)
SELECT wm.id, $2, $3, $4, $5, $6 FROM world_maps wm
WHERE wm.id = $1 AND wm.owner_user_id = $7
RETURNING id, map_id, label, x, y, marker_type, entity_id, created_at, updated_at;
```
0 rows inserted ⇒ 404. (Same for `map_regions`.)

**(3) UNIFORM 404, no oracle, and NO two-step check.** Every child-route failure mode — map missing · map not yours · marker missing · marker belongs to a different map — collapses to one identical body: `writeError(w, 404, "MARKER_NOT_FOUND", "marker not found")` (`REGION_NOT_FOUND`/"region not found" for regions). Map-level routes use the existing `MAP_NOT_FOUND`/"map not found" (mcp_maps.go:392, maps_image.go:51). **Do not** SELECT the map first to "give a better error" — a distinct "map exists but marker isn't on it" vs "map not yours" is precisely the cross-tenant existence oracle the single-statement form eliminates.

**(4) The ONE exception where `RowsAffected()==0` is NOT a 404 — BE-15d (`PATCH /v1/worlds/maps/{map_id}` with If-Match):** run `UPDATE world_maps SET name=$3, version=version+1, updated_at=now() WHERE id=$1 AND owner_user_id=$2 AND version=$4 RETURNING …`. On 0 rows, disambiguate with a second **owner-scoped** read `SELECT … FROM world_maps WHERE id=$1 AND owner_user_id=$2`: found ⇒ **412** + the current map as body; not found ⇒ **404** `MAP_NOT_FOUND`. The disambiguating read is owner-scoped, so it leaks nothing. (Missing `If-Match` header ⇒ 428 before any SQL.)

**(5) BE-15m MCP update tools** (`world_map_update_marker` / `world_map_update_region`, bare `marker_id`/`region_id`, no map_id in args): keep the owner leg via `FROM world_maps wm … m.map_id = wm.id AND wm.owner_user_id = $2` — same law, minus the containment leg (nothing to contain against). Mirror the `errors.New("marker not found")` uniform message at mcp_maps.go:438.

**(6) Go tests — literal DoD, per child route (4 REST child routes × these cases):** `TestPatchMarker_ForeignMap_404` (map owned by user B, marker really on it, caller A ⇒ 404 with a body byte-identical to a random-UUID map ⇒ assert both responses equal); `TestPatchMarker_MarkerFromAnotherMap_404` (caller owns map1 AND map2, marker lives on map2, addressed under map1 ⇒ 404 **and** assert the marker row on map2 is UNCHANGED afterward — the assertion that actually catches the bug); `TestCreateMarker_ForeignMap_404` (assert `SELECT count(*) FROM map_markers WHERE map_id=<victim>` did not increase); `TestPatchMarker_BumpsUpdatedAt` (timestamp advances). Same set for regions. Do NOT stop at asserting the status code — assert the victim row is untouched, or a handler that 404s *after* writing still passes.

*Evidence:* services/book-service/internal/migrate/migrate.go:414-434 (map_markers/map_regions have map_id FK only — NO owner_user_id column; ownership derivable only via world_maps) · services/book-service/internal/api/mcp_maps.go:431-439 + :452-460 (the existing correct owner-leg pattern: `DELETE FROM map_markers m USING world_maps wm WHERE m.id=$1 AND m.map_id=wm.id AND wm.owner_user_id=$2` + RowsAffected()==0 ⇒ uniform "marker not found") · mcp_maps.go:390 & maps_image.go:47-53 (map-level owner-scoped read ⇒ MAP_NOT_FOUND/"map not found") · docs/specs/2026-07-01-writing-studio/38_kg_and_world.md:300-305 (BE-15g..l — the child routes that carry BOTH map_id and child_id) and :297 (BE-15d — the 412/404 exception)

### Q-38-A3-FULL-RESPONSE-RENDER
UPHELD — full render, no "Created N" toast. Build it as a persistent card, not a transient toast, and FIX THE CONFLICTED COPY (the spec's string is stale against the code).

**FE — new file `frontend/src/features/knowledge/components/ProjectionResultCard.tsx`** (mirrors the existing `DrawerResultCard.tsx` pattern). Props: the BE-14a 200 body `{nodes_created, nodes_existing, entities_seen, skipped, nodes_conflicted, truncated, note?}`. It renders KEYS, never branches on their existence (BE-14a zero-fills — §4.1). It is rendered INLINE in the panel that fired the CTA (kg-graph empty state, kg-overview stats card, kg-schema secondary) and PERSISTS until dismissed or re-run — a toast auto-dismisses and is exactly how a partial projection gets missed. Rows, in order:
1. success line, always: `Seeded {nodes_created} new · {nodes_existing} already in the graph` (data-testid `proj-success`).
2. `nodes_conflicted > 0` ⇒ WARNING row (amber, data-testid `proj-conflicted`). **DO NOT use the spec's string.** The spec (and `graph_schema_tools.py:1694-1706`) says "already anchored by another knowledge project for this book" — that was true under the GLOBAL FK, which was DROPPED on 2026-07-10 (`neo4j_schema.cypher:69`). The live constraint is per `(user_id, project_id, glossary_entity_id)` (`:71-72`), and `anchor_loader.py:180-190` states a conflict is now an *in-project* duplicate. Ship: **"{n} entities couldn't be anchored — this project already has a node claiming them. Their data is unchanged; open the entity to reconcile."**
3. `truncated === true` ⇒ "the glossary read hit its page cap; more entities remain — run it again" + a `Run again` button (data-testid `proj-truncated`).
4. `skipped > 0` ⇒ muted line "{n} rows skipped" (data-testid `proj-skipped`).
5. `entities_seen === 0` ⇒ replace ALL of the above with the empty-glossary state + `host.openPanel('glossary')` (§3.1 A3 states).

**BE — fix-now, in the same slice (one file, root-cause clear, fails CLAUDE.md's defer gate):** correct the stale note in `graph_schema_tools.py:1694-1706` to match the per-project constraint. Leaving it means the AGENT tells the user a false reason while the GUI tells the true one — a cross-service normalization split-brain on the very counters this question exists to protect.

**TEST (the enforcement — `checklist-is-self-report-enforce-by-tests`):** a vitest on `ProjectionResultCard` fed `{nodes_created:3, nodes_existing:1, entities_seen:9, skipped:2, nodes_conflicted:2, truncated:true}` asserting ALL FOUR testids are present; a second case `{…, nodes_conflicted:0, skipped:0, truncated:false}` asserting `proj-conflicted`/`proj-truncated`/`proj-skipped` are `null` while `proj-success` renders. Without this test, a builder "simplifying" it back to a toast reds nothing.

PO can veto the reworded conflicted string, but not the fact — the old string is false against HEAD.

*Evidence:* services/knowledge-service/app/db/neo4j_schema.cypher:69-72 (global `entity_glossary_id_unique` DROPPED; `entity_glossary_fk_unique` is per (user_id, project_id, glossary_entity_id)) · services/knowledge-service/app/extraction/anchor_loader.py:180-190 + 231-241 ("a conflict here signals an unexpected duplicate WITHIN one project, not the old cross-project clash") · services/knowledge-service/app/tools/graph_schema_tools.py:1681-1707 (tool omits `nodes_conflicted`/`truncated` when falsy AND still emits the stale "another knowledge project for this book already owns them" note) · docs/specs/2026-07-01-writing-studio/38_kg_and_world.md:140-145 (A3 render list) and :281 (BE-14a zero-fill contract) · frontend/src/features/knowledge/components/DrawerResultCard.tsx (the card pattern to mirror)

### Q-38-BE-15h-MARKER-PATCH
BUILD IT AS SPEC'D — the semantics are already a solved problem in this repo; copy `patchWorld`. No new invention, no OCC.

**Where:** new file `services/book-service/internal/api/worlds_maps.go` (all of BE-15a..15l live here; keep `worlds.go` for the world container). Register in `services/book-service/internal/api/server.go` inside the EXISTING `r.Route("/v1/worlds", …)` block (server.go:381-392), as a sibling of `r.Route("/{world_id}", …)`:
```go
r.Route("/maps/{map_id}", func(r chi.Router) {
    r.Get("/", s.getWorldMap)                                  // BE-15c
    r.Patch("/", s.patchWorldMap)                              // BE-15d
    r.Delete("/", s.deleteWorldMap)                            // BE-15e
    r.Post("/image", s.uploadWorldMapImagePublic)              // BE-15f
    r.Post("/markers", s.createWorldMapMarker)                 // BE-15g
    r.Patch("/markers/{marker_id}", s.patchWorldMapMarker)     // BE-15h  ← this Q
    r.Delete("/markers/{marker_id}", s.deleteWorldMapMarker)   // BE-15i
    …regions…
})
```
chi's trie prefers the STATIC `maps` node over the `{world_id}` param node at the same level, so this does not collide — but write one route test asserting `PATCH /v1/worlds/maps/<uuid>/markers/<uuid>` reaches `patchWorldMapMarker` and is NOT swallowed by `{world_id}`. Zero gateway changes (`worldsProxy` already passes `/v1/worlds*` — gateway-setup.ts:90).

**Tri-state decode — do NOT use a typed struct with `*string` fields (a pointer cannot tell absent from `null`).** Use the house pattern verbatim: decode into `map[string]any` and branch on KEY PRESENCE, exactly as `patchWorld` does (worlds.go:270-292) and `patchBook` (server.go:1022-1046):
```go
var in map[string]any
if err := json.NewDecoder(r.Body).Decode(&in); err != nil { 400 BOOK_VALIDATION_ERROR }
setClauses := []string{"updated_at=now()"}
args := []any{markerID, mapID, ownerID}; paramIdx := 4
if v, ok := in["label"]; ok { … }   // present
```
Per-field rules (map_markers schema — migrate.go:414-424 — `label`/`x`/`y` are NOT NULL; `entity_id`/`marker_type` are nullable):
- `label`  — absent: unchanged. present+string: `TrimSpace` non-empty else **422**. present+`null`: **422** (column is NOT NULL — `null` is NOT a clear here).
- `x`,`y`  — absent: unchanged. present: must assert to `float64` and be in `[0,1]` else **422** (mirror mcp_maps.go:155-157). present+`null`: **422**.
- `marker_type` — absent: unchanged. present+`null`: **SET NULL**. present+string: set (free-form; no enum — BE-15m note). present+non-string: **422** (do NOT reuse `stringFromAny` blindly here: server.go:1124-1132 returns `nil` for a non-string, which would silently CLEAR the field on a typo — the silent-swallow bug class).
- `entity_id` — absent: unchanged. present+`null`: **SET NULL**. present+string: `uuid.Parse` else **422**. (Soft cross-service ref, no FK — do not try to validate it against glossary.)
- `{}` (no keys) — **200 with the current marker**, `updated_at` bumped. Do NOT add a "nothing to do" no-op guard and do NOT 422; a false no-op is worse than a redundant idempotent write.

**Ownership + 404 in ONE statement** (no pre-read → no TOCTOU, and no cross-owner existence oracle; mirrors `toolWorldMapRemoveMarker`'s owner-scoped JOIN, mcp_maps.go:431-439):
```sql
UPDATE map_markers m SET <setClauses>
FROM world_maps wm
WHERE m.id=$1 AND m.map_id=$2 AND m.map_id=wm.id AND wm.owner_user_id=$3
RETURNING m.id, m.label, m.x, m.y, m.entity_id, m.marker_type, m.updated_at
```
`pgx.ErrNoRows` ⇒ **404 `MARKER_NOT_FOUND` / "marker not found"** — uniformly for all four misses: foreign map · map not yours · marker on a DIFFERENT map · marker already DELETED. Same body in every case. 401 via `s.requireUserID(r)` → `writeError(w, 401, "BOOK_FORBIDDEN", "unauthorized")` (worlds.go:265-269).

**NO OCC — enforce it by omission AND by test.** Do not read `If-Match`, do not 428/412, do not add a `version` column to `map_markers`. The spec's migration adds `version` to `world_maps` ONLY (BE-15d) and `updated_at` to `map_markers`/`map_regions`. Write a test that a PATCH **with** a bogus `If-Match` header still returns 200 — that pins "no OCC" as behavior, so a later builder can't "helpfully" add it.

**`updated_at` must be READ (else it ships write-only):** the RETURNING above surfaces it, BE-15c returns it per marker, and the `world-map` inspector renders "edited 4m ago". Go test asserts the timestamp STRICTLY ADVANCES across a PATCH.

**FE contract (M8b.3, the load-bearing half of the question):** PATCH fires on drag-**END** only (never per mousemove). On `404`, the mutation's `onError` MUST `queryClient.invalidateQueries(['world-map-detail', mapId])` and let the refetch drop the optimistic pin — it must **NOT** fall back to `POST /markers` (that would resurrect a marker the user deleted in another tab). Chain writes per-marker (a promise queue keyed by `marker_id`) so a slow earlier PATCH cannot land after a newer one — with no OCC, last-write-wins is decided by ARRIVAL order, and out-of-order arrival is the only way a drag "snaps back".

**Tests** — `services/book-service/internal/api/worlds_maps_db_test.go`, using the existing `dbTestServer(t)` harness (mcp_maps_test.go:53): (1) label-only patch leaves x/y intact; (2) x/y patch leaves label intact; (3) **explicit `entity_id: null` clears it; `entity_id` absent PRESERVES it** — the one test that proves the tri-state; (4) same pair for `marker_type`; (5) `x: 1.5` ⇒ 422 and the row is unchanged; (6) foreign owner ⇒ 404 + row unchanged; (7) real marker id + a map_id it does not belong to ⇒ 404; (8) deleted marker ⇒ 404; (9) `updated_at` advances; (10) bogus `If-Match` ⇒ still 200.

**Same slice, same SQL:** BE-15m's `world_map_update_marker` MCP tool cannot express absent-vs-null with Go typed args (JSON `null` and an omitted key both decode a `*string` to nil), so give the TOOL explicit `clear_entity_id bool` / `clear_marker_type bool` flags and share one `updateMarker(ctx, markerID, mapID, ownerID, patch)` helper with the REST handler.

**Default I'm picking that the PO may veto:** field-validation errors return **422** (per the spec row) with the existing `BOOK_VALIDATION_ERROR` code, even though most of book-service uses 400 for validation; 422 already exists in this service (import.go:294). Malformed JSON stays **400**. If the PO would rather stay uniform with the rest of book-service, flip these to 400 — the FE treats both as "bad input, don't retry".

*Evidence:* services/book-service/internal/api/worlds.go:270-292 (`patchWorld` = the exact tri-state template: `map[string]any` decode + key-presence branching + owner-keyed UPDATE whose 0-rows ⇒ 404, no OCC) · services/book-service/internal/api/server.go:1022-1046 + :1124-1132 (`patchBook`'s "absent = unchanged, null = clear" comment, and `stringFromAny`'s silent-nil-on-non-string trap) · services/book-service/internal/api/mcp_maps.go:431-439 (`toolWorldMapRemoveMarker` — the owner-scoped `USING world_maps … wm.owner_user_id=$2` JOIN + uniform "marker not found", zero rows ⇒ not-found) · services/book-service/internal/api/mcp_maps.go:155-157 (the `[0,1]` coord guard to mirror) · services/book-service/internal/migrate/migrate.go:414-424 (`map_markers`: label/x/y NOT NULL, entity_id/marker_type nullable, no `updated_at` yet ⇒ the spec's ADD COLUMN is required) · services/book-service/internal/api/server.go:381-392 (the `/v1/worlds` chi block to mount `/maps/{map_id}` into) · services/api-gateway-bff/src/gateway-setup.ts:90 (`worldsProxy` pathFilter `/v1/worlds` ⇒ zero gateway changes). NO `PATCH …/markers/…` route exists at any layer today — grep for `worlds/maps` returns only maps_image.go, mcp_maps.go, server.go, migrate.go.

### Q-38-A3-SYNC-NOT-A-JOB
CONFIRMED BY CODE — build A3 / BE-14a as a plain SYNCHRONOUS REST call with NO job and NO cost gate. The code already settles it: `KgProjectEntitiesToNodesArgs` is documented "Tier-A: idempotent (re-projection is a no-op) + reversible" (graph_schema_tools.py:438-448), and its handler `_handle_kg_project_entities_to_nodes` (graph_schema_tools.py:1626-1710) executes the engine INLINE and returns the counters directly — it mints NO `confirm_token`, unlike every cost-gated sibling (`kg_build_graph` → build_tools.py:118; `kg_propose_edge`/schema tools → graph_schema_tools.py:1861/1912/2022). The engine `project_glossary_entities_to_nodes` (anchor_loader.py:194-264) is pure Neo4j upserts + one glossary HTTP read — zero LLM/provider calls — and the read is PAGED with a `truncated` flag (anchor_loader.py:303-327) with `entity_ids` capped at 1000, so the work is bounded and safe to run in-request.

Builder instruction (exact):
1. BE-14a `POST /v1/knowledge/projects/{project_id}/project-entities` is a normal async FastAPI route gated by `Depends(require_project_grant(GrantLevel.EDIT))`. It calls `projects_repo.project_meta(project_id)` → 409 with the tool's own message when `book_id is None` (mirror graph_schema_tools.py:1643-1648), then awaits `project_glossary_entities_to_nodes(...)` inside `neo4j_session()` and returns 200 with the ZERO-FILLED dict `{nodes_created, nodes_existing, entities_seen, skipped, nodes_conflicted, truncated, note?}`. NO enqueue, NO job row, NO `propose→confirm`, NO `estimated_cost`, NO usage/spend-guardrail check.
2. 🔴 DO NOT DROP THE STAT RECOUNT. The MCP handler calls `reconcile_project_stats(pool, session, owner, project_id)` on the same open session (graph_schema_tools.py:1667-1682) and its comment says it is "the ONLY production writer of stat_updated_at" (D-KG-STAT-CACHE-DEAD). The REST route MUST do the same, in the same best-effort try/except (a recount failure must not fail a successful projection) — otherwise the GUI seed path leaves `entity_count` UNKNOWN and re-opens the rail stall the MCP path just fixed. Simplest safe implementation: extract the body of `_handle_kg_project_entities_to_nodes` (book_id resolve → project → recount → zero-filled dict) into a shared `app/services/` (or `anchor_loader`-adjacent) function and have BOTH the tool handler and the new route call it, so the two paths cannot drift.
3. FE (kg-graph / kg-overview empty state): a single button whose `onClick` fires the mutation; while in-flight, `disabled` + inline spinner + "Seeding the graph from your glossary…". No polling, no job-detail deep-link, no confirm dialog, no cost preview. Render all six counters by their WIRE names on success (per spec §3.1 A3).
4. Guard it with a test so a reviewer cannot "fix" it back: a knowledge-service pytest asserting the 200 body of the new route contains NO `confirm_token`/`job_id` key and that all six counter keys are present (zero-filled) on an empty-glossary projection; plus a test asserting `reconcile_project_stats` is invoked by the route (spy), mirroring this repo's `checklist-is-self-report-enforce-by-tests` law.

Rationale for a reviewer: propose→confirm exists for PAID Tier-W actions (an LLM spend). This action spends nothing, is idempotent, and a human clicking the button IS the confirmation — routing it through the token spine would add a second click for zero safety and would make the empty-graph CTA a two-step flow.

*Evidence:* services/knowledge-service/app/tools/graph_schema_tools.py:438-448 (Tier-A docstring: "idempotent … + reversible") · :1626-1710 (`_handle_kg_project_entities_to_nodes` runs inline, returns counters, mints no confirm_token) · :1667-1682 (`reconcile_project_stats` — "the ONLY production writer of stat_updated_at", D-KG-STAT-CACHE-DEAD) · :1643-1648 (no-book hard-fail message → the 409) · contrast the cost-gated spine: services/knowledge-service/app/tools/build_tools.py:118 and graph_schema_tools.py:1861/1912/2022 (these DO mint `confirm_token`) · services/knowledge-service/app/extraction/anchor_loader.py:194-264 (deterministic, LLM-free, per-row error tolerant) + :303-327 (paged read with `truncated` ⇒ bounded work, safe in-request)

### Q-38-A3-NO-BOOK-LINK-409
Build it exactly as the spec's own §4.1 row already states — nothing here is open; every input exists in code. Concrete builder instruction (4 steps):

(1) GIVE THE HARD-FAIL A STABLE CODE (so BE-14a and the FE branch on a code, not a string — contract C4 discipline already used for KG_ENDPOINT_NOT_NODE). In `services/knowledge-service/app/tools/graph_schema_tools.py:1643-1647`, change the raise to:
    raise ToolExecutionError(
        "this project isn't linked to a book, so it has no glossary "
        "entities to project — link a book to the project first",
        code="KG_PROJECT_NOT_LINKED_TO_BOOK",
    )
Keep the message string byte-identical (ToolExecutionError already accepts `code`/`detail`, executor.py:202-221). Export the message as a module constant `NO_BOOK_LINK_MSG` in graph_schema_tools.py and import it in the route, so the two callers cannot drift.

(2) BE-14a — NEW route `POST /v1/knowledge/projects/{project_id}/project-entities`, added to `services/knowledge-service/app/routers/public/projects.py` (its router prefix is already `/v1/knowledge/projects`, projects.py:105-108). Signature:
    owner: UUID = Depends(require_project_grant(GrantLevel.EDIT))   # app/auth/grant_deps.py:108 — NOT the raw JWT (spec §4.1 GG-2 inverse gap)
    meta: ProjectMeta | None = Depends(project_meta_dep)            # grant_deps.py:60 — the SAME project_meta the tool uses (db/repositories/projects.py:537)
Body `{ entity_ids?: list[str] (≤1000) }`. Order of gates:
    - meta is None  -> uniform 404 via the existing `_not_found()` (projects.py:275).
    - meta.book_id is None -> raise HTTPException(status_code=409, detail={"code": "KG_PROJECT_NOT_LINKED_TO_BOOK", "message": NO_BOOK_LINK_MSG}). 409, NEVER a 500, and never let ToolExecutionError escape from the route.
    - else -> `async with neo4j_session() as s: res = await project_glossary_entities_to_nodes(s, get_glossary_client(), user_id=str(owner), project_id=str(project_id), book_id=meta.book_id, entity_ids=entity_ids or None)` (engine at app/extraction/anchor_loader.py:194), then call `reconcile_project_stats(...)` best-effort exactly as the tool does (graph_schema_tools.py:1665-1680).
Response 200, EVERY key always present (zero-filled — the tool omits the falsy ones): {nodes_created, nodes_existing, entities_seen, skipped, nodes_conflicted, truncated, note?}. Glossary unreachable (engine all-zero degrade) -> 503 "couldn't read the glossary", distinct from "nothing to project".

(3) FE — HIDE the seed CTA entirely when the project has no book. The signal is ALREADY on the wire: `GET /v1/knowledge/projects/{project_id}` returns `book_id: string | null` (frontend/src/features/knowledge/types.ts:23) — no new field, no new route. Render the CTA only when `project.book_id != null`; in its place show the static hint "link a book to this project first" (no button). Still handle a 409 from BE-14a defensively (a stale/unlinked project between load and click) by surfacing `detail.message` as an inline error and hiding the CTA — a 409 must never render as a generic "something went wrong".

(4) entities_seen == 0 is a SUCCESS (200), not an error: when `book_id` is present and the response returns `entities_seen === 0`, render "this book's glossary is empty — add entities there first" with a deep-link button calling `useStudioHost().openPanel('glossary')` (same pattern as ExtractionWizard.tsx:87 `studioHost.openPanel('jobs-list')`; `panel_id` is a closed set — confirm 'glossary' is registered in the panel enum and add it to CLOSED_SET_ARGS if the CTA is also agent-callable).

Tests (all in knowledge-service, `-n auto --dist loadgroup`): (a) route test — book-less project => 409 with code KG_PROJECT_NOT_LINKED_TO_BOOK and the exact message, asserted against the shared constant; (b) route test — EDIT-grantee collaborator (not owner) gets 200, closing the inverse gap; non-grantee gets 404; (c) route test — all six keys present when the engine returns falsy conflicted/truncated; (d) FE test — CTA absent when `book_id === null`; CTA present + "glossary is empty" + openPanel('glossary') fired when `entities_seen === 0`.

Default I am picking (veto-able): a 409 body of `{"code","message"}` rather than a bare string detail, because the FE needs to distinguish this from the 503 glossary-unreachable case without string-matching.

*Evidence:* services/knowledge-service/app/tools/graph_schema_tools.py:1639-1647 (tool already resolves book_id via projects_repo.project_meta and hard-fails with the exact message, currently with NO error code); services/knowledge-service/app/db/repositories/projects.py:537-546 (project_meta returns (owner_user_id, book_id); book_id is None for a book-less project); services/knowledge-service/app/auth/grant_deps.py:60-66,108-114 (project_meta_dep + require_project_grant(GrantLevel.EDIT) both already ship); services/knowledge-service/app/routers/public/projects.py:105-108,275 (router prefix /v1/knowledge/projects + uniform _not_found()); services/knowledge-service/app/tools/executor.py:202-221 (ToolExecutionError already carries code/detail); frontend/src/features/knowledge/types.ts:23 (`book_id: string | null` already on the FE Project type — the hide-CTA signal exists); frontend/src/features/extraction/ExtractionWizard.tsx:87 (studioHost.openPanel deep-link pattern); docs/specs/2026-07-01-writing-studio/38_kg_and_world.md:281,286 (spec row already pins 409 + require_project_grant(EDIT)).

### Q-38-A3-WIRE-NAME-DRIFT
CONFIRMED AT CODE — the drift is exactly as the spec describes, and the fix is a shared mapper, not a second re-mapping. Build it this way:

**1 · Kill the three spellings with ONE mapper (root-cause fix).** Add to `services/knowledge-service/app/extraction/anchor_loader.py`, directly under `ProjectionResult` (:166-192):

```python
def projection_result_to_wire(res: ProjectionResult) -> dict:
    """THE wire shape for a glossary→nodes projection. Every counter key is
    ALWAYS PRESENT (zero-filled); `note` is the only optional key."""
    notes: list[str] = []
    if res.truncated:
        notes.append("the book has more entities than one projection pass could read; re-run with explicit entity_ids to project the remainder")
    if res.conflicted:
        notes.append(f"{res.conflicted} entit{'y' if res.conflicted == 1 else 'ies'} could not be added because another node in this project already owns them in the graph")
    return {
        "nodes_created": res.created,
        "nodes_existing": res.existing,
        "entities_seen": res.seen,
        "skipped": res.skipped,
        "nodes_conflicted": res.conflicted,   # ALWAYS present (0, not omitted)
        "truncated": res.truncated,           # ALWAYS present (false, not omitted)
        **({"note": " · ".join(notes)} if notes else {}),
    }
```
Then **replace** `graph_schema_tools.py:1681-1707` (the `out: dict = {...}` block + the three `if res.*:` conditional-key branches) with `return projection_result_to_wire(res)`. Additive keys are safe for the LLM (`truncated: false` is strictly more informative than an absent key), and now BE-14a and the tool cannot drift because there is one producer. Update `services/knowledge-service/tests/unit/test_graph_schema_tools.py` — any assertion of the form `"truncated" not in out` / `"nodes_conflicted" not in out` flips to `out["truncated"] is False` / `out["nodes_conflicted"] == 0`.

**2 · BE-14a route** — new endpoint in `services/knowledge-service/app/routers/public/extraction.py` (its router prefix is already `/v1/knowledge/projects`, :83): `@router.post("/{project_id}/project-entities", response_model=ProjectEntitiesResponse)`, gated `owner: UUID = Depends(require_project_grant(GrantLevel.EDIT))` (same dep already used at :335/:1054 — EDIT, matching the tool's `_resolve_project_owner(ctx, GrantLevel.EDIT)`, per spec §6.3 gap #6). The route calls the **engine** `project_glossary_entities_to_nodes` (`anchor_loader.py:194`) directly — NOT the tool handler — and returns `projection_result_to_wire(res)`. Resolve `book_id` via the projects repo (`project_meta`); `book_id is None` → **409** with the tool's own message (`graph_schema_tools.py:1643-1647`).

**3 · Pin the shape in a Pydantic response model so FastAPI cannot leak an omitted key** (this is the belt to the mapper's braces):
```python
class ProjectEntitiesResponse(BaseModel):
    nodes_created: int
    nodes_existing: int
    entities_seen: int
    skipped: int
    nodes_conflicted: int = 0
    truncated: bool = False
    note: str | None = None
```
Every counter is a required int/bool; `note` is the ONLY key the FE may branch on. **The FE (A3) renders `res.nodes_created / nodes_existing / entities_seen / skipped / nodes_conflicted / truncated` and NEVER `res.created / existing / seen / conflicted`** — the engine spellings do not exist on the wire.

**4 · A REAL GAP the spec's error table cannot deliver as written (found in code — fix it in this slice).** `_load_projection_rows` **swallows** a glossary read failure: `anchor_loader.py:310-315` — `if page is None: log.warning(...); return out, False`. So "glossary unreachable" and "glossary is empty" both produce an all-zero `ProjectionResult`, and BE-14a **cannot** raise the 503 the spec demands (line 281: *surface it as "couldn't read the glossary", NOT as "nothing to project"*). Fix additively: add `glossary_unreachable: bool = False` to `ProjectionResult`; have `_load_projection_rows` return it True on the `page is None` branch (:310) and wrap the by-ids `fetch_entities_by_ids` call (:299-303) in try/except → True. Route: `if res.glossary_unreachable: raise HTTPException(503, "couldn't read the glossary — try again in a moment")`. This field is an **error signal, not a wire key** — the 200 body stays exactly the 6+1 shape above. (Otherwise the button lies "this book's glossary is empty" whenever glossary-service is down — the exact silent-success bug class this repo has already been bitten by.)

**5 · Tests (the regression that owns this question).** In the knowledge-service route test: assert on the **all-zero** projection (conflicted=0, truncated=False) that `set(resp.json()) >= {"nodes_created","nodes_existing","entities_seen","skipped","nodes_conflicted","truncated"}` and `body["nodes_conflicted"] == 0 and body["truncated"] is False` — the zero case is where the conditional-key bug hides, so that is the assertion that must exist. Plus: conflicted=2/truncated=True pass through with a `note`; 409 (no `book_id`); 503 (glossary unreachable); 403/404 (grant). In `studio-kg-write.spec.ts`, assert the **network response body's wire names** (not the DOM text alone) and that the badge row renders `0`/`false` rather than blank.

*Evidence:* services/knowledge-service/app/tools/graph_schema_tools.py:1681-1707 (`out: dict = {nodes_created, nodes_existing, entities_seen, skipped}` then `if res.truncated:` :1689, `if res.conflicted:` :1695, `if notes:` :1706 — the three conditional keys, confirmed); services/knowledge-service/app/extraction/anchor_loader.py:166-192 (`ProjectionResult` = created/existing/seen/skipped/truncated/conflicted — the second spelling), :194 (engine `project_glossary_entities_to_nodes` = BE-14a's callee), :310-315 (`if page is None: … return out, False` — glossary failure silently degrades to all-zero, so the spec's 503 is unimplementable without the new `glossary_unreachable` flag); services/knowledge-service/app/routers/public/extraction.py:83 (prefix `/v1/knowledge/projects` — the route's home) and :335 (`Depends(require_project_grant(GrantLevel.VIEW))` — the grant-dep pattern to copy at EDIT); spec docs/specs/2026-07-01-writing-studio/38_kg_and_world.md:134,281,286.

### Q-38-MIGRATION-VERSION-UPDATEDAT
BUILD IT AS FOLLOWS — the spec's 3-line DDL is right for `version` but WRONG for the two child `updated_at` columns (a blanket `DEFAULT now()` backfills every pre-existing marker/region as "edited just now" — a false-fresh timestamp the §4.2 inspector will render, and `ADD COLUMN IF NOT EXISTS` never revisits it). Ship this exact block instead.

(1) MIGRATION — append to the end of `schemaSQL` in `services/book-service/internal/migrate/migrate.go` (before the closing backtick, under a dated banner comment in the house style):

```sql
-- ═══════════════════════════════════════════════════════════════
-- Writing Studio M8b.1 — world-map OCC + child updated_at (spec 38 §4.2)
-- version: OCC baseline for BE-15d's If-Match rename. Existing maps start at 1
--   (matches the FE's first GET → no phantom 412). No backfill needed.
-- updated_at on the CHILD tables: added NULLABLE, backfilled from created_at,
--   THEN defaulted + NOT NULL — so a pre-existing marker reads its true age,
--   not "edited just now". Self-gating on re-run (the UPDATE's `IS NULL`
--   predicate matches 0 rows after the first pass), so no marker table is
--   needed (contrast canon_model_migration:349 / word_count_backfill:510,
--   which gate multi-row Go loops).
-- ⚠ ADD COLUMN IF NOT EXISTS never revisits a bad default — this shape is one-shot.
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE world_maps  ADD COLUMN IF NOT EXISTS version INT NOT NULL DEFAULT 1;

ALTER TABLE map_markers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;
UPDATE map_markers SET updated_at = created_at WHERE updated_at IS NULL;
ALTER TABLE map_markers ALTER COLUMN updated_at SET DEFAULT now();
ALTER TABLE map_markers ALTER COLUMN updated_at SET NOT NULL;

ALTER TABLE map_regions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;
UPDATE map_regions SET updated_at = created_at WHERE updated_at IS NULL;
ALTER TABLE map_regions ALTER COLUMN updated_at SET DEFAULT now();
ALTER TABLE map_regions ALTER COLUMN updated_at SET NOT NULL;
```
`version INT` (not BIGINT) is correct — renames are human-paced. `world_maps.updated_at` already exists (migrate.go:410) — do not re-add it.

(2) NO TRIGGER for `updated_at`. book-service maintains it explicitly in the handler (`maps_image.go:108` already does `UPDATE world_maps SET … updated_at=now()`). Every new PATCH handler (BE-15d/h/k) sets `updated_at = now()` in the same statement.

(3) OCC statement for BE-15d (single round-trip, then disambiguate):
`UPDATE world_maps SET name=$1, version=version+1, updated_at=now() WHERE id=$2 AND owner_user_id=$3 AND version=$4 RETURNING id, world_id, name, image_object_key, image_w, image_h, version, updated_at;`
0 rows → re-SELECT by (id, owner_user_id): row missing ⇒ **404**; row present ⇒ **412** with that current row as the body. Missing If-Match ⇒ **428**. Mirror knowledge-service's parser: accept weak `W/"N"`, strong `"N"`, and a bare `N`; malformed ⇒ 422. Emit `ETag: W/"<version>"` on BE-15b/BE-15c so the FE has one source for the header.

(4) DEFAULT the PO may veto: the image upload (`maps_image.go:108`) bumps `updated_at` but **does NOT bump `version`** — an image replace is not a competing rename, and bumping would 412 an in-flight rename for nothing. Leave that handler's SQL as-is.

(5) TESTS (same slice, mirroring the existing conventions in `services/book-service/internal/migrate/migrate_test.go`):
- `TestSchemaAddsWorldMapOCCColumns` — string-assert schemaSQL contains the `world_maps … version`, `map_markers … updated_at`, `map_regions … updated_at` alters (mirrors `TestSchemaAddsKGIndexingColumns:143`).
- `TestSchemaWorldMapAdditionsAreIdempotent` — apply schemaSQL twice against the real PG, no error (mirrors `TestSchemaC20AdditionsAreIdempotent:318`).
- Real-DB backfill test: seed a `map_markers` row with `created_at = now() - interval '3 days'`, re-run schemaSQL, assert `updated_at = created_at` (NOT ≈ now()) — this is the assertion that pins the non-obvious part of this decision.
- PATCH test: assert `updated_at` strictly ADVANCES and `version` increments by exactly 1 across BE-15d (spec §4.2 already mandates this); assert a stale If-Match yields 412 and does not mutate the row.

*Evidence:* services/book-service/internal/migrate/migrate.go:401-434 — `world_maps` already has `updated_at` (line 410) and needs only `version`; `map_markers` (line 422) and `map_regions` (line 432) carry `created_at` ONLY, which is exactly what makes the created_at backfill possible instead of a `DEFAULT now()` lie. services/book-service/internal/api/maps_image.go:108 — `UPDATE world_maps SET image_object_key=$1, image_w=$2, image_h=$3, updated_at=now()` proves the house pattern is handler-maintained `updated_at`, not a trigger (grep for a trigger in migrate.go returns none for updated_at). migrate.go:349 (`canon_model_migration`) + :510 (`word_count_backfill_migration`) — marker tables gate multi-row Go backfill LOOPS; a single self-gating `WHERE updated_at IS NULL` UPDATE needs no such table. services/knowledge-service/app/routers/public/entities.py:90-110 (`_parse_if_match`, weak/strong ETag, 422 on malformed) and :1035-1085 (428 with no If-Match; 412 returning the CURRENT entity + refreshed ETag) — the contract BE-15d mirrors.

### Q-38-A4-NOT-KG-BIO
CONFIRMED BY CODE — the spec text is right, keep it, and build A4 exactly as written, with ONE amendment (a third mount site).

1) SURFACE (unchanged, confirmed): the `⋯ → Forget` row action goes on the facts list inside `frontend/src/features/knowledge/components/EntityDetailPanel.tsx` (facts come from `useEntityFacts(open ? entityId : null)` at :135; each `EntityFact` carries `id` — `frontend/src/features/knowledge/api.ts:545-552`). It does NOT go on `kg-bio`: `GlobalBioTab.tsx:7,29` only calls `useSummaries()` — one text blob, no fact rows, no `useEntityFacts` import. Nothing to hang a row action on. Do not re-add `kg-bio` to A4.

2) AMEND THE SPEC (§3.1 A4 says "two panels" — it is THREE): `EntityDetailPanel` is mounted by `EntitiesTab.tsx:312` (→ `kg-entities`), `ProjectGraphView.tsx:171` (→ `kg-graph`), AND `frontend/src/features/world/components/WorldRollupGraph.tsx:176` (→ the `world` rollup graph, which imports it from `@/features/knowledge/components/EntityDetailPanel`). Keep the action owned entirely by `EntityDetailPanel` (no per-mount props, no per-mount handler) so all three inherit it from one edit. Change the sentence "one edit lights the action up in two panels" → "in three surfaces (`kg-entities`, `kg-graph`, `world`)".

3) BE-14b — WRITE THE ROUTE (it does not exist yet; this is unbuilt work, not a blocker): add `POST /v1/knowledge/facts/{fact_id}/invalidate` next to the existing facts read route in `services/knowledge-service/app/routers/public/entities.py` (the GET is at :631 `/entities/{entity_id}/facts`). Implement it as a thin REST mirror of `_handle_memory_forget` (`services/knowledge-service/app/tools/executor.py:710-723`): `user_id: UUID = Depends(get_current_user)`, then `async with neo4j_session() as session: fact = await invalidate_fact(session, user_id=str(user_id), fact_id=fact_id)`. Return `200 {invalidated: false, reason: "no matching fact found"}` when `fact is None` (NOT a 404 — cross-user/unknown ids must not leak existence, matching the executor's owner-keyed comment at :713-716) and `200 {invalidated: true, fact_id: fact.id}` otherwise. No project/book grant check — `invalidate_fact` is owner-keyed on `user_id`; that IS the tenancy boundary. Soft invalidation only (`valid_until`), audit history preserved.

4) FE wiring: add `knowledgeApi.invalidateFact(factId, token)` in `frontend/src/features/knowledge/api.ts` + a `useForgetFact` mutation hook in `frontend/src/features/knowledge/hooks/` that on success invalidates queryKey `['knowledge-entity-facts', userId, entityId]` (the exact key from `useEntityFacts.ts:31`). Confirm first (reuse the lightweight `window.confirm` pattern already used for unlock at `EntityDetailPanel.tsx:158-160` — copy: "Forgetting hides this fact from future context. It is not deleted from history — but there is no un-forget button."). On `{invalidated:false}` → refetch the facts list and toast "already gone"; NEVER toast success. On error → error toast.

5) HARD NEGATIVE (keep): do not wire this to `POST /v1/knowledge/pending-facts/{id}/reject` (`services/knowledge-service/app/routers/public/pending_facts.py:7` — the pre-commit triage queue, deletes a pending row) nor to `/internal/admin/…/reject-fact`. Different objects, different lifecycles.

6) TESTS (DoD): pytest — the new route returns `{invalidated:false}` (200, not 404) for a fact owned by another user, and `{invalidated:true}` for the owner's; vitest — `EntityDetailPanel` renders a Forget action per fact row, calls the mutation with that row's `fact.id`, and on `{invalidated:false}` shows the "already gone" path rather than success. Also register `memory_*` Lane-B per M8a.2.

*Evidence:* frontend/src/features/knowledge/components/EntityDetailPanel.tsx:135 (`useEntityFacts(open ? entityId : null)`); frontend/src/features/knowledge/components/GlobalBioTab.tsx:7,29 (`useSummaries()` only — no facts); mounts: EntitiesTab.tsx:312, ProjectGraphView.tsx:171, world/components/WorldRollupGraph.tsx:176 (THIRD mount the spec missed); BE mirror source: services/knowledge-service/app/tools/executor.py:710-723 (`_handle_memory_forget` → `invalidate_fact`, owner-keyed on user_id, returns `{invalidated:false, reason:"no matching fact found"}`); existing facts read route: services/knowledge-service/app/routers/public/entities.py:631; fact id field: frontend/src/features/knowledge/api.ts:545-552; do-not-touch: services/knowledge-service/app/routers/public/pending_facts.py:7

### Q-38-BE-15m-UPDATE-TOOLS
BUILD all 3 tools in slice M8b.1, in the same commit as the REST PATCH routes. Code confirms the premise: registerMapTools registers exactly 8 world_map_* tools and UPDATE exists at no layer, so after 8b the human could drag a pin and the agent could not (GG-2 inverse gap).

(1) MIGRATION — services/book-service/internal/migrate/migrate.go (world-map DDL block at :401-434), additive + idempotent (no down-migration in book-service): `ALTER TABLE world_maps ADD COLUMN IF NOT EXISTS version INT NOT NULL DEFAULT 1;` `ALTER TABLE map_markers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();` same for map_regions. world_maps.updated_at already exists (:410) but NO writer bumps it — the update core below is what makes it non-write-only.

(2) ONE SHARED UPDATE CORE, NOT TWO — new file services/book-service/internal/api/maps_update.go: updateMapCore / updateMarkerCore / updateRegionCore(ctx, ownerID, id, patch). Each is owner-scoped by the existing JOIN pattern (mirror the DELETE ... USING world_maps wm ... wm.owner_user_id=$2 at mcp_maps.go:431-433, as UPDATE), sets updated_at=now() (+ version=version+1 for the map), RETURNINGs the row; RowsAffected()==0 => uniform "not found" (no cross-owner existence oracle). BOTH the REST PATCH handlers (BE-15d/h/k) and the 3 MCP tools call these — do not write the SQL twice (css-var-duplicated-across-two-consumers-drifts). Field tri-state: `type fieldPatch struct{ Action patchAction /*unchanged|clear|set*/; Value string }`. REST decodes explicit JSON null => clear (decode into map[string]json.RawMessage — a *string or **string CANNOT distinguish null from absent; encoding/json sets both to nil). MCP maps "" => clear.

(3) THE 3 TOOLS — append to mcp_maps.go, register in registerMapTools (:465) with lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeNone, nil, [...]) exactly like the existing 8. Arg shape follows the repo's shipped partial-update precedent (glossary book_tools.go:260-281 — pointer + omitempty + base_version):
  • world_map_update: map_id string, name string, expected_version int `json:",omitempty"`. DEFAULT DECISION (PO may veto): expected_version is OPTIONAL — when present and stale the tool errors "map was renamed elsewhere (current version N, name 'X') — re-read with world_map_get and retry"; when omitted it is last-write-wins. REST keeps strict If-Match (428/412) because a GUI tab goes stale for hours, while an agent's world_map_get is seconds old; glossary's optional base_version is the standing precedent. To make the arg usable, ADD `version` + `updated_at` to worldMapDetail (mcp_maps.go:73-79) so world_map_get/world_map_list return it — an OCC arg the agent cannot read is a write-only-field bug.
  • world_map_update_marker: marker_id string, label *string, x *float64, y *float64, marker_type *string, entity_id *string. Absent = unchanged; "" = CLEAR (marker_type/entity_id) — state that verbatim in the jsonschema tag. Validate x,y in [0,1] when present (reuse mcp_maps.go:155). marker_type stays FREE-FORM (no enum), per the spec's warning.
  • world_map_update_region: region_id string, name *string, polygon [][]float64 (omitempty; present => replace-whole, >=3 points each in [0,1] — reuse the validation at :199-206), entity_id *string ("" => unlink).
  • ALL THREE: zero fields supplied => tool ERROR "nothing to update", never a 200/{updated:true} (silent-success-is-a-bug). Outputs reuse worldMapDetail / markerOut / regionOut (+ updated_at). Descriptions state reversibility the way the existing tools do: "Reversible: world_map_get returns the current values — call this tool again with them to restore."

(4) TESTS (mcp_maps_test.go): TestWorldMapUpdateMarker_RejectsOutOfRangeCoords; TestWorldMapUpdate*_NoFields_Errors; TestWorldMapUpdate_StaleVersion_Errors; and extend the DB round-trip TestMapAuthoringRoundTrip (:52) to assert (a) new values persist, (b) updated_at ADVANCES across a PATCH, (c) a foreign owner's marker id => "marker not found". mcp_prefix_contract_test.go passes unchanged (world_ is book's federated EXTRA_PREFIX_MAP namespace).

(5) NO cross-service change: repo-wide the only world_map_* references are mcp_maps.go, docs, and an eval transcript — no gateway allowlist or registry catalog enumerates the tools.

*Evidence:* services/book-service/internal/api/mcp_maps.go:465-515 (registerMapTools = 8 tools: create/add_marker/add_region/get/list/delete/remove_marker/remove_region — NO update at any layer); mcp_maps.go:73-79 (worldMapDetail has no version/updated_at); mcp_maps.go:155 + :199-206 (existing [0,1] coord + >=3-point polygon validation to reuse); mcp_maps.go:431-433 (owner-scoped JOIN-to-world_maps write pattern to mirror as UPDATE); services/book-service/internal/migrate/migrate.go:401-434 (world_maps has updated_at but NO version; map_markers/map_regions have NO updated_at); services/glossary-service/internal/api/book_tools.go:260-281 (shipped precedent: pointer+omitempty partial-update args + optional base_version OCC on a Go MCP tool); services/book-service/internal/api/server.go:200 (the only existing map REST route — the internal image upload); docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:318,389,429 (BE-15m MUST-BUILD, size S, same slice as M8b.1)

### Q-38-A4-FALSE-INVALIDATED-STATE
CONFIRMED — A4 as written is correct, and here is the exact build, with one defect the spec missed now closed.

**BE-14b — `POST /v1/knowledge/facts/{fact_id}/invalidate`** (new router `services/knowledge-service/app/routers/public/facts.py`, mounted like `relations_router`; `user_id` from JWT ONLY — never path/body/query).
Response is ALWAYS **200** with `{ invalidated: bool, fact_id: str, reason: str | null }` — key-for-key the shape of `_handle_memory_forget` (`executor.py:710-722`) so the REST mirror and the MCP tool cannot drift (this repo's cross-service-normalization law). DEFAULT I am picking, PO may veto: it does **NOT** copy the sibling relation route's 404 (`relations.py:71`), because A4's FE states are written against the tool's body and a 404 would force the FE to branch on two shapes for one condition.
Handler (three arms, in order):
1. `before = await get_fact(session, user_id=str(uid), fact_id=fact_id)` (`facts.py:390` — owner-keyed, `None` on missing AND on cross-user ⇒ no enumeration oracle).
   `before is None` → `{invalidated: false, fact_id, reason: "no matching fact found"}` (string VERBATIM from the tool).
2. `before.valid_until is not None` → `{invalidated: false, fact_id, reason: "already forgotten"}` **and write nothing**. WHY (the miss): `_INVALIDATE_FACT_CYPHER` (`facts.py:666-672`) does `SET f.valid_until = coalesce($valid_until, datetime())` — it re-stamps an already-invalidated fact and returns `invalidated:true`, so a double-forget from a stale tab would both report success AND move the original forget timestamp forward, corrupting the audit history the soft-delete exists to keep. Close the window **in the writer route**, NOT in `invalidate_fact` — that engine is shared with `memory_forget` and mirrors `invalidate_relation` (repo law: close-legacy-window-in-writer).
3. else → `await invalidate_fact(...)` → `{invalidated: true, fact_id, reason: null}`.

**FE (A4) — new `frontend/src/features/knowledge/hooks/useFactMutations.ts`**, shaped exactly like `useRelationMutations.ts:34-56` (`useInvalidateRelation`). `useForgetFact`'s `onSuccess` **must branch on the body, never on the HTTP status**:
- `invalidated === false` ⇒ **NO success toast**. `toast.info(t('facts.forget.alreadyGone'))` = "This fact is already gone — the list was out of date." then refetch.
- `invalidated === true` ⇒ success toast.
Both arms invalidate `['knowledge-entity-facts', userId, entityId]` (`useEntityFacts.ts:32`) AND the `['knowledge-entity-detail', userId]` prefix.
Row action `⋯ → Forget` hangs on the facts list inside `EntityDetailPanel.tsx` (the `useEntityFacts` render at `:135`) ⇒ lights up in `kg-entities` and `kg-graph` at once. Confirm-first via an `AlertDialog` (not `window.confirm` — it is destructive and the copy is two lines), body string VERBATIM: "Forgetting hides this fact from future context. It is not deleted from history — but there is no un-forget button." Buttons Cancel / Forget (destructive). i18n keys in `frontend/public/locales/*/knowledge.json`.

**Definition of Done (M8a.2, A4 leg) — the tests ARE the enforcement:**
- pytest `services/knowledge-service/tests/unit/test_facts_invalidate_route.py`: (a) unknown id → 200 `invalidated:false` + `reason:"no matching fact found"`; (b) ANOTHER user's fact → byte-identical body (no 404, no oracle); (c) happy path → `invalidated:true` and the fact vanishes from `GET /entities/{id}/facts`; (d) **double-forget → `invalidated:false`, `reason:"already forgotten"`, and `valid_until` is UNCHANGED** (assert the timestamp — this is the arm that regresses).
- vitest on `useFactMutations`/`EntityDetailPanel`: a mocked 200 `{invalidated:false}` asserts **no success toast** and that a refetch fired.
Do NOT wire any of this to `POST /pending-facts/{id}/reject` or `/internal/admin/…/reject-fact`.

*Evidence:* services/knowledge-service/app/tools/executor.py:710-722 (`_handle_memory_forget`: `fact is None` ⇒ `{"invalidated": False, "reason": "no matching fact found"}`) · services/knowledge-service/app/db/neo4j_repos/facts.py:666-698 (`_INVALIDATE_FACT_CYPHER` MATCHes on `(id, user_id)` and `SET f.valid_until = coalesce($valid_until, datetime())` — re-stamps an already-forgotten fact and returns invalidated:true) · facts.py:390 (`get_fact`, owner-keyed pre-read) · services/knowledge-service/app/routers/public/relations.py:63-72 (the sibling 404 pattern, deliberately not copied) · frontend/src/features/knowledge/hooks/useRelationMutations.ts:34-56 · frontend/src/features/knowledge/hooks/useEntityFacts.ts:29-36 · frontend/src/features/knowledge/components/EntityDetailPanel.tsx:135

### Q-38-STUDIOLINKS-NOT-ONE-LINE
ADOPT the spec's 3-file instruction VERBATIM — it is correct, buildable today, and needs no product call — but the slice is FOUR files, not three, because the spec named only one of the two throw-away call sites. Builder checklist for M8b.2 (do all of it or the rule is dead code):

(1) `frontend/src/features/studio/host/studioLinks.ts`
  - Add to `StudioLinkContext` (currently `:19-24`): `/** The book's world (book row `world_id`). Absent ⇒ /worlds/* stays external (degrade-safe). */ worldId?: string;`
  - Add beside the other regexes (after `AGENT_MODE_RUN_RE`, `:43`): `const WORLD_RE = /^\/worlds\/([^/]+)(?:\/|$)/;`
  - Insert the branch AFTER the `agentRun` block and BEFORE `const panelId = PATH_PANELS[path]` (`:107`) — order is irrelevant to correctness here (no PATH_PANELS key starts with /worlds) but keep it with the other *_RE blocks:
      const world = WORLD_RE.exec(path);
      if (world) {
        const [, worldId] = world;
        if (ctx.worldId && worldId === ctx.worldId) return openPanel('world');
        return { kind: 'external', url: link }; // a different world, OR a ctx that doesn't know this book's world → today's behaviour
      }
  - Comment it with the reasoning from `:51-57` (the /knowledge/projects/:id precedent): an id we cannot ASSERT is this book's own must not be naively mapped, because it would silently show the wrong world. It is mappable here only because the caller reads the id off the book row.

(2) `frontend/src/features/studio/panels/KgOverviewPanel.tsx:48` (the spec says `:44`; the actual line is 48) — MANDATORY:
      onOpenWorld={(worldId) => followStudioLink(`/worlds/${worldId}`, host, { bookId: host.bookId, worldId })}
  Safe: the id arrives from `OverviewSection.tsx:140` = `backlinks.worldId` (useProjectBacklinks, read off the book row).

(3) 🔴 `frontend/src/features/studio/panels/BookSettingsPanel.tsx:52` — **THE SPEC MISSED THIS ONE.** It is the identical throw-away and it is the *more* likely path a user takes to the world backlink:
      onOpenWorld={(worldId) => followStudioLink(`/worlds/${worldId}`, host, { bookId: host.bookId, worldId })}
  Safe: the id arrives from `SettingsTab.tsx:360` = `book.world_id`. Leaving this un-fixed ships a studio where the SAME world link opens in-panel from kg-overview but pops a browser tab from book-settings — a worse papercut than today's consistent-but-wrong behaviour.

(4) Tests — three NEW cases in `frontend/src/features/studio/host/__tests__/studioLinks.test.ts`:
   a. `resolveStudioLink('/worlds/w1', { bookId:'b1', worldId:'w1' })` ⇒ `kind:'studio'`, and running the effect calls `host.openPanel('world', …)`.
   b. `resolveStudioLink('/worlds/w9', { bookId:'b1', worldId:'w1' })` ⇒ `{ kind:'external', url:'/worlds/w9' }`.
   c. **THE DEGRADE PATH** — `resolveStudioLink('/worlds/w1', { bookId:'b1' })` (no `worldId`) ⇒ `{ kind:'external', url:'/worlds/w1' }`. This is the one a builder forgets and it is the one that guarantees no existing caller regresses.
   Also add `/worlds` (bare, no id) ⇒ external — WORLD_RE requires a segment, so it already falls through at `:113`; pin it.

(5) 🔴 TWO EXISTING TESTS GO RED — update them in the SAME commit or the wave's suite fails:
   - `panels/__tests__/KgOverviewPanel.test.tsx:133` and `panels/__tests__/BookSettingsPanel.test.tsx:123` both assert `expect(followStudioLink).toHaveBeenCalledWith('/worlds/w1', hostRef, { bookId: 'b1' })`. Change both to `{ bookId: 'b1', worldId: 'w1' }`. (These are the guard that proves the id is threaded — do not weaken them to `expect.anything()`.)

Prereq/ordering: the `world` panel id must already be registered in the studio panel catalog when (1) lands, or `openPanel('world')` is a silent no-op (the exact `mcp-tool-io` OUT-* class this repo shipped once with `panel_id`). Build the `world` container panel FIRST inside M8b.2, then flip studioLinks. If for any reason the panel slips, (1)-(5) still ship green because the degrade path is `external` — but do NOT merge (2)/(3) ahead of the panel.

Default I am picking (veto-able): the `world` panel is opened with NO params. Per spec §3.2 the panel is self-resolving (`world` = the world THIS book belongs to, exactly as `kg-overview` self-resolves the project via `useBookKnowledgeProject`), so passing `{ worldId }` as a param would be a second source of truth for the same fact. If the PO later wants `world` openable for an arbitrary world id, that is a panel-param change, not a studioLinks change.

*Evidence:* frontend/src/features/studio/host/studioLinks.ts:19-24 (StudioLinkContext = {bookId, titleFor?} — cannot learn the world), :43 (AGENT_MODE_RUN_RE — the same-book-gate pattern to copy), :51-57 (the /knowledge/projects/:id comment = the REASONING, not a rule), :113 (unmapped ⇒ external, today's /worlds behaviour) · frontend/src/features/studio/panels/KgOverviewPanel.tsx:48 (throws worldId away; id sourced from OverviewSection.tsx:140 = backlinks.worldId) · frontend/src/features/studio/panels/BookSettingsPanel.tsx:52 (SECOND throw-away, NOT in the spec; id sourced from SettingsTab.tsx:360 = book.world_id) · frontend/src/features/studio/panels/__tests__/KgOverviewPanel.test.tsx:133 and __tests__/BookSettingsPanel.test.tsx:123 (both assert the ctx object literally ⇒ both go RED on the ctx change)

### Q-38-A2-DO-NOT-FORK-RELATIONDIALOG
CONFIRMED — do NOT fork. Every claim in the concern is true in the code, and A2 is smaller than the spec assumed: BOTH the create API fn and the predicate vocabulary route already exist. Builder instruction (exact):

(1) `frontend/src/features/knowledge/hooks/useRelationMutations.ts` — add `useCreateRelation(options?)` as a THIRD export next to `useInvalidateRelation` (:35) and `useCorrectRelation` (:66). Mirror `useCorrectRelation` exactly: same `useDetailInvalidation()` prefix-invalidation (`['knowledge-entity-detail', userId]`), same `{ correct/create, isPending, error }` result shape. Its `mutationFn` calls the ALREADY-EXISTING `knowledgeApi.createRelation(payload, accessToken!)` (`api.ts:1610`, `POST {BASE}/relations`) with the ALREADY-EXISTING `CreateRelationPayload {subject_id, object_id, predicate}` (`api.ts:589`). DO NOT write a new API function — it is there, currently used only by `composition/hooks/useWorldMap.ts:134`.

(2) `frontend/src/features/knowledge/components/RelationEditDialog.tsx` — add a `mode: 'edit' | 'create'` prop (default `'edit'`, so the two existing mount sites are untouched) and make `relation` a discriminated union: `mode:'edit'` takes `relation: EntityRelation`; `mode:'create'` takes `subject: {id,name}` + optional `object`. In create mode: render subject/object pickers instead of the read-only endpoint strip (:114-122), hide the "Mark wrong" destructive block (:136-150), and route the primary button to `createMutation.create(...)`. One dialog, one hook, three verbs. A second "new relation" dialog is a review finding.

(3) UNIFY the predicate control across all three verbs IN THIS SLICE (spec §3.1 A2 line 124). Replace the free-text `<input maxLength={100}>` (RelationEditDialog.tsx:127-134) with a schema-fed `<select>` used by BOTH create and correct. The option source ALREADY EXISTS and is ALREADY SERVED: `GET /v1/knowledge/predicate-labels` (`services/knowledge-service/app/routers/public/labels.py:26`, returns the 24-code curated `PREDICATE_LABELS` catalog from `labels/predicate_labels.py:28`, `?language=` for i18n labels). It is NOT yet consumed by `frontend/src/features/knowledge/api.ts` — add `knowledgeApi.getPredicateLabels(language?, token)` + a `usePredicateLabels()` query hook and feed the `<select>`. NO new backend route is needed for the predicate select (BE-14c is entity-KINDS, a separate thing). Do NOT hand-copy the predicate array into the FE — that is the cross-service drift the Frontend-Tool-Contract discipline kills. Since correct-mode may hold an off-catalog legacy predicate (BE still accepts free strings — see D-KG-RELATION-PREDICATE-UNCONSTRAINED), the `<select>` must include the relation's current predicate as an option even when absent from the catalog, so opening the dialog never silently rewrites an existing edge.

(4) Tests: extend the EXISTING `components/__tests__/RelationEditDialog.test.tsx` (do not create a second test file) — assert create-mode calls `createRelation` with `{subject_id, object_id, predicate}`; assert create-mode renders NO "Mark wrong" button (`relation-edit-invalidate` testid absent); assert both modes render the `<select>` with options from the mocked `predicate-labels` fetch and NO free-text predicate input; assert the legacy off-catalog predicate survives as a selected option in edit mode.

(5) Per OQ-10: mount this same dialog in create mode from `ProjectGraphView` (canvas edge-draw) and in edit mode from an edge right-click — same component, no fork.

*Evidence:* frontend/src/features/knowledge/components/RelationEditDialog.tsx:31,39 (useCorrectRelation + useInvalidateRelation) and :127-134 (the free-text predicate input to replace) · frontend/src/features/knowledge/hooks/useRelationMutations.ts:35,66 (the two existing verbs; add the third here) · frontend/src/features/knowledge/components/EntityDetailPanel.tsx:623 (the single mount) · EntitiesTab.tsx:312 + ProjectGraphView.tsx:171 (BOTH mount EntityDetailPanel — a fork would double both panels) · frontend/src/features/knowledge/api.ts:1610 + :589 (knowledgeApi.createRelation + CreateRelationPayload ALREADY EXIST; only consumer is composition/hooks/useWorldMap.ts:134) · services/knowledge-service/app/routers/public/labels.py:26 (GET /v1/knowledge/predicate-labels ALREADY SERVES the closed predicate catalog) · services/knowledge-service/app/labels/predicate_labels.py:28 (PREDICATE_LABELS, 24 curated codes) — unconsumed by frontend/src/features/knowledge/api.ts

### Q-38-A2-EMPTY-ONTOLOGY
The spec's premise is FALSE and its remedy would ship a worse bug. Gate on `allow_free_edges`, NOT on `edge_types.length`.

WHY: a project that never adopted does NOT get an empty schema — `resolve_for_project` falls back to the System `general` template (graph_schemas.py:227-257), and `general` is seeded with `"edge_types": []` + `"allow_free_edges": True` (seed_graph_schemas.py:45,55). `POST /schema/blank` also defaults `allow_free_edges=True` (ontology.py:141). So `edge_types == []` is the DEFAULT state of nearly every project, not a broken one. Blocking the form there would (a) make relation-create a dead wall for the majority of projects, and (b) REGRESS the already-shipped, working free-text `Correct` verb (RelationEditDialog.tsx:123-134) into an uncallable `<select>` over `[]`. Free predicates on a `general` project are legal BY THE SCHEMA'S OWN RULE — that is not the split-brain OQ-6 fears; the split-brain is only real when the schema says closed.

BUILD THIS — one shared `PredicateField` component in `frontend/src/features/knowledge/components/` used by ALL THREE verbs of `RelationEditDialog` (create/correct/mark-wrong), fed by `useResolvedSchema(scopedProjectId)` — NOT `useGraphSchema()`; the spec names the wrong hook (`useGraphSchema(schemaId)` reads one schema TREE by id; the per-project EFFECTIVE schema is `useResolvedSchema` — hooks/useResolvedSchema.ts:9). Let `edgeTypes = schema?.edge_types ?? []`, `free = schema?.allow_free_edges !== false`. Three branches:

1. `edgeTypes.length > 0 && !free` → pure closed-set `<select>`; options = `edge_types[].code`, display `.label`; required; Save disabled while empty.
2. `free === true` (THE DEFAULT — `general`, and blank-schema default) → a **combobox**: `<input list="predicate-options" maxLength={100}>` (matches BE `max_length=100`) + a `<datalist>` whose options are the UNION of `edge_types[].code` and the observed codes from `ontologyApi.schemaObserved(projectId)` (api/ontology.ts:170-174 → `GET /projects/{id}/schema/observed`, returns `edge_types:[{code,count,...}]`), sorted by `count` desc. Free entry stays legal; the datalist is what kills the `friend_of` vs `is_friend_of` drift a bare input causes. Muted hint under it: "this project's schema allows free predicates — reuse an existing one where you can" + a link that calls `host.openPanel('kg-schema')` to tighten it.
3. `edgeTypes.length === 0 && free === false` → THE ONLY genuinely dead ontology (reachable only via `POST /projects/{id}/schema/blank` with `allow_free_edges:false`, ontology.py:506-543, or by deleting every edge type from a closed schema). HERE, and only here, the spec's remedy applies verbatim: render NO input, disable Save, show "this project's schema allows no edge types yet — add one in the Schema panel", with a button calling `host.openPanel('kg-schema')` (host method proven at studio/agent/studioUiNav.ts:35 and host/studioLinks.ts:78-80; panel id `kg-schema` exists at studio/panels/catalog.ts:159). Do NOT fall back to free text in this branch — the schema explicitly forbids it.

SPEC EDITS REQUIRED (do them when M8a.1 opens): rewrite §3.1 A2's 🔴 EMPTY ONTOLOGY bullet to the above; fix its hook name (`useResolvedSchema`, not `useGraphSchema`); soften "the predicate control must be a `<select>`" to "the predicate control must be UNIFIED across all three verbs AND obey `allow_free_edges`" — the unification requirement stands, the unconditional `<select>` does not.

TESTS (vitest on `PredicateField`, per this repo's checklist-is-self-report-enforce-by-tests law): (i) `allow_free_edges:false` + 2 edge types ⇒ a `<select>`, no free input; (ii) `allow_free_edges:true` + `edge_types: []` (the `general` default) ⇒ a combobox whose datalist carries the observed codes AND Save is ENABLED after typing — this is the regression guard that keeps a default-schema project able to create/correct a relation; (iii) `allow_free_edges:false` + `edge_types: []` ⇒ no input, Save disabled, and clicking the CTA calls `host.openPanel('kg-schema')`.

BE unchanged: OQ-6's defer row `D-KG-RELATION-PREDICATE-UNCONSTRAINED` still stands — but amend it to note the BE check, when built, must honour `allow_free_edges` (reject off-ontology predicates only when the resolved schema is closed), not reject every predicate not in `edge_types`.

DEFAULT I PICKED (veto-able): branch 2 offers free text because the resolved schema says free text is allowed. If the PO would rather force every project onto a closed ontology, that is a product call — but it must then be made at the SCHEMA layer (flip `general.allow_free_edges` to false + seed it real edge types), not by having the FE lie about what the backend permits.

*Evidence:* services/knowledge-service/app/db/repositories/graph_schemas.py:227-257 ("If the project never adopted, resolve to the System `general` template"; degenerate path returns `allow_free_edges=True`) · services/knowledge-service/app/db/seed_graph_schemas.py:45,55 (`"allow_free_edges": True`, `"edge_types": []  # free-string predicates` — the default template) · services/knowledge-service/app/routers/public/ontology.py:141 (`allow_free_edges: bool = True` on BlankSchemaCreate) + :422-430 (`GET /projects/{id}/schema` → resolve_for_project) · frontend/src/features/knowledge/types/ontology.ts:198-209 (`ResolvedSchema.allow_free_edges: boolean` already on the wire) · frontend/src/features/knowledge/hooks/useResolvedSchema.ts:9 + its own comment "Always resolves to something (system defaults even before adopt), so the inspector never dead-ends on 'no schema adopted'" · frontend/src/features/knowledge/components/RelationEditDialog.tsx:123-134 (the shipped free-text predicate `<input maxLength={100}>` that a bare `<select>` over `[]` would break) · frontend/src/features/knowledge/api/ontology.ts:170-174 (`schemaObserved` → the datalist source) · frontend/src/features/studio/panels/catalog.ts:159 (`kg-schema` panel) · frontend/src/features/studio/agent/studioUiNav.ts:35 (`host.openPanel`)

### Q-38-A5-NO-RESTORE-PROJECT
The concern is FACTUALLY CORRECT — verified against code, not docs. It is a build instruction, not an open question. Build it exactly as follows (M8a.1 / A5):

**1 · Confirmed facts (do not re-litigate):**
- `useProjects()` returns exactly `createProject / updateProject / archiveProject / deleteProject` (`frontend/src/features/knowledge/hooks/useProjects.ts:132-152`). There is NO `restoreProject` and NONE is to be added — not as a mutation, not as a `restoreProjectViaPatch` helper, not as a new hook method. Restore is an OCC PATCH of the existing `updateProject`.
- The BE has no restore route to mirror: restore = `PATCH /v1/knowledge/projects/{id}` with `{is_archived:false}` + strict If-Match (428 without, 412 + current row in the body on stale — `api.ts:1034-1041`, `api.ts:964-986`).

**2 · Wire the three dead buttons in `OverviewSection.tsx` (the noop is at `:56`, passed at `:67-69`):**
- Change `const { createProject, updateProject } = useProjects(false)` (`:42`) to also destructure `archiveProject, deleteProject`.
- Import `ConfirmDialog` from `@/components/shared`, `toast` from `sonner`, and `isVersionConflict` from `../../api`. Add `archiveTarget` / `deleteTarget` state + the two `ConfirmDialog`s, copied in shape from `ProjectsBrowser.tsx:312-336` (including the `lastArchiveName`/`lastDeleteName` ref trick at `ProjectsBrowser.tsx:109-116` — Radix keeps the dialog mounted during exit animation).
- Restore handler = a LITERAL copy of `ProjectsBrowser.tsx:142-157`:
  `await updateProject({ projectId: project.project_id, payload: { is_archived: false }, expectedVersion: project.version })`. Keep `expectedVersion` (D-K8-03). Do NOT drop it "because restore is just a flag".
- After a successful `deleteProject` from the shell/panel, `invalidate` re-runs the list query, the `project` prop resolves to `null`, and the component renders the existing `shell-overview-missing` branch (`:45-54`). That is the intended terminal state — do NOT add a navigate() here.

**3 · The one thing the spec left open — HOW to "reset the baseline from the response body" on 412. Decided (PO may veto):** add a 412 branch to the restore handler in **BOTH** `OverviewSection` and `ProjectsBrowser` (today `ProjectsBrowser.tsx:151-153` swallows a 412 as a generic `restoreFailed` toast — a real, if minor, bug; fix it in the same slice so the two copies stay byte-identical):
```ts
catch (err) {
  if (isVersionConflict<Project>(err)) {
    const current = err.current;                 // fresh row, no second GET (api.ts:964-986)
    if (!current.is_archived) {                  // another device already restored it
      toast.success(t('projects.toast.restored'));
      return;                                    // onSuccess/invalidate not fired — force a refetch here
    }
    await updateProject({ projectId: project.project_id, payload: { is_archived: false }, expectedVersion: current.version });
    toast.success(t('projects.toast.restored'));
    return;
  }
  toast.error(err instanceof Error ? err.message : t('projects.toast.restoreFailed'));
}
```
Retry-once-with-the-fresh-version is correct HERE and is NOT the `ProjectFormModal.tsx:206-219` pattern (which deliberately keeps the dialog open and makes the human re-apply their edits). The difference is load-bearing: the form PATCH carries a human-authored multi-field diff that could clobber another device's edit, so a human must adjudicate. Restore's payload is a single boolean whose only value is `false` — re-applying it on top of the fresh row cannot destroy any concurrent edit, and it is idempotent. Bound the retry to ONE attempt (no loop).

**4 · Make the props optional (`ProjectRow.tsx:29-31` are required today; `:292-314` render all three buttons unconditionally):** change to `onArchive?` / `onRestore?` / `onDelete?` and render each button only when its handler is present. A button whose handler is a no-op must not exist.

**5 · Test (required — `checklist-is-self-report-enforce-by-tests`):** a vitest that renders `ProjectRow` with NO `onDelete` and asserts `queryByTitle('projects.card.delete')` is `null`; plus one that renders an archived project without `onRestore` and asserts `queryByTitle('projects.card.restore')` is `null`. Plus a vitest on the restore path asserting `updateProject` was called with `expectedVersion: project.version` (guards against a future "simplification" dropping the version) and that on a 412 it re-fires once with `err.current.version`.

*Evidence:* frontend/src/features/knowledge/hooks/useProjects.ts:132-152 (return block: createProject/updateProject/archiveProject/deleteProject — no restoreProject) · frontend/src/features/knowledge/components/ProjectsBrowser.tsx:142-157 (handleRestore = updateProject{is_archived:false} + expectedVersion: project.version; catch has NO 412 branch — swallows it as a generic error toast) · frontend/src/features/knowledge/api.ts:964-986 (isVersionConflict → err.current = the fresh row from the 412 body) · frontend/src/features/knowledge/api.ts:1034-1041 (updateProject sets If-Match; BE 428 without, 412 stale) · frontend/src/features/knowledge/components/ProjectFormModal.tsx:206-219 (the OTHER 412 pattern — keep-dialog-open, human re-applies; deliberately NOT used for restore) · frontend/src/features/knowledge/components/shell/OverviewSection.tsx:42,56,64-71 (useProjects(false) already mounted; `const noop = () => {}` passed as onArchive/onRestore/onDelete) · frontend/src/features/knowledge/components/ProjectRow.tsx:29-31,292-314 (required props; three buttons rendered unconditionally)

### Q-38-OCC-LWW-DELIBERATE-SPLIT
AFFIRMED AS WRITTEN — build the split exactly as §3.3.1 states; do NOT "add OCC" to markers/regions. This is a decision, not an omission, and the code supports it (no version column exists on any of the three tables today, so nothing is being removed).

BE (M8b.1, book-service Go):
1. Migration (append to `internal/migrate/migrate.go`, idempotent DDL, next to the block at :401-434):
   - `ALTER TABLE world_maps  ADD COLUMN IF NOT EXISTS version INT NOT NULL DEFAULT 1;`
   - `ALTER TABLE map_markers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();`
   - `ALTER TABLE map_regions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();`
   - Do NOT add `version` to `map_markers` / `map_regions`. (`updated_at` on the children is observability only; nothing reads it for concurrency.)
2. `PATCH /v1/worlds/maps/{map_id}` (BE-15d) — OCC, mirroring `entities.py:1035`: missing `If-Match` ⇒ **428**; `UPDATE world_maps SET name=$1, version=version+1, updated_at=now() WHERE id=$2 AND owner_user_id=$3 AND version=$4 RETURNING *`. `RowsAffected()==0` ⇒ re-select the row under owner scope: exists ⇒ **412 with the CURRENT map as the body** (FE resets its baseline from it — never re-GET, never blind-retry); absent ⇒ **404** (uniform not-found, no existence oracle).
3. `PATCH /v1/worlds/maps/{map_id}/markers/{marker_id}` and `.../regions/{region_id}` — **LAST-WRITE-WINS**. These handlers must NOT read the `If-Match` header at all (a client that sends one is silently ignored — no 428, no 412). No version column, no compare-and-swap. Partial semantics: decode into a presence-aware struct (`map[string]json.RawMessage` or `*T` + explicit key-set check) so *absent key = unchanged* and *explicit `null` on `entity_id`/`marker_type` = clear* are distinguishable. `polygon` is replace-whole (≥3 points, each coord in [0,1]); `x`/`y` validated in [0,1] as the existing add-* tools do.
4. Scope gate in ONE statement, tightening the shape at `mcp_maps.go:431-433` (which checks owner but NOT the URL's map): `UPDATE map_markers m SET ... FROM world_maps wm WHERE m.id=$1 AND m.map_id=$2 AND m.map_id=wm.id AND wm.owner_user_id=$3` — a marker id belonging to another map, addressed under your map id, must **404**, not patch. `RowsAffected()==0` ⇒ 404 (this is also the deleted-marker case).

FE (M8b.3):
5. Per-object-id write serialization. Copy the chain from `useSceneInspector.ts:44-100` but key it by object id: `const chains = useRef<Map<string, Promise<void>>>(new Map())`; each PATCH does `const prev = chains.current.get(id) ?? Promise.resolve(); const next = prev.then(run, run); chains.current.set(id, next);`. One chain PER marker/region id (a single global chain would needlessly serialize independent pins). Dragging pin A twice inside one round-trip ⇒ both PATCHes land, in order, LWW — no 412, no dropped edit.
6. Debounced save binds its target at ENQUEUE time (`debounced-write-must-bind-its-target-entity`): capture `markerId` in the closure when the drag ends; never read a `selectedRef.current` at flush time. If the selection moved on, the queued edit still targets the marker it was authored on, and the response is only pushed into state if that marker is still the one rendered.
7. On **404** from a child PATCH: drop the optimistic pin and refetch the map. Do NOT re-create it.
8. Map rename only: send `If-Match: <version>`; on 412 show "renamed on another device" + the current name from the 412 body and reset the baseline.

Tests (each is a literal DoD line):
- Go: rename without If-Match ⇒ 428; with a stale version ⇒ 412 and the body carries the current map; with the right version ⇒ 200 and `version` incremented.
- Go: **two sequential marker PATCHes with NO If-Match both return 200** (the anti-regression test that pins LWW — it reds if someone "adds OCC").
- Go: marker from map B addressed under map A ⇒ 404, and map B's row is unchanged (assert the SQL, not just the status).
- Go: `PATCH {}` on a marker changes nothing; `PATCH {"entity_id": null}` clears it (absent ≠ null).
- Vitest: fire two drags on marker A within one un-resolved fetch ⇒ assert exactly two PATCHes, ordered, both applied (no self-412, no dropped 2nd edit).
- Vitest: enqueue a debounced edit on marker A, switch selection to B, flush ⇒ assert the request targeted **A** and B's state was not written.
- E2E: drive the pin drag with **CDP `page.mouse`**, not `browser_drag` (`playwright-cdp-mouse-drives-d3-drag`).

Default noted for PO veto: child routes IGNORE a stray `If-Match` rather than 400-ing on it — silently ignoring keeps a well-meaning client from being broken, and the LWW test above pins the behavior.

*Evidence:* services/book-service/internal/migrate/migrate.go:401-434 (world_maps/map_markers/map_regions — NO version column on any of the three; children carry created_at only, so the split is purely additive) · services/knowledge-service/app/routers/public/entities.py:1035-1044 (the If-Match/428/412 contract map rename mirrors) · frontend/src/features/studio/panels/useSceneInspector.ts:44-100 (`nodeRef` + `chainRef.current = chainRef.current.then(run, run)`, target id captured at call time — the serialization pattern to generalize per object id) · services/book-service/internal/api/mcp_maps.go:431-433 (owner-scoped `USING world_maps wm` delete — the shape the PATCH copies, PLUS the missing `m.map_id=$2` constraint) · mcp_maps.go:280,303 (children ORDER BY created_at — an in-place UPDATE preserves render order, delete+recreate would not)

### Q-38-NAME-COLLISION-THREE-WORLD-MAPS
DECIDED — the collision is real but it only BITES in one place (the M8b.3 entity picker), and it bites as an ID-space bug, not a naming annoyance. Three binding rules; put all three verbatim into spec 38 §3.3 and into wave 8's DoD.

**RULE 1 (the one that prevents the wrong build) — `map_markers.entity_id` / `map_regions.entity_id` are GLOSSARY entity ids, NOT knowledge-service/Neo4j node ids. The M8b.3 picker MUST NOT call `knowledgeApi`.**
- Ground truth: `services/book-service/internal/migrate/migrate.go:417` (`entity_id UUID, -- soft cross-service ref → glossary location entity (nullable)`) and `:431` (same on `map_regions`); the tool schema agrees — `services/book-service/internal/api/mcp_maps.go:135` (`jsonschema:"optional glossary location entity id (UUID) this marker represents"`) and `:180`.
- The trap: the ONLY existing "world map" that creates entities is `frontend/src/features/composition/hooks/useWorldMap.ts:129` → `knowledgeApi.createEntity({kind:'location'})`, which mints a **knowledge-service (Neo4j)** node. Its id lives in a different ID space. The column is a **nullable UUID with no FK** (migrate.go:417) — book-service will happily store a KG node id and it will resolve to nothing, forever, with no error. That is exactly this repo's `silent-success-is-a-bug` class, and it is what "builds the wrong thing in M8b.3" means concretely.
- Builder instruction for M8b.3's picker: source it from the **glossary** layer only — `worldsApi` bible entities (`worldsApi.createBibleEntity` / `getInternalWorldBible`, `frontend/src/features/world/api.ts`) first, falling back to the current book's glossary `location` entities (`glossaryApi`). If you want a KG node behind a pin, you reach it via the glossary anchor (`knowledge` nodes carry `glossary_entity_id` — the two-layer pattern), never by writing a KG id into `entity_id`. This also RESOLVES OQ-2's "I have not read the world-bible entity model end to end": the column's own contract settles the ID space; only the *lookup surface* is a fallback choice, and the fallback is stated above.
- **Test (mandatory, M8b.1 + M8b.3):** a Go test asserting the marker create/patch handler stores the id it is given verbatim (no coercion), and an FE test asserting `WorldMapPanel` + its picker make **zero** `knowledgeApi` calls (mock `knowledgeApi` and assert not-called). Add `features/composition/**` and `features/knowledge/api` to a `no-restricted-imports` rule for `frontend/src/features/studio/panels/WorldMapPanel.tsx` and the `features/world/**` map code.

**RULE 2 — the word "world map" in NEW code means #1 (the drawn map) and nothing else.** Panel ids `world` / `world-map`, `WorldMapPanel.tsx`, query keys `['world-maps']` / `['world-map-detail']`, `worldEffects.ts`, and the `world_map_*` MCP tools (`mcp_maps.go:465-515`) all denote the book-service drawn map over `world_maps`/`map_markers`/`map_regions`. `WorldMapPanel.tsx` reads/writes ONLY the BE-15a..l `/v1/worlds/**/maps` REST routes. It never touches `composition_work.settings.world_map`, never imports from `features/composition/**`.

**RULE 3 — kill the collision at its source with a mechanical rename, in wave 8a (it is ~30 minutes and the legacy page is NOT being deleted — spec 16 M9 shipped it "kept, marked deprecated, not deleted", so the collision otherwise lives in the tree forever).** Rename the composition PLACE GRAPH to the name its own code already uses (`buildPlaceGraph`, `PLACE_LINK_PREDICATES`, `createPlace`, `linkPlaces` — the file is already speaking "place graph"):
- `frontend/src/features/composition/hooks/useWorldMap.ts` → `usePlaceGraph.ts` (export `usePlaceGraph`)
- `frontend/src/features/composition/components/WorldMap.tsx` → `PlaceGraph.tsx` (export `PlaceGraph`)
- update the 2 importers: `components/CompositionPanel.tsx:30,775` and `components/PowerViewOverlay.tsx:16,95`
- rename the 2 test files (`__tests__/WorldMap.test.tsx`, `hooks/__tests__/useWorldMap.test.tsx`) and their imports
- rename the internal query keys `['composition','worldmap',*]` → `['composition','place-graph',*]`
- **DO NOT rename the persisted `composition_work.settings.world_map` JSON key** — it is user data in a blob; renaming it needs a migration and buys nothing. Keep the key, and leave a one-line comment at its read site (`usePlaceGraph.ts`, the `work.settings.world_map` line): `// NOT book-service's world_maps (a drawn map w/ pins). This is a place-graph layout blob. See spec 38 §1.2.`
- The composition WorldMap's tab label / UI copy changes from "World Map" to "Place Graph".
- Safe to do in 8a because 8a's A1/A2 add the KG entity+relation create affordances that make this legacy writer redundant anyway (spec 38 §1.1 hole #1/#2).

**Nothing here contradicts plan 30 §0 or §10** — §10:757 already REFUTED "`useWorldMap.ts` is book-service's world maps"; this decision operationalizes that refutation instead of re-raising it. Third sense (the KG subgraph, `useWorldSubgraph` in `features/world`) needs no action — its name is already distinct.

PO veto hook: if you object to Rule 3's rename touching legacy composition files in wave 8a, drop Rule 3 only — Rules 1 and 2 are the ones that prevent the bug and are non-negotiable.

*Evidence:* services/book-service/internal/migrate/migrate.go:417 (`entity_id UUID, -- soft cross-service ref → glossary location entity (nullable)`; same at :431) · services/book-service/internal/api/mcp_maps.go:135 + :180 (`jsonschema:"optional glossary location entity id (UUID)"`) — vs — frontend/src/features/composition/hooks/useWorldMap.ts:94 (`work.settings.world_map` positions/backdrop blob) and :129 (`knowledgeApi.createEntity({kind:'location'})` → a Neo4j KG node, a DIFFERENT id space). No FK on `map_markers.entity_id` ⇒ a KG id written there is accepted and dangles silently. Importers to update for the rename: frontend/src/features/composition/components/CompositionPanel.tsx:30,775 · frontend/src/features/composition/components/PowerViewOverlay.tsx:16,95. Legacy page is kept-not-deleted: docs/specs/2026-07-01-writing-studio/16_chapter_editor_parity_and_retirement.md:3 ("Phase 4b (M9 — kept `ChapterEditorPage.tsx`, marked deprecated, not deleted)"). Prior refutation not re-raised: docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:757.

### Q-38-A2-PREDICATE-SPLIT-BRAIN
YES — unify the predicate control across all three verbs in `RelationEditDialog.tsx` this slice. But the control is NOT a bare closed `<select>`: it is a **schema-fed `<select>` whose closed-ness is driven by `ResolvedSchema.allow_free_edges`**, because that is the repo's OWN already-locked edge-vocab rule (`validate_edge`, knowledge-service `app/ontology/validation.py:111-140`: predicate ∈ edge_types → OK · ∉ AND allow_free_edges → OK (free edge) · ∉ AND closed → `unknown_edge_type`). A hard-closed FE select would invent a rule STRICTER than the ontology contract and would brick every project on the `general` seed (`seed_graph_schemas.py:92` sets `allow_free_edges: True` — "Q2 default; tighten per-project as opt-in").

BUILD IT EXACTLY LIKE THIS (one component + one hook call + one prop; zero backend):

1. **Get the project scope from the loaded ROW, not from 3 call sites.** `RelationEditDialog` currently takes only `{open, onOpenChange, relation}` (`RelationEditDialog.tsx:17-23`) and `EntityRelation` carries no `project_id` (`frontend/src/features/knowledge/api.ts:497-512`). `EntityDetailPanel` mounts it at `EntityDetailPanel.tsx:623` and is itself mounted in THREE places (`EntitiesTab.tsx:312`, `ProjectGraphView.tsx:171`, `WorldRollupGraph.tsx:176`) — only one of which has a `projectId` in scope. So: add prop `projectId: string | null` to `RelationEditDialogProps`, and in `EntityDetailPanel` pass `projectId={detail.entity.project_id ?? null}` (that field is already loaded — rendered at `EntityDetailPanel.tsx:375-376`). Zero call-site churn.

2. **Feed the options.** In `RelationEditDialog`, call the EXISTING `useResolvedSchema(projectId)` (`frontend/src/features/knowledge/hooks/useResolvedSchema.ts:9`; it is currently imported by NOTHING in prod code — this is its first real consumer). Options = `schema?.edge_types ?? []` filtered to `deprecated_at == null`, mapped to `{value: e.code, label: e.label || e.code}`, sorted by label. `ResolvedSchema` already declares `edge_types?: EdgeType[]` and `allow_free_edges: boolean` (`frontend/src/features/knowledge/types/ontology.ts:198-206`).

3. **Replace the free-text input** at `RelationEditDialog.tsx:127-134` with a `<select>` — **keep `data-testid="relation-edit-predicate"`** so existing selectors/E2E anchors survive.

4. **LEGACY-VALUE GUARD — do not skip this, it is a data-corruption bug, not polish.** An existing relation's `predicate` is frequently NOT in `edge_types`: extraction writes free predicates whenever `allow_free_edges` (default true), which is precisely why `useSchemaObserved` exists (`useGraphSchema.ts:158` — "the node kinds + edge types the project's extracted graph ALREADY CONTAINS, for one-click promotion into the schema"). If the current predicate is absent from the option list, a `<select>` mounts with no matching value → the browser auto-selects `option[0]` → the user clicks **Save** and the edge is silently re-predicated to an unrelated type. So: **always append the current `relation.predicate` as an option when it is not in `edge_types`**, in a trailing `<optgroup label="not in schema">`, and preselect it. In `create` mode there is no current value → start on an empty placeholder option and keep `canCorrect`/`canCreate` false until a real choice is made.

5. **Escape hatch = the schema's own flag.** If `schema.allow_free_edges === true`, render a final `Other…` option that reveals the old free-text `<input maxLength={100}>` (same testid suffixed `-custom`). If `false`, no `Other…` — the select is strictly closed. This makes the FE the FIRST consumer of `allow_free_edges`, which today is patchable (`ontology_mutations.py:565-581`) and read only by the extraction write boundary (`pass2_writer.py:383`) — never by any human path. That is a SET-* "stored-but-not-consumed" fix for free.
   Degenerate cases: `projectId == null` (a global entity) or `schema == null` (query disabled/loading/error) → fall back to the current free-text input. Never dead-end the shipped Correct verb behind a query.

6. **i18n:** add `relations.edit.predicate.placeholder`, `relations.edit.predicate.other`, `relations.edit.predicate.offOntologyGroup` to `frontend/src/i18n/locales/en/knowledge.json` and propagate with `scripts/i18n_translate.py` (all ~12 locales carry `relations.edit.*` today).

7. **Tests — `frontend/src/features/knowledge/components/__tests__/RelationEditDialog.test.tsx`** (mock `useResolvedSchema`), four cases: (a) options are exactly the schema's `edge_types[].code`; (b) **off-ontology current predicate is preserved and preselected, and submitting without touching the control does NOT change the predicate** (this is the guard from #4 — it must red without the fix); (c) `allow_free_edges: false` ⇒ no `Other…` option; (d) `allow_free_edges: true` ⇒ `Other…` reveals the free-text input and its value is what gets submitted.

PO veto point (my default, stated so you can overrule): I did NOT make the select hard-closed regardless of `allow_free_edges`. If you want ontology-strict authoring everywhere, the correct lever is flipping the `general` seed's `allow_free_edges` to `false` — one line in `seed_graph_schemas.py:92` — NOT a FE that contradicts the backend's validator.

BE half stays deferred as OQ-6 says (`D-KG-RELATION-PREDICATE-UNCONSTRAINED`) — but flag it at this wave's `/review-impl`: `relations.py:102` still takes `predicate: str = Field(min_length=1, max_length=100)` with NO call to `validate_edge`, and `validate_edge` ALREADY EXISTS and is already wired at `pass2_writer.py:383`. Wiring it into the human create/correct routes is ~10 lines (resolve the schema from the subject entity's `project_id`, call `validate_edge`, 422 on `unknown_edge_type`). Per CLAUDE.md's fix-now default, that row likely does not earn its keep.

*Evidence:* frontend/src/features/knowledge/components/RelationEditDialog.tsx:127-134 (the free-text `<input maxLength={100}>` — the split-brain) · RelationEditDialog.tsx:17-23 (no projectId prop) · frontend/src/features/knowledge/hooks/useResolvedSchema.ts:9 (the hook to call; zero prod consumers today) · frontend/src/features/knowledge/types/ontology.ts:198-206 (`ResolvedSchema.edge_types` + `allow_free_edges`) · services/knowledge-service/app/ontology/validation.py:111-140 (`validate_edge` — the canonical rule the FE must mirror: closed-set IFF `allow_free_edges` is false) · services/knowledge-service/app/db/seed_graph_schemas.py:92 (`allow_free_edges: True` — "Q2 default; tighten per-project as opt-in") · services/knowledge-service/app/extraction/pass2_writer.py:383 (the only place the flag is enforced today) · frontend/src/features/knowledge/hooks/useGraphSchema.ts:158 (`useSchemaObserved` — proves extracted edges are routinely off-ontology ⇒ the legacy-value guard is mandatory) · frontend/src/features/knowledge/components/EntityDetailPanel.tsx:623 (mount) + :375-376 (`detail.entity.project_id` is already loaded) · services/knowledge-service/app/routers/public/relations.py:102 (BE predicate still an unvalidated free string — the deferred half)

### Q-38-A5-NO-RESTORE-PROJECT
CONFIRMED against code — the spec's claim is exactly right, and it is binding on the builder. Restore is an OCC PATCH via `updateProject`; do NOT add a `restoreProject` mutation to `useProjects`, do NOT add a `restoreProject` method to `knowledgeApi`, do NOT drop `expectedVersion`. ONE addition the spec asks for but no site actually implements: the 412 handler. Build M8a.1/A5 exactly as follows.

(1) NEW FILE `frontend/src/features/knowledge/lib/projectRestore.ts` — a plain composed function, NOT a mutation and NOT an api method (this does not violate "no restoreProject"; it wraps the existing `updateProject` call so both call sites share the 412 logic instead of forking it):

```ts
import { isVersionConflict } from '../api';
import type { Project, ProjectUpdatePayload } from '../types';

type UpdateFn = (a: { projectId: string; payload: ProjectUpdatePayload; expectedVersion: number }) => Promise<Project>;

/** D-K8-03 — restore = OCC PATCH, never a bespoke mutation. Returns 'restored'
 *  or 'already' (another device beat us to it). Absorbs ONE 412 by resetting the
 *  baseline from the 412 body (the BE returns the current row — api.ts:977-986). */
export async function restoreArchivedProject(updateProject: UpdateFn, project: Project): Promise<'restored' | 'already'> {
  try {
    await updateProject({ projectId: project.project_id, payload: { is_archived: false }, expectedVersion: project.version });
    return 'restored';
  } catch (err) {
    if (!isVersionConflict<Project>(err)) throw err;
    const current = err.current;                       // fresh row from the 412 body
    if (current.is_archived === false) return 'already';  // someone else restored it — NOT an error
    await updateProject({ projectId: project.project_id, payload: { is_archived: false }, expectedVersion: current.version });
    return 'restored';                                 // retry ONCE with the reset baseline; a 2nd 412 throws
  }
}
```

(2) `ProjectsBrowser.tsx:142-156` — replace the body of `handleRestore` with `const r = await restoreArchivedProject(updateProject, project)` and toast `projects.toast.restored` on 'restored', a muted `projects.toast.alreadyRestored` (new i18n key, en + the other locales via scripts/i18n_translate.py) on 'already'. Keep the existing catch/`toast.error(projects.toast.restoreFailed)`. Do not change the `expectedVersion: project.version` argument.

(3) `ProjectRow.tsx:29-31` — make `onArchive?` / `onRestore?` / `onDelete?` OPTIONAL and render nothing when absent (guard the buttons at `:294`, `:302`, `:310` on the handler's presence, not on a truthy no-op).

(4) `shell/OverviewSection.tsx` — DELETE `const noop = () => {}` (`:56`). Pull `archiveProject, deleteProject` from the SAME `useProjects(false)` at `:42`, add ProjectsBrowser's two `ConfirmDialog`s (archive + destructive delete), and pass `onRestore={(p) => void restoreArchivedProject(updateProject, p).then(...)}` using the shared helper from (1). Same OCC call, same version.

(5) TESTS (a slice is not done without them — checklist-is-self-report-enforce-by-tests):
 · `ProjectRow.test.tsx` — render WITHOUT `onDelete`, assert `queryByTitle('projects.card.delete')` is `null` (same for onArchive/onRestore).
 · NEW `lib/__tests__/projectRestore.test.ts` — (a) happy path asserts `updateProject` called with `{is_archived:false}` AND `expectedVersion: project.version`; (b) a 412 whose body is `{...project, version: 5, is_archived: true}` ⇒ SECOND call carries `expectedVersion: 5` (mirror `GlobalMobile.test.tsx:126` "absorbs 412 by advancing baselineVersion from error.body"); (c) a 412 whose body has `is_archived:false` ⇒ resolves 'already' with exactly ONE call.
 · `OverviewSection` test — clicking Delete opens a real ConfirmDialog (no silent no-op).

DEFAULT THE PO MAY VETO: on 412-with-already-restored I report success-ish ("already restored"), not an error — a false error on a row that IS restored is the worse failure. Everything else is the spec's letter.

*Evidence:* frontend/src/features/knowledge/hooks/useProjects.ts:133-153 (exports exactly createProject/updateProject/archiveProject/deleteProject — no restoreProject; updateMutation takes {projectId,payload,expectedVersion} → knowledgeApi.updateProject) · frontend/src/features/knowledge/components/ProjectsBrowser.tsx:142-156 (handleRestore = updateProject{is_archived:false} + expectedVersion: project.version; its catch at :153-155 ONLY toasts — the 412 baseline-reset the spec demands is MISSING today, so "reuse that exact call" must not copy the incomplete catch) · frontend/src/features/knowledge/api.ts:977-986 (isVersionConflict<T> — BE returns the current row in the 412 body, `err.current`, "no second GET needed") · frontend/src/features/knowledge/api.ts:1034-1048 (updateProject sets If-Match: W/"version"; strictly required — BE 428s without it) · frontend/src/features/knowledge/components/shell/OverviewSection.tsx:56 + :64-70 (`const noop = () => {}` passed as onArchive/onRestore/onDelete — the three dead buttons) · frontend/src/features/knowledge/components/ProjectRow.tsx:29-31 (props currently REQUIRED, which is what forced the noops) + :294,:302,:310 (the three buttons) · frontend/src/features/knowledge/components/mobile/__tests__/GlobalMobile.test.tsx:126-182 (the existing "absorbs 412 by advancing baselineVersion from error.body" pattern to mirror)

### Q-38-NAME-COLLISION-THREE-WORLD-MAPS
DECIDED — the concern is real but it is a VOCABULARY + WRONG-STORE hazard, not a design hole. Bake these five mechanical rules into spec 38 §1.2 (replace the prose "they are three different things" with them) and into M8b.3's Definition of Done. No re-litigation of plan 30 §10.

RULE 1 — Vocabulary is LOCKED for wave 8 (use these words in code, comments, panel titles, commits):
  • "world map"  = book-service's DRAWN MAP (`world_maps`/`map_markers`/`map_regions`). THE ONLY thing spec 38 / M8b builds.
  • "place graph" = `composition_work.settings.world_map` + `features/composition/{hooks/useWorldMap.ts,components/WorldMap.tsx}`. NEVER called a world map again.
  • "the knowledge graph" = the Neo4j subgraph. Never "world map".

RULE 2 — THE BITE, and it is sharper than the spec says: the two "maps" hang off DIFFERENT ENTITY STORES.
  • book-service `map_markers.entity_id` / `map_regions.entity_id` = a soft, unvalidated cross-service UUID pointing at a **GLOSSARY** `location` entity (migrate.go:415 comment "soft cross-service ref → glossary location entity"; mcp_maps.go:135,180 jsonschema "optional glossary location entity id"; mcp_maps.go:56 `parseOptionalEntityID` only parses the UUID — there is NO FK and NO existence check, so a wrong-store UUID is accepted silently and renders as a dangling pin).
  • `useWorldMap.ts` places = **KNOWLEDGE** entities (`knowledgeApi.getEntities/createEntity`, useWorldMap.ts:9,129).
  ⇒ A builder who copies useWorldMap.ts's entity picker into M8b.3's marker/region picker wires knowledge-entity UUIDs into a glossary-entity column and NOTHING ERRORS. That is this repo's `silent-success-is-a-bug` + `cross-service-normalization` class, pre-loaded. M8b.3's picker MUST source from the GLOSSARY (per OQ-2: world bible book first, then member books) — never from `knowledgeApi`.

RULE 3 — Coordinates are different too: world-map marker x,y are RELATIVE [0,1] over the base image (migrate.go:418-419, DOUBLE PRECISION); place-graph positions are ABSOLUTE React-Flow/SVG pixels (`gridLayout` in useWorldMap.ts:22-31, gapX=200px). Do not reuse `GraphCanvas`/`Pos` for the map canvas.

RULE 4 — HARD ISOLATION, mechanically checkable. All M8b.3 code lives in a NEW dir `frontend/src/features/worlds/**`. It MUST NOT import anything from `features/composition/**`, and MUST NOT read or write `work.settings.world_map`. Add to M8b.3's DoD a literal command whose output is pasted into VERIFY:
    grep -rn "features/composition" frontend/src/features/worlds/   → must be EMPTY
    grep -rn "settings.world_map\|knowledgeApi" frontend/src/features/worlds/ → must be EMPTY

RULE 5 — Kill the ambiguous identifier at the source (10-minute mechanical step, do it FIRST in M8b.3, FE-only, composition-service untouched): rename `features/composition/hooks/useWorldMap.ts` → `usePlaceGraph.ts`, `components/WorldMap.tsx` → `PlaceGraph.tsx` (+ their two `__tests__` files and the import in `CompositionPanel.tsx` / `PowerViewOverlay.tsx`; symbols `useWorldMap`→`usePlaceGraph`, `WorldMap`→`PlaceGraph`). DO NOT rename the persisted JSONB key `work.settings.world_map` — that would need a data migration on a page spec 16 already slates for deletion; instead put this exact comment at the read site (useWorldMap.ts:94): `// legacy key name — this is the PLACE GRAPH over KNOWLEDGE entities, NOT book-service's world_maps (drawn map, glossary entities). See spec 38 §1.2.` Post-rename invariant, also in the DoD: `grep -rln "WorldMap" frontend/src` returns ONLY files under `features/worlds/**`.

Default I am picking (PO may veto): Rule 5's rename happens even though the legacy page is slated for retirement — a one-import, four-file rename is cheaper than carrying this collision through an autonomous build, and it converts the concern into a grep the builder can run. Rules 1-4 are non-negotiable regardless. OQ-9 stands unchanged: the place graph itself is NOT ported in this wave.

*Evidence:* services/book-service/internal/migrate/migrate.go:395-434 (world_maps/map_markers/map_regions; :415 "soft cross-service ref → glossary location entity"; :418-419 x,y "relative [0,1] on the base image") · services/book-service/internal/api/mcp_maps.go:56 (parseOptionalEntityID — UUID parse only, no existence/store check), :135 + :180 (jsonschema "optional glossary location entity id") · frontend/src/features/composition/hooks/useWorldMap.ts:9 (imports knowledgeApi — KNOWLEDGE entities), :22-31 (gridLayout, absolute px), :94 + :108 (reads/writes work.settings.world_map), :129/:134 (only human callers of createEntity/createRelation) · docs/specs/2026-07-01-writing-studio/38_kg_and_world.md §1.2 table + OQ-2/OQ-9

### Q-38-THIRD-MACHINE-GUARD-HYGIENE
The concern is real and the code already dictates the answer — no product call here. Build M8b.2/M8b.3 to these five rules (add them verbatim to the wave's DoD, and add a row to plan 30 §GG-8's table naming `panels/__tests__/dockablePanelHygiene.test.ts` as the THIRD machine guard — it is a 1-line doc fix, fix-now, not a defer).

**1 · DOCK-7 — the "Open the full world workspace" escape hatch (WorldPanel.tsx).**
Render a plain `<button>` whose onClick is:
`followStudioLink(`/worlds/${worldId}`, host, { bookId: host.bookId })` — imported from `../host/studioLinks`, `host` from `useStudioPanel(...)`. Exact precedent: `frontend/src/features/studio/panels/BookSettingsPanel.tsx:52`. Never `<Link>`, `useNavigate`, `useParams`.

**⚠ TRAP the spec's own step 7 creates — do NOT pass `worldId` in the ctx of THIS call.** Spec 38 step 7 makes `/worlds/{id}` resolve to `openPanel('world')` when `ctx.worldId === worldId`. If the escape hatch passed `{ bookId, worldId }` it would re-open the very panel the user is standing in (a self-focus no-op) instead of the full workspace. The rule to write into the code comment: **ctx carrying `worldId` = "open it inside the studio" (that is what KgOverviewPanel step 7b wants); ctx omitting `worldId` = "leave for the full app"** — it falls through `studioLinks.ts:113` to `{kind:'external'}` and `followStudioLink` `window.open`s a new tab (`studioLinks.ts:117-122`), studio stays mounted. Spec step 7c's third case ("`worldId` absent ⇒ external") is therefore not just a degrade path — it is this escape hatch's contract; assert it.

**2 · DOCK-7's blind spot — the guard only scans `panels/**`.** `features/world/components/{LivingWorldTree,WorldsBrowser,WorldPopulateActions}.tsx` each import `useNavigate` (LivingWorldTree.tsx:16, WorldPopulateActions.tsx:3, WorldsBrowser.tsx:3). Reusing any of them inside WorldPanel PASSES the hygiene test and still unmounts the studio at runtime. If the panel reuses one, refactor it to take an injected navigation callback prop and pass the `followStudioLink` handler from the panel — the exact pattern already documented at `features/world/components/BookWorldSection.tsx:17-27` (`onOpenWorld`; SettingsTab injects a `useNavigate` handler, BookSettingsPanel injects a `followStudioLink` one; the component itself imports neither react-router nor the studio host). Keep the classic route call sites working by leaving their `useNavigate`-based handler in place.

**3 · DOCK-9 — the five surfaces, resolved one by one:**
- **World picker** → not a dialog at all: use the existing `WorldPicker` (`@/components/shared/WorldPicker` — an inline combobox, `WorldPicker.tsx:30`).
- **Create a world** → `FormDialog`, wired to WorldPicker's existing `onCreateNew` prop (`WorldPicker.tsx:27` — "creation is delegated to the consumer (which owns the modal)").
- **`+ New map`** → `FormDialog`.
- **Marker / region delete confirms** → `ConfirmDialog` with `variant="destructive"` (one shared instance per panel driven by a `pendingDelete` state, not one per row).
- **Image dropzone** → **not a dialog**. Render it inline in the panel body; a drag-highlight overlay must be `absolute inset-0` inside a `relative` parent — **never `fixed`**. (Both because DOCK-9 reds on the `fixed`+`inset-0` token pair, and because in dockview `fixed` pins to the WINDOW, not the panel — a bug this repo already ate.) If it truly must be modal, wrap it in `FormDialog`.

**4 · Import specifier matters.** Import the dialogs from the **barrel**: `import { FormDialog, ConfirmDialog } from '@/components/shared'`. The DOCK-9 exemption is a literal regex on `from '@/components/shared'` or `@radix-ui/react-dialog` (`dockablePanelHygiene.test.ts:54`) — a deep import like `@/components/shared/FormDialog` does NOT satisfy it, so the moment the file contains a `fixed` and an `inset-0` token anywhere it reds.

**5 · DoD (literal step in each wave):** `cd frontend && npx vitest run src/features/studio/panels/__tests__/dockablePanelHygiene.test.ts` green — it is already in spec 38 §5's verify block; it must also be named in plan 30 §GG-8 so the next panel builder doesn't rediscover it. Plus `/review-impl` at wave close, per the PO's run policy.

*Evidence:* frontend/src/features/studio/panels/__tests__/dockablePanelHygiene.test.ts:39-44 (DOCK-7 regexes), :46-62 (DOCK-9 token pair + the ONLY two exempt imports at :54), :21-30 (recursive scan of panels/**, so nothing outside panels/** is covered) · frontend/src/features/studio/panels/BookSettingsPanel.tsx:52 — `onOpenWorld={(worldId) => followStudioLink(`/worlds/${worldId}`, host, { bookId: host.bookId })}` (the escape-hatch shape, ctx WITHOUT worldId) · frontend/src/features/studio/host/studioLinks.ts:113 (unmapped app path ⇒ external) and :117-122 (`followStudioLink` window.open's `_blank`) · frontend/src/features/world/components/BookWorldSection.tsx:17-27 (injected-callback precedent for a component shared by a route AND a panel) · frontend/src/features/world/components/LivingWorldTree.tsx:16, WorldPopulateActions.tsx:3, WorldsBrowser.tsx:3 (useNavigate — the un-scanned DOCK-7 landmines) · frontend/src/components/shared/index.ts:2-3 (barrel exports ConfirmDialog/FormDialog) · frontend/src/components/shared/WorldPicker.tsx:27 (`onCreateNew` — consumer owns the modal) · frontend/src/App.tsx:191 (`/worlds/:worldId` route exists, so the new-tab escape hatch lands on a real page)

### Q-38-COORDS-RELATIVE-NEVER-PIXELS
The "relative [0,1], never pixels" rule is CORRECT and already true in the schema — but the CONCERN's word "clamps" is WRONG for the backend and contradicts the spec's own route table. Decide it as a split of responsibility, and fix the spec prose.

**RULE (binding for M8b.1 + M8b.3): the BACKEND NEVER CLAMPS — IT REJECTS (422). THE FRONTEND CLAMPS AT THE SOURCE.**

A server that silently clamps x=1.4 → 1.0 and returns 201 is the `silent-success-is-a-bug` class: the caller (an agent, a buggy FE) is told the pin landed where it asked, and it did not. Rejection is also what the code already does and what the spec's own BE-15 table already specifies (BE-15g/h/j/k: "422 (coords ∉ [0,1])").

**1. M8b.1 (book-service, Go) — validate + reject, in ONE shared helper.**
Extract the two existing inline checks into shared validators in `services/book-service/internal/api/mcp_maps.go` (or a new `maps_validate.go`) and call them from BOTH writers:
```go
func validateRelPoint(x, y float64) error   // lifts mcp_maps.go:156
func validateRelPolygon(pts [][]float64) error  // lifts mcp_maps.go:200-206 (>=3 pts, each len==2, each in [0,1])
```
Also reject NaN/±Inf explicitly (`math.IsNaN || math.IsInf`) — today `x < 0 || x > 1` lets NaN through both checks, and NaN into a DOUBLE PRECISION column is a permanently un-renderable pin. This is a real bug in the code at HEAD; fix it in the shared helper.
- MCP tools (`toolWorldMapAddMarker`, `toolWorldMapAddRegion`, and the NEW BE-15m `world_map_update_marker` / `_update_region`) → return the error, as today.
- REST handlers (BE-15g/h/i/j/k/l) → map the same error to **422**, LoreWeave error envelope. No clamping, no coercion, no rounding.
- **PATCH partial semantics:** `x`, `y`, `polygon` are `*float64` / `*[][]float64`. Absent ⇒ unchanged. **Present ⇒ validated ⇒ 422 on violation.** Never coerce an out-of-range value into range on a PATCH.
- **Do NOT add a DB CHECK constraint.** `polygon` is JSONB (not CHECK-able cleanly) and `ALTER TABLE … ADD CONSTRAINT` has no `IF NOT EXISTS` in PG, so it breaks the forward-only idempotent migration pattern. Both writers now share one validator — close the window in the WRITER, per `close-legacy-window-in-writer-not-base-schema`.

**2. M8b.3 (canvas, FE) — clamp at the source; convert on render from the RENDERED RECT, never from `image_w/image_h`.**
- Write path (drag/drop, polygon vertex placement) clamps in the pointer handler before a request body is ever built:
  `const x = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));` (same for `y` / `rect.height`; same clamp per polygon vertex). Clamping here is a UI affordance — "you cannot drag a pin off the image" — not a data-integrity mechanism. Because the FE clamps, the BE's 422 should be unreachable from the GUI; it exists to catch agents and bugs.
- Read path converts with the **live rendered element rect**: `left: x * rect.width, top: y * rect.height`. **Never use `world_maps.image_w` / `image_h` for coordinate math.** Those columns (written only at `services/book-service/internal/api/maps_image.go:108`) are metadata — use them at most for an aspect-ratio box / zoom-to-fit. Using them to convert coords re-introduces exactly the resolution coupling the relative schema exists to prevent: replace the base image at a new resolution (BE-15f is an upload/**replace**), and every pin moves.
- Never store a pixel value in component state that outlives the gesture, and never send one. In-flight pixel deltas during a drag are fine; the value that hits `setState`/the PATCH body is relative.
- The inspector displays 3-decimal relative values (`x .412  y .688`) — matching the §3.3 wireframe. Confirms by eye that pixels never leaked.

**3. Tests (name them in the slice DoD):**
- Go: `POST /v1/worlds/maps/{id}/markers` with `x=1.4` ⇒ **422**, and assert `SELECT count(*) FROM map_markers` did not increase — i.e. assert it was NOT clamped to 1.0 and stored. Same for a polygon point ∉ [0,1] and for `x=NaN`.
- Go: `PATCH …/markers/{id}` with `x=-0.2` ⇒ 422 AND the row's prior `x` is unchanged.
- Vitest: simulate a drag whose pointer exits the image on the left/top ⇒ the PATCH body contains exactly `x: 0` (not a negative), and a drag past right/bottom ⇒ `x: 1`. Assert no value in the body is `<0`, `>1`, or `> 2` (the pixel tell).
- Vitest: render the canvas at two different container widths with the SAME stored marker and assert the pin's relative position is identical — the regression test for "the base image was replaced at a different resolution."

**4. Fix the spec (M8b.1, same commit).** `docs/specs/2026-07-01-writing-studio/38_kg_and_world.md:228` currently reads "the canvas converts on render, and every write clamps." Rewrite to: "the canvas converts on render **from the rendered rect (never from `image_w/image_h`)**; the **FE clamps at the source**, the **BE validates and rejects with 422 — it never clamps**. Never store pixels." As written, line 228 tells a 3am builder to make the server silently coerce, which contradicts BE-15g/h/j/k in the same document and the code at `mcp_maps.go:156`.

**5. Do NOT "fix" `frontend/src/features/composition/hooks/useWorldMap.ts`.** It is a *different feature* (T2.5 composition place-GRAPH: `gridLayout` writes pixel `Pos {x,y}` into `work.settings`). A force-directed graph has no base image, so pixels are correct there. This rule governs only `map_markers` / `map_regions` on a `world_maps` base image. A builder grepping "worldMap" will find that hook first — the risk of conflating them is real.

No PO input needed: this contradicts nothing in plan 30 §0 (PO-1..4), and it is what the code and the BE-15 table already say. The only judgment call is reject-vs-clamp on the server, and the default chosen (reject/422) is the one the existing writers implement — the PO can veto by asking for server-side clamping, but that would be a new behavior, not the status quo.

*Evidence:* services/book-service/internal/migrate/migrate.go:414-419 (`map_markers.x/y DOUBLE PRECISION -- relative [0,1] on the base image`) and :430 (`map_regions.polygon JSONB -- array of [x,y] relative points`) — schema is relative, confirming the rule. services/book-service/internal/api/mcp_maps.go:156 (`if in.X < 0 || in.X > 1 || in.Y < 0 || in.Y > 1 { return ... errors.New("x and y must be relative coords in [0,1]") }`) and :204 (`each polygon point must be [x,y] with x,y in [0,1]`) — the existing writers REJECT, they do not clamp; both also let NaN through. services/book-service/internal/api/maps_image.go:108 (`UPDATE world_maps SET image_object_key=$1, image_w=$2, image_h=$3`) — the only writer of image_w/h, and the reason a base image can be replaced at a new resolution. docs/specs/2026-07-01-writing-studio/38_kg_and_world.md:228 (the "every write clamps" prose) vs the BE-15g/h/j/k rows in the same file's route table ("422 (coords ∉ [0,1])") — the self-contradiction this decision settles. frontend/src/features/composition/hooks/useWorldMap.ts:296-320 (`gridLayout` → pixel `Pos`) — the lookalike hook that is NOT in scope.

### Q-38-A4-FALSE-INVALIDATED-STATE
CONFIRMED, with one amendment to the wire shape that makes the "never report success" rule structurally enforced instead of merely instructed.

**BE-14b (knowledge-service) — the REST mirror is STRICT, the MCP tool stays soft.**
1. New router `services/knowledge-service/app/routers/public/facts.py` (mount beside `relations.py` in the same public router include). Route: `POST /v1/knowledge/facts/{fact_id}/invalidate`, no body, `user_id: UUID = Depends(get_current_user)`, `fact_id: str = Path(min_length=1, max_length=200)`.
2. Body: `fact = await invalidate_fact(session, user_id=str(user_id), fact_id=fact_id)` inside `async with neo4j_session()`.
3. **On `fact is None` raise `HTTPException(404, detail="fact not found")`** — copy `relations.py:75-76` verbatim (KSA §6.4 no-oracle: cross-user and missing collapse to the same code). **Do NOT return `200 {invalidated:false, reason:...}` on the REST path.** Reason: a 200 body is exactly the shape that lets a builder write `onSuccess: () => toast('Forgotten')` and ship the false-success this concern names. A rejected promise cannot be mistaken for success. Response model on the happy path: `{invalidated: true, fact_id}` (200). This amends spec §3.1 A4's stated wire shape (`{invalidated: bool}`) — PO may veto, but the honesty requirement is met more strongly, not less.
4. `memory_forget` / `executor.py:718` is **unchanged** — the LLM path keeps its non-throwing `{invalidated:false, reason:"no matching fact found"}` body. Two callers, two idioms, one engine.
5. **Emit no outbox event.** There is no `FACT_CORRECTED` (`outbox_emit.py:63-64`) and `memory_forget` emits none. Do not invent one in this wave.
6. pytest (`tests/unit/test_public_facts_invalidate.py`, `xdist_group("pg")` only if it hits a real DB): 200 + `invalidated:true`; **404 on another user's fact_id**; 404 on an unknown id; re-invalidating an already-forgotten fact returns **200 again** (idempotent — `facts.py:667-671` re-MATCHes regardless of `valid_until`).

**FE (the part the concern is actually about).**
7. `frontend/src/features/knowledge/api.ts` — add `invalidateFact(factId, token)` next to `invalidateRelation` (`api.ts:1722`).
8. New hook `frontend/src/features/knowledge/hooks/useForgetFact.ts`, modelled on `useRelationMutations.ts:35-56` but it MUST invalidate `['knowledge-entity-facts', userId, entityId]` — the key `useEntityFacts.ts:31` owns — **not** `['knowledge-entity-detail', …]`. Invalidating the wrong key leaves the stale row on screen (this repo's `invalidatequeries-cannot-reach-hand-rolled-state` class).
9. Success (200): invalidate that key → the row disappears on refetch because `list_facts_for_entity` filters `f.valid_until IS NULL` (`facts.py:598`). Neutral toast `kg.facts.forget.done` ("Forgotten").
10. **STALE (404): in `onError`, branch on status === 404 → invalidate the SAME facts key (refetch) and show an INFO toast `kg.facts.forget.alreadyGone` ("That fact is already gone.") — no success toast, no red error toast. Every other status → the normal error toast.** This is the A4 requirement, implemented.
11. Confirm-first is mandatory: an AlertDialog on the `⋯ → Forget` row action in `EntityDetailPanel` (facts list at `:135`; the panel is mounted by both `EntitiesTab`→`kg-entities` and `ProjectGraphView`→`kg-graph`, so one edit lights both). Copy, verbatim, as the i18n string `kg.facts.forget.confirmBody`: "Forgetting hides this fact from future context. It is not deleted from history — but there is no un-forget button." Title `kg.facts.forget.confirmTitle`: "Forget this fact?" Confirm label: "Forget" (destructive variant). No cost gate (deterministic, LLM-free).
12. **Vitest is the enforcement, not the checklist** (`checklist-is-self-report-enforce-by-tests`): in `frontend/src/features/knowledge/hooks/__tests__/useForgetFact.test.tsx` — (a) mock `invalidateFact` rejecting with a 404 ⇒ assert the success callback/toast was NOT called, the facts query WAS invalidated, and the "already gone" path fired; (b) 200 ⇒ facts query invalidated; (c) in `EntityDetailPanel` test: cancelling the confirm dialog fires zero requests. Note the Vitest trap: do not return the mock from `beforeEach` (`vitest-beforeeach-returning-a-mock-is-treated-as-teardown`).
13. Do NOT wire any of this to `POST /pending-facts/{id}/reject` or `/internal/admin/…/reject-fact` — different objects, different lifecycles (already stated in A4; restated because it is the likely 3am mistake).

*Evidence:* services/knowledge-service/app/tools/executor.py:710-722 (`_handle_memory_forget` → `{"invalidated": False, "reason": "no matching fact found"}`); services/knowledge-service/app/db/neo4j_repos/facts.py:667-698 (`invalidate_fact` MATCHes on (id,user_id) ignoring `valid_until` ⇒ None means unknown/foreign, never "already forgotten") and facts.py:598 (`AND f.valid_until IS NULL` in `list_facts_for_entity` ⇒ refetch drops the row); services/knowledge-service/app/routers/public/relations.py:63-93 (the sibling human-write mirror raises 404 on `None` — the pattern to copy); services/knowledge-service/app/events/outbox_emit.py:63-64 (no FACT_CORRECTED ⇒ emit nothing); frontend/src/features/knowledge/hooks/useRelationMutations.ts:35-56 (hook shape) vs frontend/src/features/knowledge/hooks/useEntityFacts.ts:31 (the query key that must be invalidated: `['knowledge-entity-facts', userId, entityId]`); frontend/src/features/knowledge/components/EntityDetailPanel.tsx:135 (facts list = the surface for the row action).

### Q-38-MARKER-ENTITY-IS-GLOSSARY-NOT-KG
CONFIRMED BY CODE — the marker/region link is a GLOSSARY entity id, and it is NULLABLE by design. Build M8b.3 exactly like this:

(1) FE PICKER SOURCE = GLOSSARY, NEVER KNOWLEDGE. In the map inspector (marker + region), the entity picker calls `glossaryApi.listEntities(bookId, { kindCodes: ['location'], searchQuery, status: 'all', limit: 50 })` (frontend/src/features/glossary/api.ts:73). It MUST NOT call `knowledgeApi.listEntities` / `knowledgeApi.createEntity` (frontend/src/features/knowledge/api.ts:1600) — a KG entity UUID written into `map_markers.entity_id` is a dangling id nothing validates.

(2) WHICH BOOK (this also RESOLVES OQ-2 — its premise is VERIFIED, no fallback needed). The world's bible book is a real glossary book: `createWorld` auto-provisions a hidden bible BOOK + sort_order-0 bible CHAPTER (services/book-service/internal/api/worlds.go:51-126), `getWorld` returns `bible_book_id`/`bible_chapter_id` (worlds.go:163-175), and the FE already authors into it via `worldApi.createBibleEntity` → `POST /v1/glossary/books/{bibleBookId}/entities` (frontend/src/features/world/api.ts:90-95). So the picker is a grouped combobox over TWO sources, in this order:
   - group 1 "World bible" — `glossaryApi.listEntities(world.bible_book_id, {kindCodes:['location']})`;
   - group 2..n one group per member book — `worldApi.listWorldBooks(token, worldId)` (GET /v1/worlds/{world_id}/books, server.go:387), then `listEntities(book.id, {kindCodes:['location']})` for the selected book (lazy: only fetch a book's entities when its group is expanded/searched — do not N+1 on open).
   Filter `kindCodes:['location']` (a seeded system kind) but expose a "show all kinds" toggle, because `entity_id` is untyped at the DB and a user may legitimately pin a faction/character.

(3) "NO LINK" IS A FIRST-CLASS OPTION, NOT AN ERROR STATE. The picker's first row is a literal `— No entity link —` option, and a linked marker shows a Clear (×) affordance. Clearing sends the entity_id field as omitted/empty-string, which the BE already maps to NULL: `parseOptionalEntityID` returns `(nil, nil)` on blank (services/book-service/internal/api/mcp_maps.go:56-65). A marker with `entity_id = NULL` is VALID and must render normally (label only, no entity chip). Do not make the field required; do not auto-create a glossary entity to satisfy it.

(4) NEW REST ROUTES (BE-15f) MUST MIRROR THE TOOL'S SEMANTICS EXACTLY — reuse `parseOptionalEntityID`: accept `entity_id` as optional/nullable, validate UUID SHAPE ONLY, and do NOT round-trip to glossary-service to check existence. The soft FK is intentional (migrate.go:414 comment: "soft cross-service ref → glossary location entity (nullable)"; glossary is a separate DB). An existence check would (a) couple book-service to glossary-service on the write path and (b) become an existence oracle across tenants. For UPDATE (the new PATCH semantics §3.3), model the field as a tri-state on the wire: field absent = leave unchanged, `null`/`""` = clear to NULL, UUID = set.

(5) DANGLING IDS ARE EXPECTED — RENDER, DON'T CRASH. Because the FK is soft, a glossary entity can be deleted after a marker links it. On map load, resolve linked entities by batching `GET /v1/glossary/books/{bookId}/entities` results; when an `entity_id` resolves to nothing, render the marker with its own `label` plus a muted "link unresolved" chip and an "unlink" action. Never 500, never hide the marker, never silently drop the id.

(6) TEST (make it a red-first test, per policy): book-service `internal/api/maps_rest_test.go` — POST a marker with `entity_id` omitted ⇒ 201 and the row's `entity_id IS NULL`; POST with a random (non-existent) UUID ⇒ 201 (no existence check); POST with `"not-a-uuid"` ⇒ 400 "entity_id must be a UUID". FE: `MapInspector.test.tsx` — asserts the picker's query hits the GLOSSARY api module (mock `glossaryApi.listEntities`, assert `knowledgeApi.listEntities` is NEVER called) and that selecting "— No entity link —" submits with entity_id cleared.

VETO NOTE for the PO: the default I picked for the picker scope is "world bible first, then member books, kind-filtered to `location` with a show-all toggle". If you would rather ship v1 as bible-book-only (simpler, one query), say so — everything else above is forced by the code and does not change.

*Evidence:* services/book-service/internal/migrate/migrate.go:414 + :430 — `entity_id UUID, -- soft cross-service ref → glossary location entity (nullable)` (no FK, NULLABLE) · services/book-service/internal/api/mcp_maps.go:56-65 `parseOptionalEntityID` (blank ⇒ NULL; UUID-shape-only, NO existence check) and :135/:180 jsonschema "optional glossary location entity id (UUID)" · frontend/src/features/glossary/api.ts:73 `listEntities(bookId, {kindCodes,…})` (the correct picker source) · frontend/src/features/knowledge/api.ts:1600 `knowledgeApi.createEntity` (the WRONG source — do not wire) · OQ-2 verified: services/book-service/internal/api/worlds.go:51-126 (world auto-provisions bible book+chapter) and :163-175 (getWorld returns bible_book_id/bible_chapter_id); frontend/src/features/world/api.ts:90-95 `createBibleEntity` posts to `/v1/glossary/books/{bibleBookId}/entities`; services/book-service/internal/api/server.go:387 `GET /v1/worlds/{world_id}/books`

### Q-38-A5-THREE-DEAD-BUTTONS
CONFIRMED DEFECT — do BOTH parts, exactly as the spec frames them (part 2 is the load-bearing one). No new BE, no new i18n keys, no new route.

**(A) `ProjectRow.tsx` — make the three destructive props OPTIONAL and render nothing when absent (the structural fix).**
1. `:29-31` — change `onArchive: (p: Project) => void;` / `onRestore` / `onDelete` to `onArchive?:` / `onRestore?:` / `onDelete?:`.
2. `:292-308` — wrap the archive/restore branch so it renders only when the matching handler exists: `{!isArchived && onArchive && (<button onClick={() => onArchive(project)} …/>)}` and `{isArchived && onRestore && (<button onClick={() => onRestore(project)} …/>)}` (keep it a flat pair of guarded blocks — do NOT keep the `!isArchived ? … : …` ternary, or the archived branch renders a Restore button with no `onRestore`).
3. `:309-315` — guard the delete button: `{onDelete && (<button onClick={() => onDelete(project)} title={t('projects.card.delete')} …/>)}`.
   `onEdit` stays REQUIRED (both call sites supply a real one).

**(B) `OverviewSection.tsx` — wire the real handlers (kill the `noop`).**
4. DELETE `:56` (`const noop = () => {};`) entirely.
5. `:42` — widen the existing destructure to `const { createProject, updateProject, archiveProject, deleteProject } = useProjects(false);` (already exported — `useProjects.ts:144-147`; its mutations invalidate the whole `['knowledge-projects']` family at `:93-94`, so every view self-refreshes).
6. Add local state mirroring `ProjectsBrowser.tsx:105-107`: `const [archiveOpen, setArchiveOpen] = useState(false); const [deleteOpen, setDeleteOpen] = useState(false); const [actionPending, setActionPending] = useState(false);`
7. Add three handlers copied in shape from `ProjectsBrowser.tsx:128-170` (same i18n keys — they all already exist in all 18 locales, so NO locale sweep):
   - `handleArchive`: `await archiveProject(project.project_id)` → `toast.success(t('projects.toast.archived'))` → `setArchiveOpen(false)`; catch → `toast.error(… t('projects.toast.archiveFailed'))`; `actionPending` in finally.
   - `handleRestore`: `await updateProject({ projectId: project.project_id, payload: { is_archived: false }, expectedVersion: project.version })` → `toast.success(t('projects.toast.restored'))`; catch → `projects.toast.restoreFailed`. (No confirm dialog — matches the browser.)
   - `handleDelete`: `await deleteProject(project.project_id)` → `toast.success(t('projects.toast.deleted'))` → `setDeleteOpen(false)` → `onProjectDeleted?.()`; catch → `projects.toast.deleteFailed`.
8. Replace `:67-69` with `onArchive={() => setArchiveOpen(true)}` / `onRestore={() => void handleRestore()}` / `onDelete={() => setDeleteOpen(true)}`.
9. Render two `<ConfirmDialog>`s (import from `@/components/shared`, already used by ProjectRow at `:6`) using the SAME keys as `ProjectsBrowser.tsx:312-335`: archive → `projects.archiveDialog.title/description/confirm`; delete → `projects.deleteDialog.title/description/confirm` with `variant="destructive"`. Pass `loading={actionPending}`.
10. Add ONE new optional prop to `Props` (`:10-23`): `/** Called after a successful DELETE — the project no longer exists, so the host must leave this view. Threaded as a callback (not a router import) per the DOCK-7 rule this file already follows at :15-20. */ onProjectDeleted?: () => void;` — do NOT import react-router here.

**(C) The two hosts.**
11. `ProjectDetailShell.tsx:148-154` — pass `onProjectDeleted={() => navigate('/knowledge')}`.
12. `ProjectDetailShell.tsx:84` — change `useProjects(false)` to `useProjects(true)`. **This is required, not optional polish:** the shell resolves its project from a list that EXCLUDES archived rows, so archiving in-place would make the project instantly vanish from its own detail route into the `shell.notFound` empty state (`OverviewSection.tsx:45-54`) and would make the Restore button permanently unreachable in the shell. With `true`, archive flips the row to the archived badge + Restore button in place, and deep-linking an archived project shows it instead of lying "not found".
13. `KgOverviewPanel.tsx:39-50` — pass NOTHING new. Omitting `onProjectDeleted` is correct: after delete, the mutation's `['knowledge-projects']` invalidation makes `useBookKnowledgeProject` refetch → `projectId` goes null → the panel's existing `KgNoProjectState` branch (`:29-35`) renders. Verify this by effect in the test below.

**(D) Tests (the anti-regression teeth — `checklist-is-self-report-enforce-by-tests`).**
14. NEW `frontend/src/features/knowledge/components/__tests__/ProjectRow.optionalActions.test.tsx` (none exists today). Mock `react-i18next` so `t` returns the key (same 3-line mock as `OverviewSection.backlinks.test.tsx:4-6`), mock `@/auth` (`useAuth: () => ({ accessToken: 't' })`), `../hooks/useProjectState` (return `{ state: { kind: 'empty' }, actions: {} }` + the real `PROJECT_ACTION_KEYS` shape), and wrap in a `QueryClientProvider`. Assert, with a non-archived project and NO `onArchive`/`onDelete` passed: `expect(screen.queryByTitle('projects.card.delete')).toBeNull()` and `expect(screen.queryByTitle('projects.card.archive')).toBeNull()`; then with an archived project and no `onRestore`: `expect(screen.queryByTitle('projects.card.restore')).toBeNull()`. Add the positive counterpart: when each handler IS passed, the button renders AND clicking it calls the handler with the project.
15. EXTEND `frontend/src/features/knowledge/components/shell/__tests__/OverviewSection.backlinks.test.tsx` — its `ProjectRow` stub (`:10-14`) currently only exposes an edit trigger. Add `stub-row-archive` / `stub-row-restore` / `stub-row-delete` buttons to the stub, extend the `useProjects` mock (`:24-26`) to also return `archiveProject`/`deleteProject` spies, and assert: clicking archive opens the confirm dialog and confirming calls `archiveProject('p1')`; clicking delete + confirming calls `deleteProject('p1')` AND then calls the `onProjectDeleted` spy. This is the test that would have caught the `noop`.

RATIONALE FOR THE OPTIONAL-PROPS RULE (why (A) is the part that matters): today a required prop can be satisfied by a lie (`noop`) and the button still renders. After (A), "no handler ⇒ no button" is enforced by the type + the render, so the next caller physically cannot re-create a dead button by passing a no-op — it has to omit the prop, and the button disappears. This is `silent-success-is-a-bug` closed at the structural level, not the discipline level.

DEFAULT I AM PICKING (veto-able): archive/restore stay IN PLACE in the detail shell (no navigate-away), delete navigates to `/knowledge`. That's the least surprising mapping of "archive is reversible, delete is not".

*Evidence:* frontend/src/features/knowledge/components/shell/OverviewSection.tsx:56 (`const noop = () => {};`) passed at :67-69 → frontend/src/features/knowledge/components/ProjectRow.tsx:29-31 (required props) rendered unconditionally at :292-315. Fix ingredients already present: OverviewSection.tsx:42 already mounts `useProjects(false)`; frontend/src/features/knowledge/hooks/useProjects.ts:144-147 already exports `archiveProject`/`deleteProject`/`updateProject` (invalidating `['knowledge-projects']` at :93-94); frontend/src/features/knowledge/components/ProjectsBrowser.tsx:128-170 + :312-335 is the handler+ConfirmDialog+toast pattern to mirror, using i18n keys that already exist in en/knowledge.json:642-657. The archive trap: frontend/src/pages/ProjectDetailShell.tsx:84 resolves the project with `useProjects(false)` (includeArchived=false). Only 2 ProjectRow call sites: ProjectsBrowser.tsx:274 and OverviewSection.tsx:64.

### Q-38-UPDATE-SEMANTICS-REJECT-DELETE-RECREATE
UPHOLD the spec: delete+recreate stays REJECTED; build real PATCH routes (BE-15d/h/k). All four of §3.3.1's reasons are TRUE against HEAD — I verified each. The concern is a confirmation, not an open design question, so here is the builder-ready instruction (M8b.1):

(1) MIGRATION (book-service `internal/migrate/migrate.go`, append to the forward-only DDL after the map block at :399-434):
  `ALTER TABLE world_maps ADD COLUMN IF NOT EXISTS version INT NOT NULL DEFAULT 1;`
  `ALTER TABLE map_markers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();`
  `ALTER TABLE map_regions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();`
  (`world_maps.updated_at` already exists — migrate.go:409. Children have `created_at` only.)

(2) PARTIAL-PATCH BODY DECODE (BE-15h/k) — COPY the pattern already in `services/book-service/internal/api/worlds.go:270-293` (`patchWorld`): decode into `map[string]any`, build `setClauses` by KEY PRESENCE. That gives absent-vs-explicit-null for free: an absent key never enters `setClauses` (= unchanged); a JSON `null` decodes to a present key with a nil value (= clear `entity_id`/`marker_type`). Do NOT decode into a struct of pointers-of-pointers — the existing map[string]any idiom in this file is the house pattern and already ships.

(3) SCOPE GATE (the tenancy-critical bit) — express it in SQL exactly as the existing delete does at `services/book-service/internal/api/mcp_maps.go:429-432`:
  `UPDATE map_markers m SET <set…>, updated_at=now() FROM world_maps wm WHERE m.id=$1 AND m.map_id=$2 AND m.map_id=wm.id AND wm.owner_user_id=$3` → `RowsAffected()==0` ⇒ uniform 404 ("marker not found"). A marker id from ANOTHER map addressed under YOUR map id must 404, not patch. Same shape for regions. This is `gate-must-derive-scope-from-the-loaded-row` — never trust a bare `marker_id`.

(4) OCC on map rename (BE-15d) — ⚠ book-service has NO If-Match precedent anywhere (grep: only a comment in `chapter_reorder.go:16` saying no version column is needed there); the 428/412 contract you are mirroring lives in Python (`knowledge-service … entities.py:1035`). Write it fresh in Go: read `If-Match` (strip weak `W/` + quotes, parse int) → missing/unparseable ⇒ **428**; then `UPDATE world_maps SET name=$3, version=version+1, updated_at=now() WHERE id=$1 AND owner_user_id=$2 AND version=$4`; on `RowsAffected()==0` re-SELECT the owner-scoped row to disambiguate: not found ⇒ **404**, found ⇒ **412 with the current map as the body** (the FE resets its baseline from that body — never re-GET, never blind-retry). Markers/regions get NO version and NO If-Match — positional writes are LWW by design (§3.3.1), FE serializes per object id.

(5) ROUTING — mount the map routes on the EXISTING `/v1/worlds` chi subrouter in `services/book-service/internal/api/server.go:381-391`. Register `r.Route("/maps", …)` BEFORE `r.Route("/{world_id}", …)`; add a Go test asserting `GET /v1/worlds/maps/{uuid}` hits the map handler and NOT `getWorld` (a `{world_id}` param would swallow the literal `maps` if precedence ever regresses). **No gateway change is required** — `services/api-gateway-bff/src/gateway-setup.ts:90` already proxies by prefix `pathname.startsWith('/v1/worlds')`, so all 12 new routes are reachable through :3123 the moment they mount.

(6) ORDERING — keep `ORDER BY created_at` (mcp_maps.go:280, 303) and add `, id` as a stable tie-break (ids are uuidv7, monotonic). Because PATCH never touches `created_at`, a drag now preserves render order — which is exactly reason (4) being fixed. Do NOT switch the sort to `updated_at`; that would re-introduce the jump-to-end bug through the back door.

(7) `updated_at` MUST BE READ or it ships write-only (CLAUDE.md's stored-but-unread ban): BE-15c returns it per marker/region; the `world-map` inspector renders "edited 4m ago"; a Go test asserts the timestamp ADVANCES across a PATCH.

(8) AGENT PARITY (BE-15m, same slice): `world_map_update` / `world_map_update_marker` / `world_map_update_region` as Tier-A MCP tools in `mcp_maps.go`, registered in `registerMapTools` (:462), sharing the SQL above. Without them 8b creates a NEW inverse gap (human can move a pin, agent cannot) — GG-2.

DEFAULT I AM PICKING (veto-able): keep If-Match on the map RENAME only, even though it is the first OCC in this Go service. Rationale: a rename is human-paced and conflict-worthy, and the cost is ~20 lines; dropping it to LWW would be cheaper to build but silently loses a cross-device rename, which is the one map write a user would notice losing.

*Evidence:* All four rejection reasons confirmed at HEAD 9262ed53e: (1) UPDATE exists at NO layer — the ONLY UPDATE statement touching any map table repo-wide is `services/book-service/internal/api/maps_image.go:108` (`UPDATE world_maps SET image_object_key…`); zero UPDATEs against `map_markers` / `map_regions`; the tool set registered at `services/book-service/internal/api/mcp_maps.go:462-514` is add/remove-only (create, add_marker, add_region, get, list, delete, remove_marker, remove_region — no update). (2) Public REST for maps = ZERO routes: `services/book-service/internal/api/server.go:381-391` mounts `/v1/worlds` with create/list/get/patch/delete + books-membership and NO `/maps`; the only map HTTP route is the internal image upload at `server.go:200`. (3) ORDERING claim VERIFIED: `mcp_maps.go:280` (`SELECT … FROM map_markers WHERE map_id=$1 ORDER BY created_at`) and `mcp_maps.go:303` (same for `map_regions`) — a delete+recreate "move" would jump the pin to the end of render order. (4) Schema confirms no `version` on `world_maps` and `created_at`-only on both children: `services/book-service/internal/migrate/migrate.go:401-434`. Templates to copy: partial-PATCH decode `services/book-service/internal/api/worlds.go:270-293`; owner-scoped child gate `services/book-service/internal/api/mcp_maps.go:429-432`. Gateway needs no change: `services/api-gateway-bff/src/gateway-setup.ts:90` proxies `/v1/worlds*` by prefix.

### Q-38-STUDIOLINKS-NOT-ONE-LINE
The concern is CORRECT and its prescribed fix is CORRECT — build it exactly as §3.2 says, but in FOUR files, not three (the spec missed a second call site). This is not a design question; it is a fully-specified work item. Builder instruction (M8b.2):

(1) `frontend/src/features/studio/host/studioLinks.ts`
  - `StudioLinkContext` (`:19-24`) gains `worldId?: string` with a doc-comment: "The book's world (book row `world_id`). Optional: the resolver is pure/sync and cannot look it up — a caller that doesn't know it degrades to `external`."
  - Add `const WORLD_RE = /^\/worlds\/([^/]+)(?:\/|$)/;` next to `AGENT_MODE_RUN_RE` (`:43`).
  - In `resolveStudioLink`, add the branch AFTER the `agentRun` block (`:105`) and BEFORE `PATH_PANELS` (`:107`):
      const world = WORLD_RE.exec(path);
      if (world) {
        const [, worldId] = world;
        if (ctx.worldId && worldId === ctx.worldId) return openPanel('world');
        return { kind: 'external', url: link };   // a different world, or ctx.worldId absent → today's behaviour
      }
    Note `ctx.worldId` absent falls to `external` by the SAME return — no separate branch needed, and `/worlds` (bare, no id) does not match WORLD_RE so it keeps falling through to `external` (correct: the worlds *browser* has no panel).
  - Do NOT touch the `:51-57` comment block; it is reasoning about `/knowledge/projects/:id`, not a rule to mirror.

(2) `frontend/src/features/studio/panels/KgOverviewPanel.tsx` — line **47-49** (the spec's `:44` is stale): change `followStudioLink(\`/worlds/${worldId}\`, host, { bookId: host.bookId })` → `followStudioLink(\`/worlds/${worldId}\`, host, { bookId: host.bookId, worldId })`. Justified: the id comes from `useProjectBacklinks.ts:21` = `bookQuery.data?.world_id`, i.e. the book row — it IS this book's world.

(3) **[SPEC GAP — the spec's 3-file list is incomplete]** `frontend/src/features/studio/panels/BookSettingsPanel.tsx:52` — identical bug, identical fix: `onOpenWorld={(worldId) => followStudioLink(\`/worlds/${worldId}\`, host, { bookId: host.bookId, worldId })}`. Its `worldId` is also the book's own world (`BookWorldSection.tsx:31,64` ← `SettingsTab` ← `book.world_id`). Without this line, the Book-Settings "World" chip STILL pops a browser tab out of the studio after M8b.2 ships — the exact papercut the slice claims to close. Update spec 38 §3.2 / checklist row 7b to name both call sites.

(4) `frontend/src/features/studio/host/__tests__/studioLinks.test.ts` — three new `it()` cases in the existing `describe('resolveStudioLink')` (mirror the style of the `agent-mode` cases at `:117-128`):
  - `/worlds/W1` with `ctx = {bookId:'B1', worldId:'W1'}` ⇒ `kind:'studio'`, effect calls `host.openPanel('world', …)`;
  - `/worlds/W2` with `ctx = {bookId:'B1', worldId:'W1'}` ⇒ `kind:'external'`, url `/worlds/W2`;
  - `/worlds/W1` with `ctx = {bookId:'B1'}` (worldId ABSENT) ⇒ `kind:'external'` — the degrade path.
  Optionally a 4th: bare `/worlds` ⇒ `external` (worlds browser has no panel).

Prerequisite ordering: the `world` panel id must be registered in `frontend/src/features/studio/panels/catalog.ts` (+ the enum/contract triple — "enum 58 == contract 58 == openable 58" per spec §M8b.2) in the SAME slice, or `openPanel('world')` is a silent no-op (Frontend-Tool-Contract: a resolver must never silently no-op). Default I am picking (veto-able): the `external` fallback is retained forever rather than blocked — `/worlds/:worldId` remains a real route (`App.tsx:191`), so a foreign world opening in a new tab is a correct, safe degrade, not a bug.

*Evidence:* frontend/src/features/studio/host/studioLinks.ts:19-24 (ctx = {bookId, titleFor?}; pure sync fn, :69-114, unmapped → external at :113) · frontend/src/features/knowledge/hooks/useProjectBacklinks.ts:21 (`const worldId = bookQuery.data?.world_id ?? null` — the book row, so the id IS this book's world) · frontend/src/features/studio/panels/KgOverviewPanel.tsx:47-49 (spec's ":44" is stale) · frontend/src/features/studio/panels/BookSettingsPanel.tsx:52 (SECOND call site the spec's 3-file list omits; its worldId provenance: BookWorldSection.tsx:31,64 ← SettingsTab ← book.world_id) · frontend/src/App.tsx:190-191 (/worlds/:worldId is a real route ⇒ external fallback is safe) · catalog.ts has no 'world' panel yet (M8b.2 registers it) · studioLinks.ts:43 AGENT_MODE_RUN_RE is the same-book-rule precedent to copy; :51-57 is a comment, NOT a rule (spec §3.2 warning confirmed).

### Q-38-PANEL-COUNT-DELTA-NOT-LITERAL
The machine guard is ALREADY delta-safe — do NOT add a count assertion to it. Two concrete actions:

(1) TEST — `frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts`: **CHANGE NOTHING about its assertion shape.** It contains zero count literals today. It asserts three-way SET equality: L23 enum non-empty; L28 every advertised id ∈ `STUDIO_PANEL_COMPONENTS` (buildable); L34 `sorted(enumIds) === sorted(OPENABLE_STUDIO_PANELS.map(p=>p.id))`; L42 every openable panel has a `category`. Set equality is strictly STRONGER than `N_before + 2`: it catches a swap (one panel added + one removed) that any count check waves through, and it is inherently baseline-free. Adding `expect(enumIds.length).toBe(59)` — or any `N_before + 2` arithmetic — would INTRODUCE the phantom-regression trap this concern warns about. Explicit builder instruction: when M8b.2/M8b.3 register `world` and `world-map`, add them to `STUDIO_PANELS` in `frontend/src/features/studio/panels/catalog.tsx` (with `category` ∈ CATEGORY_ORDER + `guideBodyKey`), add the two ids to the `panel_id` enum in `services/chat-service/app/services/frontend_tools.py:402`, regenerate the contract with `WRITE_FRONTEND_CONTRACT=1 pytest services/chat-service/tests/test_frontend_tools_contract.py`, and commit `catalog.tsx` + `frontend_tools.py` + `contracts/frontend-tools.contract.json` in ONE commit. The existing test then passes with no edit at any wave-ordering. Note `OPENABLE_STUDIO_PANELS` is DERIVED (`catalog.tsx:279` = `STUDIO_PANELS.filter(p => !p.hiddenFromPalette)`), so the openable set cannot drift by hand — the only real drift surface is py-enum ↔ contract ↔ catalog, and all three are covered.

(2) SPEC — fix the self-contradiction in `docs/specs/2026-07-01-writing-studio/38_kg_and_world.md`. Line 430 (M8b.2 milestone row) still carries the literal `enum 58 == contract 58 == openable 58`. Replace that DoD cell with: "contract tests green — `panelCatalogContract.test.ts` set-equality holds (enum == openable == buildable); this milestone moves all three by +1 in lockstep". Lines 326 and 438 already state the delta rule correctly, so line 430 is the only offender. Do NOT restate 57/58/59 anywhere: at Wave 8 the true baseline is 69 (Waves 1-6 land 12 panels; Wave 7/spec 37 adds none) and the end state is 71 — but the builder never needs those numbers, because no assertion consumes a count.

Sane default flagged for PO veto: the guard stays count-free permanently. If a future reviewer wants a cardinality tripwire, the correct one is a snapshot of the sorted id LIST (not a number) — but that is unnecessary given set equality already holds.

*Evidence:* frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts:34 — `expect([...(enumIds ?? [])].sort()).toEqual(openable);` (three-way set equality, no count literal anywhere in the file); frontend/src/features/studio/panels/catalog.tsx:279 — `export const OPENABLE_STUDIO_PANELS = STUDIO_PANELS.filter((p) => !p.hiddenFromPalette);` (openable is derived, not hand-maintained); verified live: py enum (services/chat-service/app/services/frontend_tools.py:402) = 57, contract enum (contracts/frontend-tools.contract.json → /ui_open_studio_panel/args/panel_id) = 57, sets identical. The literal trap: docs/specs/2026-07-01-writing-studio/38_kg_and_world.md:430 ("enum 58 == contract 58 == openable 58"), contradicted by its own lines 326 and 438 which say "assert the delta, never a literal".

### Q-38-BARE-OPEN-NOT-ALWAYS-REAL
The concern is CORRECT and the fix is fully buildable — but it is FIVE states, not four, and the split is not the one the spec wrote. Build it as ONE gate hook + ONE shared states module imported by BOTH panels (forking is then physically impossible), and resolve `mapId` against the rail list, never by a by-id GET.

**1 · NEW `frontend/src/features/studio/panels/useBookWorld.ts`** (mirror `useQualityWork.ts`). Reads the book row's `world_id` (same source `BookWorldSection`/`useProjectBacklinks` use), then `useWorld(worldId)`. Returns a discriminated union — and it MUST inspect the HTTP status, not `isError`:
```ts
type BookWorldState =
  | { kind: 'loading' }
  | { kind: 'no-world' }     // book.world_id == null
  | { kind: 'no-access' }    // world_id set, GET /v1/worlds/{id} → 404 (foreign OR deleted — worlds.go:167 gives NO oracle; collapse them, that is correct, not a shortcut)
  | { kind: 'unavailable' }  // any non-404 error / 503 — THE STATE §3.3's TABLE IS MISSING
  | { kind: 'ready'; worldId: string; world: World };
```
Collapsing 500 into `no-access` ("you don't have access") when we simply could not look is the exact wrong-answer-dressed-as-a-nudge that `QualityNoWorkState.tsx:1-11` was written to kill. §3.2's table has the error row; §3.3's does not — add it.

**2 · NEW `frontend/src/features/studio/panels/WorldPanelStates.tsx`** (one file, four exported components, imported by BOTH `WorldPanel.tsx` and `WorldMapPanel.tsx`):
- `<WorldNotLinkedState bookId onChanged/>` — `<EmptyState icon={Globe2} title="Link this book to a world">` whose `action` is the EXISTING `<WorldPicker>` + `useBookWorldLink().link` (lift the body of `BookWorldSection.tsx:31-73` into this component and have `BookWorldSection` render it — one link control in the repo, zero forks). testid `world-not-linked`.
- `<WorldNoAccessState/>` — uniform card: "This book belongs to a world you don't have access to." **No world name, no id, no retry** — printing either re-creates the existence oracle `worlds.go:157` deliberately refuses. testid `world-no-access`.
- `<WorldUnavailableState onRetry/>` — error card + Retry. testid `world-unavailable`.
- `<WorldNoMapsState onCreate/>` — `<EmptyState>` + `autoFocus` primary `+ New map`. testid `world-no-maps`.

**3 · `WorldMapPanel.tsx` branches BEFORE the rail/canvas layout mounts** on `useBookWorld(host.bookId)`: loading→skeleton · no-world→`<WorldNotLinkedState/>` · no-access→`<WorldNoAccessState/>` · unavailable→`<WorldUnavailableState/>` · ready+`maps.length===0`→`<WorldNoMapsState/>` · else rail+canvas. `WorldPanel.tsx` branches on the same first four. Never render an empty rail.

**4 · `params.mapId` is a HINT, never a truth (resolution d):**
```ts
const requested = params.mapId ?? null;
const found = requested ? maps.find(m => m.map_id === requested) : null;   // resolve against the ALREADY-FETCHED rail list
const selectedId = found?.map_id ?? maps[0]?.map_id ?? null;
const staleParam = !!requested && !found;
```
Do NOT implement this as `GET /v1/worlds/maps/{mapId}` + catch-404: a map you own **in another world** would 200 and get painted as this book's map — a different, worse silent lie. `staleParam` ⇒ render a dismissible banner above the canvas ("That map is gone — showing {name} instead.", testid `world-map-stale-param`) AND clear `mapId` from the panel params so a re-open doesn't re-raise it. If `staleParam && maps.length===0` render `<WorldNoMapsState/>` **and** the banner (both).

**5 · `ui_open_studio_panel` keeps returning `{opened:true}` — do NOT change `studioUiNav.ts:38`.** It is pure/sync by design (`studioUiNav.ts:5-7`) and cannot know the panel's async data state; `opened:true` is honest — the panel DID open and renders a real, readable state. The silent-success class is a *blank* panel behind `shown:true`, and states 1-4 are exactly what kills it. **Default noted for PO veto:** I am deliberately NOT adding an async panel→agent state echo (it needs a new host callback and buys the agent nothing the next user turn can't say).

**6 · Tests (DoD, literal steps — an item is done only when a test asserts its effect):**
- `useBookWorld.test.tsx`: 404 ⇒ `no-access`; **500 ⇒ `unavailable`, NOT `no-access`** (the case a builder will otherwise collapse).
- `WorldMapPanel.states.test.tsx`: one case per state; each asserts the testid is present **and `container.textContent.trim()` is non-empty** (a testid on an empty div passes a naive query — this is the anti-blank assertion). Plus one case asserting `WorldPanel` and `WorldMapPanel` render the SAME `world-not-linked` testid (the anti-fork assertion).
- E2E `studio-world-map.spec.ts`: DoD #4's bare-open leg (no-world book ⇒ `world-not-linked` visible) **plus a second leg for (d)**: open with a deleted map's `mapId` ⇒ `world-map-stale-param` visible and the canvas shows the rail's first map, not the requested one.

**7 · Spec edit in the same commit:** `38_kg_and_world.md:205` says "Three resolutions" above a four-row table — make it "Five", and add the `unavailable`/error row to §3.3's table so it matches §3.2's.

*Evidence:* services/book-service/internal/api/worlds.go:157-170 (`getWorldByID` keys on `WHERE w.id=$1 AND w.owner_user_id=$2` → pgx.ErrNoRows → 404 "WORLD_NOT_FOUND"; its own comment: "a non-owner gets pgx.ErrNoRows → 404 (no existence oracle)") — so FOREIGN and DELETED are indistinguishable to the FE, and the only FE-observable split is `book.world_id == null` vs `world_id set but GET 404`. Precedent to copy verbatim: frontend/src/features/studio/panels/QualityNoWorkState.tsx:1-11 (+ useQualityWork.ts) — a shared states module + a gate hook whose whole point is telling "empty" from "we could not look". Reuse targets: frontend/src/components/shared/EmptyState.tsx:20 · frontend/src/features/world/components/BookWorldSection.tsx:31-73 + hooks/useBookWorldLink.ts:9 (the existing WorldPicker+link control) · frontend/src/features/studio/agent/studioUiNav.ts:38 (`return { result: { opened: true }, effect: (host) => host.openPanel(panelId) }`).

### Q-38-FOREIGN-WORLD-NO-COLLABORATORS
CONFIRMED AS-SPEC'D — do NOT widen the world routes. Backend change: ZERO. The FE already has every signal it needs; build the state, don't build a route.

WHY IT'S ALREADY DECIDABLE FROM CODE (all three legs verified):
1. Worlds are owner-only by construction: `getWorldByID` is `WHERE w.id=$1 AND w.owner_user_id=$2` → uniform `404 WORLD_NOT_FOUND` (`services/book-service/internal/api/worlds.go:157-176`). Every `/v1/worlds/*` route (`server.go:377-391`) is owner-scoped. The server already gives NO oracle (missing and foreign are byte-identical 404s), so "no oracle" is a property the BE hands us for free — the FE must not re-introduce one.
2. A book COLLABORATOR CAN still read the world id: `GET /v1/books/{id}` is gated at `GrantView` via `authBook` (`server.go:931`) and its SELECT includes `b.world_id` (`server.go:955`). `useProjectBacklinks.ts:21` already reads `bookQuery.data?.world_id`. ⇒ the FE can distinguish "no world" from "a world I can't see" WITHOUT any oracle from the server: `book.world_id == null` ⇒ *not in a world*; `book.world_id != null` **AND** `GET /v1/worlds/{world_id}` → 404 ⇒ the uniform no-access card. (Bonus: `books.world_id` is `ON DELETE SET NULL` — `worlds.go:306` — so a *deleted* world nulls the column; the world_id-set + 404 case really is only "foreign", but the copy stays neutral anyway.)
3. The thrown error carries `.status` (`frontend/src/api.ts:158-162`: `throw Object.assign(new Error(...), { status: res.status, code, body })`), so a 404 is discriminable in the hook.

BUILDER INSTRUCTION (M8b.2 + M8b.3, exact):
A. NEW hook `frontend/src/features/world/hooks/useBookWorld.ts` — the single resolver both panels use (no fork, DOCK-2). Signature: `useBookWorld(bookId: string)` → `{ status: 'loading' | 'none' | 'no-access' | 'ready' | 'error', world: World | null, worldId: string | null, refetch }`.
   - read the book (existing books query) → `worldId = book.world_id ?? null`;
   - world query: `useQuery({ queryKey: ['book-world', worldId], queryFn: () => worldsApi.getWorld(token, worldId!), enabled: !!token && !!worldId, retry: (n, e) => (e as {status?:number}).status !== 404 && n < 1, refetchOnWindowFocus: false })`. The `retry` override is MANDATORY and is the whole "must NOT loop on 404s" clause: the global default is `retry: 1` + `refetchOnWindowFocus: true` (`frontend/src/App.tsx:9-12`), which today would re-fire a doomed 404 on every tab focus. `useWorld.ts:13-17` has NO override — do not reuse it for this path.
   - map result: `worldId == null` ⇒ `'none'`; 404 ⇒ `'no-access'`; other error ⇒ `'error'`; data ⇒ `'ready'`.
B. Gate EVERY downstream world query on `status === 'ready'` (`enabled: status === 'ready'`) — the maps rail (`GET /v1/worlds/{id}/maps`, BE-15b), world books, world lore. A foreign world must fire exactly ONE 404 for the whole panel, not one per section. This is the 404-fan-out that would otherwise read as a loop.
C. NEW shared view `frontend/src/features/world/components/WorldNoAccessCard.tsx` — renders i18n key `world.no_access` = "This book belongs to a world you don't have access to." Nothing else: no world name, no owner, no "request access", no retry button (retrying a permanent 404 IS the loop), no "create/link a world here" CTA (the book is already in a world — offering to link it would 409/confuse). Add a single muted secondary line only: "Ask the world's owner to add you." — no identity is disclosed.
D. Mount it in BOTH panels, identically (spec §3.2 state table + §3.3 bare-open table):
   - `world` panel (M8b.2): `status==='no-access'` ⇒ render `<WorldNoAccessCard/>` INSTEAD of the identity card / member books / maps sections. `status==='none'` ⇒ the existing "Link this book to a world" empty state (link is fine there — `listWorlds` is owner-scoped so the picker only ever offers worlds the user owns, and `moveBookIntoWorld` requires world ownership + book EDIT: `worlds.go:370-374`).
   - `world-map` panel (M8b.3): resolve via the SAME `useBookWorld`; `status==='no-access'` ⇒ the SAME `<WorldNoAccessCard/>`, and the maps rail / canvas / inspector / `+ New map` are NOT rendered at all (no write affordance may exist in this state). Do not fork a second copy of the card or the copy string.
E. Tests (the state is only DONE when a test asserts its effect — repo law `checklist-is-self-report-enforce-by-tests`):
   - `frontend/src/features/world/hooks/__tests__/useBookWorld.test.tsx`: (i) book with `world_id` + world GET mocked 404 ⇒ `status==='no-access'` AND the world queryFn was called **exactly once** (proves `retry:false` on 404); (ii) `world_id: null` ⇒ `'none'`; (iii) 500 ⇒ `'error'` (retries once, per default).
   - a panel test for each of `world` and `world-map` asserting the 404 path renders `world.no_access` and that the maps queryFn was **never called** (proves B).
DEFAULT I AM PICKING (veto-able): the no-access card shows NO retry affordance and NO owner identity. Rationale: a 404 here is permanent for this user, and naming the owner would leak cross-tenant identity — the exact thing the uniform 404 protects.

*Evidence:* services/book-service/internal/api/worlds.go:157-176 (`getWorldByID`: `WHERE w.id=$1 AND w.owner_user_id=$2` → uniform 404 WORLD_NOT_FOUND, no oracle) · services/book-service/internal/api/server.go:377-391 (all `/v1/worlds` routes owner-scoped; the "no collaborators on worlds" comment) · services/book-service/internal/api/server.go:931 + :955 (book GET is `authBook(..., GrantView)` and its SELECT carries `b.world_id` ⇒ a collaborator CAN read the world id) · frontend/src/features/knowledge/hooks/useProjectBacklinks.ts:21 (`worldId = bookQuery.data?.world_id ?? null` — the signal is already consumed today) · frontend/src/api.ts:158-162 (thrown error carries `.status`) · frontend/src/App.tsx:9-12 (global `retry: 1` + `refetchOnWindowFocus: true` — the default that MUST be overridden to satisfy "no 404 loop") · frontend/src/features/world/hooks/useWorld.ts:13-17 (today's world query has no retry override — do not reuse it for the studio path) · docs/specs/2026-07-01-writing-studio/38_kg_and_world.md:187, :210, :407

### Q-38-WORLD-PANEL-SELF-RESOLVING
ADOPT the self-resolving `world` panel. It is correct, it is buildable today, and plan 30 §8.2 already registers it (row 13, line 558: category `storyBible`, "self-resolving from the book's `world_id` ⇒ bare-id openable"; check 5, lines 576-579: "ZERO panels need hiddenFromPalette"). Build it exactly as follows.

1) NEW HOOK — `frontend/src/features/world/hooks/useBookWorld.ts`. Mirror `useBookKnowledgeProject.ts:20` 1:1: `useBookWorld(bookId) -> { worldId, isLoading }`, one `booksApi.getBook` query, `worldId = book?.world_id ?? null`. Do NOT reuse/rename `useBookWorldLink` — it is the link/unlink MUTATION hook (`useBookWorldLink.ts:9-25`) and never reads `world_id`. (The spec's line "useProjectBacklinks/useBookWorldLink both rely on it" is half wrong; only `useProjectBacklinks.ts:21` does. Correct that sentence in spec 38 §3.2 when you touch it.)

2) NEW PANEL — `frontend/src/features/studio/panels/WorldPanel.tsx`. Root `data-testid="studio-world-panel"`; `useStudioPanel('world', props.api)`. Resolve: `const override = (props.params as {worldId?: string})?.worldId; const { worldId: bookWorld, isLoading } = useBookWorld(host.bookId); const worldId = override ?? bookWorld;`
   - `params.worldId` is OPTIONAL, never required — precedent `KgEntitiesPanel.tsx:12-19` (optional `scopedProjectId`, palette-visible). Optional != required, so the panel still enters the enum/palette.
   - NULL-WORLD EMPTY STATE (the case the spec never states): a book may have no world (`world_id` is nullable). When `!worldId`, render `BookWorldSection` (`features/world/components/BookWorldSection.tsx:31`) with `bookId={host.bookId} worldId={null} onChanged={refetch}` — the WorldPicker IS the attach control. Mirrors `KgOverviewPanel.tsx:29-34`'s `KgNoProjectState`. NEVER render a blank panel.
   - BODY: compose the SECTIONS; do NOT wrap `WorldWorkspacePage` (it calls `useParams` + `<Link>` — DOCK-7 ban). Mount `WorldLorePanel`, `WorldPopulateActions`, `LivingWorldTree`, `WorldGraphSection`, `WorldTimelineSection`.

3) 🔴 DOCK-7 FIX THE SPEC MISSED (do this first or the panel ships a router crash/route-hop): `LivingWorldTree.tsx:16,28` and `WorldPopulateActions.tsx:3,24` both `import { useNavigate } from 'react-router-dom'`. Hoist navigation to an INJECTED CALLBACK prop (`onOpenWork(bookId)` / `onCreated(bookId)`) exactly as `BookWorldSection` already did — its Props doc at `BookWorldSection.tsx:18-28` spells out this precedent verbatim. `WorldWorkspacePage` passes a `useNavigate()` handler; `WorldPanel` passes a `followStudioLink`/`host.openPanel` handler. No fork, no `useOptionalStudioHost()` branching inside the component.

4) CATALOG — `catalog.ts`, one row in the storyBible block (after `wiki`, ~line 139): `{ id: 'world', component: WorldPanel, titleKey: 'panels.world.title', descKey: 'panels.world.desc', category: 'storyBible', guideBodyKey: 'panels.world.guideBody' }`. NO `hiddenFromPalette`. NO new category — `CATEGORY_ORDER` (`useStudioCommands.ts:20-22`) stays at its 9 members. The spec's warning is CONFIRMED LIVE: `'quality'` is in `StudioPanelCategory` (`catalog.ts:86`) but NOT in `CATEGORY_ORDER:21`, so the 5 quality panels sort to the TOP today via `indexOf -> -1` (`useStudioCommands.ts:55-56`). Do not add a 10th member for `world`; reuse `storyBible`.

5) i18n — `en/studio.json`: `panels.world.title` / `.desc` / `.guideBody`; then 17 locales via `python scripts/i18n_translate.py` (never hand-write).

6) BE ENUM — `services/chat-service/app/services/frontend_tools.py`: append `"world"` to the `panel_id` enum (line 402) AND a description clause in the prose block (~403-481): "'world' = the world THIS BOOK belongs to (lore, living-world tree, world graph + timeline); takes no argument."

7) CONTRACT — regenerate, never hand-edit: `cd services/chat-service && WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py`; commit `contracts/frontend-tools.contract.json` in the SAME commit as 4 + 6.

8) DEEP LINK — `studioLinks.ts`: add a `WORLDS_PAGE_RE = /^\/worlds\/([^/]+)/` resolving to panel `world` with `params: { worldId }` (explicit id, not bare). This kills the external-tab pop at `KgOverviewPanel.tsx:44` and sidesteps the "arbitrary :id silently shows the wrong project" hazard called out at `studioLinks.ts:54-58`. Leave bare `/worlds` OUT of `PATH_PANELS` — `WorldsPage` is the cross-world browser, a different surface from "this book's world".

TESTS (Definition of Done): `panelCatalogContract.test.ts` green in DELTA form (`N_before + 1`, never a literal) across openable == py enum == contract enum, plus category present; and a new `WorldPanel.test.tsx` asserting (a) book with `world_id` -> sections render for that world, (b) `world_id === null` -> the BookWorldSection attach state renders, NOT a blank panel, (c) `params.worldId` overrides the book's world.

DEFAULT NOTED FOR PO VETO: I gave `world` an OPTIONAL `params.worldId` override rather than making it strictly book-derived. Rationale: it makes the `/worlds/:worldId` deep link exact instead of approximate, and it is the same shape plan 30 row 14 already grants `world-map` ("takes params.mapId but still self-resolves a default"). If the PO wants strict book-derivation only, drop the override and map `/worlds/:worldId` to external — nothing else in the plan changes.

*Evidence:* frontend/src/features/books/api.ts:21 (`world_id?: string | null` on the book read) + frontend/src/features/knowledge/hooks/useProjectBacklinks.ts:21 (`const worldId = bookQuery.data?.world_id ?? null`) — self-resolution needs no param, proving the `hiddenFromPalette` premise false. Precedent for the resolver shape: frontend/src/features/knowledge/hooks/useBookKnowledgeProject.ts:20 consumed at frontend/src/features/studio/panels/KgOverviewPanel.tsx:18. Optional-param-yet-palette-visible precedent: frontend/src/features/studio/panels/KgEntitiesPanel.tsx:12-19. Category hazard CONFIRMED: 'quality' present at frontend/src/features/studio/panels/catalog.ts:86 but absent from CATEGORY_ORDER at frontend/src/features/studio/palette/useStudioCommands.ts:20-22, sorted by indexOf at :55-56. Contract triple-lock: frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts:31-34 + services/chat-service/app/services/frontend_tools.py:402. NEW BLOCKER (not in spec 38): frontend/src/features/world/components/LivingWorldTree.tsx:16,28 and frontend/src/features/world/components/WorldPopulateActions.tsx:3,24 import useNavigate — DOCK-7 violation; the injected-callback fix pattern is already documented at frontend/src/features/world/components/BookWorldSection.tsx:18-28. Spec correction: frontend/src/features/world/hooks/useBookWorldLink.ts:9-25 never reads world_id. Plan alignment: docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:558 and :576-579.

### Q-38-OCC-LWW-DELIBERATE-SPLIT
AFFIRM the split exactly as §3.3.1 + §7 state it — it is a decision, not an omission, and the code confirms every premise. Builder instructions:

BE (M8b.1, book-service Go — maps live here, not composition):
1. migrate.go (after the world_maps DDL at :411): `ALTER TABLE world_maps ADD COLUMN IF NOT EXISTS version INT NOT NULL DEFAULT 1;` and `ALTER TABLE map_markers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();` (same for map_regions). Do NOT add `version` to the two child tables — no column = the wrong fix is impossible to write later.
2. BE-15d `PATCH /v1/worlds/maps/{map_id}` (RENAME) = strict If-Match OCC. Parse both `"N"` and `W/"N"` (mirror knowledge-service `entities.py:90-108`). Missing header -> 428. Guard-CTE: `UPDATE world_maps SET name=$1, version=version+1, updated_at=now() WHERE id=$2 AND owner_user_id=$3 AND version=$4 RETURNING *`. 0 rows -> re-SELECT by (id, owner) to distinguish 404 from 412 — the exact Go pattern glossary-service already uses at entity_handler.go:1136-1138. On 412 return the CURRENT map row as the response body + an ETag header (mirrors entities.py:1078-1084) so the FE resets its baseline with no second GET. Rail message on 412: "renamed on another device" + the current name.
3. Marker/region PATCH = NO version, NO If-Match, LAST-WRITE-WINS. Partial: absent key = unchanged; explicit null on entity_id/marker_type = clear. Owner-scope by JOIN to world_maps (reuse the DELETE join at mcp_maps.go:432): `UPDATE map_markers m SET ... FROM world_maps wm WHERE m.map_id=wm.id AND m.id=$1 AND wm.owner_user_id=$2`. A child route that trusts a bare marker_id is a tenancy defect (§7).

FE (M8b.3): copy the single-flight chain from useSceneInspector.ts:44-101, but key it PER OBJECT ID (a map holds many draggable markers, the inspector held one node): `chainsRef = useRef<Map<string, Promise<void>>>()`; `chains.set(id, (chains.get(id) ?? Promise.resolve()).then(run, run))`. The debounced save binds targetId at ENQUEUE time and drops the queued write if that marker is no longer selected/present — never read a `latestRef` at flush time (debounced-write-must-bind-its-target-entity).

Tests (mandatory — without them a later reviewer re-adds OCC): Go — two back-to-back marker PATCHes both land (no 412 reachable); rename 428 without If-Match, 412 + current body on stale, 200 + version+1 on match; a foreign marker_id -> 404. Vitest — two rapid drags of marker A serialize (2nd request begins only after the 1st resolves) and both land; drag A then select B -> the flush targets A and B is never written with A's coords. E2E drives the drag with CDP `page.mouse`, not browser_drag (playwright-cdp-mouse-drives-d3-drag).

Leave §3.3.1's rationale paragraph in the spec verbatim; it is the anti-regression note.

*Evidence:* services/book-service/internal/migrate/migrate.go:401-434 (world_maps has NO version col; map_markers/:414 + map_regions/:426 have created_at only) · services/book-service/internal/api/mcp_maps.go:117/167/220/398/432/453 (INSERT/SELECT/DELETE only — NO UPDATE route exists for any map object today; the sole UPDATE world_maps in the repo is the image upload at maps_image.go:108, so the semantics are being chosen here, not inherited) · frontend/src/features/studio/panels/useSceneInspector.ts:41-44 + :64-101 (the shipped single-flight chain + its comment recording the exact 412-storm this spec is avoiding: "two rapid Cast&Setting edits both sent If-Match v1 -> the 2nd 412'd -> silently dropped + a false 'changed elsewhere'") · services/book-service/internal/api/chapter_reorder.go:16 (repo precedent for the inverse choice: serialization instead of OCC — "That is why no version/If-Match column is needed here") · services/knowledge-service/app/routers/public/entities.py:90-108 (If-Match parse, strong+weak ETag) + :1043-1084 (428 without If-Match, 412 + CURRENT entity as body + refreshed ETag — the contract the map rename must mirror) · services/glossary-service/internal/api/entity_handler.go:1136-1138 (the Go 0-rows -> 404-vs-412 disambiguation to copy)

### Q-38-SCALE-NO-VIRTUALIZATION
AFFIRM the no-virtualization decision, but STRIKE the "above ~500 markers, cull to the viewport" clause from §3.3.3 — it is a second, unbuilt, untested render path with zero profiling evidence (CLAUDE.md defer-gate #4: perf items get fixed when profiling shows pain), and it culls only RENDER while the payload stays unbounded anyway (mcp_maps.go:280 has no LIMIT). Ship ONE render path in M8b.3:

1. MARKERS — one `<MapMarker>` per marker, ALL of them, unconditionally: `React.memo`'d component, `position:absolute; left:${x*100}%; top:${y*100}%` over the image (fractional coords, matching BE-15g's 422 on coords ∉ [0,1]). No culling, no virtualization, no `slice()`.
2. THE THING THAT ACTUALLY MATTERS AT 300 PINS — drag must not re-render the list. Hold the in-flight drag offset in the DRAGGED marker's own local state/ref (CSS `transform: translate(dx,dy)`), NOT in the parent's marker array. The parent array is touched only once, on drag-commit, feeding the serialized+debounced PATCH §3.3.3 already specifies. (Mounting 300 divs is free; re-rendering 300 divs per mousemove is not — that is the only real cliff at expected scale.)
3. REGIONS — exactly as specced: ONE `<svg>` with one `<path>` per region. Unchanged.
4. MAKE THE CLAIM FALSIFIABLE (repo lesson `checklist⇒test the effect`) — a vitest in `frontend/src/features/studio/world/__tests__/WorldMapCanvas.test.tsx` that renders the panel with **500 synthetic markers** and asserts (a) 500 marker nodes are in the DOM (nothing was silently culled), and (b) a simulated drag of ONE marker increments a render-count spy on the memo'd marker by 1, not by 500. That test IS the "no virtualization needed" decision; if it ever reds or goes slow, that is the profiling evidence that earns virtualization — file it then.
5. Record the decision inline at the marker-list render site, mirroring the repo's own precedent (`StudioPaletteShell.tsx:5-6`, `JobLogsPanel.tsx:14-18`): a 2-line comment "Not virtualized: markers are hand-placed, expected ≤ a few hundred; drag is render-isolated per-marker. Escape hatch if ever needed: @tanstack/react-virtual is already a dep (package.json:32) — but it's a LIST virtualizer; spatial culling would be a hand-rolled viewport filter. Don't build it without profiling evidence."

DEFAULT NOTED FOR PO VETO: this ships with NO marker ceiling and NO truncation flag anywhere in the stack. Markers are human-placed one at a time, so the ceiling is self-limiting; adding a server LIMIT would silently hide user-placed markers from the editing surface (this repo's `silent-success-is-a-bug` class) and is the worse trade. Veto only if you expect an agent loop to bulk-mint thousands of pins.

*Evidence:* services/book-service/internal/api/mcp_maps.go:280 — `SELECT id, label, x, y, entity_id, marker_type FROM map_markers WHERE map_id=$1 ORDER BY created_at` (no LIMIT ⇒ viewport culling would not bound the payload, only the DOM). frontend/package.json:32 + frontend/src/features/studio/manuscript/ManuscriptNavigator.tsx:18 (@tanstack/react-virtual already a dep, but list-only — spatial culling is unbuilt work, not a library call). Precedent for the inline "not virtualized, and why" note: frontend/src/features/studio/palette/StudioPaletteShell.tsx:5-6 and frontend/src/features/knowledge/components/JobLogsPanel.tsx:14-18. Spec clause being struck: docs/specs/2026-07-01-writing-studio/38_kg_and_world.md:267.

### Q-38-NO-SETTINGS-NO-COST-GATE
UPHELD as written — the code confirms every claim in §7, so it stands as a binding guard rail for M8a.2 (A3) and M8b.3, with ONE addition the code forced out.

BUILDER INSTRUCTION (three literal rules; a violation of any is a /review-impl finding at the wave's DoD):

1. NO SETTING. Wave 8 adds zero SET-1..8 surface: no toggle, mode, threshold, or model choice; no new env flag; no row in a preferences/settings table; no `/v1/me/preferences` write. Canvas zoom/pan and the selected `map_id` are per-device UI state and live in the dock panel's `params` + component state. They persist for free: panel params are inside `api.toJSON()`, which `frontend/src/features/studio/hooks/useStudioLayout.ts:50` already writes to the per-book localStorage layout blob. So: NO new localStorage key of your own, and NO server preference. (A later "default map per world" would be a per-user setting with a scope key — out of this spec.)

2. NO COST GATE, AND NO INVENTED ROUTE. Every write in this wave is deterministic — verified: entity create = Neo4j `merge_entity` only (entities.py:999-1032, no embedding/provider client on that path); relation create = `recreate_relation` (relations.py:182-218); glossary projection = `project_glossary_entities_to_nodes`, whose docstring literally says "Deterministically project" (anchor_loader.py:194); fact invalidate = a `valid_until` set (facts.py:675); every map write is SQL + MinIO (mcp_maps.go:93-462). Therefore BE-14a/BE-14b and all 12 book-service map routes are PLAIN JWT-authed REST that write on the first call. Do NOT route them through `GET /v1/composition/actions/preview` → `POST /actions/confirm` (that spine is composition's, for LLM spend), do NOT mint a confirm_token, and above all do NOT add a per-action `/estimate` route — `frontend/src/features/composition/motif/api.ts:224` POSTs `/v1/composition/actions/conformance_run/estimate`, which does not exist in `composition-service/app/routers/actions.py` (only `/actions/preview` + `/actions/confirm`) and 404s in production today. Do not copy that pattern.

3. NEW (the code found a hole in §7's own claim): the ONE path in this surface that DOES spend money is `GET /v1/knowledge/entities?semantic_query=…` — the same list route, but that param embeds the query server-side via the project's provider-registry embedding model (entities.py:311-349, wiring at :385). So the A2 relation dialog's subject/object entity pickers (and any A1/A3 typeahead) MUST call the list route with the deterministic `search=` substring filter and MUST NOT pass `semantic_query` — otherwise a per-keystroke picker turns a "no LLM spend" wave into a BYOK embed bill with no cost gate. State this in the A2 slice; add a vitest that asserts the picker's request URL carries `search=` and never `semantic_query=`.

*Evidence:* services/knowledge-service/app/routers/public/entities.py:999-1032 (create = neo4j_session + merge_entity, no provider call) · relations.py:182-218 · services/knowledge-service/app/extraction/anchor_loader.py:194 ("Deterministically project…") · app/db/neo4j_repos/facts.py:675 · services/book-service/internal/api/mcp_maps.go:93-462 (SQL only) · PAID PATH: entities.py:311-349 + :385 (`semantic_query` → embedding_client via provider-registry) · INVENTED-ROUTE PROOF: frontend/src/features/composition/motif/api.ts:224 posts `/actions/conformance_run/estimate` vs services/composition-service/app/routers/actions.py:7-8 which declares only GET /actions/preview + POST /actions/confirm · per-device persistence precedent: frontend/src/features/studio/hooks/useStudioLayout.ts:50

### Q-38-GATEWAY-ZERO-CHANGES-CLAIM
CLAIM CONFIRMED BY CODE — the spec is right: **ZERO gateway changes for all 12 BE-15 routes + BE-15f multipart.** `worldsProxy` is a genuine prefix wildcard (`pathFilter: (pathname) => pathname.startsWith('/v1/worlds')`), not an enumerated route list, and nothing in the dispatch chain shadows it. Builder instruction for M8b.1:

1. **DO NOT touch `services/api-gateway-bff/`.** No new proxy, no new pathFilter, no route registration. A PR for M8b.1 that edits `gateway-setup.ts` is wrong by construction and should be reverted.

2. **Mount every new route INSIDE the existing chi subrouter** `r.Route("/v1/worlds", ...)` at `services/book-service/internal/api/server.go:381`. This is the one condition that keeps "zero gateway changes" true. Concretely, all 12 BE-15 paths must literally begin `/v1/worlds` — i.e. `POST /v1/worlds/{world_id}/maps`, `GET /v1/worlds/maps/{map_id}`, `POST /v1/worlds/maps/{map_id}/image`, `.../markers/...`, `.../regions/...` exactly as spec 38 §4.2's table already writes them. **Never invent a sibling top-level prefix** (`/v1/maps`, `/v1/world-maps`) — that WOULD require a gateway change and is the only way this claim breaks.

3. **BE-15f (multipart image upload) needs no gateway work either.** The gateway runs with `bodyParser: false` (`services/api-gateway-bff/src/main.ts:19`) and mounts `json()` on ONLY `/v1/ai/tools` and `/v1/assistant` (`gateway-setup.ts:402,406`), so `/v1/worlds` request bodies stream raw upstream. **Explicit prohibition: do NOT add `instance.use('/v1/worlds', json())`** — that would parse-and-swallow the multipart body and break BE-15f exactly the way the spec fears. The multipart-through-gateway precedent is `booksApi.uploadChapterMedia` (`frontend/src/features/books/api.ts:587`) riding `bookProxy` (`gateway-setup.ts:75-81`), whose config is byte-identical to `worldsProxy` (same `urls.bookUrl` target, `changeOrigin: true`, `selfHandleResponse: false`).

4. **Mount BE-15f in the PUBLIC `/v1/worlds` subrouter, not `/internal`.** The dead route `POST /internal/worlds/maps/{map_id}/image` (`server.go:200`) sits behind `r.Use(s.requireInternalToken)` (`server.go:185-186`) and is therefore unreachable through the gateway BY DESIGN — the gateway only forwards `/v1/worlds*`, never `/internal*`. Extract the handler body to take a `userID uuid.UUID`, mount the public JWT-scoped version under `/v1/worlds`, and (per OQ-3) delete the internal one after a final `grep -rn "worlds/maps" services/ frontend/src` confirms zero callers.

5. **DoD #1 stays as written but gets teeth:** the M8b.1 curl smoke runs against **:3123** (the host-mapped gateway), not the book-service port, and must hit all 12 routes. Expected proof that the wildcard works: a `401` (no token) or a real `200/201/404` from book-service — **any `404 Cannot POST /v1/worlds/...` shaped like a *Nest* 404 means the route never left the gateway** and is the failure mode this question was guarding against. It will not happen; the smoke is there to prove it, not to fix it.

DEFAULT NOTED FOR PO VETO: I am treating the internal image route's retirement (OQ-3) as GO — delete it in M8b.1 — because it is unreachable through the edge and has zero callers repo-wide.

*Evidence:* services/api-gateway-bff/src/gateway-setup.ts:86-91 — `worldsProxy = createProxyMiddleware({ target: urls.bookUrl, changeOrigin: true, selfHandleResponse: false, pathFilter: (pathname: string) => pathname.startsWith('/v1/worlds') })` (TRUE prefix wildcard). Dispatch: gateway-setup.ts:592-594 — `if (req.path.startsWith('/v1/worlds')) return worldsProxyFn(req, res, next);`, preceded only by disjoint prefixes (/mcp :573, /v1/auth|/v1/account|/v1/me/preferences|/v1/users|/v1/admin|/oauth :577-581, /v1/book/actions :586, /v1/books :589) — no shadowing. Multipart: services/api-gateway-bff/src/main.ts:19 `NestFactory.create(AppModule, { bodyParser: false })` + gateway-setup.ts:402,406 (`json()` mounted ONLY on /v1/ai/tools and /v1/assistant) ⇒ /v1/worlds bodies stream raw; precedent frontend/src/features/books/api.ts:587 `uploadChapterMedia` → bookProxy (gateway-setup.ts:75-81, identical config). Upstream mount: services/book-service/internal/api/server.go:381 `r.Route("/v1/worlds", func(r chi.Router) {...})` — new subroutes inherit the proxied prefix automatically. Dead internal route: server.go:200 `r.Post("/worlds/maps/{map_id}/image", s.uploadWorldMapImage)` inside `r.Route("/internal", ...)` + `r.Use(s.requireInternalToken)` (server.go:185-186) — not proxied, zero callers.

### Q-38-E2E-CDP-MOUSE-DRAG
CONFIRMED AS-SPEC — build it exactly as §3.3.3 + DoD #4 state. No design call needed; here is the builder recipe, which is now the DoD of Waves 8a/8b (the wave does not close until both specs are green + /review-impl clean).

1) HARNESS. Two new files, siblings of studio-compose.spec.ts: frontend/tests/e2e/specs/studio-kg-write.spec.ts and frontend/tests/e2e/specs/studio-world-map.spec.ts. Use loginViaUI + TEST_USER from tests/e2e/helpers/auth.ts (= claude-test@loreweave.dev) and StudioPage.openPanel(panelId, searchTerm) from tests/e2e/pages/StudioPage.ts:43 — NO raw selectors in the spec (CONVENTIONS §2). Run against the BAKED FE: playwright.config.ts:3 already defaults baseURL to http://localhost:5174, so either `docker compose build frontend && up -d frontend` BEFORE running, or run with PLAYWRIGHT_BASE_URL=http://localhost:5199 against `vite dev`. Never run against :5174 while a host vite dev is up — it SHADOWs the baked bundle and you smoke the wrong code.

2) THE DRAG (the whole point). FORBIDDEN in studio-world-map.spec.ts: `locator.dragTo()`, `browser_drag`, and any hand-dispatched PointerEvent/MouseEvent — dragTo emits only 2 moves and synthetic events are untrusted, so a d3-drag/canvas handler never sees the gesture (lesson playwright-cdp-mouse-drives-d3-drag). REQUIRED shape:
   const box = await pin.boundingBox();
   await page.mouse.move(box.x + box.width/2, box.y + box.height/2);
   await page.mouse.down();
   await page.mouse.move(tx, ty, { steps: 12 });   // >=10 steps, intermediate moves are load-bearing
   await page.mouse.up();

3) ASSERT BY EFFECT AT THREE POINTS (all three, per the lesson):
   (a) mid-drag: after mouse.down + one partial move, sample the pin's rendered position and assert it MOVED under the cursor (proves the handler is live, not just that a write fired — the reactflow-controlled-nodes-need-onnodeschange bug class);
   (b) the write: `const patch = page.waitForRequest(r => r.method() === 'PATCH' && /\/pins\//.test(r.url()))` around mouse.up;
   (c) THE ONE THAT COUNTS: `await page.reload()`, re-open the panel, assert the pin is at the NEW coords. Optimistic repaint cannot survive a reload — this is the only proof the PATCH landed.
   Plus a NEGATIVE leg: a sub-threshold twitch (<5px, down→move→up) must fire ZERO PATCH requests (assert via a request counter on page.on('request')).

4) FE PREREQUISITE the drag assertion needs (build it in WorldMapPanel, do not fudge it in the test): each pin renders `data-testid="world-map-pin-{pinId}"` AND its persisted coords as `data-x` / `data-y` (normalized 0..1, the wire values). Assert on those attributes, not on pixel boundingBox — a pixel compare after reload is flaky under canvas zoom/pan restore.

5) The rest of DoD #4 unchanged: studio-kg-write.spec.ts = create entity → assert it appears AFTER a refetch (intercept the LIST refetch, or reload) not from optimistic state → open kg-graph → link → RELOAD → both survive → Mark wrong on the edge → gone; then seed-from-glossary asserting counters by their WIRE names (nodes_created / nodes_existing / entities_seen / skipped / nodes_conflicted / truncated — a spec asserting `created` reads undefined). studio-world-map.spec.ts also: rename in a SECOND TAB (`page.context().newPage()` — same storage state, real second tab) then rename in tab 1 with the stale version → `page.waitForResponse(r => r.status() === 412)` and assert the UI surfaces the CURRENT name.

6) AGENT LEG + DEGRADED LEG, in the same two specs: use tests/e2e/helpers/frontendToolInject.ts to inject a suspended `ui_open_studio_panel {panel_id:"kg-entities"}` and `{panel_id:"world-map"}` and assert the dock tab actually mounts (do NOT depend on a local model choosing the tool). Then the bare-open degraded leg: open `world-map` with no map/no book selection and assert a RENDERED empty/degraded state testid — a blank panel after `shown:true` is the silent-success bug this plan exists to kill (spec 38:205).

*Evidence:* docs/specs/2026-07-01-writing-studio/38_kg_and_world.md:264 (§3.3.3 "The E2E must drive this with CDP mouse events (page.mouse), not browser_drag") + :440-442 (DoD #4, the two spec files, baked-FE caveat, wire-name counters, the 412 second-tab leg) + :205 (bare-open must be a rendered state). Harness grounding: frontend/playwright.config.ts:3 (baseURL = PLAYWRIGHT_BASE_URL ?? http://localhost:5174; testDir ./tests/e2e/specs); frontend/tests/e2e/pages/StudioPage.ts:43 (openPanel via real Command Palette); frontend/tests/e2e/helpers/auth.ts:17 (loginViaUI / TEST_USER = claude-test@loreweave.dev); frontend/tests/e2e/helpers/frontendToolInject.ts:22-40 (suspended frontend-tool injection = the agent leg). Gap that makes this worth spelling out: `grep -rn "page.mouse" frontend/tests/e2e/` returns ZERO hits across all 37 existing specs — there is no drag precedent in this repo, so a builder left to itself reaches for locator.dragTo() and gets a false green.

### Q-38-SLICES-ARE-TWO-BUILDS
CONFIRMED — 8a and 8b are TWO TASKS, not one XL task. The spec already asserts it (§0.2, §8's M8a.* / M8b.* split); what was missing is the *mechanical* consequence. Do all five of the following, and nothing more.

(1) TWO workflow-gate classifications, TWO wave closes. Wave 8 is executed as two independent gate runs:
  - **W8a (KG write holes) — size L** (logic: A1 create-entity, A2 create-relation as a 3rd verb on `RelationEditDialog` + convert its free-text Correct field, A3 seed-from-glossary CTA, A4 forget-fact row action, A5 the three dead buttons, BE-14a/b/c/d = 4 new knowledge-service routes/constants; side effects: 3 new REST routes ⇒ risk floor ≥ M, breadth bumps to L). Services: `knowledge-service` + `frontend/src/features/knowledge/**`.
  - **W8b (world container + world-map) — size XL** (12 new Go routes BE-15a…l + a `version`/`updated_at` migration + 3 new MCP tools BE-15m + 2 new dock panels + the UPDATE semantics that exist at no layer). Services: `book-service` + `frontend` (+ registration files).
  Run: `./scripts/workflow-gate.sh size L …` for 8a, ship it, close it; then a **fresh** `size XL …` for 8b. Do NOT classify Wave 8 once.

(2) `/review-impl` runs at the close of EACH of the two, and each has its own POST-REVIEW + its own commit(s). Per PO policy item 2, bake `/review-impl` into both DoDs literally.

(3) SPLIT §9 Definition of Done into §9a and §9b — this is the one spec edit this adjudication requires, because today's monolithic §9 makes 8a un-closable:
  - **§9a (W8a DoD):** DoD-1 restricted to BE-14a/b/c reachable through the gateway `:3123`; DoD-3 (knowledge pytest `-n auto --dist loadgroup` + frontend vitest); DoD-4's **`studio-kg-write.spec.ts`** live browser smoke ONLY; DoD-5 cross-service live-smoke token (knowledge + frontend); DoD-6 the **KG-affordances** draft only; DoD-7; DoD-8; **plus `/review-impl` clean**. 🔴 **DoD-2's panel-count contract assertion is NOT in §9a** — §3.1 says 8a adds *no new panel id*, and the catalog confirms `kg-overview/kg-entities/kg-schema/kg-graph` are already registered (`frontend/src/features/studio/panels/catalog.ts:153-160`). An 8a DoD that demands a panel-count delta would send the builder hunting a delta that does not exist.
  - **§9b (W8b DoD):** DoD-1 for BE-15a…l; DoD-2 (openable == enum == contract, **+2 delta**, never a literal); DoD-3 (`go test ./...`); DoD-4's **`studio-world-map.spec.ts`** + the agent leg + the bare-open degraded leg; DoD-5; DoD-6 the world-map draft; DoD-7; DoD-8; **plus `/review-impl` clean**. M8b.0 (the Track C `world`-container ownership handoff, recorded in SESSION_HANDOFF) stays the **entry gate to W8b only** — it does not gate W8a.

(4) INDEPENDENT REVERTABILITY (GG-7) is real and is grounded in disjoint file sets — enforce it by never touching a shared file from 8a: 8a touches `services/knowledge-service/app/routers/public/{entities,relations,facts}.py`, `app/tools/graph_schema_tools.py` (BE-14d constant), `frontend/src/features/knowledge/**` (EntitiesTab, ProjectGraphView, RelationEditDialog, useRelationMutations, EntityDetailPanel, OverviewSection, ProjectRow) — and **zero** registration files. 8b is the only slice that touches `catalog.ts`, the panel-id enum, `chat-service/app/services/frontend_tools.py`, `contracts/frontend-tools.contract.json`, i18n panel keys, the User Guide, and `book-service/**`. Therefore `git revert` of either wave's commits cannot break the other. If a builder finds themselves editing `catalog.ts` during 8a, they have drifted — stop.

(5) ORDER 8a → 8b, and 8a does NOT block on anything. 8a is unencumbered (plan 30 §9 flags only 8b/8c on the Track C collision; Track C's own RUN-STATE has P-5 **PARKED**, so nothing is in flight in `world`). If the Track C handoff for the `world` container stalls, **ship 8a and keep going** (defer row, per PO policy item 3) — that ability is precisely what the split buys, and it is the answer to the concern.

Default I am choosing (veto-able): the two waves are NOT interleaved and NOT run as one continuous effort even though CLAUDE.md says "classify the whole EFFORT" — because these are not one coherent effort: they share no service, no file, no route, no panel, and no test. The only thing they share is a wave number.

*Evidence:* docs/specs/2026-07-01-writing-studio/38_kg_and_world.md:4 + §0.2 (l.21-25) already declare the two-build split; §8 (l.422-433) already carries M8a.1/M8a.2 vs M8b.0/M8b.1/M8b.2/M8b.3, but §9 (l.435-449) is a single monolithic DoD that mixes 8a and 8b gates — that is the actual defect this concern points at. Disjointness proof: 8a adds no panel (spec §3.1 heading "No new panel id"), and frontend/src/features/studio/panels/catalog.ts:153-160 already registers kg-overview/kg-entities/kg-schema/kg-graph, while a grep for `world` in catalog.ts returns only the unrelated `book-settings` comment at :222 — so `catalog.ts`/the enum/`contracts/frontend-tools.contract.json` are touched by 8b ONLY. Track C non-collision for 8a: docs/plans/2026-07-12-track-c-completion-RUN-STATE.md:212 (P-5 = "workflow rack, binding UI, W8/W10/W11" — PARKED, and claims the `world` container, not the KG panels). Plan 30 §9 (l.714) gates only "Wave 8b/8c" on the Track C handoff, never 8a. Sizing inputs: spec §4.1 (4 knowledge routes, l.281-284) vs §4.2 (12 book-service routes, l.294-305) + BE-15m (l.318) + the migration (l.316).

### Q-38-LEGACY-ONLY-NOT-UNBUILT
The trap is REAL but already DEFUSED — and spec 38's premise is STALE. Spec 16 does NOT slate ChapterEditorPage for deletion any more: its Phase 4b (M9, user's call 2026-07-05, spec COMPLETE) explicitly reversed "delete after soak" to "keep INDEFINITELY, deprecation-bannered, no route change" (16_chapter_editor_parity_and_retirement.md:133). The route is still live (App.tsx:134). So nothing can delete the last human write path today, and Wave 8 is NOT gating a retirement that is scheduled — there is no scheduled retirement. Keep GG-4 as written (it is sealed in plan 30 §1/§9 — do not weaken it), but do three concrete things and DO NOT let this block or reorder anything:

(1) FIX THE STALE SENTENCE — spec-only, 5 min, do it at the start of Wave 8. In `docs/specs/2026-07-01-writing-studio/38_kg_and_world.md` §1.1 hole #1 table cell, replace "the page spec 16 slates for deletion (GG-3 …; GG-4: retiring that page today deletes this)" with: "the page plan 30's GG-3 marks LEGACY-ONLY. ⚠ Note spec 16 Phase 4b (:133) already resolved M9 to **keep, don't delete** — so no deletion is scheduled and GG-4's trap cannot fire today. GG-4 remains in force as a guard against a FUTURE unplanned deletion/dead-code sweep." Same correction in §1.2's OQ-9 note if it repeats the "slated for deletion" phrasing.

(2) MAKE THE INVARIANT MECHANICAL, NOT A DOC NOTE (this repo's own `checklist⇒test the effect` lesson). Add to M8a.1's Definition of Done a new source-guard vitest: `frontend/src/features/knowledge/__tests__/kgWritePaths.guard.test.ts`. It reads the FE tree with node `fs`/`fast-glob` (mirror whatever existing repo-wide guard test does; if none, plain `fs.readdirSync` recursion over `frontend/src`) and asserts, for each of `createEntity` and `createRelation` on `knowledgeApi`: **at least one call site exists OUTSIDE `frontend/src/features/composition/**`** (i.e. under `features/knowledge/**`). Test message must name the law: "GG-1: every backend capability a user owns must have a human surface — POST /v1/knowledge/entities|relations must have a non-legacy FE caller." This test is RED today and GREEN the moment M8a.1's A1/A2 land, and it permanently blocks a future ChapterEditorPage/composition dead-code sweep from silently deleting the last human write path — which is the ONLY way GG-4's trap can still fire.

(3) DO NOT add any new sequencing gate, defer row, or PO checkpoint for this. Wave 8a proceeds exactly as specced (M8a.1 ports the capability into the KG panels; the legacy WorldMap stays on ChapterEditorPage per OQ-9). No wave is blocked on this item.

Default I am picking (veto-able): the guard test lives in M8a.1's DoD, not as a standalone pre-wave task — bundling it costs nothing and guarantees it lands with the code it protects.

*Evidence:* docs/specs/2026-07-01-writing-studio/16_chapter_editor_parity_and_retirement.md:133 ("Phase 4b — M9 resolved: keep, don't delete ✅ COMPLETE 2026-07-05 … kept **indefinitely**, not deleted. No route change either.") + :3 (spec status COMPLETE, "Phase 4b (M9 — kept `ChapterEditorPage.tsx`, marked deprecated, not deleted)") · frontend/src/App.tsx:134 (legacy route still mounted) · frontend/src/features/composition/hooks/useWorldMap.ts:129 + :134 (sole FE callers of knowledgeApi.createEntity/createRelation; repo-wide `grep -rn "createEntity\|createRelation" frontend/src` returns exactly these 2 knowledge-api hits, zero under features/knowledge/**) · frontend/src/features/knowledge/api.ts:1600,1610 (the API methods exist, uncalled) · docs/specs/2026-07-01-writing-studio/38_kg_and_world.md:424 (M8a.1 = A1 create entity + A2 create relation) and :465 (OQ-9 already records the handoff) · docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md §1 GG-4 + §9 sequencing diagram ("spec-16 RETIREMENT (GG-4 gate)") — sealed, unchanged by this decision.

### Q-38-M8A1-SIZING-REORDER
CONFIRMED BY CODE — spec 38 §8's reorder is correct and is now binding. **M8a.1 = M**, and BE-14c + BE-14d ship INSIDE it, landing BEFORE A1's `<select>`. Build in this exact order:

**(1) Hoist the constant — new file `services/knowledge-service/app/entity_kinds.py`** (top-level module, matching the existing `pricing.py` / `effort.py` / `spoiler_window.py` pattern; a neutral home avoids a router↔tools import cycle):
`AUTHORABLE_ENTITY_KINDS: tuple[str, ...] = ("character", "concept", "faction", "location")` — ordered, deterministic, so the FE `<select>` order is stable.

**(2) `entities.py:975`** — DELETE `_AUTHORABLE_KINDS`; import the constant; validator (`:992`) becomes `if self.kind not in AUTHORABLE_ENTITY_KINDS`. Keep the existing ValueError message shape.

**(3) BE-14c — `GET /v1/knowledge/entity-kinds`** on `entities_router` → `200 {"kinds": list(AUTHORABLE_ENTITY_KINDS)}`. Standard JWT (401 unauth). System-tier, read-only, NO write route (CLAUDE.md User Boundaries). Do NOT unify with glossary-service's per-user `entity_kinds` — different object, the `/v1/knowledge/` prefix keeps them apart.

**(4) BE-14d — `graph_schema_tools.py:460-463`** — `kind` becomes a closed set over the same constant. ⚠ TWO things the spec understates: (a) the field's **description string is itself the bug** — it reads `"e.g. 'character', 'location', 'faction', 'item'"`, i.e. it actively teaches the LLM to send `'item'`, which REST rejects at `entities.py:992`. Rewrite it to name only the 4 legal kinds. (b) **The 3-schema-source FastMCP caveat applies** (`knowledge-mcp-three-schema-sources-fastmcp-strips`): FastMCP STRIPS the enum — propagate the closed set to ALL THREE schema sources or the LLM never sees it and BE-14d is theatre. Also align `max_length` (tool says 100, REST says 50).

**(5) A1 FE `<select>`** — options come from `GET /v1/knowledge/entity-kinds`. A hard-coded FE array is a review-blocking finding.

**Tests (all in M8a.1's DoD):** knowledge pytest — (a) route returns exactly the 4 kinds + 401 unauth; (b) a **parity test** asserting the tool's closed set == `AUTHORABLE_ENTITY_KINDS` == the REST validator's set (this is the machine-check that keeps the three from drifting again); (c) `kg_create_node` with `kind="item"` is now REJECTED (today it succeeds — that is the GG-2 inverse gap: the agent can mint a node the human cannot). vitest — the `kind` `<select>` renders from fetched data, with no literal kind array in the component.

**FIX-NOW doc edit (this is the drift the concern actually names):** plan 30 line 308's **BE-14 row** is the stale artifact — it is sized **S** and lists only `project-entities` + `invalidate`, never mentioning BE-14c/BE-14d. (Note: plan 30 has NO `M8a.1` milestone table at all — grep for `M8a` returns nothing — so the concern's "older plan-30 milestone table" does not exist; the BE-14 row is what misleads.) Amend line 308 to enumerate BE-14a/b/c/d with their sizes and to point at **spec 38 §8:424 as the SINGLE owner of Wave-8 sequencing**. One home, one name.

Nothing here contradicts §0 (PO-2 dropped 8c; PO-4 is spec-first — both orthogonal).

*Evidence:* services/knowledge-service/app/routers/public/entities.py:975 — `_AUTHORABLE_KINDS = {"character","location","faction","concept"}` (module-private set inside a router; enforced :992-994, `max_length=50`). services/knowledge-service/app/tools/graph_schema_tools.py:460-463 — `kind: str = Field(min_length=1, max_length=100, description="the entity kind, e.g. 'character', 'location', 'faction', 'item'")` — free string whose description induces the invalid `'item'` value REST rejects. No `GET /entity-kinds` route exists anywhere in knowledge-service (grep `entity-kinds` → zero route hits) ⇒ BE-14c is unbuilt work, not a blocker. docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:308 — BE-14 row sized **S**, lists only the two routes, omits BE-14c/BE-14d (the stale artifact). docs/specs/2026-07-01-writing-studio/38_kg_and_world.md:424,427 — the corrected M8a.1 = M milestone row + its rationale.

### Q-38-WORLDEFFECTS-LANE-B
BUILD IT AS SPEC'D — but the spec's REGEXES are right and its QUERY KEYS are wrong (3 of 4 don't exist). Do this:

=== A · NEW frontend/src/features/studio/agent/handlers/worldEffects.ts (M8b.3) ===
Keep the spec's regex VERBATIM — I traced all 12 real tool names through it:
  export const WORLD_WRITE_PATTERN = /^world_(map_)?(create|delete|update|rename|add_marker|remove_marker|update_marker|add_region|remove_region|update_region|move_book)/;
It matches all 8 real writes (world_create, world_move_book, world_map_create, world_map_add_marker, world_map_add_region, world_map_delete, world_map_remove_marker, world_map_remove_region) and matches NONE of the 4 real reads (world_list, world_get, world_map_get, world_map_list) — the 🔴 anti-thrash requirement holds. It over-enumerates verbs that don't exist yet (update/rename/update_marker/update_region/world_delete); leave them as harmless future-proofing.

REPLACE the spec's 4 invalidation keys — ['world-maps'], ['world-map-detail'], ['worlds'], ['world-books'] — because only ['worlds'] exists and ['world-books'] is a phantom. worldEffect(ctx) must invalidate (TanStack matches by key PREFIX, so the short prefixes below cover their sub-keys):
  ['worlds']                    // useWorlds.ts:14
  ['world']                     // prefix → ['world', worldId], useWorld.ts:14
  ['living-world']              // prefix → ['living-world','books',id] (useLivingWorld.ts:55) + ['living-world','works',id] (:68). THIS is the real "world-books"
  ['world-subgraph']            // useWorldSubgraph.ts:29
  ['world-timeline']            // useWorldTimeline.ts:17
  ['project-backlink-world']    // useProjectBacklinks.ts:24 — goes stale on world_move_book
  ['world-maps']                // NEW key, see hard constraint below
  ['world-map-detail']          // NEW key, see hard constraint below
Rationale for the first six: useAddBookToWorld.ts:25-26 is the REST PRODUCER of the same write and invalidates ['living-world','books',worldId] + ['world-subgraph'] — the Lane-B handler must mirror the producer's own invalidate set, not invent one.

🔴 HARD CONSTRAINT (M8b.3): ['world-maps'] and ['world-map-detail'] exist NOWHERE in the codebase today — M8b.3 creates them. The new map hooks (frontend/src/features/world/hooks/useWorldMaps.ts / useWorldMapDetail.ts) MUST use exactly the literals ['world-maps'] and ['world-map-detail', mapId]. If they drift, the handler invalidates dead keys and the map panel silently never refreshes after an agent write — a false-green (unit tests pass, live loop broken).

🔴 DO NOT invalidate ['composition','worldmap',*] (useWorldMap.ts:70,81). That is composition's PLACES map — a different subsystem. No world_* tool writes it.

=== B · knowledgeEffects.ts gains the memory_ registration (M8a.2) ===
CONFIRMED as the spec states: KNOWLEDGE_WRITE_PATTERN = /^kg_(?!…)/ (knowledgeEffects.ts:16-17) is anchored on `kg_` and CANNOT match memory_forget/memory_remember. In registerKnowledgeEffectHandlers() (knowledgeEffects.ts:48-52) add a SECOND registration reusing the SAME handler fn:
  export const MEMORY_WRITE_PATTERN = /^memory_(remember|forget)$/;
  registerEffectHandler(MEMORY_WRITE_PATTERN, knowledgeEffect);
The trailing $ excludes the three reads (memory_search, memory_recall_entity, memory_timeline) by construction. Reuse knowledgeEffect unchanged — memory facts land in the surfaces it already invalidates (['knowledge-entity-facts'], ['knowledge-summaries']).

=== C · useStudioEffectReconciler.ts ===
Import registerWorldEffectHandlers from './handlers/worldEffects' and call it as the 5th line of the existing registration useEffect (useStudioEffectReconciler.ts:34-39). worldEffects.ts follows the established module shape: `let registered = false` idempotency guard + a `_resetWorldEffectHandlers()` test hook (copy knowledgeEffects.ts:19, 47-56).

=== D · TESTS (frontend/src/features/studio/agent/__tests__/worldEffects.test.ts, mirroring knowledgeEffects.test.ts) ===
1. Table test — each of the 8 write tool names → matchEffectHandlers(name) is non-empty and worldEffect runs.
2. 🔴 Table test — each of world_get / world_list / world_map_get / world_map_list → matchEffectHandlers(name) === [] (this is the anti-cache-thrash assertion; it is the point of the ticket).
3. Assert every one of the 8 invalidateQueries keys above is called with a spied queryClient.
4. In knowledgeEffects.test.ts: memory_remember + memory_forget MATCH; memory_search + memory_recall_entity + memory_timeline DO NOT.

DEFAULT NOTED FOR PO VETO: I included ['world-timeline'] and ['project-backlink-world'] beyond what the spec listed, because world_move_book changes book↔world membership and both read it. If you'd rather keep the blast radius minimal, drop those two — nothing else changes.

*Evidence:* Regex validated against the 12 real tool names: services/book-service/internal/api/mcp_worlds.go:295-316 (world_list, world_get, world_create, world_move_book) + services/book-service/internal/api/mcp_maps.go:466-510 (world_map_create/add_marker/add_region/get/list/delete/remove_marker/remove_region). memory_ half: services/knowledge-service/app/tools/definitions.py:176-177 (memory_remember, memory_forget) vs frontend/src/features/studio/agent/handlers/knowledgeEffects.ts:16-17 (KNOWLEDGE_WRITE_PATTERN = /^kg_(?!project_list|graph_query|…)/ — anchored on kg_, cannot match memory_*). Query keys — the spec's list is wrong: ['worlds'] exists at frontend/src/features/world/hooks/useWorlds.ts:14; ['world', worldId] at useWorld.ts:14; the real "world-books" is ['living-world','books',worldId] at useLivingWorld.ts:55 (+ ['living-world','works',bookId] at :68); ['world-subgraph'] at useWorldSubgraph.ts:29; ['world-timeline'] at useWorldTimeline.ts:17; ['project-backlink-world'] at frontend/src/features/knowledge/hooks/useProjectBacklinks.ts:24. The REST producer of the same write, frontend/src/features/world/hooks/useAddBookToWorld.ts:25-26, invalidates ['living-world','books',worldId] + ['world-subgraph'] — the handler mirrors it. ['world-maps'] / ['world-map-detail'] / ['world-books'] appear in ZERO files (grep of all queryKey occurrences matching /world/ across frontend/src). Registration call site: frontend/src/features/studio/agent/useStudioEffectReconciler.ts:34-39. Module shape to copy: knowledgeEffects.ts:19,47-56.

### Q-38-REGISTRATION-CHECKLIST
ADOPT spec 38 §5 GG-8 verbatim as the build order — it is code-accurate — with THREE amendments the builder must apply.

VERIFIED AS WRITTEN (no change): (2) `catalog.ts` — `'storyBible'` already exists as a `StudioPanelCategory` (catalog.ts:83) and is in `CATEGORY_ORDER` (palette/useStudioCommands.ts:21); copy the row shape at catalog.ts:128/:266 exactly (`category` + `guideBodyKey` both present, no `tourAnchor`). Do NOT add a category. (5) `frontend_tools.py:402` is the `panel_id` enum (57 entries at HEAD) and `:403` the description prose — both refs exact; append `"world"`,`"world-map"` to the enum AND their gloss clauses to the prose. (6) regenerate `contracts/frontend-tools.contract.json` via `cd services/chat-service && WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py`, commit it in the SAME commit as steps 2+5. (7) `StudioLinkContext` is `{bookId, titleFor?}` (studioLinks.ts:19-24) and `resolveStudioLink` is a pure sync fn — it provably cannot look a world up, so `worldId?: string` must be added to the ctx; absent ⇒ `external`. (8) `registerEffectHandler(pattern: string | RegExp, handler)` (effectRegistry.ts:32) accepts the regex as given; register `worldEffects` in `useStudioEffectReconciler.ts` alongside the four existing registrars at :18-21. (8b) `KNOWLEDGE_WRITE_PATTERN = /^kg_(?!…)/` (knowledgeEffects.ts:17-18) provably cannot match `memory_forget` — add `registerEffectHandler(/^memory_(remember|forget)$/, knowledgeEffect)` INSIDE the existing `registerKnowledgeEffectHandlers()` (it is already idempotent-guarded by the `registered` flag). (1b) `useStudioPanel(panelId, api, extras?)` accepts `mcpToolPrefixes` (useStudioPanel.ts:11-15) — compiles as written. The 🔴 DOCK-7/DOCK-9 warning is real: `dockablePanelHygiene.test.ts:39,46` recursively scans `panels/**`, so the world panel's escape hatch MUST be `followStudioLink(...)` (never `<Link>`), and all five dialog surfaces MUST use `@/components/shared` FormDialog/ConfirmDialog or Radix.

AMENDMENT A (item 1 is INCOMPLETE — this is the one that bites): `WorldPanel.tsx` must ALSO call `useStudioPanel('world', props.api, { mcpToolPrefixes: ['world_'] })` as its first hook. The spec names that call only under 1b (world-map), but EVERY dock panel does it (GlossaryPanel.tsx:26, KgOverviewPanel.tsx:16). Omit it and the dock tab renders the raw id "world" and the panel never registers with the StudioHost agent rack — a silent half-registration that no listed test catches.

AMENDMENT B (item 7b line ref is stale): `onOpenWorld` is at `KgOverviewPanel.tsx:47-48`, not `:44`. The exact edit: `followStudioLink(`/worlds/${worldId}`, host, { bookId: host.bookId, worldId })` — today it passes only `{ bookId: host.bookId }` and throws `worldId` away, which would make step 7's rule dead code.

AMENDMENT C (kill a phantom step): there is NO `CLOSED_SET_ARGS` symbol anywhere in service code — grep hits only CLAUDE.md and docs. The closed-set-enum rule is enforced by `services/chat-service/tests/test_frontend_tools_contract.py` reading the schema. Steps 5 (enum) + 6 (regen) ARE the whole closed-set obligation; do not go hunting for a registry list to append to.

DoD unchanged: assert the DELTA (all three counts +2 in lockstep: py enum == contract enum == openable), never a literal — baseline at M8b is 69, not 57.

*Evidence:* frontend_tools.py:402 (panel_id enum, 57) + :403 (desc prose) · catalog.ts:83 ('storyBible' in StudioPanelCategory), :128/:266 (row shape) · palette/useStudioCommands.ts:21 (CATEGORY_ORDER contains storyBible) · useStudioPanel.ts:11-15 (extras: mcpToolPrefixes) · GlossaryPanel.tsx:26 + KgOverviewPanel.tsx:16 (every panel calls useStudioPanel — AMENDMENT A) · KgOverviewPanel.tsx:47-48 (onOpenWorld drops worldId — AMENDMENT B) · host/studioLinks.ts:19-24 (StudioLinkContext = {bookId,titleFor?}, pure sync) · agent/effectRegistry.ts:32 (registerEffectHandler accepts RegExp) · agent/useStudioEffectReconciler.ts:18-21 (4 existing registrars) · agent/handlers/knowledgeEffects.ts:17-18 (KNOWLEDGE_WRITE_PATTERN /^kg_(?!…)/ cannot match memory_*) · panels/__tests__/dockablePanelHygiene.test.ts:39,46 (DOCK-7/DOCK-9 recursive scan) · services/chat-service/tests/test_frontend_tools_contract.py:1-30 (closed-set enum enforced HERE; no CLOSED_SET_ARGS symbol exists — AMENDMENT C)

### Q-38-A1-SCOPED-PROJECT-REQUIRED
Build A1 exactly as follows — four concrete changes, all in M8a.1.

(1) BUTTON GATE — gate on `effectiveProjectId`, not on `scopedProjectId`. In `frontend/src/features/knowledge/components/EntitiesTab.tsx`, add a `+ New entity` button to the header row (the `flex flex-wrap items-end gap-2` div at :113). Render it `disabled={!effectiveProjectId}` with `title={t('entities.create.needsProject')}` = "Pick a project first — a new entity has to live in one." `effectiveProjectId` (:70) is ALREADY `scopedProjectId ?? projectFilter`, so the button lights up both when the panel is route-scoped AND when the user picks a project in the unscoped cross-project `<select>` (:120-133). This is a deliberate, narrow widening of the spec's literal "disabled when `scopedProjectId` is absent": the spec's rationale is "a create needs a project", and in the unscoped browse the user CAN supply one. PO may veto — if vetoed, change one expression to `disabled={!scoped}`.

(2) DO NOT put `KgNoProjectState` in `EntitiesTab`. It takes a required `bookId` prop (frontend/src/features/knowledge/components/shell/KgNoProjectState.tsx:15-22) that `EntitiesTab` does not have and cannot resolve, and `KgEntitiesPanel` intentionally supports global cross-project browse — a vitest pins the GLOBAL passthrough (`panels/__tests__/KgEntitiesPanel.test.tsx:56-59`). The spec's "empty ⇒ KgNoProjectState" is already satisfied where it belongs: the book-scoped panels (KgOverviewPanel.tsx:31-35, KgGraphPanel.tsx:32, KgSchemaPanel.tsx:94, KgGapReportPanel.tsx:31) gate on `useBookKnowledgeProject(host.bookId)`. In unscoped `EntitiesTab` the correct empty state is the disabled button + its tooltip. Leave `KgEntitiesPanel.tsx` untouched.

(3) BE-14c + the kind `<select>` (the array is ALREADY drifting — build the route). New route in `services/knowledge-service/app/routers/public/entities.py`: `GET /entity-kinds` → `200 {"kinds": sorted(_AUTHORABLE_KINDS)}` reading `_AUTHORABLE_KINDS` at :975 (currently {character, location, faction, concept}) — no auth-scoped data, but keep `Depends(get_current_user)` for consistency. Add `knowledgeApi.listEntityKinds()` in `frontend/src/features/knowledge/api.ts` + a `useEntityKinds()` react-query hook; the create form's `kind` control is a `<select>` fed ONLY from it (disabled + "loading kinds…" while pending; if the fetch fails, disable Save and show the error — never a hand-coded fallback array). LEAVE the existing `KIND_OPTIONS` (EntitiesTab.tsx:24-32) as the BROWSE-FILTER vocabulary — it is a different, wider set (organization/item/event_ref/preference are extractable but not authorable, and it is missing `faction`) — and add a one-line comment saying exactly that, so /review-impl does not read it as the drift BE-14c was meant to kill.

(4) IDEMPOTENCY — the BE currently makes the honest message IMPOSSIBLE; fix it in the same slice. `create_entity_endpoint` (entities.py:999-1032) hardcodes `status_code=201` and returns a bare `Entity`; `merge_entity` (app/db/neo4j_repos/entities.py:305, `_MERGE_ENTITY_CYPHER` :244) is a silent MERGE with no created-vs-matched signal, so an FE that says "created" would be a `silent-success` lie. Change the route ONLY (do not touch the shared Cypher — extractors depend on it):
   - add `class CreateEntityResponse(Entity): created: bool` (ALWAYS present — no conditional key, per §3.1 A3's wire-name rule);
   - in the handler, inside the existing `neo4j_session()`, before `merge_entity`: `canonical_id = entity_canonical_id(user_id=str(user_id), project_id=str(body.project_id), name=body.name.strip(), kind=body.kind, canonical_version=1)` (import from `app.db.neo4j_repos.canonical` — sibling of `canonicalize_entity_name`, already imported at :28) then `existing = await get_entity(session, user_id=str(user_id), canonical_id=canonical_id)` (`get_entity` is ALREADY imported at :41);
   - `created = existing is None`; still call `merge_entity` unchanged; take `response: Response` and set `response.status_code = 200` when `not created` (keep the route default 201);
   - return `CreateEntityResponse(**entity.model_dump(exclude={"status"}), created=created)` (`status` is a computed_field — passing it as a kwarg raises).
   FE: `createEntity` (frontend/src/features/knowledge/api.ts:1600) keeps returning the body; read `res.created` — `true` ⇒ toast "Created «name»" + select the new row; `false` ⇒ toast "Already exists — opened it" and select the returned entity id. `apiJson` discards the status code, so read the BODY field, not the 200/201.
   Tests: `services/knowledge-service/tests/unit/test_world_map_authoring_api.py::test_create_entity_happy` (:88) patches only `merge_entity` — it must ALSO patch `app.routers.public.entities.get_entity` (AsyncMock → None) or it will hit the noop session; assert `201` + `created is True`. Add a sibling test: `get_entity` returns an existing stub ⇒ `200` + `created is False`. FE vitest: button disabled with tooltip when no project; enabled once a project is selected; `<select>` options come from the mocked `/entity-kinds` (assert `faction` present, `organization` absent — the drift guard); the "already exists — opened it" toast on `created:false` and NO "created" claim.

Existing consumer safety: `useWorldMap.ts:129` calls `createEntity` and ignores the body — the additive `created` field and the 200-on-existing are backward compatible.

*Evidence:* services/knowledge-service/app/routers/public/entities.py:975 (`_AUTHORABLE_KINDS = {"character","location","faction","concept"}`) and :999-1032 (`create_entity_endpoint` — hardcoded `status_code=201`, returns bare `Entity`, no created/matched signal from `merge_entity`); app/db/neo4j_repos/entities.py:244-303 (`_MERGE_ENTITY_CYPHER` silent MERGE) + :305 `merge_entity` + :684 `get_entity`; frontend/src/features/knowledge/components/EntitiesTab.tsx:24-32 (hand-coded `KIND_OPTIONS`, drifts from the BE set), :67-70 (`scoped` / `effectiveProjectId`), :113-133 (header row + project `<select>`); frontend/src/features/knowledge/components/shell/KgNoProjectState.tsx:15-22 (requires `bookId`); frontend/src/features/studio/panels/KgEntitiesPanel.tsx:18-23 + panels/__tests__/KgEntitiesPanel.test.tsx:56-59 (global mode is pinned); frontend/src/api.ts:80-100 (`apiJson` drops the status code ⇒ the signal must ride in the body); grep for `entity-kinds` across services/ + frontend/src returns nothing ⇒ BE-14c is unbuilt, not blocked.

## Not a question (already answered by code / a sealed decision)
- **Q-38-BE-16-WORKFLOWS-OUT-OF-SCOPE** — Already settled by sealed PO-2 (plan 30 §0, line 20): G-WORKFLOWS / BE-16 is NOT this spec's work and NOT wave 8's. Wave 8 = KG write holes + world maps only. **Builder instruction for wave 8: write ZERO code in `services/agent-registry-service/**` and ZERO code in `frontend/src/features/extensions/**`. Do not add BE-16's routes. Do not touch `mcp_server.go`'s tool descriptions.**

The ONE action this question earns is a doc fix, because the handoff paragraph Track C will inherit is factually wrong and would send them building the wrong thing. Do this now, in `docs/specs/2026-07-01-writing-studio/38_kg_and_world.md`, §0.1 (line 19) — replace the paragraph's body (keep the "out of scope by PO-2 / Track C owns it" framing verbatim) with this text:

> **The defect is real and live, but it is a GUI+CRUD hole, not an approval hole — verified against code at HEAD.** `registry_propose_workflow`'s tool description (`services/agent-registry-service/internal/api/mcp_server.go:81`) tells the model the user approves "in the UI", and **no UI exists**: a repo-wide grep of `frontend/src` for `workflow-proposal` / `mode-binding` returns **zero hits**; the extensions hub's `ProposalsView` consumes `/proposals` only (`frontend/src/features/extensions/api.ts:91-99`). **However, the approve/reject spine DOES exist and is publicly reachable**: `server.go:294-297` registers `GET /workflow-proposals`, `GET /workflow-proposals/{id}`, `PUT /workflow-proposals/{id}/approve`, `POST /workflow-proposals/{id}/reject` inside the JWT-gated public block (`server.go:224`), owner-scoped in `workflows.go:636`, and gateway-proxied at `/v1/agent-registry/*` (`api-gateway-bff/src/gateway-setup.ts:176,630`). `mode-bindings` likewise has public `GET/PUT` (`server.go:292-293`). So the earlier claim "a row no human can ever approve" is **REFUTED** — a human can approve over REST today; they simply have no button. What is genuinely absent is (a) any human surface, and (b) the public CRUD on the **approved workflow entity** — only `/internal/workflows` exists (`server.go:313`).
> **Track C, this is the handoff.** BE-16 reduces to **4 Go routes** on `agent-registry` (`GET /workflows`, `GET /workflows/{slug}`, `DELETE /workflows/{slug}`, `PUT /workflows/{slug}/enablement`) **+ `DELETE /mode-bindings/{mode}`** (reset-to-inherited — closes the SET-1..8 write-only-behavior violation by making the effective value + source tier resettable). The FE is a **clone of an existing view, not a new spine**: add `WorkflowsView.tsx` + `WorkflowProposalsView.tsx` beside `frontend/src/features/extensions/components/ProposalsView.tsx`, extend `features/extensions/api.ts` (BASE `/v1/agent-registry`) with the workflow-proposal calls, and register them in the extensions hub the way the skills/proposals tabs already are. **DoD for Track C P-5:** once the view ships, `mcp_server.go:81`'s "approve in the UI" becomes TRUE — until then it is a live `silent-success-is-a-bug` instance and must not be reworded into a different lie.

Also fix plan 30 line 256 (the G-WORKFLOWS register row), which carries the same wrong claim: change "the proposals half is buildable today; the workflows half is NOT: the public surface is completely empty" to "the proposal **approve/reject/list/get** routes already ship (`server.go:294-297`); only the **approved-workflow** CRUD (LIST/GET/DELETE/enablement) and the **FE** are missing." Keep the row marked OWNED-BY-TRACK-C.

Default I am picking (veto-able): the correction is doc-only and lands with wave 8's spec commit — no code, no scope creep, sealed decision untouched.
- **Q-38-A2-HUMAN-BYPASSES-TRIAGE** — CONFIRMED BY CODE — the bypass is already how the two paths are built, and it is correct. Two distinct primitives exist on purpose: the AGENT path `kg_propose_edge` "NEVER writes Neo4j: the proposal is parked to the triage inbox" (graph_schema_tools.py:297-301), while the HUMAN path `POST /v1/knowledge/relations` (relations.py:182-218) calls `recreate_relation` (neo4j_repos/relations.py:1307) which writes the edge directly at confidence 1.0 / pending_validation false and even resurrects a previously-invalidated `valid_until` (F5). A human authoring an edge IS the confirmation. No triage/propose plumbing on the human path. Builder instructions (do exactly this, nothing more):

1) A2's create mode in `frontend/src/features/knowledge/components/RelationEditDialog.tsx` + `useCreateRelation` in `hooks/useRelationMutations.ts` call `knowledgeApi.createRelation` → `POST /v1/knowledge/relations`. Do NOT route it through `kg_propose_edge`, the triage inbox, or a confirm-token. Add a one-line comment at both seams (the dialog's create branch, and the docstring of `create_relation_endpoint` at relations.py:182) reading: "INV: the human path is the confirmation — never enqueue to triage (kg_propose_edge is the AGENT path)."

2) Lock it with a regression test so a later reviewer cannot silently "fix" it: in `services/knowledge-service/tests/` assert `POST /v1/knowledge/relations` returns 201 with `confidence == 1.0` and `pending_validation is False` AND that the project's triage queue row-count is unchanged by the call (zero proposals created).

3) 409 rendering (no enumeration oracle): the BE detail is literally "subject or object entity not found for this user" (relations.py:210-213). The FE must NOT echo it and must not say which endpoint failed — render an i18n string (`relations.create.error.notYours`): "One of those entities isn't yours." Never surface the offending id.

4) 422 self-loop: disable Save while `subject_id === object_id` (client guard). Keep the BE guard (relations.py:196-200) as defense; if a 422 still arrives, surface its `detail` verbatim.

5) Optimistic edge: `ProjectGraphView` must add the edge to the canvas ONLY in `onSuccess` of the mutation, using the returned `Relation` (then invalidate the graph query). No pre-201 optimistic append, no rollback path to write.

6) One asymmetry to hold, not to "fix": the BE does NOT validate the predicate against the project ontology (`predicate: str = Field(min_length=1, max_length=100)`, relations.py:176) — so the `<select>` fed by `useGraphSchema().schema.edge_types[].code` is the ONLY ontology guard on the human path. That is intentional and consistent with "human = confirmation". Do NOT add a BE ontology-reject in this slice, and do NOT fall back to free text when `edge_types` is `[]` — render the empty-ontology state per §3.1 A2 (`host.openPanel('kg-schema')`).

Nothing here contradicts §0 PO-1..4 of plan 30 (PO-4 keeps this a spec-only phase; this is a build instruction for the wave-8a build).
- **Q-38-A4-NOT-KG-BIO** — CONFIRMED BY CODE — the spec's §3.1 A4 is already correct; nothing to change in the spec, and the concern needs no PO input. It is a "do not regress" record, so treat it as a BUILD CONSTRAINT on M8a.2 (A4), not an open item.

Builder instruction for M8a.2 / A4 (follow exactly):

1. SURFACE — `frontend/src/features/knowledge/components/EntityDetailPanel.tsx`. NOT `KgGlobalBioPanel`/`GlobalBioTab`/`kg-bio` (verified: that file imports `useSummaries`, has no facts list, no fact rows, and grep for `useEntityFacts` in it is EMPTY). Do not create a new panel id.

2. EXTRACT A ROW COMPONENT — the fact row is currently INLINE at `EntityDetailPanel.tsx:513-517` (`facts.map((f) => <li data-testid="entity-detail-fact">…`), unlike relations which already have a `RelationRow` component at `:60-119`. Extract `function FactRow({ fact, onForget })` mirroring `RelationRow`'s shape exactly, and hang the action off it as an icon-button that mirrors the existing relation-edit button at `:104-118` (same `TOUCH_TARGET_SQUARE_MOBILE_ONLY_CLASS`, same `title`/`aria-label`/`data-testid` convention): `data-testid="entity-detail-fact-forget"`, `Trash2`/`EyeOff` icon. `f.id` is already the React key at `:515`, so the `fact_id` is in hand.

3. DIALOG AT PANEL SCOPE, NOT PER ROW — follow the relation precedent: `EntityDetailPanel` holds `const [forgettingFact, setForgettingFact] = useState<EntityFact | null>(null)` (mirroring `editingRelation` at `:147`) and mounts ONE confirm dialog near the existing `RelationEditDialog` mount at `:623`. Copy is per spec: "Forgetting hides this fact from future context. It is not deleted from history — but there is no un-forget button."

4. WRITE — new hook `frontend/src/features/knowledge/hooks/useForgetFact.ts` + `knowledgeApi.invalidateFact` in `features/knowledge/api.ts`, calling BE-14b `POST /v1/knowledge/facts/{fact_id}/invalidate` → `{ invalidated: bool, fact_id }`. That route DOES NOT EXIST YET — write it (unbuilt work, not blocked): add `services/knowledge-service/app/routers/public/facts.py` modelled line-for-line on `routers/public/relations.py:63-93` (`invalidate_relation_endpoint`), calling the ALREADY-BUILT owner-keyed engine `invalidate_fact` at `app/db/neo4j_repos/facts.py:675`. Register the router where `relations_router` is registered. Owner scoping is the engine's `user_id` match — no project gate (see the rationale comment at `app/tools/executor.py:710-716`).
   - `invalidated: false` (engine returns None) ⇒ FE refetches `['knowledge-entity-facts', userId, entityId]` and shows "already gone". NEVER report success (silent-success-is-a-bug).
   - Do NOT wire to `POST /pending-facts/{id}/reject` or `/internal/admin/…/reject-fact` — different objects, different lifecycles.

5. FREE BONUS, AND ONE TRAP THE SPEC MISSES:
   - Bonus (spec is right): one edit lights the action up in BOTH `kg-entities` (`EntitiesTab.tsx:312`) and `kg-graph` (`ProjectGraphView.tsx:171`). But there is a THIRD mount the spec does not name: `frontend/src/features/world/components/WorldRollupGraph.tsx:176` (classic world page). Harmless — the action is correct there too — but the builder must know a change here touches three call sites and their three test files.
   - TRAP: the facts section is gated on `facts.length > 0` at `:507`. Forgetting the LAST fact collapses the whole section with no explanation. Add an empty-state line ("no known facts") inside the section instead of unmounting it, or the user's successful forget looks like a crash.

6. TESTS — extend `frontend/src/features/knowledge/components/__tests__/EntityDetailPanelC9.test.tsx` (it already mocks `useEntityFacts` at `:29-31` and drives facts at `:102`): (a) row renders the forget button; (b) click → confirm → mutation called with `f.id`; (c) `{invalidated:false}` ⇒ refetch + "already gone", NOT a success toast; (d) forgetting the last fact leaves the empty state, not a vanished section. Plus a pytest for the new route in knowledge-service (200 happy path, and unknown/foreign fact_id ⇒ `{invalidated:false}`, never a 404 oracle) run with `-n auto --dist loadgroup`.

DEFAULT THE PO MAY VETO: I am NOT adding an un-forget/restore affordance in this slice (OQ-5 owns it). The soft `valid_until` write keeps history, so it stays recoverable later.
- **Q-38-PLAN30-TABLE-ROW-RENAME** — Already done — plan 30 §11's table row (and §7's Wave-8 block, and 00_OVERVIEW row 38) all already say `38_kg_and_world.md`; a repo-wide grep for `kg_world_workflows` finds ZERO dangling references outside the reminder sentence itself. Builder action (housekeeping, do it at the Wave-8 COMMIT, zero code impact): in `docs/specs/2026-07-01-writing-studio/38_kg_and_world.md` line 6, delete the now-obsolete trailing clause so the blockquote ends after the filename — i.e. change "...is therefore retired in favour of **`38_kg_and_world.md`**; update plan 30 §11's table row when this lands." to "...is therefore retired in favour of **`38_kg_and_world.md`** (plan 30 §11 + §7 already updated)." Do NOT touch plan 30 §11 — it is correct. Leave plan 30's remaining `G-WORKFLOWS` mentions alone (line 310 BE-16 and line 818 `D-WS3-BINDING-GUI`): both already carry the "coordinate with / or Track C P-5" flag and are consistent with sealed PO-2.
- **Q-38-X4-REFUTATION-DO-NOT-FIX** — CONFIRMED BY CODE — the refutation is correct; plan 30's X-4 bullet is WRONG on this one tool. Builder instructions, in force for M8a/Wave 0:

1. DO NOT add an effect handler for `kg_create_node` or `kg_project_entities_to_nodes`. DO NOT edit `KNOWLEDGE_WRITE_PATTERN` (`frontend/src/features/studio/agent/handlers/knowledgeEffects.ts:16-17`). Both tools ALREADY match it and ALREADY invalidate `['knowledge-entities']`, `['knowledge-subgraph']`, `['knowledge-entity-detail']`, `['knowledge-entity-facts']`, et al. Adding a second handler = duplicate invalidations; rewriting the lookahead as an allow-list of the 14 enumerated names = a SILENT REGRESSION that removes coverage that works today.

2. STRIKE `kg_create_node` from X-4's missing-handler list in plan 30 §8 (line 337). X-4's remaining handlers are still REAL and still mandatory: `composition_canon_rule_*`, `composition_motif_*`, `composition_arc_*`, `plan_*`, `composition_authoring_run_*`, `world_map_*`, `registry_*workflow*`. X-4's handler count drops from ~15 by one domain; scope is otherwise unchanged. (X-4's other sub-item — deleting the now-false comment at `useStudioEffectReconciler.ts:10` — is untouched by this and still stands.)

3. FIX THE ACTUAL BUG, which is the STALE ENUMERATION that makes builders think coverage is missing (this is why the refutation was needed at all). Two edits, both cheap, both in Wave 0:
   a. `knowledgeEffects.ts:9-15` — the comment enumerates write shapes ("project_create, build_graph/build_wiki/run_benchmark, propose_fact/propose_edge, view_upsert/view_delete, triage_*, schema_edit, adopt_template, sync_apply") and OMITS create_node / project_entities_to_nodes. Rewrite it to state the actual semantics: "DENY-LIST BY DESIGN — every kg_* tool is treated as a write EXCEPT the 10 named reads in the lookahead. New kg_* write tools are covered automatically; only a new kg_* READ needs an edit here. Do not convert this to an allow-list."
   b. `knowledgeEffects.test.ts:52-56` — add `'kg_create_node'` and `'kg_project_entities_to_nodes'` to the `it.each` write-name list. This is the load-bearing step: it makes the refutation MECHANICALLY ENFORCED, so any future "fix" that narrows the pattern turns the suite red instead of silently dropping coverage. (Per CLAUDE.md's checklist⇒test-the-effect rule: a claim is only settled when a test asserts it.)

Rationale for treating this as NOT_A_QUESTION rather than a work item: the behavior already exists and is already wired; the only deliverable is a comment + test that stop it being un-done.
- **Q-38-WORLDS-NO-TOOL-GAP** — The refutation is CORRECT and the code confirms it — this is a guard, not an open question. Instruction to the builder, verbatim: (1) Do NOT create, plan, or "close a gap" with any new world-CONTAINER MCP tool. `world_create` / `world_get` / `world_list` / `world_move_book` already exist in `services/book-service/internal/api/mcp_worlds.go:295-320` (a different file from `mcp_maps.go`, which is why an earlier draft missed them). Total `world_*` tools = 12 (8 map + 4 container), not 8. (2) Federation already works: `book: ['world_']` is registered in `EXTRA_PREFIX_MAP` (`services/ai-gateway/src/config/config.ts:128`), so the C-GW prefix gate keeps all 12 — do NOT add a prefix entry, and do NOT "fix" the namespacing. (3) The ONLY new MCP tools Wave 8 ships are the 3 in BE-15m (`world_map_update`, `world_map_update_marker`, `world_map_update_region`) — the map UPDATE gap, which is real. (4) GUARD (new, from reading `server.go:381-392`): agent parity on the container holds ONLY because spec 38 §3.2 scopes the `world` panel to create / list / read / link-book. REST also exposes `PATCH /v1/worlds/{id}` (`patchWorld`), `DELETE /v1/worlds/{id}` (`deleteWorld`), and `DELETE /v1/worlds/{id}/books/{book_id}` (`removeBookFromWorld`) — and there is NO `world_update` / `world_delete` / `world_remove_book` MCP tool. So: if any slice adds a rename-world, delete-world, or unlink-book control to the `world` panel, it MUST ship the matching MCP tool in the same slice (GG-2 inverse-gap rule, same reasoning as BE-15m). If it does not add those controls — which is the spec'd default and the one to keep — build nothing here. (5) The effect-handler regex at spec 38 checklist row 8 already covers both namespaces via `/^world_(map_)?(create|delete|update|...|move_book)/` — leave it as written; it is deliberately reads-excluded.
- **Q-38-DESIGN-DRAFTS-BEFORE-BUILD** — ALREADY DONE — GG-6's gate is CLEARED, not open. Both mandatory drafts exist, are committed (d0f17555e, "…+ 10 design drafts"), and satisfy every clause of the house style (plan 30 §8.3:664-668 = WHY / ARCHITECTURE / BACKEND WORK IMPLIED / STATES / SCALE banner):

• design-drafts/screens/studio/screen-kg-write-affordances.html (83 KB) — banner :78 ARCHITECTURE, :93 "BACKEND WORK THIS SCREEN IMPLIES", :141 "STATES THIS MOCK MUST SHOW (all rendered below, none hand-waved)", :169 SCALE. The *Before* is rendered: :165 "⑥ 🔴 BEFORE / AFTER — kg-overview's THREE DEAD BUTTONS, struck", grounded in the banner's own :69-73 citation of OverviewSection.tsx:56 (`const noop`) → ProjectRow.tsx:293-314. 7 `.strike` uses. Multilingual: VI 60 + CJK 12 chars (Nghịch thiên, Hắc Diện Nhân, Vân Lam / Nhậm Mục).
• design-drafts/screens/studio/screen-world-map.html (78 KB) — banner :43 ARCHITECTURE, :92 "BACKEND WORK THESE SCREENS IMPLY", :129 STATES, :148 SCALE. The *Before* is rendered: :130 "① BEFORE — no host. The World backlink pops a browser tab out of the studio", plus the maps-empty state (:61). 8 `.strike` uses: :357 class def, :448-452 strike out "open the world in the dock", "open a map in the dock", "pin an entity to a place", "rename a map" and "drag a pin" — the last two tagged "no route at any layer", exactly the empty-map-with-no-route the item asks for. Multilingual: VI 73 + CJK 20 (Tứ Hải).

BUILDER INSTRUCTION: do NOT author these files — they exist. Before starting M8a, open screen-kg-write-affordances.html and read its banner :78-169; before M8b, open screen-world-map.html and read its banner :43-148. Treat each as the binding visual contract for its slice: the STATES block enumerates every state the panel must render (a state present in the mock and absent from the FE is a wave-DoD failure), and the "BACKEND WORK … IMPLIES" block is the authoritative list of BE routes the slice must create (world-map lists BE-15i DELETE …/markers/{id}, BE-15l DELETE …/regions/{id}, etc. at :106-108). Add "every state in the mock's STATES block renders in the live panel" to each wave's Definition of Done alongside the mandatory /review-impl step. No further design-draft work is a prerequisite for BUILD; the gate is green.

git status is clean for design-drafts/screens/studio/ — nothing pending, nothing to re-verify.
