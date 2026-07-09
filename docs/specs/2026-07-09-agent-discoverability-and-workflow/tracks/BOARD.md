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

## Contract change log

- 2026-07-09 (Track B) — **C5 `glossary_entity_rename` refined**: signature `(book_id, entity_id, name)`
  (book_id required, anti-oracle) and **Tier-A** not Tier-W (rename is reversible; set_attributes already
  renames at Tier-A). `glossary_entity_delete` unchanged (Tier-W, already reachable). Detail + rationale in
  `contracts.md` change log. **Track C:** workflow steps calling rename use `gate: none`. Notified via this log.
