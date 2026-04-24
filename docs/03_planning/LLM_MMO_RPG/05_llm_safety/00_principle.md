<!-- CHUNK-META
source: 05_LLM_SAFETY_LAYER.ARCHIVED.md
chunk: 00_principle.md
byte_range: 0-1418
sha256: 98b4e0729af0f4ef236fad18209ce587c972f9d142fa5c45c7fc0159546e1312
generated_by: scripts/chunk_doc.py
-->

# 05 — LLM Safety Layer

> **Status:** Locked design — 13 decisions committed 2026-04-23. Implementation contract for `roleplay-service` and `world-service` (Phase 6+).
> **Scope:** Cross-cutting LLM I/O discipline resolving [01 A3 / A5 / A6](01_OPEN_PROBLEMS.md).
> **Created:** 2026-04-23

---

## 1. Principle

**LLM narrates, world-service decides.**

World state is the single source of truth (event-sourced per [02](02_STORAGE_ARCHITECTURE.md), per-reality per [03](03_MULTIVERSE_MODEL.md)). The LLM's job is to provide voice, prose, personality, and narrative texture. It is **not** the world model. It does not decide what happens, what is true, or what other players know.

This principle is the root of all three safety properties:

| Property | Mechanism |
|---|---|
| **Determinism** (A3) | Fact questions resolved by deterministic World Oracle; LLM wraps fixed answer in persona voice |
| **Reliability** (A5) | State-changing actions come from client commands, never from LLM output; LLM narrates POST-mutation |
| **Injection resistance** (A6) | Canon-scoped retrieval at DB layer = forbidden facts structurally absent from LLM context; prompt discipline is defense-in-depth, not the primary defense |

If the LLM goes rogue, hallucinates, or is fully jailbroken, the damage is bounded to *prose quality* — not world state, not cross-player leaks, not canon drift.

---

