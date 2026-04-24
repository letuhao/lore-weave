<!-- CHUNK-META
source: 01_OPEN_PROBLEMS.ARCHIVED.md
chunk: 99_status_and_readiness.md
byte_range: 38205-46518
sha256: fcd3a8834dd094aca91f02b5fb197b22e97964be7d12e8d612b82e7727da8042
generated_by: scripts/chunk_doc.py
-->

## Status summary

| Category | OPEN | PARTIAL | KNOWN PATTERN | ACCEPTED |
|---|---|---|---|---|
| A. LLM reasoning & grounding | 0 | 6 | 0 | 0 |
| B. Distributed systems | 0 | 3 | 3 | 0 |
| C. Product / UX | 0 | 4 | 0 | 1 |
| D. Economics | 1 | 1 | 0 | 1 |
| E. Moderation & legal | 1 | 1 | 1 | 0 |
| F. Content design | 0 | 2 | 0 | 2 |
| G. Testing & ops | 0 | 3 | 0 | 0 |
| **M. Multiverse-specific** | **0** | **6** | **1** | **0** |
| **Total** | **2** | **26** | **5** | **4** |

> **Note:** Counts accurate as of 2026-04-23. Reconciled pre-existing off-by-one baseline miscounts discovered during M and A batch resolutions (the M OPEN baseline was 4 not 3; the A OPEN baseline included A2 which had already moved to PARTIAL via the multiverse reframe). M1/M2/M3/M4/M5/M7 all `PARTIAL` in 01; M6 `KNOWN PATTERN`. M2/M3/M4/M5 additionally marked **MITIGATED in [03 §11](03_MULTIVERSE_MODEL.md)**; stay `PARTIAL` in 01 due to residual sub-items pending V1 data or external input. All A1–A6 now `PARTIAL` after the LLM Safety Layer ([05](05_LLM_SAFETY_LAYER.md)) resolution.

