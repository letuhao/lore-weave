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
| `L6_ws_obs_llm_prespec.md` | DONE | 12 sub-components, ~4 cycles |
| `L7_ops_logs_monitor.md` | DONE | 12 sub-components, ~7 cycles — added 2026-05-29 after gap discovered |
| `OPEN_QUESTIONS_LOCKED.md` | DONE | 73 LOCKED decisions consolidated |
| `CYCLE_DECOMPOSITION.md` | DONE | 38 RAID cycles + dependency graph + per-cycle prompt template |
| `RAID_WORKFLOW.md` | DONE | RAID v1.0 full 12-phase spec + role contract + audit schemas + bootstrap |
| `I3_INVARIANT_AMENDMENT.md` | DONE | I3 amendment text + service map updates + CI lint spec, ready for Cycle 7 PR |
| `PRE_FLIGHT_CHECKLIST.md` | LIVE | Manual user sign-off items before invoking Cycle 0 (added v1.2 amendment) |

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
- [x] L1 deep-dive — 12 sub-components, ~135 artifacts, ~7 cycles
- [x] L2 deep-dive — 12 sub-components, ~50 artifacts, ~4 cycles
- [x] L3 deep-dive — 11 sub-components, ~30 artifacts, ~5 cycles
- [x] L4 deep-dive — 17 sub-components, ~100 artifacts, ~6 cycles
- [x] L5 deep-dive — 10 sub-components, ~40 artifacts, ~5 cycles
- [x] L6 deep-dive — 12 sub-components, ~40 artifacts, ~4 cycles
- [x] L7 deep-dive — 12 sub-components, ~150 artifacts, ~7 cycles (added 2026-05-29 — gap discovered)
- [x] All 73 open Qs LOCKED (3 L1.A + 19 L1.B-L + 8 L2 + 8 L3 + 8 L4 + 7 L5 + 8 L6 + 12 L7)
- [x] Write OPEN_QUESTIONS_LOCKED.md
- [x] Write CYCLE_DECOMPOSITION.md (38 cycles total)
- [x] Write RAID_WORKFLOW.md (12 phases mapped)
- [x] Write I3_INVARIANT_AMENDMENT.md (final artifact)

**Cumulative scope:** 86 sub-components, ~545 artifacts, **38 RAID XL cycles** (Cycle 0 RAID infra + 37 foundation cycles).

**CLARIFY COMPLETE 2026-05-29.** Ready for RAID execution starting at Cycle 0.

**v1.1 amendment 2026-05-29 (same day, post-research):** RAID workflow amended with
§12 Context Management Protections (10 protections P1-P10) to handle 38-cycle execution
without context bloat / compaction loss / lost-in-the-middle. Cycle 0 deliverables
expanded with 6 new scripts + 2 directories. Per-cycle brief template now mandates
TL;DR-top + REMINDERS-bottom structure (lost-in-middle aware) with 4000-token cap.
See [RAID_WORKFLOW.md §12](RAID_WORKFLOW.md) for protection contract.

**v1.2 amendment 2026-05-29 (same day, post production-readiness audit):** RAID workflow
amended with §13 Production-Readiness Protections covering 6 BLOCKER fixes (B1-B6) +
auto C0→C1 dispatch gate. B1 git worktree lifecycle. B2 per-DPS isolated test infra
(deterministic port allocation). B3 cost kill-switch ($50/cycle + $1500/foundation
hard caps). B4 brief auto-generation + schema validator. B5 foundation-vs-existing-prod
isolation (dev/staging/prod env split). B6 secret scan in DPS workflow (gitleaks).
Cycle 0 deliverables expanded to 36 items total. Cycle 0 size bumped to L. User opted
AUTO continue (no human checkpoint before C1) — auto-dispatcher with 60s pause window.
See [RAID_WORKFLOW.md §13](RAID_WORKFLOW.md) for BLOCKER fix contract +
[PRE_FLIGHT_CHECKLIST.md](PRE_FLIGHT_CHECKLIST.md) for user sign-off items.
