# Foundation Mega-Task — Plan Folder

> **Created:** 2026-05-29
> **Branch:** `mmo-rpg/foundation-mega-task`
> **Workflow:** RAID (Recursive Autonomous Implementation Drive) — new 100%-autonomous workflow, parallel to AMAW v3.0
> **Status:** CLARIFY in progress (bottom-up deep-dive per layer)

---

## Purpose

Build the foundation infrastructure for the LLM MMO RPG engine — 4 architectural layers
(DB physical → event sourcing → snapshot/projection → SDK) plus inbound canon ingestion,
WebSocket security, observability/capacity, and LLM safety pre-spec.

Goal of the plan: produce per-layer detailed plans + RAID-ready cycle briefs so that
cold-start sub-agents can execute the foundation build with 0 human intervention
after CLARIFY closes.

## Folder contents

| File | Status | Purpose |
|---|---|---|
| `_index.md` | LIVE | This file — TOC + status |
| `00_CLARIFY_MASTER.md` | DRAFT | Scope, tech stack, RAID rules — locked decisions go here |
| `L1_db_physical_meta.md` | DRAFT | L1 deep enumeration (12 sub-components) |
| `L2_event_sourcing.md` | PENDING | After L1 confirmed |
| `L3_snapshot_projection.md` | PENDING | After L2 confirmed |
| `L4_sdk_kernel_api.md` | PENDING | After L3 confirmed |
| `L5_inbound_canon.md` | PENDING | After L4 confirmed |
| `L6_ws_obs_llm_prespec.md` | PENDING | After L5 confirmed |
| `RAID_WORKFLOW.md` | PENDING | After all layers confirmed |
| `CYCLE_DECOMPOSITION.md` | PENDING | After RAID workflow confirmed |

## Reading order

1. `00_CLARIFY_MASTER.md` — what's locked, what's still open
2. Each `L{N}_*.md` in order — per-layer deep enumeration
3. `RAID_WORKFLOW.md` — how cycles execute autonomously
4. `CYCLE_DECOMPOSITION.md` — the final cycle list with RAID prompts

## Status — CLARIFY progress

- [x] Survey current state of foundation design
- [x] Confirm scope boundary (drop actor substrate from this program)
- [x] Lock tech stack (Rust kernel-derived / Go meta+existing / Python LLM-heavy)
- [x] Define acceptance-criteria philosophy (CI gates + retry 3x + cold-start review + auto post-review)
- [ ] L1 deep-dive (in progress)
- [ ] L2 deep-dive
- [ ] L3 deep-dive
- [ ] L4 deep-dive
- [ ] L5 deep-dive
- [ ] L6 deep-dive
- [ ] Decompose layers into RAID cycles
- [ ] Specify RAID workflow
- [ ] Final CLARIFY artifacts (including I3 invariant amendment)
