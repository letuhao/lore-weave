# 00_foundation — Index

> **Purpose:** The compressed contract layer for the LLM MMO RPG track. Lets multiple AI agents design different features in parallel without loading the full 532 KB of kernel content (`02_storage/` + `03_multiverse/`). Foundation is a **reference** to the kernel, never a duplicate — if a kernel contract changes, its chunk file is the source of truth and foundation is updated in the same commit.
> **Created:** 2026-04-24

**Active:** (empty — no agent currently editing)

---

## Reading order (~5 minutes for a new agent)

Read these 7 files top-to-bottom on session start. Total ~30 KB; cache-friendly.

| # | File | What you'll learn | When you need it |
|---:|---|---|---|
| 1 | [01_READ_THIS_FIRST.md](01_READ_THIS_FIRST.md) | Kernel vs features split; what this folder is / isn't | Every session |
| 2 | [02_invariants.md](02_invariants.md) | 15 non-negotiable architectural rules | Before writing any code or contract |
| 3 | [03_service_map.md](03_service_map.md) | 19 services, responsibilities, events in/out | When your feature crosses services |
| 4 | [04_kernel_api.md](04_kernel_api.md) | MetaWrite / AssemblePrompt / GetEntityStatus / outbox / WS ticket | When your feature calls into the kernel |
| 5 | [05_vocabulary.md](05_vocabulary.md) | Shared enums (canon layers, lifecycle states, GoneState, statuses) | Before naming any new state / enum |
| 6 | [06_id_catalog.md](06_id_catalog.md) | Stable ID namespace directory + owning subfolder | Before picking an ID for your feature |
| 7 | [07_feature_workflow.md](07_feature_workflow.md) | Full agent workflow: session-start → commit | Every feature design task |

---

## How to work here

1. **On session start:** read all 7 files in order. This is the cheat sheet — no other subfolder's chunk files should be needed unless your feature directly touches that area.
2. **Editing foundation:** foundation is a mirror of decisions that live in the kernel (`02_storage/`, `03_multiverse/`) or other chunks. **Do not edit foundation in isolation.** Edit the kernel chunk first, then reflect the change here in the same commit.
3. **Adding a new invariant:** propose via SESSION_HANDOFF; new invariants require architectural sign-off (architect role from CLAUDE.md §workflow). Never add to `02_invariants.md` without that.
4. **Adding a new service:** add the service row to `03_service_map.md` + declare its kernel-API usage + register its SVID (`02_storage/S11_service_to_service_auth.md`) + add to `contracts/service_acl/matrix.yaml` — all in the same commit as the service scaffold.
5. **Claiming subfolder edit:** set the **Active:** line above with your agent name + ISO UTC timestamp + scope. Clear it when done. Do not edit foundation while another agent is active here.

For the full rules see [`../AGENT_GUIDE.md`](../AGENT_GUIDE.md).

---

## Relationship to other documents

- **CLAUDE.md** (repo root) — project-wide invariants (gateway, language rule, contract-first, no hardcoded secrets). Foundation extends CLAUDE.md with track-specific contracts.
- **ORGANIZATION.md** (LLM_MMO_RPG root) — folder layout spec.
- **AGENT_GUIDE.md** (LLM_MMO_RPG root) — per-subfolder workflow rules.
- **SESSION_HANDOFF.md** (LLM_MMO_RPG root) — append-only session log.
- **02_storage/** + **03_multiverse/** — the kernel. Foundation is a distillation of these two; any authoritative change originates there.
- **01_problems/** + **04_player_character/** + **05_llm_safety/** + **catalog/** + **decisions/** — feature-design subfolders. These are OK to load in full alongside foundation.

---

## Pending splits / follow-ups

None. Foundation files are designed to stay small (<200 lines each). If one grows past soft cap, the content likely belongs in the kernel, not here.
