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
| **B · Domain backend** ([brief](TRACK-B.md)) | *closed 2026-07-10* | ✅ **CLOSED except W8/W10/W11.** WS-4A ✅ · rename ✅ · **delete reachable ✅** (`mcp_server.go:89`) · WS-4B ✅ · WS-4C Half B ✅ (facts→L2) · **WS-4C Half A ✅** ([spec](../../2026-07-10-ws4c-half-a-canon-auto-capture.md) — chat→glossary `capture-canon`, grant-checked, **opt-in**, drafts into the `ai-suggested` inbox; 3-service live smoke + `/review-impl`) · domain feedback: dedup NFC/NFD+CJK ✅ · read-your-writes ✅ (no status filter in select-for-context) · upsert-on-create ✅ *by design* (create-only + `set_attributes`/`rename`) · `propose_*` naming → **owned by Track D (D1)** · `glossary_confirm_action` doc-drift ⬜ *(needs its original feedback item)*. **Defers: none — `D-WS4C-EFFECTIVE-VALUE` CLEARED 2026-07-10** (`GET /v1/chat/capabilities` publishes the deploy ceiling; the knowledge project modal ANDs it with the user knob and surfaces the "silently-off" case). **NOT STARTED: the W10 + W11 product-journey backends** (world-container graph/map authoring · reader spoiler-cutoff) — P2, structurally large, needs its own design pass before code (defer gate #2). **Track C's W10/W11 surfaces are blocked on these** (TRACK-C.md "Consumes: B's backing tools for W2/W4/W10/W11"). **W8 needs no Track-B backend** — the brief names it in the heading but scopes only W10/W11 work, and C's consumes-line omits W8: the onboarding fork is a Track-C routing/surface change. | ✅ |
| **C · User-facing/catalog** ([brief](TRACK-C.md)) | — | WS-3 / WS-5 / WS-7 | ⬜ |
| **D · Tool liveness & metadata** ([spec](../../2026-07-09-mcp-tool-liveness-eval/README.md) · [brief](../../2026-07-09-mcp-tool-liveness-eval/TRACK-D.md)) | — | WS-D0 (tiering/spend-hole) → D1 (`propose_*` law) → D2 (harness P0) → D3 (**ship gate**) → D4/5/6 | ⬜ |

## Integration nodes (the only cross-track sync points)

| Node | Gate (all must be true) | Status |
|---|---|---|
| **N1** — after A's WS-1 | `tool_list`/`tool_load` + C1 enum + activation live → B's tools discoverable, C's UI binds real enum | ✅ |
| **N2** — after A's WS-2 | C3 `steps` schema + step-runner live → C's authored workflows run; async guard active | ✅ **FULL E2E** — live gemma-4-26b turn: workflow_list→workflow_load→step tools activated→presented rail w/ correct confirm/approval + async-job flags (also re-confirms the /v1/responses arg fix) |
| **ND3** — after D's WS-D3 | **CD4 ship gate live**: no workflow may reference a tool that hasn't passed G1–G4; `tool_list` never advertises a RED-G3 tool → **Track C's curated workflows may ship** | ⬜ |
| **N3** — before flagship | A(mechanism) + B(features) + C(catalog+UI) + **D(tools proven effectful)** present → run flagship S06 live-test (go/no-go). *Blocked on ND3: S06 baseline recorded `effectful_tool_calls: 0`.* | ⬜ |

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
