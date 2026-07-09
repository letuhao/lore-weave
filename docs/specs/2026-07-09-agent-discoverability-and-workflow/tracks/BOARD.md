# Coordination board — 3-session parallel run

Status: ⬜ not started · 🔄 in progress · ✅ done. Update your track's row as you go.

## Prerequisite

| Item | Status | Note |
|---|---|---|
| **Contracts frozen (`contracts.md` C1–C6)** | ✅ | Frozen 2026-07-09. Change = cross-track decision. |

## Tracks

| Track | Session/branch | Milestone in flight | Status |
|---|---|---|---|
| **A · Mechanism spine** ([brief](TRACK-A.md)) | *this session* | WS-0 done · **WS-1a done + wired all 3 surfaces** (ai-gateway 187✓ · mcp-public-gateway 262✓ · chat-service ✓); review-impl + the S02 context-id fix next | 🔄 |
| **B · Domain backend** ([brief](TRACK-B.md)) | *this session* | WS-4A ✅ · entity rename ✅ · WS-4B ✅ (kg projection + edge fail-fast) · WS-4C next | 🔄 |
| **C · User-facing/catalog** ([brief](TRACK-C.md)) | — | WS-3 / WS-5 / WS-7 | ⬜ |

## Integration nodes (the only cross-track sync points)

| Node | Gate (all must be true) | Status |
|---|---|---|
| **N1** — after A's WS-1 | `tool_list`/`tool_load` + C1 enum + activation live → B's tools discoverable, C's UI binds real enum | ⬜ |
| **N2** — after A's WS-2 | C3 `steps` schema + step-runner live → C's authored workflows run; async guard active | ⬜ |
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
