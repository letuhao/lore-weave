# Session Handoff — LLM MMO RPG Design Track

> **Scope:** This handoff is scoped to the `LLM_MMO_RPG` exploratory design track ONLY.
> **Does NOT conflict with** `docs/sessions/SESSION_PATCH.md` (main project session). This folder is a self-contained design exploration that can resume independently.
> **Next session bootstrap:** Start with [README.md](README.md) → this file → follow reading order.

---

## 1. What this track is

An exploratory design for a **text-based LLM-driven MMO RPG** built on top of LoreWeave's existing knowledge + glossary + book infrastructure. Status: **Exploratory — NOT approved for implementation.** Nothing here gates current Phase 1–5 work.

Started 2026-04-23 from a SillyTavern prior-art survey. Evolved through systematic design of:
- Four product shapes → Shape D (shared persistent world)
- Multiverse model (peer realities, snapshot fork, 4-layer canon)
- PC design (identity, lifecycle, social)
- Full storage engineering (R1–R13 resolution)

See [00_VISION.md](00_VISION.md) for the dream, [01_OPEN_PROBLEMS.md](01_OPEN_PROBLEMS.md) for why it is hard.

## 2. Current state summary (2026-04-23 EOD)

### Design docs (7 files)
| File | Content |
|---|---|
| [README.md](README.md) | Folder index, reading order |
| [00_VISION.md](00_VISION.md) | Vision: shape D, staged V1→V2→V3 path |
| [01_OPEN_PROBLEMS.md](01_OPEN_PROBLEMS.md) | 30+ problems categorized; current counts below |
| [02_STORAGE_ARCHITECTURE.md](02_STORAGE_ARCHITECTURE.md) | Storage engineering — §12A–§12L cover all R1–R13 mitigations |
| [03_MULTIVERSE_MODEL.md](03_MULTIVERSE_MODEL.md) | Peer realities + 4-layer canon + snapshot fork |
| [04_PLAYER_CHARACTER_DESIGN.md](04_PLAYER_CHARACTER_DESIGN.md) | PC semantics, creation/lifecycle/social |
| [FEATURE_CATALOG.md](FEATURE_CATALOG.md) | Bird's-eye of 179 features across 12 categories |
| [OPEN_DECISIONS.md](OPEN_DECISIONS.md) | Every decision locked or pending |

### Governance (created outside folder, referenced from here)
- [`docs/02_governance/CROSS_INSTANCE_DATA_ACCESS_POLICY.md`](../../02_governance/CROSS_INSTANCE_DATA_ACCESS_POLICY.md) — R5 anti-pattern policy
- [`docs/02_governance/ADMIN_ACTION_POLICY.md`](../../02_governance/ADMIN_ACTION_POLICY.md) — R13 admin discipline

### Feature catalog status
- **Total:** 179 features
- **✅ Designed:** 92 (all core storage + multiverse + PC + R1–R13 layers)
- **🟡 Partial:** 39 (broad strokes, detail pending)
- **📦 Deferred:** 43 (DF1–DF13; DF12 withdrawn)
- **❓ Open:** 1 — A4 (retrieval quality, external V1 measurement). *(NAR-8 closed via M4; CC-6 closed 2026-04-23 via new `A11Y_POLICY.md`.)*
- **🚫 Out of scope:** 2 — SOC-6 (parties), SOC-7 (global chat)

### Storage risk resolution (R1–R13 in [02 §13](02_STORAGE_ARCHITECTURE.md))
**ALL 13 RESOLVED:**