**Deltas across design rounds:**
- A1 `OPEN` → `PARTIAL` (R8 [§12H](02_STORAGE_ARCHITECTURE.md) resolves infrastructure; semantic layer still open)
- A2 `OPEN` → `PARTIAL` (multiverse reframes cross-player consistency as a feature)
- B5 `OPEN` → `PARTIAL` (event sourcing + snapshot fork + DB-per-reality give rollback)
- C4 `OPEN` → `PARTIAL` (four-layer canon resolves the tension)
- F1 `OPEN` → `PARTIAL` (canon_lock_level per attribute)
- New category M added with 7 multiverse-specific risks
- **M1 `OPEN` → `PARTIAL`** (2026-04-23 — 7-layer discovery design in [03 §9.1](03_MULTIVERSE_MODEL.md#91-reality-discovery); weight tuning + preview format pending V1 data; M1-D1..D7 locked in [OPEN_DECISIONS.md](OPEN_DECISIONS.md))
- **M7 `OPEN` → `PARTIAL`** (2026-04-23 — 5-layer progressive disclosure in [03 §9.6](03_MULTIVERSE_MODEL.md#96-progressive-disclosure--m7-resolution); tutorial A/B + tier thresholds pending V1 data; M7-D1..D5 locked + new governance doc `UI_COPY_STYLEGUIDE.md`)
- **M3 `OPEN` → `PARTIAL`** (2026-04-23 — 8-layer canonization safeguards in [03 §9.7](03_MULTIVERSE_MODEL.md#97-canonization-safeguards--m3-resolution); M3-D1..D8 locked. Framework-level TECHNICAL + UX safeguards; DF3 implements; E3 legal review remains an independent platform-mode launch gate — self-hosted exempt)
- **M4 `OPEN` → `PARTIAL`** (2026-04-23 — 6-layer author-safety UX in [03 §9.8](03_MULTIVERSE_MODEL.md#98-canon-update-propagation--m4-resolution) reusing locked R5-L2 xreality infrastructure; M4-D1..D6 locked)
- **M2 `PARTIAL` → `MITIGATED`** in 03 only (2026-04-23 — all mitigation layers locked: MV10/MV11/R9-L6/MV4-b/M1-D5 cohesive)
- **M5 `PARTIAL` → `MITIGATED`** in 03 only (2026-04-23 — MV9 auto-rebase + projection flattening + ops metrics cohesive)
- **M category batch fully closed** (2026-04-23 — M1/M7/M3/M4 all moved to `PARTIAL`; M2/M5 confirmed MITIGATED in 03; M6 KNOWN PATTERN unchanged)
- **A3 `OPEN` → `PARTIAL`** (2026-04-23 — World Oracle pattern in [05 §4](05_LLM_SAFETY_LAYER.md); A3-D1..D4 locked. Deterministic fact-question routing via `oracle.query()` with pre-computed categories + PC timeline-cutoff; miss → LLM fallback + audit flag)
- **A5 + A6 framework formalized** (2026-04-23 — A5 / A6 remain `PARTIAL` status-wise but their architecture is now locked via [05 §3 command dispatch + §5 5-layer injection defense](05_LLM_SAFETY_LAYER.md); A5-D1..D4 + A6-D1..D5 locked)
- **A category batch fully closed** (2026-04-23 — A1/A2/A3/A4/A5/A6 all `PARTIAL`; no fully OPEN items remain in A)
- **B3 `OPEN` → `PARTIAL`** (2026-04-23 — 3-mode tick framework (frozen V1 / lazy-when-visited V2 / scheduled V3), per-reality configurable, budget-capped; B3-D1..D5 locked)
- **C1 `OPEN` → `PARTIAL`** (2026-04-23 — 3-voice modes (terse / novel / mixed) with inline override + world-rule override + persistence; V1 default = mixed; C1-D1..D5 locked)
- **F3 `OPEN` → `PARTIAL`** (2026-04-23 — hybrid scaffold + LLM fill-in; emergent deferred to V3+ with author review; F3-D1..D6 locked)
- **B category batch fully closed** (2026-04-23 — B3 moves to PARTIAL; no fully OPEN items remain in B)
- **G1 `OPEN` → `PARTIAL`** (2026-04-23 — 3-tier CI framework in new [`05_qa/LLM_MMO_TESTING_STRATEGY.md §2`](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#2-g1--ci-for-non-deterministic-llm-flows); G1-D1..D5 locked)
- **G2 `OPEN` → `PARTIAL`** (2026-04-23 — tiered load matrix + `loadtest-service` + budget kill-switch in [`05_qa §3`](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#3-g2--multi-user-load--simulation-testing); G2-D1..D5 locked)
- **G3 `OPEN` → `PARTIAL`** (2026-04-23 — 5-layer drift detection + per-tier SLOs in [`05_qa §4`](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#4-g3--canon-drift-detection-in-production); G3-D1..D6 locked)
- **G category batch fully closed** (2026-04-23 — G1/G2/G3 all PARTIAL; no OPEN remaining)
- **C3 `OPEN` → `PARTIAL`** (2026-04-23 — product strategy locked: V1 solo-first, NPC-populated world, staged funnel, scheduled events V2+, friend-follow organic concentration; C3-D1..D6 locked. Largely dissolved by earlier multiverse + M1 + M7 decisions.)
- **D2 `OPEN` → `PARTIAL`** (2026-04-23 — 3-tier shape (Free BYOK / Paid / Premium) + 1.5x margin target + per-tier feature gating mapped to B3/M1/M7/PC-C1 + V1 measurement protocol locked; D2-D1..D6 locked. Exact prices pending D1 data.)
- **C2 `OPEN` → `ACCEPTED` (research frontier)** (2026-04-23 — AI-driven narrative pacing is open research. V1 pragmatic workaround via F3 quest scaffolds for structural pacing at scene level; small-talk allowed to drift. Revisit V2+ with prototype data or public research progress.)
- **F2 `OPEN` → `ACCEPTED` (research frontier)** (2026-04-23 — dedicated AI GM agent is open research (Generative Agents partial). V1-V2 ships without GM agent; F3 scaffolds + NPCs + A6 retrieval cover the structural need. Revisit V3+ or on research delivery.)

**Final interpretation (2026-04-23 session close):** Systematic design resolutions have compressed the OPEN set from 18 → **2**. Every multiverse-specific, LLM reasoning, distributed-systems, testing/ops, and most product / economics / content-design risk now has either a PARTIAL answer or an explicit ACCEPTED stance. The design track has reached **steady state**:

- **Remaining 2 OPEN** (critical-path external blockers):
  - **D1** cost per user-hour — V1 prototype measurement
  - **E3** IP ownership — legal review (platform-mode launch gate; self-hosted exempt)
- **Also critical-path but already PARTIAL:** A4 retrieval quality — V1 measurement on real LoreWeave books
- **ACCEPTED research frontier (2):** C2 narrative pacing, F2 AI GM layer — V1-V2 ship without these; revisit on research or prototype trigger

Categories fully closed: **M · A · B · G**. **No productive design batches remain.** Next meaningful movement requires: (a) V1 prototype build + instrumented measurement (for A4 / D1 and tier pricing fill-in), (b) legal counsel engagement (for E3 and canonization launch gate), or (c) upstream research results (for C2 / F2 revisit). See [SESSION_HANDOFF.md](SESSION_HANDOFF.md) for the detailed closure brief and external-dependency action list.

## What "ready to implement" would look like

Before converting this into a real design doc with governance sign-off:

- **A1 (NPC memory)** has a concrete plan with a bounded per-reality memory budget
- **A4 (retrieval quality)** moves to `PARTIAL` with measurable evaluation on a real LoreWeave book
- **D1 (cost)** has real numbers from V1 prototype — cost per user-hour is measured, not estimated
- **E3 (IP)** has legal review of a proposed ToS model (canonization flow makes this more urgent)
- **M1–M7** have default policies confirmed (currently defaults are applied but pending user confirmation — see [OPEN_DECISIONS.md](OPEN_DECISIONS.md))

Until A1/A4/D1/E3 move off `OPEN`, Shape D (persistent MMO) is not ready for design. Shape A (solo RP within a single reality) sidesteps A2/C4/F1 entirely and could ship earlier — its critical-path `OPEN` list is **A1 + A4 + D1**.
