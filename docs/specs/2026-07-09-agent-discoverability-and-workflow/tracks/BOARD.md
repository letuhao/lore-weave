# Coordination board — 3-session parallel run

Status: ⬜ not started · 🔄 in progress · ✅ done. Update your track's row as you go.

## Prerequisite

| Item | Status | Note |
|---|---|---|
| **Contracts frozen (`contracts.md` C1–C6)** | ✅ | Frozen 2026-07-09. Change = cross-track decision. |

## Tracks

| Track | Session/branch | Milestone in flight | Status |
|---|---|---|---|
| **A · Mechanism spine** ([brief](TRACK-A.md)) | *this session* | ✅ **COMPLETE.** WS-0 · **WS-1a** (`de464522d`) · **WS-1b** (`f11e69d6a`) · **ROOT-CAUSE FIX** LM Studio /v1/responses batches tool-args into `.done` (no `.delta`) → dropped every stateful turn; fixed `e008416f0` live-smoked (the real "weak model can't add entities" cause, not discovery) · **WS-2a** (`e1cfbd0f2` workflows+C3+HITL) · **WS-2b** (`7a70a8b1a` step-runner rail+list/load+async guard) · **C4** (`85c7d2a8c` uniform error envelope + output uniformity; live-smoked VALIDATION) · **WS-6** (`1c390c6c0` find_tools→optional/legacy, tool_list primary). **N1 + N2 met + FULL CHAT-TURN E2E PASSED** (live gemma). Remaining: WS-3/5/7 belong to Track C | ✅ |
| **B · Domain backend** ([brief](TRACK-B.md)) | *closed 2026-07-10* | ✅ **CLOSED except W8/W10/W11.** WS-4A ✅ · rename ✅ · **delete reachable ✅** (`mcp_server.go:89`) · WS-4B ✅ · WS-4C Half B ✅ (facts→L2) · **WS-4C Half A ✅** ([spec](../../2026-07-10-ws4c-half-a-canon-auto-capture.md) — chat→glossary `capture-canon`, grant-checked, **opt-in**, drafts into the `ai-suggested` inbox; 3-service live smoke + `/review-impl`) · domain feedback: dedup NFC/NFD+CJK ✅ · read-your-writes ✅ (no status filter in select-for-context) · upsert-on-create ✅ *by design* (create-only + `set_attributes`/`rename`) · `propose_*` naming → **owned by Track D (D1)** · `glossary_confirm_action` doc-drift ⬜ *(needs its original feedback item)*. **Defers: none — `D-WS4C-EFFECTIVE-VALUE` CLEARED 2026-07-10** (`GET /v1/chat/capabilities` publishes the deploy ceiling; the knowledge project modal ANDs it with the user knob and surfaces the "silently-off" case). **W10 + W11 backends ✅ BUILT (2026-07-15)** — W10 maps (8 `world_map_*` tools + 3 tables + MinIO + `/v1/worlds/{id}/maps` read REST); W11 reader spoiler-cutoff facade (resolve-to-owner, `before_chapter_id` server-enforced, fail-closed, canon-only `status='active'` guard) + `story_search` cutoff. See spec `2026-07-11-w10-w11-…` (status → BUILT). **Track C's W10/W11 surfaces are now UNBLOCKED and BUILT** (maps canvas + lore-seeker reader, both browser-proven). **W8 needs no Track-B backend** — the brief names it in the heading but scopes only W10/W11 work, and C's consumes-line omits W8: the onboarding fork is a Track-C routing/surface change. | ✅ |
| **C · User-facing/catalog** ([brief](TRACK-C.md) · **[AUDIT](TRACK-C-AUDIT.md)**) | *this session* | **~COMPLETE (2026-07-15).** WS-3 binding ✅ + binding UI ✅ (browser-proven) + workflow rack ✅ (browser-proven); permission-management UI ✅ (consent CRUD + S00e journey 3/3). WS-5 **12 System workflows** live (glossary-bootstrap · entity-triage · populate-from-notes · kg-build · vision-to-book · translation-pass · draw-a-map · lore-so-far · canon-check · chapter-compose · build-a-book · autonomous-drafting — seeded in `migrate.go`; driven via intent→workflow pinning + rail-driver grounding). WS-7 scenarios **18/18 green ≥2/3** by DB ground truth + honest judge reads (2026-07-15 clean run, post book-quota fix): 13 DB-scored green (incl. **S06 flagship 3/3 = the DoD**, S04 3/3 nodes=6, S06b/S10/S12 2/3) + 4 judge (S09 2/3 names the planted contradiction, S11 3/3 spoiler-safe, S00a/S08 3/3) + S00e 3/3 (`90e3f417e`). NB: evidence assembled across several small batches because a concurrent session recreated chat-service mid-run (~every 1.5h) — each scenario has a clean 3-consecutive-run block; see the all-tracks-clear RUN-STATE §1b. W10 maps canvas + W11 lore-seeker reader surfaces ✅ browser-proven (maps: 3 maps + Ironhold marker rendered; reader: panel renders, fail-closed windowing per 26 knowledge-service tests — browser search vacuous on un-extracted fixtures, noted DR15). | ✅ |
| **D · Tool liveness & metadata** ([spec](../../2026-07-09-mcp-tool-liveness-eval/README.md) · [brief](../../2026-07-09-mcp-tool-liveness-eval/TRACK-D.md)) | — | WS-D0 (tiering/spend-hole) → D1 (`propose_*` law) → D2 (harness P0) → D3 (**ship gate**) → D4/5/6 | ⬜ |

