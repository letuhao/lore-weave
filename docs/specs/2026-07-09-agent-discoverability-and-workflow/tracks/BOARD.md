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
| **B · Domain backend** ([brief](TRACK-B.md)) | *this session* | WS-4A ✅ · rename ✅ · WS-4B ✅ · WS-4C Half B ✅ (facts→L2); Half A deferred `D-WS4C-HALFA` (needs 1 spawn line in A's `stream_service.py`) · domain fixes next | 🔄 |
| **C · User-facing/catalog** ([brief](TRACK-C.md)) | — | WS-3 / WS-5 / WS-7 | ⬜ |

## Integration nodes (the only cross-track sync points)

| Node | Gate (all must be true) | Status |
|---|---|---|
| **N1** — after A's WS-1 | `tool_list`/`tool_load` + C1 enum + activation live → B's tools discoverable, C's UI binds real enum | ✅ |
| **N2** — after A's WS-2 | C3 `steps` schema + step-runner live → C's authored workflows run; async guard active | ✅ **FULL E2E** — live gemma-4-26b turn: workflow_list→workflow_load→step tools activated→presented rail w/ correct confirm/approval + async-job flags (also re-confirms the /v1/responses arg fix) |
| **N3** — before flagship | A(mechanism) + B(features) + C(catalog+UI) present → run flagship S06 live-test (go/no-go) | ⬜ |

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

**Remaining (small follow-on):**
- **D-KNOWLEDGE-META-ADOPTION** — knowledge-service tools (`kg_build_graph`, `kg_build_wiki`, story/memory
  search) predate `_meta` and carry none, so the two async kg tools rely on the name heuristic instead of
  `_meta.async`. Adopting `require_meta(...)` there (with tiers) lets them carry the durable flag. Gate #2.
- Won't-fix (recorded so they stop resurfacing): `confirm_token` is stored-but-unverified on approve
  (consistent with skills — the browser JWT authorizes); C4 unclassifiable-error default is
  UPSTREAM_UNAVAILABLE (treat unknown≈transient, bounded by the tool-loop cap).

## Contract change log

- 2026-07-09 (Track B) — **C5 `glossary_entity_rename` refined**: signature `(book_id, entity_id, name)`
  (book_id required, anti-oracle) and **Tier-A** not Tier-W (rename is reversible; set_attributes already
  renames at Tier-A). `glossary_entity_delete` unchanged (Tier-W, already reachable). Detail + rationale in
  `contracts.md` change log. **Track C:** workflow steps calling rename use `gate: none`. Notified via this log.