| Risk | Status | Section |
|---|---|---|
| R1 Event volume explosion | MITIGATED | [§12A](02_STORAGE_ARCHITECTURE.md) — 6-layer: audit split, discipline, retention, archive, truncate, lz4 |
| R2 Projection rebuild | MITIGATED | [§12B](02_STORAGE_ARCHITECTURE.md) — 5-layer: snapshot, parallel, blue-green, integrity, catastrophic |
| R3 Schema evolution | MITIGATED | [§12C](02_STORAGE_ARCHITECTURE.md) — 6-layer: additive, schema-as-code, upcasters, validation, new-type for breaking |
| R4 Fleet ops | MITIGATED | [§12D](02_STORAGE_ARCHITECTURE.md) — 7-layer: provisioning, orchestrator, tiered backup, pgbouncer, metrics, sharding, orphan detection |
| R5 Cross-instance queries | MITIGATED (reframed) | [§12E](02_STORAGE_ARCHITECTURE.md) — 3-layer + anti-pattern policy. No product feature requires live cross-instance query. |
| R6 Publisher failure | MITIGATED | [§12F](02_STORAGE_ARCHITECTURE.md) — 7-layer incl. client catchup, DLQ, Redis-cache+DB-SSOT |
| R7 Multi-aggregate deadlocks | MITIGATED (reframed) | [§12G](02_STORAGE_ARCHITECTURE.md) — session is concurrency unit, cross-session event handler (DF13) |
| R8 Snapshot size drift | MITIGATED | [§12H](02_STORAGE_ARCHITECTURE.md) — NPC split into core + per-pair memory aggregates (foundation for A1) |
| R9 Instance close destructive | MITIGATED | [§12I](02_STORAGE_ARCHITECTURE.md) — 8-layer 6-state machine, 120-day floor, soft-delete rename, double-approval |
| R10 Global event ordering | **ACCEPTED** | [§12J](02_STORAGE_ARCHITECTURE.md) — no product feature needs it |
| R11 pgvector footprint | MITIGATED | [§12K](02_STORAGE_ARCHITECTURE.md) — fits <1% RAM at V3; tuning + monitoring |
| R12 Redis stream ephemerality | MITIGATED | Subsumed by R6-L6 (Redis is cache, DB is SSOT) |
| R13 Admin tooling complexity | MITIGATED | [§12L](02_STORAGE_ARCHITECTURE.md) — 6-layer discipline + governance policy |

### A1 progression
- **A1 NPC memory at scale:** `OPEN` → `PARTIAL` after R8 resolution
- R8 provides infrastructure (bounded per-pair aggregates, lazy loading, cold decay)
- Semantic layer (retrieval quality, summary prompt) remains open — needs V1 prototype data

### Critical-path OPEN (3) — all require external input
- **A4** retrieval quality — needs V1 prototype measurement on real LoreWeave books
- **D1** LLM cost per user-hour — needs V1 prototype data
- **E3** IP ownership — needs legal review

### Non-critical OPEN (0)
*(C2 + F2 formally ACCEPTED as research frontier on 2026-04-23. Non-critical bucket is empty.)*