## Integration nodes (the only cross-track sync points)

| Node | Gate (all must be true) | Status |
|---|---|---|
| **N1** — after A's WS-1 | `tool_list`/`tool_load` + C1 enum + activation live → B's tools discoverable, C's UI binds real enum | ✅ |
| **N2** — after A's WS-2 | C3 `steps` schema + step-runner live → C's authored workflows run; async guard active | ✅ **FULL E2E** — live gemma-4-26b turn: workflow_list→workflow_load→step tools activated→presented rail w/ correct confirm/approval + async-job flags (also re-confirms the /v1/responses arg fix) |
| **ND3** — after D's WS-D3 | **CD4 ship gate live** as **reject-on-`executes:false`** (0 tools blocked, 26 warn-on-`null`); `tool_list`/`tool_load` withdraw a proven-broken tool. The literal "must pass G1–G4" was consciously **redefined** to "not proven-broken" (WS-D5c: `proven`/G1 is a chat-surface property, irrelevant to a curated workflow that names its tool). → **Track C's curated workflows may ship** | ✅ (redefined) |
| **N3** — before flagship | A(mechanism)+B(features)+**D(tools proven effectful)** present → flagship S06 go/no-go. **D-side PROVEN 2026-07-11**: S06 now shows `effectful_tool_calls>0` (4/5 warm) + `persist_claims_without_write==[]` (6/6), DB-verified (was `0` at baseline). Full product go/no-go still needs **C(catalog+UI)**. | 🔄 (D-side ✅; blocked on C) |

## Shared-file watch (chat-service — 3 tracks, disjoint files)

- **A:** `tool_discovery.py` · `tool_surface.py` · `catalog.py` · step-runner/workflow client · `tool_result_wire.py` · `stream_service.py` (LLM/advertise)
- **B:** context/persist (auto-capture)
- **C:** `skill_registry.py` (mode→capability resolve)
- One coordinated touch-point: `resolve_skills_to_inject()` (A reads, C extends — keep additive, per C6).

## Track A deferred (post-review)

**Recently cleared (2026-07-09):**
- ✅ **D-WF-BOOK-TIER-AUTHORING** — CLEARED (`95af9cabc`). book-tier workflow authoring re-enabled,
  now grant-gated (`bookGrantOK` ctx helper; ≥edit to write, ≥view to read; re-checked at approve;
  anti-oracle). book_id on propose/update/get.
- ✅ **Async-ness from catalog metadata** — CLEARED (`b1544c7b4`). `_meta.async` kit flag (Go WithAsync
  / Py require_meta async_job) marked on 5 real async tools; runner reads catalog flag (authored →
  catalog → heuristic). Only knowledge's kg_build_* stay on the heuristic (see below).
- ✅ **C4 at the public MCP edge** — CLEARED (`f2de0a0a1`). edge-generated errors now use the C4 closed
  set (`toC4Code` + top-level `result.code`); relayed downstream errors already inherit C4; anti-oracle
  denials kept as -32601.

- ✅ **D-KNOWLEDGE-META-ADOPTION** — CLEARED (`f191cb858`). All 31 knowledge tools now declare
  `_meta.tier`+`scope` (14 R / 10 A / 7 W); `kg_build_graph`+`kg_build_wiki` carry `_meta.async`.
  **Fixed a latent hole found doing it:** untiered ⇒ default `R`, so every knowledge WRITE was
  executable in read-only *ask* mode and skipped the Tier-A approval card. A tools/list gate now
  fails any new untiered tool. Interim heuristic verbs removed from `workflow_runner`.

**Remaining: none.** Track A is complete with an empty deferred list.

- Won't-fix (recorded so they stop resurfacing): `confirm_token` is stored-but-unverified on approve
  (consistent with skills — the browser JWT authorizes); C4 unclassifiable-error default is
  UPSTREAM_UNAVAILABLE (treat unknown≈transient, bounded by the tool-loop cap).

## Contract change log

- 2026-07-09 (**Track D**) — **C1 += `research`** (a new category value). `glossary_web_search` is
  universal infrastructure misfiled under a domain prefix → renamed **`web_search`** and moved to
  **provider-registry** (which owns the capability per the provider-gateway invariant). Its prefix
  `web` had no `GROUP_DIRECTORY` home; `web → knowledge` would be wrong (`knowledge` is the INTERNAL
  KG, web search is EXTERNAL retrieval), so `research` is minted. **Tracks B/C: any `category` enum in
  a UI/authoring surface must now include `research`.** Lockstep: `find-tools.ts` + `tool_discovery.py`
  `GROUP_DIRECTORY`, `tool-policy.ts` `Domain`, `_DOMAIN_ALIASES: web → research`. `glossary_web_search`
  survives as a `visibility: legacy` alias. `glossary_deep_research` is **unchanged** (verified NOT
  universal — needs `book_id`+`entity_id`). Detail: Track D `contracts.md` CD5. Implemented in WS-D0f.
- 2026-07-09 (Track B) — **C5 `glossary_entity_rename` refined**: signature `(book_id, entity_id, name)`
  (book_id required, anti-oracle) and **Tier-A** not Tier-W (rename is reversible; set_attributes already
  renames at Tier-A). `glossary_entity_delete` unchanged (Tier-W, already reachable). Detail + rationale in
  `contracts.md` change log. **Track C:** workflow steps calling rename use `gate: none`. Notified via this log.