### ⚠️ V1 implementation design NOT complete
The OPEN/PARTIAL problem table is mostly closed, but **V1 shipping requires 3 deferred big features (DF4/DF5/DF7) to have their own design docs** — they are V1-blocking. Plus 2 small inline gaps (WA-4 heuristics, session invite/share). See [Next session agenda](#next-session-agenda--v1-implementation-design-gaps) below.

---

## Session 2026-04-23 — progress summary

### Session arc
Starting OPEN = **18**. Current OPEN = **2** (external-only: D1, E3). ACCEPTED = **4**. PARTIAL = **26**.

**12 commits** this session, **90+ design decisions** locked, **4 new top-level docs** (`UI_COPY_STYLEGUIDE.md`, `A11Y_POLICY.md`, `05_LLM_SAFETY_LAYER.md`, `LLM_MMO_TESTING_STRATEGY.md`). Category batches **M · A · B · G** fully closed (0 OPEN in each).

Design-session work on the OPEN track has reached steady state for items that can be resolved without external data. **However, V1 implementation is not design-complete** — see next section.

### Next session agenda — V1 implementation design gaps

The following items are V1-required and must be designed before V1 implementation can commit. Listed in priority order for the next session:

**🔴 V1-blocking deferred big features (need their own design docs)**

| # | Item | Scope | Effort |
|---|---|---|---|
| 1 | **DF4 World Rules** | Per-reality rule engine — death behavior, paradox tolerance, PvP consent, canon strictness, voice-mode lock (C1-D3), quest-eligibility category gating (M3-D3), `accept_player_quests` toggle (F3-D6); covers PC-B1 / D2 / E3 + F1 runtime enforcement | Full design doc, ~300-400 lines |
| 2 | **DF5 Session / Group Chat** | Multi-character scene, turn arbitration (B4 PARTIAL), PvP consent flow, message routing, **session invite + share-link**, player-voice override inline commands (C1-D2); covers PC-D1 / D2 / D3 + PL-1 / PL-3 | Full design doc, ~400-500 lines |
| 3 | **DF7 PC Stats & Capabilities** | Concrete schema for PCS-4 "simple state-based" — inventory, relationships, optional simple stats per F4 ACCEPTED scope (no D&D mechanics); death outcomes per DF4 | Small design doc, ~150-200 lines |

**🟡 Small gaps — close inline (OPEN_DECISIONS + doc updates)**

| # | Item | Scope | Effort |
|---|---|---|---|
| ~~4~~ | ~~**WA-4 L1 auto-assignment heuristics**~~ | ✅ **DONE 2026-04-24** — 5 decisions locked (WA4-D1..D5). Strong L1/L2 category lists + ambiguous recommendation UX + asymmetric override policy. See [03 §3 "Category heuristics"](03_MULTIVERSE_MODEL.md) and OPEN_DECISIONS tail. | Closed |
| 5 | **Session invite / share-link framework** | Link shape + visibility inheritance from `sharing-service`; can fold into DF5 or lock framework first | ~3 decisions, inline or within DF5 |

**🟢 Synthesis doc (no new design — aggregation only)**

| # | Item | Scope |
|---|---|---|
| 6 | **V1 MVP scope doc** (`06_V1_MVP_SCOPE.md`) | Filter FEATURE_CATALOG by V1 tier, organize by implementation order, cross-ref Phase 6+ breakdown from root [README](../../../README.md) |

**🔵 Later (scheduled per existing impl order — not next-session)**

- **DF9 Admin Ops** — V1+30d per R2/R6/R8/R9 impl order
- **DF1 Daily Life** — V2 (NPC routines, PC → NPC conversion)
- **DF10 Event Schema Tooling** — V1+30d → V3
- **DF3 Canonization** — V3
- **DF6 World Travel** · **DF8 NPC persona from PC history** · **DF11 DB Fleet** · **DF13 Cross-session event handler** — each per their schedule

### Suggested next-session order

1. ~~**WA-4** first (5-decision warmup, builds momentum)~~ ✅ **DONE 2026-04-24**
2. **DF5 Session / Group Chat** (biggest V1 unknown; DF4 + DF7 hang off its session boundaries)
3. **DF4 World Rules** (many features reference World Rules; clearer scope after DF5)
4. **DF7 PC Stats** (smallest, mostly schema work)
5. Optional: fold **session invite/share** into DF5 during that batch
6. Finish with **V1 MVP scope doc** synthesis once DF4/5/7 land

**Storage + multiverse scope status (2026-04-24):** WA-4 completion closes the last design-resolvable gap in storage/multiverse. All residual items in those categories are external-data-dependent (A4 retrieval benchmark, D1 cost measurement, E3 legal) and cannot advance without V1 prototype / legal counsel / research progress. Future storage/multiverse work comes from: (a) M1/M5/M7 threshold tuning post-V1 data; (b) DFs that span storage (DF9/DF10/DF11/DF13 admin UX); (c) A1 semantic layer post-prototype.

### Remaining 2 OPEN — external dependencies only

| # | Dependency | What unblocks it |
|---|---|---|
| **D1** cost per user-hour | V1 prototype with instrumented cost measurement across session script mix (G2-D4) | Build solo-RP prototype + run synthetic load with `loadtest-service` scripts for 1-2 weeks to land real cost numbers |
| **E3** IP ownership | External legal review of canonization flow + ToS language | Engage legal counsel; scope: IP transfer semantics, player-contributed canon ownership, jurisdiction coverage (fanfic precedent — AO3, Wattpad) |

Plus **A4 retrieval quality** — status PARTIAL in 01 but still a critical-path external blocker: needs V1 benchmark dataset from actual LoreWeave books + human-graded canon-faithfulness measurements.

### 4 ACCEPTED items (scope discipline)

| # | Stance | Revisit trigger |
|---|---|---|
| D3 self-hosted vs platform | Both modes supported | — (permanent) |
| F4 progression system | Minimal RPG mechanics; game = conversation | — (permanent) |
| **C2 narrative pacing** *(new)* | Research frontier; V1 uses F3 scaffolds for structural pacing | V2+ prototype data OR public research progress |
| **F2 AI GM layer** *(new)* | Research frontier; V1-V2 ships without GM agent; F3 + NPCs + A6 cover structural need | V3+ roadmap review OR validated multi-agent narrative planner research |

### External-dependency action list (for whoever picks up the baton)

**When V1 prototype work begins:**
1. Instrument `loadtest-service` (G2-D4) with cost telemetry before first real-LLM run
2. Build A4 retrieval benchmark dataset from ≥1 complete LoreWeave book with human canon-faithfulness ratings
3. Run 1–2 weeks of synthetic sessions across G2-D4 script mix (casual / combat / fact / jailbreak)
4. Feed D1 results back → compute D2 exact prices using D2-D3 formula (1.5x margin target)
5. Feed A4 retrieval scores back → tune G1-D3 judge rubric weights

**When legal review begins (for E3 / platform-mode launch):**
1. Brief counsel on canonization flow mechanics ([03 §9.7](03_MULTIVERSE_MODEL.md#97-canonization-safeguards--m3-resolution) + M3-D1..D8)
2. Scope questions: ownership of canonized content, player consent (M3-D3), author veto, jurisdiction
3. Precedent review: AO3, Wattpad, fanfic platform ToS patterns
4. Output: ToS language + canonization attribution policy (feeds M3-D6 export UI)
5. Platform-mode launch GATED on E3 signoff; self-hosted mode is exempt

**Research triggers to watch (C2 / F2):**
- Generative Agents successors (watch arXiv CS.AI for multi-agent narrative planners)
- Tabletop RPG × LLM research (tension tracking, beat detection)
- Commercial AI GM products (if any land with validated UX)

### When to reopen design session

**The OPEN/PARTIAL problem track** is paused until external data lands — see external-dependency action list above. But **V1 implementation design is NOT paused** — the next session continues with the agenda above (DF4/DF5/DF7 + WA-4 + session invite/share + V1 MVP scope doc).

Reopen conditions for the OPEN/PARTIAL track specifically:

- V1 prototype delivers D1 / A4 measurements → reopen D2 for exact pricing; A4 moves toward SOLVED
- Legal counsel returns E3 brief → E3 moves toward SOLVED; canonization launch gate cleared
- Public research delivers narrative-pacing primitive → C2 / F2 reopen from ACCEPTED
- A new problem surfaces (`N1+` open item) during V1 build → standard OPEN resolution cycle

**Do not reopen the OPEN track for**: minor UX tuning, residual items already marked `pending V1 data`, or research frontier items without concrete new input. Those belong to implementation sprints or future design sessions with concrete triggers.

### Handoff checklist for next session
- [ ] **Read "Next session agenda" above** — it is the top priority: V1-blocking DF docs + inline gaps + synthesis doc, in priority order
- [ ] Read [01_OPEN_PROBLEMS.md](01_OPEN_PROBLEMS.md) status summary — confirm 2 OPEN / 26 PARTIAL / 5 KNOWN / 4 ACCEPTED still accurate
- [ ] Read [OPEN_DECISIONS.md](OPEN_DECISIONS.md) tail ~25 rows for most recent locks (M/A/B/C/D/F/G batches + V-1/V-2/V-3/MV5-pri + CC-6)
- [ ] Read [05_LLM_SAFETY_LAYER.md](05_LLM_SAFETY_LAYER.md) + [`../../05_qa/LLM_MMO_TESTING_STRATEGY.md`](../../05_qa/LLM_MMO_TESTING_STRATEGY.md) + [`../../02_governance/A11Y_POLICY.md`](../../02_governance/A11Y_POLICY.md) + [`../../02_governance/UI_COPY_STYLEGUIDE.md`](../../02_governance/UI_COPY_STYLEGUIDE.md) for cross-cutting constraints on DF4/DF5/DF7 design
- [ ] Pick from "Next session agenda" priority order (WA-4 → DF5 → DF4 → DF7 → session-invite → V1 MVP scope) or user can reorder. Each DF gets its own design doc (`docs/03_planning/LLM_MMO_RPG/DF_X_<NAME>.md` or similar, pattern TBD)
- [ ] For external triggers (V1 prototype data, legal brief, research progress): still the primary reopen condition for the remaining 2 OPEN (D1, E3) — see "When to reopen design session" below
- [ ] When starting a DF design, scan OPEN_DECISIONS for all `D...` references pointing to that DF (they list scope requirements from prior locked decisions)

---

### Multiverse-specific risks (M1–M7 in [01 §M](01_OPEN_PROBLEMS.md)) — NOT yet batch-addressed
- M1 Reality discovery (**PARTIAL — resolved 2026-04-23**) — 7-layer design in [03 §9.1](03_MULTIVERSE_MODEL.md#91-reality-discovery), M1-D1..D7 locked; weight tuning + preview format pending V1 data
- M2 Storage cost inactive realities (**PARTIAL — confirmed MITIGATED in 03 §11 on 2026-04-23**) — all layers locked (MV10/MV11/R9-L6/MV4-b/M1-D5); residual platform-mode tier quota deferred to `103_PLATFORM_MODE_PLAN.md`
- M3 Canonization contamination (**PARTIAL — resolved 2026-04-23**) — 8-layer safeguards in [03 §9.7](03_MULTIVERSE_MODEL.md#97-canonization-safeguards--m3-resolution), M3-D1..D8 locked; DF3 implementation + E3 legal remain independent (platform-mode launch gate; self-hosted exempt)
- M4 L1/L2 update propagation (**PARTIAL — resolved 2026-04-23**) — 6-layer author-safety UX in [03 §9.8](03_MULTIVERSE_MODEL.md#98-canon-update-propagation--m4-resolution) reusing R5-L2 xreality infrastructure; M4-D1..D6 locked
- M5 Fork depth explosion (**PARTIAL — confirmed MITIGATED in 03 §11 on 2026-04-23**) — MV9 auto-rebase at N=5 + projection flattening + R4-L5 ops metrics; threshold tuning pending V1 data
- M6 Cross-reality analytics (KNOWN pattern)
- M7 Concept complexity for users (**PARTIAL — resolved 2026-04-23**) — 5-layer progressive disclosure in [03 §9.6](03_MULTIVERSE_MODEL.md#96-progressive-disclosure--m7-resolution), M7-D1..D5 locked + new governance doc [`UI_COPY_STYLEGUIDE.md`](../../02_governance/UI_COPY_STYLEGUIDE.md); tutorial A/B + tier thresholds pending V1 data

### Deferred big features (DF1–DF13)
12 active, 1 withdrawn (DF12). Each gets its own design doc when implementation commits.

| ID | Feature | Covers |
|---|---|---|
| DF1 | Daily Life / "Sinh hoạt" | NPC routines, PC→NPC conversion |
| DF2 | Monetization / PC slot purchase | C-PC1 extension, platform tier |
| DF3 | Canonization / Author Review | L3→L2 promotion, IP attribution |
| DF4 | World Rule Feature | Per-reality rule engine |
| DF5 | Session / Group Chat | Multi-character scene mechanics |
| DF6 | World Travel | Cross-reality PC movement |
| DF7 | PC Stats & Capabilities | Concrete state schema |
| DF8 | NPC persona from PC history | LLM persona generation |
| DF9 | Event + Projection + Publisher + NPC Memory Ops | Per-reality correctness admin UX |
| DF10 | Event Schema Tooling | Dev UX for R3 mechanisms |
| DF11 | Database Fleet + Reality Lifecycle Management | Platform fleet ops + R9 closure UX |
| ~~DF12~~ | ~~Cross-Reality Analytics & Search~~ | **WITHDRAWN** — no justifying feature |
| DF13 | Cross-Session Event Handler | Admin UX for R7 event propagation |

### Services identified for V1
| Service | Size | Purpose |
|---|---|---|
| `world-service` | Large | Reality lifecycle, command processing, session host |
| `roleplay-service` | Large | LLM orchestration, turn processing |
| `publisher` | Small | Outbox → Redis broadcast (R6) |
| `meta-worker` | Small | Cross-reality event consumer (R5) |
| `event-handler` | Small | Cross-session event routing (R7) |
| `migration-orchestrator` | Small | Fleet schema migrations (R4-L2) |
| `admin-cli` | Small | Canonical admin command library (R13-L1) |

## 3. Decision history (chronological)

| Date | Milestone |
|---|---|
| 2026-04-23 | SillyTavern feature comparison saved (References/) |
| 2026-04-23 | Folder created, 00_VISION + 01_OPEN_PROBLEMS established |
| 2026-04-23 | Storage architecture locked: full event sourcing + DB-per-reality |
| 2026-04-23 | Multiverse model locked: peer realities, snapshot fork, 4-layer canon, MV1–MV11 |
| 2026-04-23 | PC design locked: PC-A1..E3 + DF1–DF8 registered |
| 2026-04-23 | FEATURE_CATALOG created (120→179 features as resolutions added) |
| 2026-04-23 | R1 volume mitigated (6-layer) |
| 2026-04-23 | R2 rebuild mitigated (5-layer) + DF9 |
| 2026-04-23 | R3 schema evolution mitigated (6-layer) + DF10 |
| 2026-04-23 | R4 fleet ops mitigated (7-layer) + DF11 |
| 2026-04-23 | R5 cross-instance reframed as anti-pattern + governance policy; DF12 withdrawn |
| 2026-04-23 | R6 publisher + R12 Redis ephemerality mitigated (7-layer) |
| 2026-04-23 | R7 reframed: session = concurrency unit; + DF13 |
| 2026-04-23 | R8 NPC memory aggregate split; A1 → PARTIAL |
| 2026-04-23 | R9 safe reality closure (8-layer 6-state machine, 120d floor) |
| 2026-04-23 | R10 ACCEPTED, R11 pgvector managed, R13 admin discipline + governance policy |
| 2026-04-23 | **Session end** — all R1–R13 resolved, handoff created |
| 2026-04-24 | WA-4 category heuristics locked (5 decisions) — storage + multiverse design-complete; residual items all external-dependent |

## 4. How to resume (for next session)

### Quick bootstrap (5 min)
1. Read [README.md](README.md)
2. Read this file (SESSION_HANDOFF.md)
3. Skim [FEATURE_CATALOG.md](FEATURE_CATALOG.md) § "Status summary"
4. Check [OPEN_DECISIONS.md](OPEN_DECISIONS.md) tail for most-recent locks

### Deep bootstrap (30 min)
1. Above, plus:
2. Read [00_VISION.md](00_VISION.md) fully
3. Skim [03_MULTIVERSE_MODEL.md](03_MULTIVERSE_MODEL.md) §1–§3 (framing + 4-layer canon)
4. Skim [02_STORAGE_ARCHITECTURE.md](02_STORAGE_ARCHITECTURE.md) §12A–§12L (all R1–R13)
5. Skim [04_PLAYER_CHARACTER_DESIGN.md](04_PLAYER_CHARACTER_DESIGN.md)
6. Read [01_OPEN_PROBLEMS.md](01_OPEN_PROBLEMS.md) status table

## 5. Natural next steps

Ordered by likely value:

### Option A — Address multiverse risks M1–M7 (batch)
- Most are product/UX concerns, some trivially resolved by prior work
- M4 can likely bump to PARTIAL immediately (R5-L2 event propagation solves)
- M1 reality discovery needs product thought
- M7 concept complexity needs UX strategy
- ~Medium session, completes the 01 risk panel

### Option B — Design a DF (pick one)
Highest-value DFs for prototyping:
- **DF5 Session / Group Chat** — natural V1 core. Multi-character scene mechanics. Foundation for everything else.
- **DF4 World Rules** — unlocks PC-A3/B1/E3 paradox behaviors. Needed before any reality actually opens to play.
- **DF9 Admin tooling** — operational readiness. Needed before first V1 reality goes live.

### Option C — Write V1 MVP scope doc
Take the 92 Designed + 39 Partial features, filter by V1 tier, produce a concrete "what we build first" doc. Useful if implementation is actually about to start.

### Option D — Critical-path OPEN groundwork
The 3 OPEN items (A4, D1, E3) all need external input:
- A4: design retrieval benchmark methodology (needs real book data → defer)
- D1: design cost measurement methodology for V1 prototype
- E3: draft ToS questions for legal review

### Option E — Integration with existing LoreWeave planning
This folder is exploratory. If/when it graduates to implementation:
- Update [09_ROADMAP_OVERVIEW](../09_ROADMAP_OVERVIEW.md) with a new phase
- Promote relevant parts to numbered `10X_*.md` design docs
- Governance sign-off via standard module protocol

## 6. Conflict-free coexistence with main session

This folder is **read-only from main session's perspective** until implementation commits. Main session (`docs/sessions/SESSION_PATCH.md`) tracks active Phase 1–5 work. This folder parks future-direction design.

**Rules:**
- New work in this folder → update this file (SESSION_HANDOFF.md)
- Do NOT modify `docs/sessions/SESSION_PATCH.md` from this track
- Governance docs (`docs/02_governance/*`) are shared — coordinate with main track if touching
- References from this folder can point to main planning docs (one-way)

## 7. Known resumption risks

- **Context amnesia**: AI agents in new session may not remember reasoning behind locked decisions. OPEN_DECISIONS.md is the source of truth; read it.
- **Drift temptation**: when resuming, there may be pressure to "reconsider" locked decisions. Don't unless explicit reason. Locks took careful discussion.
- **Scope creep**: easy to escalate from "talk about this" to "design it now". Hold the line — exploratory is exploratory until implementation commits.
- **Cross-track confusion**: if main session's work (Phase 1–5 active implementation) touches something in this folder's design, surface the conflict explicitly.

## 8. This session's raw summary

- **Duration:** one session (2026-04-23)
- **Files created:** 9 in this folder + 2 governance docs + 1 references doc
- **Files modified:** this folder's files iterated ~30 times as resolutions landed
- **Decisions locked:** ~150+ individual decisions
- **Risks resolved:** 13 storage (R1–R13)
- **Deferred features registered:** 12 active (DF1–DF13, DF12 withdrawn)
- **Governance policies:** 2 new

**Ready for commit and handoff to future session.**
